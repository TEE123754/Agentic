"""One frozen owned-fixture Phase 8 quality and matched-comparison gate."""

import asyncio
import hashlib
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
import pytest
import uvicorn
from harness import SemanticHarness
from playwright.async_api import async_playwright

from frictionlab.api import create_app
from frictionlab.cohorts.coordinator import CohortCoordinator
from frictionlab.configuration import CONFIG_DIRECTORY, ROOT, read_json, resolve_run
from frictionlab.evaluation.comparison import compare_runs
from frictionlab.evaluation.mind2web import lexical_reference, load_actions, score_actions
from frictionlab.evaluation.quality import evaluate_fixture_cases, save_quality_report
from frictionlab.planning.runner import run_persona


def test_mind2web_explicit_split_and_offline_action_scoring(tmp_path):
    directory = tmp_path / "train"
    directory.mkdir()
    path = directory / "train_0.json"
    path.write_text(
        json.dumps(
            [
                {
                    "annotation_id": "fixture-task",
                    "confirmed_task": "Click checkout",
                    "actions": [
                        {
                            "action_uid": "a1",
                            "operation": {"op": "CLICK", "value": ""},
                            "pos_candidates": [
                                {
                                    "backend_node_id": "7",
                                    "tag": "button",
                                    "attributes": '{"aria-label":"Checkout"}',
                                }
                            ],
                            "neg_candidates": [
                                {
                                    "backend_node_id": "8",
                                    "tag": "button",
                                    "attributes": '{"aria-label":"Help"}',
                                }
                            ],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    tasks = load_actions(path, split="train", sha256=sha)
    result = score_actions(tasks, lexical_reference(tasks))
    assert result["element_accuracy"] == result["joint_macro_accuracy"] == 1
    with pytest.raises(ValueError, match="checksum"):
        load_actions(path, split="train", sha256="0" * 64)
    with pytest.raises(ValueError, match="split"):
        load_actions(path, split="test_domain", sha256=sha)


async def _matched_batch(root):
    async def executor(sampled, **kwargs):
        return await run_persona(sampled, model_factory=SemanticHarness, **kwargs)

    coordinator = CohortCoordinator(root, executor=executor)
    await coordinator.start()
    frozen = read_json(ROOT / "configs" / "phase8-evaluation.json")
    template = read_json(CONFIG_DIRECTORY / "run.example.json")
    cases = []
    comparisons = []
    try:
        for pair in frozen["pairs"]:
            run_ids = {}
            for index, variant in enumerate(pair["order"]):
                payload = dict(
                    template,
                    id=str(uuid4()),
                    personas=[frozen["persona"]],
                    journeys=[frozen["journey"]],
                    repetitions=1,
                    seed=pair["seed"],
                )
                resolved = resolve_run(payload)
                await coordinator.submit(resolved, variant=variant)
                await asyncio.wait_for(coordinator.wait(payload["id"]), timeout=120)
                run_ids[variant] = payload["id"]
                cases.append(
                    {
                        "run_id": payload["id"],
                        "variant": variant,
                        "label": frozen["labels"][variant],
                        "order": index + 1,
                    }
                )
            comparison = compare_runs(
                root, coordinator.store, run_ids["dead_button"], run_ids["healthy"]
            )
            assert comparison["completion_delta"] == 1
            assert comparison["resolved_findings"] and not comparison["new_findings"]
            assert comparison["paired_sessions"][0]["seed"] == pair["seed"]
            comparisons.append(comparison)
        with pytest.raises(ValueError, match="not matched"):
            compare_runs(root, coordinator.store, cases[0]["run_id"], cases[-1]["run_id"])
        quality = evaluate_fixture_cases(root, coordinator.store, cases)
        for metric, threshold in frozen["targets"].items():
            assert quality["metrics"][metric] >= threshold
        assert quality["metrics"]["reports"] == 4
        assert quality["metrics"]["inconclusive_sessions"] == 0
        assert quality["metrics"]["zero_live_sentinel_traffic"]
        save_quality_report(root / "quality.json", quality)
        (root / "comparisons.json").write_text(json.dumps(comparisons, indent=2), encoding="utf-8")
    finally:
        await coordinator.close()
    return cases


def _free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def _inspect_comparison_ui(ui_port, screenshot):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, executable_path=os.environ["FRICTIONLAB_BROWSER_PATH"]
        )
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 980})
            await page.goto(f"http://127.0.0.1:{ui_port}", wait_until="domcontentloaded")
            await page.get_by_role("tab", name="Comparison").wait_for(timeout=20000)
            await page.get_by_role("tab", name="Comparison").click()
            await page.get_by_text("Change in completed synthetic sessions").wait_for(timeout=20000)
            await page.screenshot(path=str(screenshot), full_page=True)
        finally:
            await browser.close()


def test_frozen_matched_fixture_quality_and_dashboard(tmp_path):
    root = (
        Path(os.environ["FRICTIONLAB_PHASE8_EVIDENCE"]) / str(uuid4())
        if "FRICTIONLAB_PHASE8_EVIDENCE" in os.environ
        else tmp_path / "phase8"
    )
    root.mkdir(parents=True, exist_ok=True)
    cases = asyncio.run(_matched_batch(root))
    api_port, ui_port = _free_port(), _free_port()
    app = create_app(enable_cohorts=True, cohort_root=root)
    paths = []

    @app.middleware("http")
    async def record_paths(request, call_next):
        paths.append(request.url.path)
        return await call_next(request)

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=api_port, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    environment = os.environ.copy()
    environment["FRICTIONLAB_API_BASE"] = f"http://127.0.0.1:{api_port}"
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
                if (
                    httpx.get(f"http://127.0.0.1:{ui_port}/_stcore/health", timeout=0.5).status_code
                    == 200
                ):
                    break
            except httpx.RequestError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("Comparison dashboard did not start")
        first, second = cases[-1]["run_id"], cases[-2]["run_id"]
        response = httpx.get(f"http://127.0.0.1:{api_port}/dashboard/compare/{first}/{second}")
        assert response.status_code == 200 and response.json()["matched"]
        asyncio.run(_inspect_comparison_ui(ui_port, root / "comparison-dashboard.png"))
        assert (root / "comparison-dashboard.png").is_file()
        assert paths and not any(item.startswith("/fixture/") for item in paths)
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
        server.should_exit = True
        thread.join(timeout=15)
