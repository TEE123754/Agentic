"""Offline smoke path used only to qualify the extracted Windows download."""

import time
from pathlib import Path

import httpx

from frictionlab.launcher import LocalServer


def smoke():
    server = LocalServer(Path.cwd() / "smoke-workspace")
    server.start()
    try:
        for _ in range(200):
            if server.ready:
                break
            time.sleep(0.05)
        assert server.ready
        with httpx.Client(base_url=server.url, trust_env=False) as client:
            assert "New assessment" in client.get("/").text
            headers = {"x-frictionlab-token": server.app.state.token}
            response = client.post(
                "/api/assessments",
                headers=headers,
                json={
                    "url": "https://example.com",
                    "mode": "snapshot",
                    "html": '<html lang="en"><title>Desktop test</title><h1>Desktop</h1></html>',
                },
            )
            assert response.status_code == 202
            id = response.json()["id"]
            for _ in range(400):
                state = client.get(f"/api/assessments/{id}", headers=headers).json()
                if state["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            report = client.get(f"/api/assessments/{id}/report", headers=headers).json()
            assert report["execution_status"] == "completed"
            assert report["acquisition"]["target_requests"] == 0
            assert len(report["evidence_files"]) == 3
            assert not any(c["id"].endswith(".renderer") for c in report["checks"])
        return 0
    finally:
        server.stop()
        server.thread.join(60)
