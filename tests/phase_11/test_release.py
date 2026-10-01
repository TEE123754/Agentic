"""Release pilot: real local inference, owned fixtures, and offline report review."""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from playwright.async_api import async_playwright

from frictionlab.audit.service import latest_report_path
from frictionlab.cohorts.coordinator import CohortCoordinator
from frictionlab.configuration import CONFIG_DIRECTORY, read_json, resolve_run
from frictionlab.contracts.models import RunReport
from frictionlab.evaluation.comparison import compare_runs
from frictionlab.reporting import unexecuted_report, write_report
from frictionlab.sharing.bundle import export_bundle


def test_three_profile_local_release_pilot():
    root = Path(os.environ["FRICTIONLAB_PHASE11_EVIDENCE"]).resolve() / "pilot"

    async def run():
        coordinator = CohortCoordinator(root)
        payload = read_json(CONFIG_DIRECTORY / "run.example.json")
        payload.update(journeys=["checkout_review"], repetitions=1)
        runs = {}
        try:
            for variant in ("dead_button", "healthy"):
                payload["id"] = str(uuid4())
                await coordinator.submit(resolve_run(payload), variant=variant)
                await asyncio.wait_for(coordinator.wait(payload["id"]), timeout=950)
                path = latest_report_path(root, coordinator.store, payload["id"])
                assert path is not None
                report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
                runs[variant] = payload["id"]
                assert report.report_status == "ready", report.terminal_reason
                assert report.cohort_results.executed_sessions == 3
                assert report.protection.sentinel_requests == 0
                assert report.protection.sentinel_data_unchanged
                assert not report.review.missing_evidence
                for finding in report.findings:
                    assert finding.evidence
                    for ref in finding.evidence:
                        assert (path.parent / ref.path).is_file()
                for suffix in ("json", "md", "html"):
                    assert path.with_suffix("." + suffix).is_file()
                if variant == "healthy":
                    assert report.cohort_results.outcome_counts.get("completed", 0) == 3
                else:
                    assert report.findings and report.abandonment_explanations
            comparison = compare_runs(root, coordinator.store, runs["dead_button"], runs["healthy"])
            assert comparison["completion_delta"] > 0 and comparison["resolved_findings"]
            bundle = export_bundle(root, runs["dead_button"], root / "portable")
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True, executable_path=os.environ["FRICTIONLAB_BROWSER_PATH"]
                )
                try:
                    page = await browser.new_page()
                    requests = []
                    page.on("request", lambda request: requests.append(request.url))
                    await page.goto((root / "portable/index.html").as_uri())
                    await page.get_by_text("FrictionLab portable audit").wait_for()
                    await page.get_by_role("button", name="Full report").click()
                    await page.get_by_text("Complete sanitized report").wait_for()
                    await page.screenshot(path=str(root / "portable-review.png"), full_page=True)
                    assert not any(url.startswith(("http://", "https://")) for url in requests)
                finally:
                    await browser.close()
            for status in ("cancelled", "blocked", "interrupted", "failed"):
                # Explicit illustrative examples; real fault/recovery paths are in the regression.
                report = unexecuted_report(
                    "Illustrative pre-navigation partial report; no website was tested.",
                    resolve_run(dict(payload, id=str(uuid4()))), status,
                )
                write_report(report, root / "partial-examples" / status)
            (root / "release-review.json").write_text(
                json.dumps({
                    "runs": runs, "comparison": comparison, "bundle": str(bundle),
                    "profiles": payload["personas"], "real_local_inference": True,
                    "review_http_requests": 0, "sentinel_requests": 0,
                    "sentinel_data_unchanged": True,
                    "partial_examples": "Illustrative; executed faults verified by regression",
                }, indent=2), encoding="utf-8",
            )
        finally:
            await coordinator.close()
        assert not any(not task.done() for task in coordinator.tasks.values())

    asyncio.run(run())
