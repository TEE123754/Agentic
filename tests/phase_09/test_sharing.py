"""One post-build offline sharing walkthrough with an owned fixture report."""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from harness import SemanticHarness
from playwright.async_api import async_playwright

from frictionlab.cohorts.coordinator import CohortCoordinator
from frictionlab.configuration import CONFIG_DIRECTORY, read_json, resolve_run
from frictionlab.contracts.models import RunReport
from frictionlab.planning.runner import run_persona
from frictionlab.sharing.bundle import _inside, export_bundle


async def _capture_fixture(root):
    async def executor(sampled, **kwargs):
        return await run_persona(sampled, model_factory=SemanticHarness, **kwargs)

    coordinator = CohortCoordinator(root, executor=executor)
    await coordinator.start()
    payload = read_json(CONFIG_DIRECTORY / "run.example.json")
    payload.update(
        id=str(uuid4()), personas=["impatient_mobile"], journeys=["checkout_review"], repetitions=1
    )
    try:
        await coordinator.submit(resolve_run(payload), variant="dead_button")
        await asyncio.wait_for(coordinator.wait(payload["id"]), timeout=120)
    finally:
        await coordinator.close()
    return payload["id"]


async def _inspect_offline(viewer, private_bundle, bad_bundle, screenshot):
    requests = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, executable_path=os.environ["FRICTIONLAB_BROWSER_PATH"]
        )
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 950})
            page.on("request", lambda request: requests.append(request.url))
            await page.goto(viewer.as_uri(), wait_until="domcontentloaded")
            await page.get_by_text("FrictionLab portable audit").wait_for()
            await page.get_by_role("button", name="Full report").click()
            await page.get_by_text("Complete sanitized report").wait_for()
            await page.get_by_role("button", name="Findings").click()
            await page.get_by_label("Filter severity").select_option("high")
            await page.get_by_text("Control gives no visible response").first.wait_for()
            await page.get_by_role("button", name="Trajectories").click()
            await page.get_by_role("button", name="Next step").click()
            assert await page.locator("#trajectory img").count() >= 1
            await page.get_by_role("button", name="Heatmaps").click()
            assert await page.locator("#heatmap .dot").count() >= 1
            await page.locator("#heatmap img").evaluate("image => image.decode()")
            assert await page.locator("#heatmap .heat-stage").evaluate(
                "stage => { const s=stage.getBoundingClientRect(); "
                "const i=stage.querySelector('img').getBoundingClientRect(); "
                "return Math.abs(s.height-i.height)<=3 && Math.abs(s.width-i.width)<=3; }"
            )

            await page.locator("#import-file").set_input_files(str(private_bundle))
            await page.get_by_text("Opened private local bundle", exact=False).wait_for()
            assert await page.evaluate("window.evil") is None
            await page.locator("#import-file").set_input_files(str(bad_bundle))
            await page.get_by_text("Rejected: Bundle format", exact=False).wait_for()
            await page.screenshot(path=str(screenshot), full_page=True)
            landing = Path(__file__).resolve().parents[2] / "site" / "index.html"
            await page.goto(landing.as_uri(), wait_until="domcontentloaded")
            await page.get_by_role("link", name="Explore a sample audit").click()
            await page.get_by_text("FrictionLab portable audit").wait_for()
            await page.goto(landing.as_uri())
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.get_by_role("link", name="Get started", exact=True).click()
            assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            await page.screenshot(
                path=str(screenshot.with_name("landing-mobile.png")), full_page=True
            )
            await page.set_viewport_size({"width": 1440, "height": 950})
            await page.screenshot(
                path=str(screenshot.with_name("landing-desktop.png")), full_page=True
            )

        finally:
            await browser.close()
    assert not any(url.startswith(("http://", "https://")) for url in requests)


def test_phase9_offline_export_import_and_sanitization(tmp_path):
    root = (
        Path(os.environ["FRICTIONLAB_PHASE9_EVIDENCE"]) / str(uuid4())
        if "FRICTIONLAB_PHASE9_EVIDENCE" in os.environ
        else tmp_path / "phase9"
    )
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = asyncio.run(_capture_fixture(root))
    report_dir = root / "reports" / run_id / "revisions" / "2"
    report = RunReport.model_validate_json((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report.findings and report.heatmaps
    export_bundle(root, run_id, root / "public", public_fixture=True)
    contaminated = report.model_copy(
        update={
            "executive_summary": (
                "<script>window.evil=1</script> Authorization: Bearer TOPSECRET "
                "api_key=HIDDEN https://private.example/path?token=HIDDEN alice@example.com"
            )
        }
    )
    with patch(
        "frictionlab.sharing.bundle._latest_report", return_value=(contaminated, report_dir)
    ):
        export_bundle(root, run_id, root / "private")
    private_json = (root / "private" / "bundle.json").read_text(encoding="utf-8")
    private_html = (root / "private" / "index.html").read_text(encoding="utf-8")
    for secret in (
        "TOPSECRET",
        "HIDDEN",
        "private.example",
        "alice@example.com",
        "credential_reference",
        "planner_decisions",
    ):
        assert secret not in private_json and secret not in private_html
    assert "window.evil=1" in private_json and "<script>window.evil=1</script>" not in private_html
    data = json.loads(private_json)
    assert data["findings"] and data["sessions"][0]["steps"] and data["heatmaps"]
    assert data["manifest"]["visibility"] == "private_local"
    assert (
        json.loads((root / "public" / "bundle.json").read_text())["manifest"]["visibility"]
        == "public_fixture_example"
    )
    bad = dict(data, assets={"image-1": "https://private.example/tracker.png"})
    (root / "invalid-import.json").write_text(json.dumps(bad), encoding="utf-8")
    try:
        _inside(root, "../outside.json")
    except ValueError:
        pass
    else:
        raise AssertionError("Path traversal must be rejected")
    asyncio.run(
        _inspect_offline(
            root / "public" / "index.html",
            root / "private" / "bundle.json",
            root / "invalid-import.json",
            root / "offline-viewer.png",
        )
    )


def test_phase9_free_service_policy_mocked_exhaustion():
    import pytest

    from frictionlab.planning.free_service_policy import (
        FreeQuotaPaused,
        FreeServiceBudget,
        FreeServicePolicy,
    )

    with pytest.raises(ValueError, match="Paid"):
        FreeServicePolicy(paid_fallback=True)
    with pytest.raises(FreeQuotaPaused):
        FreeServiceBudget(FreeServicePolicy()).reserve("groq", tokens=1)
    policy = FreeServicePolicy(
        enabled=True,
        providers=("groq", "gemini"),
        max_requests_per_run=2,
        max_tokens_per_run=100,
        max_retries_per_request=1,
    )
    budget = FreeServiceBudget(policy)
    budget.reserve("groq", tokens=20)
    budget.reserve("gemini", tokens=20)
    assert not budget.strict_comparable
    with pytest.raises(FreeQuotaPaused, match="ceiling"):
        budget.reserve("groq", tokens=1)
    quota = FreeServiceBudget(policy)
    with pytest.raises(FreeQuotaPaused, match="exhaustion"):
        quota.quota_response(429)
    assert quota.paused and policy.local_fallback
    with pytest.raises(FreeQuotaPaused):
        quota.reserve("groq", tokens=1)
    tokens = FreeServiceBudget(policy)
    with pytest.raises(FreeQuotaPaused, match="ceiling"):
        tokens.reserve("groq", tokens=101)
    retries = FreeServiceBudget(policy)
    with pytest.raises(FreeQuotaPaused, match="retry"):
        retries.reserve("groq", tokens=1, retry=2)
