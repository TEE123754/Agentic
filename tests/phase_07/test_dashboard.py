"""One protected dashboard walkthrough after Phase 7 construction."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from harness import SemanticHarness
from playwright.async_api import async_playwright

from frictionlab.api import create_app
from frictionlab.configuration import CONFIG_DIRECTORY, ROOT, read_json
from frictionlab.planning.runner import run_persona


def _free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def _cohort_walkthrough(root: Path, blocked_root: Path, monkeypatch):
    async def executor(sampled, **kwargs):
        return await run_persona(sampled, model_factory=SemanticHarness, **kwargs)

    app = create_app(
        enable_cohorts=True, cohort_root=root, artifact_root=blocked_root, cohort_executor=executor
    )
    await app.state.cohorts.start()
    payload = read_json(CONFIG_DIRECTORY / "run.example.json")
    payload.update(
        id=str(uuid4()), personas=["impatient_mobile"], journeys=["checkout_review"], repetitions=1
    )
    run_id = payload["id"]
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
        ) as client:
            catalog = (await client.get("/dashboard/catalog")).json()
            assert catalog["execution_enabled"] and catalog["max_cohort_sessions"] == 6
            assert catalog["environment"]["origin"] == "http://127.0.0.1:8765"
            assert catalog["environment"]["isolation"]["no_live_credentials"]
            assert "credential_reference" not in json.dumps(catalog)
            assert (await client.get("/dashboard/runs")).json()["runs"] == []
            unsafe = dict(payload, id=str(uuid4()), environment="production")
            denied = await client.post("/runs?variant=dead_button", json=unsafe)
            assert denied.status_code == 409 and not denied.json()["execution_enabled"]
            assert (await client.get("/dashboard/runs")).json()["runs"] == []
            launched = await client.post("/runs?variant=dead_button", json=payload)
            assert launched.status_code == 202
            early = (await client.get(f"/dashboard/runs/{run_id}/progress")).json()
            assert early["execution_status"] in {"queued", "running", "completed"}
            await asyncio.wait_for(app.state.cohorts.wait(run_id), timeout=120)
            status = (await client.get(f"/runs/{run_id}")).json()
            assert status["run"]["report_status"] == "ready"
            progress = (await client.get(f"/dashboard/runs/{run_id}/progress")).json()
            assert progress["report_revision"] == 2
            assert progress["sessions"][0]["patience_remaining"] == 0
            assert progress["sessions"][0]["last_action"] == "click"
            assert progress["sessions"][0]["elapsed_seconds"] is not None
            report = (await client.get(f"/reports/{run_id}/json")).json()
            assert report["findings"] and report["heatmaps"] and report["trajectory_index"]
            assert report["protection"]["sentinel_requests"] == 0
            assert report["protection"]["sentinel_data_unchanged"]
            sid = status["sessions"][0]["session_id"]
            session = (await client.get(f"/dashboard/runs/{run_id}/sessions/{sid}/report")).json()
            assert session["trajectories"] and session["patience_ledger"]
            observation_id = session["trajectories"][0]["observation_before"]
            obs = (
                await client.get(
                    f"/dashboard/runs/{run_id}/sessions/{sid}/observations/{observation_id}"
                )
            ).json()
            assert obs["screenshot_available"] and "focus" in obs
            screenshot = await client.get(
                f"/dashboard/runs/{run_id}/sessions/{sid}/screenshots/{observation_id}"
            )
            assert screenshot.status_code == 200 and screenshot.content.startswith(b"\x89PNG")
            group_id = report["heatmaps"][0]["id"]
            heatmap = await client.get(f"/dashboard/reports/{run_id}/heatmaps/{group_id}")
            assert heatmap.status_code == 200 and b"<svg" in heatmap.content
            ref_name = report["findings"][0]["evidence"][0]["path"].split("/")[-1]
            evidence = await client.get(f"/dashboard/reports/{run_id}/evidence/{ref_name}")
            assert evidence.status_code == 200
            assert (
                await client.get(f"/dashboard/reports/{run_id}/evidence/private.json")
            ).status_code == 404
            for suffix in ("json", "md", "html"):
                assert (await client.get(f"/reports/{run_id}/{suffix}")).status_code == 200
            finding_id = report["findings"][0]["id"]
            with monkeypatch.context() as patch:
                patch.setattr(
                    socket.socket,
                    "connect",
                    lambda *_: (_ for _ in ()).throw(
                        AssertionError("Saved dashboard review must not revisit the tested website")
                    ),
                )
                reviewed = await client.post(
                    f"/runs/{run_id}/findings/{finding_id}/review",
                    json={"status": "confirmed", "note": "Saved fixture evidence reviewed."},
                )
                assert reviewed.status_code == 200 and reviewed.json()["revision"] == 3
                assert (await client.get(f"/reports/{run_id}/json")).json()["revision"] == 3
                assert (await client.get(f"/reports/{run_id}/revisions/2/json")).status_code == 200
    finally:
        await app.state.cohorts.close()
    return run_id


def _serve_saved_api(root: Path):
    port = _free_port()
    app = create_app(enable_cohorts=True, cohort_root=root)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            return port, server, thread
        time.sleep(0.1)
    raise AssertionError("Local saved-evidence API did not start")


async def _inspect_dashboard(ui_port: int, screenshot_path: Path):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, executable_path=os.environ["FRICTIONLAB_BROWSER_PATH"]
        )
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 980})
            await page.goto(f"http://127.0.0.1:{ui_port}", wait_until="domcontentloaded")
            await page.get_by_text("FrictionLab", exact=True).first.wait_for(timeout=20000)
            assert await page.get_by_text("Protected synthetic UX audits", exact=False).count()
            await page.get_by_role("tab", name="Findings").click()
            await page.get_by_text("Start checkout", exact=False).first.wait_for(timeout=20000)
            await page.screenshot(path=str(screenshot_path), full_page=True)
            await page.get_by_role("textbox", name="Review note").fill(
                "Confirmed from the saved masked screenshot and click trajectory."
            )
            await page.get_by_role("button", name="Save reviewed revision").click()
            await page.get_by_role("tab", name="Full report").click()
            await page.get_by_text("Revision 4", exact=False).first.wait_for(timeout=20000)
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="Download JSON").click()
            assert (await download_info.value).suggested_filename.endswith(".json")
        finally:
            await browser.close()


def test_phase7_complete_owned_fixture_dashboard_walkthrough(tmp_path, monkeypatch):
    root = (
        Path(os.environ["FRICTIONLAB_PHASE7_EVIDENCE"]) / str(uuid4())
        if "FRICTIONLAB_PHASE7_EVIDENCE" in os.environ
        else tmp_path / "cohort"
    )
    root.mkdir(parents=True, exist_ok=True)
    run_id = asyncio.run(_cohort_walkthrough(root, tmp_path / "blocked", monkeypatch))
    manifest = json.loads((root / "runs" / run_id / "manifest.json").read_text())
    assert manifest["environment"]["replica_origins"] == ["http://127.0.0.1:8765"]
    port, server, thread = _serve_saved_api(root)
    ui_port = _free_port()
    environment = os.environ.copy()
    environment["FRICTIONLAB_API_BASE"] = f"http://127.0.0.1:{port}"
    environment["PYTHONPATH"] = str(ROOT)
    log = (root / "dashboard-server.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "frictionlab" / "dashboard" / "app.py"),
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(ui_port),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=ROOT,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(100):
            try:
                response = httpx.get(f"http://127.0.0.1:{ui_port}/_stcore/health", timeout=0.5)
                if response.status_code == 200:
                    break
            except httpx.RequestError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("Local Streamlit dashboard did not start")
        asyncio.run(_inspect_dashboard(ui_port, root / "dashboard.png"))
        assert (root / "dashboard.png").is_file()
        assert (
            json.loads((root / "reports" / run_id / "revisions" / "4" / "report.json").read_text())[
                "revision"
            ]
            == 4
        )
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
        server.should_exit = True
        thread.join(timeout=15)
