"""HTTP gateway connects only to the broker-owned upstream; it never follows redirects."""

from __future__ import annotations

import http.client
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlsplit


class LocalHTTPServer:
    def __init__(self, handler):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("Local server did not stop")


def proxy_handler(policy):
    upstream_port = urlsplit(policy.origin).port

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def reply(self, status, body=b"Fixture protection policy blocked the request"):
            try:
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
            except ConnectionError:
                # A rejected Chrome background connection can close before reading its response.
                pass

        def do_CONNECT(self):
            policy.record("blocked", "network", "CONNECT tunnels are forbidden")
            self.reply(403)

        def dispatch(self):
            self.connection.settimeout(5)
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                size = -1
            if size < 0 or size > 1024 or self.headers.get("Transfer-Encoding"):
                policy.record("blocked", "network", "Unsupported payload framing or size")
                self.reply(403)
                return
            body = self.rfile.read(size) if size else b""
            reason = policy.reason(
                self.command, self.path, body, upgrade=bool(self.headers.get("Upgrade"))
            )
            if reason:
                policy.record("blocked", "network", reason)
                self.reply(403)
                return
            if not policy.acquire():
                self.reply(403)
                return
            upstream = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=5)
            try:
                parsed = urlsplit(self.path)
                target = parsed.path + ("?" + parsed.query if parsed.query else "")
                # No cookies, authorizations, user-selected Host, or proxy credentials are relayed.
                headers = {"Content-Type": "application/json"} if self.command == "POST" else {}
                upstream.request(self.command, target, body=body or None, headers=headers)
                response = upstream.getresponse()
                payload = response.read(2 * 1024 * 1024 + 1)
                redirect = response.getheader("Location")
                if redirect and policy.reason("GET", urljoin(policy.origin, redirect)):
                    policy.record(
                        "blocked",
                        "network",
                        "Redirect destination is outside the permitted fixture endpoints",
                    )
                    self.reply(403)
                    return
                if len(payload) > 2 * 1024 * 1024:
                    policy.record(
                        "blocked", "network", "Upstream response exceeds bounded fixture size"
                    )
                    self.reply(502)
                    return
                policy.record(
                    "allowed",
                    "network",
                    f"{self.command} {parsed.path} passed endpoint and payload checks",
                )
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "text/plain"))
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                if redirect:
                    self.send_header("Location", redirect)
                self.end_headers()
                self.wfile.write(payload)
            except (OSError, http.client.HTTPException):
                policy.record("blocked", "network", "Owned fixture upstream unavailable")
                self.reply(502)
            finally:
                upstream.close()
                policy.release()

        do_GET = dispatch
        do_POST = dispatch
        do_PUT = dispatch
        do_PATCH = dispatch
        do_DELETE = dispatch
        do_OPTIONS = dispatch
        do_HEAD = dispatch

        def log_message(self, *args):
            pass

    return Handler


def sentinel_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def handle_attempt(self):
            state["requests"].append({"method": self.command, "path": self.path})
            if self.command != "GET":
                state["balance"] -= 1
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = handle_attempt
        do_POST = handle_attempt

        def log_message(self, *args):
            pass

    return Handler
