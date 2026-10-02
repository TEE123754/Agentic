"""One post-construction gate: safety, semantics, secrets and real local browser/UI."""

import asyncio
import base64
import io
import json
import socket
import threading
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from frictionlab import credentials
from frictionlab.app import Connection, connect, create_app
from frictionlab.assessment.models import AssessmentRequest, Check, scores
from frictionlab.assessment.report import export_zip
from frictionlab.assessment.service import Assessments, ai_review
from frictionlab.assessment.snapshot import (
    capture_url,
    public_endpoint,
    safe_document,
    uploaded_snapshot,
)
from frictionlab.planning.inference import InferenceSettings, safe_text

KEY = "gsk_SYNTHETIC_LOCAL_APP_123456789"
HTML = '<!doctype html><html lang="en"><head><title>Test store</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{width:1600px}</style></head><body><h1>Store</h1><img src="https://sentinel.invalid/log"><input id="email"><a href="#">Empty link</a><script>fetch("https://sentinel.invalid/write")</script><form action="https://sentinel.invalid/pay"><button>Pay</button></form></body></html>'


@pytest.fixture(autouse=True)
def clean_keys(monkeypatch):
    credentials._SESSION.clear()
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        credentials, "secure_backend", lambda: (_ for _ in ()).throw(ValueError("Unavailable"))
    )
    yield
    credentials._SESSION.clear()


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "capture"},
        {"mode": "snapshot"},
        {"mode": "snapshot", "html": "x", "bundle_b64": "eA=="},
        {"html": "x"},
        {"categories": ["security", "security"]},
        {"categories": []},
        {"url": "https://example.com\n"},
    ],
)
def test_request_boundaries(payload):
    value = {"url": "https://example.com", **payload}
    with pytest.raises(ValidationError):
        AssessmentRequest(**value)


def test_unknown_never_passes():
    unknown = Check(
        id="a", category="security", title="Unknown", status="skipped", detail="Needs source"
    )
    value = scores([unknown], ["security"])
    assert value["overall"] is None and value["coverage"] == 0
    assert value["categories"]["security"]["score"] is None


def test_zero_contact_url_and_report(tmp_path):
    async def run():
        service = Assessments(tmp_path)
        with (
            patch("socket.getaddrinfo", side_effect=AssertionError("No DNS allowed")),
            patch("socket.create_connection", side_effect=AssertionError("No target contact")),
        ):
            id = service.submit(AssessmentRequest(url="https://example.com"))
            await service.tasks[id]
        report = service.report(id)
        assert report["acquisition"]["target_requests"] == 0
        assert report["summary"]["skipped"] > 0
        assert report["scores"]["coverage"] < 100
        assert report["scores"]["categories"]["functionality"]["score"] is None
        assert set(report["summary"]) == {"passed", "failed", "skipped", "incomplete"}
        assert set(report) >= {"issues", "limitations", "checks", "scores", "ai_review"}
        zipped = zipfile.ZipFile(io.BytesIO(export_zip(service.path(id), report)))
        assert set(zipped.namelist()) == {"report.json", "report.md", "report.html"}
        assert "<pre>" in zipped.read("report.html").decode()

    asyncio.run(run())


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.4", "169.254.169.254", "::1", "192.0.2.1"])
def test_capture_ssrf(ip):
    with (
        patch(
            "socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))],
        ),
        pytest.raises(ValueError),
    ):
        public_endpoint("https://example.com")


@pytest.mark.parametrize(
    "url",
    [
        "https://u:p@example.com",
        "https://example.com?token=x",
        "http://example.com:8080",
        "https://example.com/logout",
        "file:///a",
    ],
)
def test_capture_rejects_unsafe_url(url):
    with pytest.raises(ValueError):
        public_endpoint(url)


def test_all_dns_addresses_and_pin():
    public = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
    private = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))
    with patch("socket.getaddrinfo", return_value=[public, private]), pytest.raises(ValueError):
        public_endpoint("https://example.com")
    with patch("socket.getaddrinfo", return_value=[public]):
        assert public_endpoint("https://example.com")[2] == "8.8.8.8"


def test_capture_single_get_and_redirect_stop():
    calls = []

    class Response:
        status = 200
        data = b"<title>Snapshot</title>"

        def getheader(self, name, default=""):
            return "text/html" if name == "Content-Type" else default

        def read(self, n):
            data, self.data = self.data, b""
            return data

    class Connection:
        response = Response()

        def __init__(self, *args, **kwargs):
            self.args = args

        def request(self, method, path, headers):
            calls.append((method, path, headers))

        def getresponse(self):
            return self.response

        def close(self):
            pass

    with (
        patch(
            "frictionlab.assessment.snapshot.public_endpoint",
            return_value=(
                __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit("https://example.com"),
                443,
                "8.8.8.8",
            ),
        ),
        patch("frictionlab.assessment.snapshot.PinnedConnection", Connection),
    ):
        snapshot = capture_url("https://example.com", threading.Event())
        assert snapshot.acquisition["target_requests"] == 1
        assert len(calls) == 1 and calls[0][0] == "GET"
        assert not any(k.lower() in {"authorization", "cookie"} for k in calls[0][2])
        Connection.response.status = 302
        with pytest.raises(ValueError):
            capture_url("https://example.com", threading.Event())
        assert len(calls) == 2


@pytest.mark.parametrize("name", ["../index.html", "/index.html", "C:/index.html"])
def test_zip_paths_rejected(name):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        z.writestr(name, "<h1>Test</h1>")
    request = AssessmentRequest(
        url="https://example.com",
        mode="snapshot",
        bundle_b64=base64.b64encode(output.getvalue()).decode(),
    )
    with pytest.raises(ValueError):
        uploaded_snapshot(request)


def test_sanitizer_disables_actions_and_masks_known_secret():
    credentials.save_key("groq", KEY)
    value = safe_document(
        HTML
        + f'<p>{KEY}</p><input value="private"><div onclick="evil()">x</div><meta http-equiv="refresh" content="0;https://sentinel.invalid">'
    )
    assert "<script" not in value and "onclick" not in value and "http-equiv" not in value
    assert 'value="private"' not in value and KEY not in value
    assert "width:1600px" in value and 'action="#"' in value


def test_native_only_and_session_redaction(tmp_path):
    with pytest.raises(ValueError):
        credentials.save_key("groq", KEY, remember=True)
    assert not credentials.known_keys()
    connect(
        tmp_path,
        Connection(
            provider="groq",
            key=KEY,
            model="fixture-model",
            share_findings=True,
            free_tier_confirmed=True,
        ),
    )
    assert credentials.get_key("groq") == KEY
    assert KEY not in (tmp_path / "app-settings.json").read_text()
    assert KEY not in safe_text(KEY)


def test_environment_key_not_cached(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    assert credentials.get_key("groq") == KEY
    monkeypatch.delenv("GROQ_API_KEY")
    assert credentials.get_key("groq") is None


def test_api_boundaries_and_key_response(tmp_path):
    async def run():
        app = create_app(tmp_path, 9080, token="test-token")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:9080"
        ) as client:
            assert (await client.get("/api/settings")).status_code == 403
            headers = {"x-frictionlab-token": "test-token"}
            assert (
                await client.get(
                    "/api/settings", headers={**headers, "origin": "https://attacker.invalid"}
                )
            ).status_code == 403
            assert (
                await client.get("/", headers={"host": "attacker.invalid:9080"})
            ).status_code == 403
            response = await client.post(
                "/api/settings",
                headers=headers,
                json={
                    "provider": "groq",
                    "key": KEY,
                    "model": "fixture-model",
                    "share_findings": True,
                    "free_tier_confirmed": True,
                },
            )
            assert response.status_code == 200 and KEY not in response.text
            response = await client.get("/api/settings", headers=headers)
            assert response.json()["connected"] and KEY not in response.text
            bad = await client.post(
                "/api/settings", headers=headers, json={"provider": "bad", "key": KEY}
            )
            assert KEY not in bad.text
            response = await client.post(
                "/api/assessments",
                headers=headers,
                json={"url": "https://example.com", "categories": ["security"]},
            )
            assert response.status_code == 202
            id = response.json()["id"]
            await app.state.assessments.tasks[id]
            assert (
                await client.get(f"/api/assessments/{id}/export/zip", headers=headers)
            ).status_code == 200
            assert (
                await client.get("/api/assessments/not-a-uuid", headers=headers)
            ).status_code == 404
        await app.state.assessments.close()

    asyncio.run(run())


def test_cancel_and_restart_report(tmp_path):
    async def run():
        service = Assessments(tmp_path)
        id = service.submit(AssessmentRequest(url="https://example.com"))
        service.cancel(id)
        await service.tasks[id]
        assert service.status(id)["status"] == "cancelled"
        assert service.report(id)["summary"]["incomplete"] > 0
        service.progress(id, "running", "Interrupted stage", 30)
        restored = Assessments(tmp_path)
        assert restored.status(id)["status"] == "interrupted"
        assert restored.report(id)["execution_status"] == "interrupted"

    asyncio.run(run())


def test_mocked_ai_cannot_invent_findings():
    async def run():
        credentials.save_key("groq", KEY)
        settings = InferenceSettings(
            provider="groq",
            model="fixture-model",
            allow_remote=True,
            share_sanitized_state=True,
            free_tier_confirmed=True,
        )
        check = Check(
            id="known",
            category="security",
            title="Missing header",
            status="failed",
            severity="medium",
            detail="Measured",
            evidence=["Header absent"],
        )

        class Runtime:
            def __init__(self, settings):
                self.settings = settings

            async def __aenter__(self):
                pass

            async def close(self):
                pass

            def provenance(self):
                return {"requests": 1}

            def complete(self, messages, max_output, deadline):
                assert KEY not in json.dumps(messages)
                assert self.settings.max_requests == 1 and self.settings.max_retries == 0
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"advice": [{"id": "invented", "recommendation": "Fake"}]}
                                )
                            }
                        }
                    ]
                }

        with (
            patch("frictionlab.planning.cloud_transport.CloudModelRuntime", Runtime),
            pytest.raises(ValueError),
        ):
            await ai_review([check], settings)
        assert check.ai_recommendation is None and check.status == "failed"

    asyncio.run(run())


def test_real_offline_browser_and_dashboard(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from playwright.async_api import async_playwright

    from frictionlab.assessment.render import browser_path
    from frictionlab.launcher import LocalServer

    contacts = []

    class Sentinel(BaseHTTPRequestHandler):
        def do_GET(self):
            contacts.append("GET")
            self.send_response(200)
            self.end_headers()

        def do_POST(self):
            contacts.append("POST")
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    sentinel = ThreadingHTTPServer(("127.0.0.1", 0), Sentinel)
    sentinel_thread = threading.Thread(target=sentinel.serve_forever, daemon=True)
    sentinel_thread.start()
    target = f"http://127.0.0.1:{sentinel.server_port}"
    document = (
        HTML.replace("https://sentinel.invalid", target)
        + f'<iframe src="{target}/frame"></iframe><svg onload="fetch(\'{target}/event\')"></svg>'
    )
    server = LocalServer(tmp_path)
    server.start()
    for _ in range(200):
        if server.ready:
            break
        time.sleep(0.05)
    assert server.ready

    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, executable_path=browser_path())
            page = await browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(server.url)
            await page.locator("#url").fill(target)
            await page.locator("#mode").select_option("snapshot")
            await page.locator("#snapshot").set_input_files(
                {"name": "index.html", "mimeType": "text/html", "buffer": document.encode()}
            )
            await page.locator("#start").click()
            try:
                await page.locator("#results").wait_for(state="visible", timeout=60000)
            except Exception:
                print("Dashboard page errors:", errors)
                print("Dashboard error:", await page.locator("#error").inner_text())
                print("Progress:", await page.locator("#progress-detail").inner_text())
                print("Jobs:", server.app.state.assessments.list())
                for job in server.app.state.assessments.list():
                    print("Partial report:", server.app.state.assessments.report(job["id"]))
                destination = Path(
                    __import__("os").environ.get("FRICTIONLAB_APP_EVIDENCE", str(tmp_path))
                )
                destination.mkdir(parents=True, exist_ok=True)
                await page.screenshot(
                    path=str(destination / "failed-dashboard.png"), full_page=True
                )
                raise
            text = await page.locator("#results").inner_text()
            assert "FAILED" in text and "SKIPPED" in text and "Horizontal overflow" in text
            assert "Browser isolation alone" in text
            assert not errors
            id = server.app.state.assessments.list()[0]["id"]
            report = server.app.state.assessments.report(id)
            assert report["acquisition"]["target_requests"] == 0
            assert len(report["evidence_files"]) == 3
            assert report["summary"]["failed"] > 0
            assert any(c["id"].startswith("accessibility.axe-") for c in report["issues"]), (
                json.dumps(report)
            )
            assert not any(c["id"].endswith(".renderer") for c in report["checks"]), json.dumps(
                report
            )
            async with page.expect_download() as download:
                await page.get_by_role("button", name="ZIP", exact=True).click()
            saved = await download.value
            await saved.save_as(tmp_path / "assessment.zip")
            await page.screenshot(path=str(tmp_path / "dashboard.png"), full_page=True)
            await browser.close()

    try:
        asyncio.run(run())
    finally:
        server.stop()
        server.thread.join(60)
        sentinel.shutdown()
        sentinel.server_close()
        sentinel_thread.join(5)
    assert contacts == []
    assert not server.thread.is_alive()
    destination = Path(__import__("os").environ.get("FRICTIONLAB_APP_EVIDENCE", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    import shutil

    if destination != tmp_path:
        shutil.copytree(tmp_path, destination / "walkthrough", dirs_exist_ok=True)


def test_renderer_deadline_preserves_partial_checks(tmp_path, monkeypatch):
    from frictionlab.assessment import service as module

    async def blocked(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(module, "render_snapshot", blocked)
    monkeypatch.setattr(module, "RENDER_DEADLINE_SECONDS", 0.01)

    async def run():
        service = Assessments(tmp_path)
        id = service.submit(
            AssessmentRequest(
                url="https://example.com", mode="snapshot", html="<title>Timeout</title>"
            )
        )
        await service.tasks[id]
        report = service.report(id)
        assert report["execution_status"] == "failed"
        assert report["summary"]["incomplete"] >= 2
        ids = [c["id"] for c in report["checks"]]
        assert len(ids) == len(set(ids))
        assert any(
            c["id"] == "security.scheme" and c["status"] == "passed" for c in report["checks"]
        )

    asyncio.run(run())


def test_ai_fault_keeps_measured_findings(tmp_path, monkeypatch):
    from frictionlab.assessment import service as module

    async def rejected(*args):
        raise ValueError(KEY)

    monkeypatch.setattr(module, "ai_review", rejected)

    async def run():
        service = Assessments(tmp_path)
        request = AssessmentRequest(
            url="https://example.com",
            mode="snapshot",
            html="<p>No title or heading</p>",
            categories=["usability"],
            ai_enabled=True,
        )
        id = service.submit(request)
        await service.tasks[id]
        report = service.report(id)
        assert report["execution_status"] == "completed"
        assert report["ai_review"]["status"] == "incomplete"
        assert report["summary"]["failed"] == 2 and report["scores"]["overall"] == 0
        assert KEY not in json.dumps(report)

    asyncio.run(run())
