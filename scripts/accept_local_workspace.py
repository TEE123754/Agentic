"""Installed wheel dashboard acceptance away from the source checkout."""

import json
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

import httpx

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-m",
            "frictionlab",
            "start",
            "--no-open",
            "--workspace",
            str(root / "workspace"),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = process.stdout.readline().strip()
        assert line.startswith("Dashboard: http://127.0.0.1:")
        client = httpx.Client(base_url=line.removeprefix("Dashboard: "), trust_env=False)
        for _ in range(200):
            try:
                response = client.get("/")
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.05)

        class Parser(HTMLParser):
            token = None

            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if tag == "meta" and a.get("name") == "frictionlab-token":
                    self.token = a["content"]

        parser = Parser()
        parser.feed(response.text)
        assert parser.token
        headers = {"x-frictionlab-token": parser.token}
        started = client.post(
            "/api/assessments", headers=headers, json={"url": "https://example.com"}
        )
        assert started.status_code == 202
        id = started.json()["id"]
        for _ in range(100):
            state = client.get(f"/api/assessments/{id}", headers=headers).json()
            if state["status"] not in {"queued", "running"}:
                break
            time.sleep(0.1)
        report = client.get(f"/api/assessments/{id}/report", headers=headers).json()
        assert (
            report["execution_status"] == "completed"
            and report["acquisition"]["target_requests"] == 0
        )
        assert client.get(f"/api/assessments/{id}/export/html", headers=headers).status_code == 200
        Path("/tmp/frictionlab-installed-acceptance.json").write_text(
            json.dumps(
                {
                    "installed_wheel_cli_dashboard": "passed",
                    "offline_export": "passed",
                    "target_requests": 0,
                }
            )
        )
        client.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
