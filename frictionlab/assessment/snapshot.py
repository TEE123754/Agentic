"""No-contact snapshots and a separately approved, bounded one-GET acquisition."""

from __future__ import annotations

import base64
import html
import http.client
import ipaddress
import mimetypes
import socket
import ssl
import stat
import time
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from frictionlab.planning.inference import safe_text

MAX_BYTES = 2_000_000
MAX_BUNDLE = 10_000_000
ALLOW_FILES = {
    ".html",
    ".htm",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".gif",
    ".woff",
    ".woff2",
}


@dataclass
class Snapshot:
    files: dict[str, bytes]
    document: str
    headers: dict[str, str]
    acquisition: dict
    limitations: list[str]


def public_endpoint(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use an HTTP(S) URL without embedded credentials")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in {80, 443} or parsed.query:
        raise ValueError(
            "URL capture accepts public standard ports without query parameters; use an offline snapshot otherwise"
        )
    path = parsed.path or "/"
    if any(
        word in unquote(path).casefold().split("/")
        for word in (
            "logout",
            "delete",
            "unsubscribe",
            "purchase",
            "payment",
            "checkout",
            "subscribe",
        )
    ):
        raise ValueError("Potentially state-changing endpoint is excluded; use an offline snapshot")
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    ips = sorted({item[4][0] for item in addresses})
    if not ips or not all(ipaddress.ip_address(value).is_global for value in ips):
        raise ValueError(
            "Private, loopback, reserved and mixed public/private destinations are blocked"
        )
    return parsed, port, ips[0]


class PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, *, tls):
        super().__init__(host, port, timeout=5)
        self.address, self.tls = address, tls

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), timeout=5)
        if self.tls:
            self.sock = ssl.create_default_context().wrap_socket(
                self.sock, server_hostname=self.host
            )


def capture_url(url, stop):
    started = time.monotonic()
    parsed, port, address = public_endpoint(url)
    if stop.is_set():
        raise ValueError("Acquisition cancelled before dispatch")
    connection = PinnedConnection(parsed.hostname, port, address, tls=parsed.scheme == "https")
    try:
        connection.request(
            "GET",
            parsed.path or "/",
            headers={
                "Host": parsed.hostname,
                "User-Agent": "FrictionLab/0.1 passive-snapshot",
                "Accept": "text/html",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise ValueError(
                "Capture stopped at a non-success response; redirects are never followed"
            )
        content_type = response.getheader("Content-Type", "")
        if (
            "text/html" not in content_type.casefold()
            or response.getheader("Content-Encoding", "identity") != "identity"
        ):
            raise ValueError("Capture requires an uncompressed HTML response")
        content = bytearray()
        while True:
            if stop.is_set() or time.monotonic() - started > 15:
                raise ValueError("Acquisition cancelled or exceeded its bounded deadline")
            chunk = response.read(32_768)
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise ValueError("Captured document exceeds 2 MB")
        headers = {
            name.lower(): safe_text(response.getheader(name, ""))[:2000]
            for name in (
                "Content-Security-Policy",
                "Strict-Transport-Security",
                "X-Content-Type-Options",
                "Referrer-Policy",
            )
        }
        document = bytes(content).decode("utf-8", errors="replace")
        return Snapshot(
            {"index.html": bytes(content)},
            document,
            headers,
            {
                "mode": "approved_capture",
                "target_requests": 1,
                "method": "GET",
                "redirects": 0,
                "credentials_sent": False,
                "subresources_fetched": 0,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "tls_certificate_verified": parsed.scheme == "https",
                "document_bytes": len(content),
            },
            [
                "Acquisition sent one GET and may have affected server logs or a state-changing endpoint. It is not a zero-contact guarantee.",
                "External assets, scripts, authenticated state and backend behavior were not acquired. Rendering may differ from the website.",
            ],
        )
    finally:
        connection.close()


def uploaded_snapshot(request):
    if request.html is not None:
        files = {"index.html": request.html.encode("utf-8")}
    else:
        raw = base64.b64decode(request.bundle_b64, validate=True)
        if len(raw) > MAX_BUNDLE:
            raise ValueError("ZIP exceeds 10 MB")
        files, total = {}, 0
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            if len(archive.infolist()) > 256:
                raise ValueError("ZIP has too many entries")
            for info in archive.infolist():
                path = PurePosixPath(info.filename.replace("\\", "/"))
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or ":" in info.filename
                    or "\x00" in info.filename
                    or stat.S_ISLNK(info.external_attr >> 16)
                ):
                    raise ValueError("Unsafe ZIP path or symbolic link rejected")
                total += info.file_size
                if (
                    total > 20_000_000
                    or info.file_size > MAX_BYTES
                    or (info.file_size and info.file_size / max(1, info.compress_size) > 100)
                ):
                    raise ValueError("ZIP expansion exceeds bounds")
                if not info.is_dir() and path.suffix.casefold() in ALLOW_FILES:
                    files[str(path)] = archive.read(info)
        if "index.html" not in files:
            raise ValueError("ZIP needs index.html at its root, with relative CSS/images")
    if len(files["index.html"]) > MAX_BYTES:
        raise ValueError("HTML exceeds 2 MB in UTF-8")
    document = files["index.html"].decode("utf-8", errors="replace")
    return Snapshot(
        files,
        document,
        {},
        {
            "mode": "operator_snapshot",
            "target_requests": 0,
            "document_bytes": len(files["index.html"]),
            "scripts_executed": False,
        },
        [
            "Only the supplied static copy is assessed. Scripts, API calls, forms, frames and live integrations are disabled.",
            "Dynamic journeys and production behavior require a verified isolated replica and additional access; a snapshot is not that replica.",
        ],
    )


class SafeDocument(HTMLParser):
    BLOCKED = frozenset({"script", "iframe", "object", "embed", "base", "applet", "audio", "video"})
    VOID = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output, self.blocked = [], []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if self.blocked:
            if tag in self.BLOCKED and tag not in self.VOID:
                self.blocked.append(tag)
            return
        if tag in self.BLOCKED:
            if tag not in self.VOID:
                self.blocked.append(tag)
            return
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("http-equiv", "").casefold() in {
            "refresh",
            "content-security-policy",
        }:
            return
        if tag == "link" and attributes.get("rel", "").casefold() != "stylesheet":
            return
        clean = []
        for name, value in attrs:
            if name.startswith("on") or name in {
                "value",
                "srcdoc",
                "formaction",
                "ping",
                "target",
                "nonce",
                "integrity",
            }:
                continue
            if name == "action":
                value = "#"
            if (
                name in {"href", "src"}
                and value
                and urlsplit(value).scheme.casefold() in {"javascript", "vbscript", "file"}
            ):
                continue
            clean.append(
                name if value is None else f'{name}="{html.escape(safe_text(value), quote=True)}"'
            )
        if tag == "style":
            self.in_style = True
        self.output.append("<" + tag + (" " + " ".join(clean) if clean else "") + ">")

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
        elif tag not in self.BLOCKED:
            self.output.append("</" + tag + ">")

    def handle_data(self, data):
        if not self.blocked:
            self.output.append(safe_text(data) if self.in_style else html.escape(safe_text(data)))


def safe_document(document):
    parser = SafeDocument()
    parser.feed(document)
    return "".join(parser.output)


def mime(path):
    return mimetypes.guess_type(path)[0] or "application/octet-stream"
