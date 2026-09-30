import asyncio
import json
import os
import socket
import struct
import zlib
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from harness import SemanticHarness

import frictionlab.audit.service as audit_service
from frictionlab.api import create_app
from frictionlab.audit.service import finalize_audit, latest_report_path
from frictionlab.audit.synthesis import AuditEngine
from frictionlab.browser.evidence import BrowserObservation
from frictionlab.cohorts.coordinator import CohortCoordinator, CohortSettings
from frictionlab.cohorts.persistence import EventStore
from frictionlab.configuration import CONFIG_DIRECTORY, read_json, resolve_run
from frictionlab.contracts.models import RunReport
from frictionlab.planning.runner import run_persona
from frictionlab.reporting import unexecuted_report, write_report


def png(width=390, height=844):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    rows = b"".join(b"\0" + b"\xff\xff\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def observation(directory, signature, *, identifier=None, pixel_scale=1):
    identifier = identifier or uuid4()
    refs = [
        {"path": f"evidence/{identifier}.png", "kind": "screenshot"},
        {"path": f"evidence/{identifier}.observation.json", "kind": "event"},
    ]
    value = BrowserObservation.model_validate(
        {
            "id": str(identifier),
            "target_id": "owned-fixture",
            "route": "/",
            "viewport": {"width": 390, "height": 844},
            "candidates": [
                {
                    "candidate_id": 1,
                    "observation_id": str(identifier),
                    "target_id": "owned-fixture",
                    "role": "button",
                    "name": "Start checkout",
                    "visible": True,
                    "enabled": True,
                    "bounds": [40, 60, 100, 40],
                }
            ],
            "semantic_text": "Start checkout",
            "evidence": refs,
            "document_id": "fixture-document",
            "mutation_epoch": 1,
            "state_digest": signature,
            "semantic_signature": signature,
            "focus": {"name": "Start checkout", "role": "button"},
            "validation": [],
            "frame_urls": [],
            "coverage_gaps": [],
            "coordinates": {
                "offset_x": 0,
                "offset_y": 0,
                "css_width": 390,
                "css_height": 844,
                "pixel_width": 390 * pixel_scale,
                "pixel_height": 844 * pixel_scale,
            },
            "extraction_timing_ms": {},
        }
    )
    evidence = directory / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{identifier}.png").write_bytes(png(390 * pixel_scale, 844 * pixel_scale))
    (evidence / f"{identifier}.observation.json").write_text(
        value.model_dump_json(indent=2), encoding="utf-8"
    )
    return value


def create_saved_cohort(
    root: Path,
    outcomes=("abandoned_patience", "completed"),
    *,
    repeated_clicks=False,
    malformed=False,
    pixel_scales=None,
):
    payload = read_json(CONFIG_DIRECTORY / "run.example.json")
    payload.update(
        personas=["impatient_mobile"], journeys=["checkout_review"], repetitions=len(outcomes)
    )
    resolved = resolve_run(payload)
    run_id = str(resolved.config.id)
    store = EventStore(root)
    manifest = {
        "configuration": resolved.config.model_dump(mode="json"),
        "environment": resolved.environment.model_dump(mode="json"),
        "profiles": {item.id: item.model_dump(mode="json") for item in resolved.personas},
        "journeys": {item.id: item.model_dump(mode="json") for item in resolved.journeys},
        "variant": "dead_button",
        "sessions": [],
    }
    manifest_path = root / "runs" / run_id / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    store.append(
        "run_created",
        run_id,
        {
            "configuration_hash": resolved.configuration_hash,
            "manifest_path": str(manifest_path.relative_to(root)),
        },
    )
    store.append("report_job", run_id, {"revision": 1, "status": "pending"})
    summaries = []
    counts = {}
    for repetition, outcome in enumerate(outcomes):
        pixel_scale = pixel_scales[repetition] if pixel_scales else 1
        sid = str(uuid4())
        spec = {
            "session_id": sid,
            "persona_id": "impatient_mobile",
            "journey_id": "checkout_review",
            "repetition": repetition,
            "seed": 42 + repetition,
            "attempt": 1,
            "parent_session_id": None,
        }
        manifest["sessions"].append(spec)
        store.append("session_queued", run_id, spec, sid)
        directory = root / "runs" / run_id / "sessions" / sid
        before = observation(directory, "a" * 64, pixel_scale=pixel_scale)
        steps = []
        current = before
        for index in range(3 if repeated_clicks else 1):
            after = observation(
                directory,
                "a" * 64 if outcome == "abandoned_patience" or repeated_clicks else "b" * 64,
                pixel_scale=pixel_scale,
            )
            action_id = uuid4()
            steps.append(
                {
                    "action_id": str(action_id),
                    "action": {
                        "id": str(action_id),
                        "kind": "click",
                        "observation_id": str(current.id),
                        "candidate_id": 1,
                    },
                    "observation_before": str(current.id),
                    "observation_after": str(after.id),
                    "result": "no_change"
                    if outcome == "abandoned_patience" or repeated_clicks
                    else "progress",
                    "application_seconds": 0.2,
                    "inference_seconds": 0.0,
                    "detail": "Saved synthetic browser result",
                    "evidence": [ref.model_dump(mode="json") for ref in after.evidence],
                }
            )
            current = after
        session = unexecuted_report("Saved synthetic session reviewed offline.", resolved, "failed")
        data = session.model_dump(mode="json")
        data["run_id"] = sid
        data["scope"].update(
            phase=4,
            personas=["impatient_mobile"],
            journeys=["checkout_review"],
            seed=42 + repetition,
        )
        data["execution_status"] = (
            "completed" if outcome in {"completed", "abandoned_patience"} else outcome
        )
        data["cohort_results"] = {
            "requested_sessions": 1,
            "executed_sessions": 1 if outcome in {"completed", "abandoned_patience"} else 0,
            "eligible_sessions": 1 if outcome in {"completed", "abandoned_patience"} else 0,
            "outcome_counts": {outcome: 1}
            if outcome in {"completed", "abandoned_patience"}
            else {},
        }
        data["protection"].update(
            network_boundary_validated=True,
            sentinel_requests=0,
            sentinel_data_unchanged=True,
            boundary_scope="owned_fixture_browser_proxy",
            target_requests=2,
        )
        data["trajectories"] = steps if outcome in {"completed", "abandoned_patience"} else []
        data["visual_evidence"] = [
            ref.model_dump(mode="json") for ref in current.evidence if ref.path.endswith(".png")
        ]
        if outcome == "abandoned_patience":
            event_id = uuid4()
            data["friction_events"] = [
                {
                    "id": str(event_id),
                    "detector": "dead_interaction",
                    "session_id": sid,
                    "action_id": str(steps[-1]["action_id"] if not malformed else uuid4()),
                    "confidence": 0.94,
                    "patience_delta": -55,
                    "evidence": [ref.model_dump(mode="json") for ref in current.evidence],
                    "observation_before": steps[-1]["observation_before"],
                    "observation_after": steps[-1]["observation_after"],
                    "target_name": "Start checkout",
                    "observed_behavior": "Saved dead interaction",
                }
            ]
            data["abandonment_diagnosis"] = {
                "first_person": "I pressed Start checkout and saw no response.",
                "event_ids": [str(event_id)],
                "terminal_observation_id": str(current.id),
                "evidence": [ref.model_dump(mode="json") for ref in current.evidence],
            }
        report = RunReport.model_validate(data)
        write_report(report, directory.parent, prepared_directory=True)
        relative = f"runs/{run_id}/sessions/{sid}/report.html"
        store.append(
            "session_terminal",
            run_id,
            {
                "status": data["execution_status"],
                "outcome": outcome if outcome in {"completed", "abandoned_patience"} else None,
                "report_path": relative,
            },
            sid,
        )
        passed = outcome == "completed"
        for criterion in resolved.journeys[0].completion:
            store.append("milestone", run_id, {"name": criterion.id, "passed": passed}, sid)
        summaries.append(
            {
                **spec,
                "execution_status": data["execution_status"],
                "outcome": outcome if outcome in {"completed", "abandoned_patience"} else None,
                "steps": len(data["trajectories"]),
                "friction_events": len(data["friction_events"]),
                "model_calls": 0,
                "passed_milestones": [item.id for item in resolved.journeys[0].completion]
                if passed
                else [],
                "report_path": relative,
            }
        )
        if outcome in {"completed", "abandoned_patience"}:
            counts[outcome] = counts.get(outcome, 0) + 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    base = unexecuted_report("Synthetic cohort reached terminal states.", resolved, "failed")
    data = base.model_dump(mode="json")
    data["scope"]["phase"] = 5
    data["execution_status"] = (
        "completed"
        if all(item in {"completed", "abandoned_patience"} for item in outcomes)
        else outcomes[0]
        if len(outcomes) == 1
        else "cancelled"
    )
    data["cohort_results"] = {
        "requested_sessions": len(outcomes),
        "executed_sessions": sum(counts.values()),
        "eligible_sessions": sum(counts.values()),
        "outcome_counts": counts,
    }
    data["session_summaries"] = summaries
    data["protection"].update(
        network_boundary_validated=True,
        sentinel_requests=0,
        sentinel_data_unchanged=True,
        boundary_scope="owned_fixture_browser_proxy",
    )
    report = RunReport.model_validate(data)
    write_report(report, root / "reports")
    store.append("run_status", run_id, {"status": data["execution_status"]})
    store.append(
        "report_job",
        run_id,
        {"revision": 1, "status": "partial", "report_path": f"reports/{run_id}/report.html"},
    )
    return run_id, store


def test_grouped_finding_denominator_heatmap_and_immutable_revisions(tmp_path, monkeypatch):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(root)
    try:
        monkeypatch.setattr(
            socket.socket,
            "connect",
            lambda *_: (_ for _ in ()).throw(
                AssertionError("Report synthesis must not contact a target")
            ),
        )
        report = finalize_audit(root, store, run_id)
        assert report and report.report_status == "ready" and report.revision == 2
        assert report.scope.phase == 6 and len(report.findings) == 1
        finding = report.findings[0]
        assert (
            finding.detector,
            finding.affected_sessions,
            finding.eligible_sessions,
            finding.reproduction_rate,
        ) == ("dead_interaction", 1, 2, 0.5)
        assert finding.inferred_mechanism and finding.recommendation and finding.verification
        assert len(finding.event_ids) == 1 and len(finding.affected_session_ids) == 1
        assert all(
            (latest_report_path(root, store, run_id).parent / ref.path).is_file()
            for ref in finding.evidence
        )
        assert report.review.status == "evidence_reviewed" and not report.review.missing_evidence
        assert report.review.dispositions[0].status == "requires_investigation"
        assert report.abandonment_explanations[0].startswith("I ")
        assert len(report.trajectory_index) == 2
        assert report.milestone_funnel and report.milestone_funnel[0].eligible_sessions == 2
        assert report.milestone_funnel[0].passed_sessions == 1
        assert len(report.heatmaps) == 1
        group = report.heatmaps[0]
        assert len(group.points) == 2 and group.rage_click_clusters == 0
        assert all((point.x, point.y) == (90, 80) for point in group.points)
        svg = (latest_report_path(root, store, run_id).parent / group.svg_path).read_text()
        assert "data:image/png;base64," in svg and "http://127.0.0.1" not in svg
        html_report = latest_report_path(root, store, run_id, "html").read_text()
        assert "data:image/svg+xml;base64," in html_report
        assert "Evidence exclusions" in html_report and "Conversion milestones" in html_report
        for ref in finding.evidence:
            assert f'href="{ref.path}"' in html_report
            assert f"]({ref.path})" in latest_report_path(root, store, run_id, "md").read_text()
        assert f'href="{group.svg_path.removesuffix(".svg")}.json"' in html_report
        assert (root / "reports" / run_id / "report.json").is_file()
        assert store.run(run_id)["report_revision"] == 2
        assert len(store.rows("SELECT * FROM findings WHERE run_id = ?", [run_id])) == 1
        event_count = store.event_count(run_id)
        assert finalize_audit(root, store, run_id).revision == 2
        assert store.event_count(run_id) == event_count + 1  # report-job acknowledgement only
    finally:
        store.close()


def test_unsupported_friction_is_excluded_and_report_stays_partial(tmp_path):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(root, malformed=True)
    try:
        report = finalize_audit(root, store, run_id)
        assert report and report.report_status == "partial"
        assert not report.findings and not report.abandonment_explanations
        assert any(item.kind == "event" for item in report.exclusions)
        assert report.review.missing_evidence
        assert (root / "reports" / run_id / "report.json").is_file()
    finally:
        store.close()


def test_repeated_failed_click_cluster_uses_actual_actions(tmp_path):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(root, outcomes=("completed",), repeated_clicks=True)
    try:
        report = finalize_audit(root, store, run_id)
        assert report and not report.findings
        assert report.heatmaps[0].rage_click_clusters == 1
        assert len(report.heatmaps[0].points) == 3
        assert all(point.rage_cluster for point in report.heatmaps[0].points)
    finally:
        store.close()


def test_pixel_density_separates_heatmaps_without_splitting_ux_context(tmp_path):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(
        root, outcomes=("completed", "completed"), pixel_scales=(1, 2)
    )
    try:
        report = finalize_audit(root, store, run_id)
        assert report and report.report_status == "ready"
        assert len(report.heatmaps) == 2
        assert {(group.pixel_width, group.pixel_height) for group in report.heatmaps} == {
            (390, 844),
            (780, 1688),
        }
        assert {(point.x, point.y) for group in report.heatmaps for point in group.points} == {
            (90, 80),
            (180, 160),
        }
    finally:
        store.close()


def test_unmapped_click_is_excluded_and_report_becomes_partial(tmp_path):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(root, outcomes=("completed",))
    try:
        sid = store.sessions(run_id)[0]["session_id"]
        session_dir = root / "runs" / run_id / "sessions" / sid
        session = RunReport.model_validate_json((session_dir / "report.json").read_text())
        observation_id = session.trajectories[0].observation_before
        path = session_dir / "evidence" / f"{observation_id}.observation.json"
        saved = json.loads(path.read_text())
        saved["candidates"] = []
        path.write_text(json.dumps(saved), encoding="utf-8")
        report = finalize_audit(root, store, run_id)
        assert report and report.report_status == "partial"
        assert any(item.kind == "action" for item in report.exclusions)
        assert report.review.missing_evidence
        assert not report.heatmaps
    finally:
        store.close()


def test_screenshot_coordinate_mismatch_excludes_session(tmp_path):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(root, outcomes=("completed",))
    try:
        sid = store.sessions(run_id)[0]["session_id"]
        session_dir = root / "runs" / run_id / "sessions" / sid
        session = RunReport.model_validate_json((session_dir / "report.json").read_text())
        observation_id = session.trajectories[0].observation_before
        path = session_dir / "evidence" / f"{observation_id}.observation.json"
        saved = json.loads(path.read_text())
        saved["coordinates"]["pixel_width"] += 1
        path.write_text(json.dumps(saved), encoding="utf-8")
        report = finalize_audit(root, store, run_id)
        assert report and report.report_status == "partial"
        assert any("Screenshot dimensions differ" in item.reason for item in report.exclusions)
        assert not report.heatmaps
    finally:
        store.close()


def test_missing_heatmap_asset_keeps_fallback_and_recovers_offline(tmp_path, monkeypatch):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(root, outcomes=("completed",))
    original = audit_service._write_assets

    def omit_point_data(directory, assets):
        original(
            directory,
            {
                name: value
                for name, value in assets.items()
                if not name.startswith("heatmaps/") or not name.endswith(".json")
            },
        )

    try:
        monkeypatch.setattr(audit_service, "_write_assets", omit_point_data)
        assert finalize_audit(root, store, run_id) is None
        assert latest_report_path(root, store, run_id).parent == root / "reports" / run_id
        monkeypatch.setattr(audit_service, "_write_assets", original)
        repaired = finalize_audit(root, store, run_id)
        assert repaired and repaired.report_status == "ready"
        assert latest_report_path(root, store, run_id).parent.name == "2"
    finally:
        store.close()


def test_synthesis_failure_preserves_phase5_partial_report(tmp_path, monkeypatch):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(root, outcomes=("completed",))
    try:

        def fail(*_args, **_kwargs):
            raise RuntimeError("Synthetic synthesis fault")

        monkeypatch.setattr(AuditEngine, "build", fail)
        assert finalize_audit(root, store, run_id) is None
        assert store.run(run_id)["report_status"] == "failed"
        assert latest_report_path(root, store, run_id) == root / "reports" / run_id / "report.json"
        assert (
            RunReport.model_validate_json(
                latest_report_path(root, store, run_id).read_text()
            ).report_status
            == "partial"
        )
    finally:
        store.close()


@pytest.mark.parametrize("outcome", ["cancelled", "blocked", "failed", "interrupted"])
def test_stopped_terminal_runs_export_explicit_partial_audits(tmp_path, outcome):
    root = tmp_path / "cohort"
    run_id, store = create_saved_cohort(root, outcomes=(outcome,))
    try:
        report = finalize_audit(root, store, run_id)
        assert report and report.execution_status == outcome
        assert report.report_status == "partial" and report.scope.phase == 6
        assert not report.findings and report.review.missing_evidence
        assert any(item.kind == "session" for item in report.exclusions)
        for format_name in ("json", "md", "html"):
            assert latest_report_path(root, store, run_id, format_name).is_file()
    finally:
        store.close()


def test_api_latest_revision_human_disposition_and_no_target_revisit(tmp_path, monkeypatch):
    async def scenario():
        root = tmp_path / "cohort"
        run_id, store = create_saved_cohort(root)
        store.close()
        app = create_app(enable_cohorts=True, cohort_root=root, artifact_root=tmp_path / "blocked")
        await app.state.cohorts.start()  # offline recovery synthesizes revision 2
        try:
            report = RunReport.model_validate_json(
                latest_report_path(root, app.state.cohorts.store, run_id).read_text()
            )
            finding_id = str(report.findings[0].id)
            monkeypatch.setattr(
                socket.socket,
                "connect",
                lambda *_: (_ for _ in ()).throw(
                    AssertionError("Report review must not contact a target")
                ),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
            ) as client:
                prior = await client.get(f"/reports/{run_id}/revisions/2/json")
                assert prior.status_code == 200 and prior.json()["revision"] == 2
                updated = await client.post(
                    f"/runs/{run_id}/findings/{finding_id}/review",
                    json={"status": "confirmed", "note": "Reviewed saved evidence."},
                )
                assert updated.status_code == 200 and updated.json()["revision"] == 3
                latest = await client.get(f"/reports/{run_id}/json")
                assert latest.status_code == 200 and latest.json()["revision"] == 3
                assert latest.json()["review"]["dispositions"][0]["status"] == "confirmed"
                assert (await client.get(f"/reports/{run_id}/revisions/2/json")).json()[
                    "revision"
                ] == 2
                missing = await client.post(
                    f"/runs/{run_id}/findings/{uuid4()}/review",
                    json={"status": "confirmed", "note": "No evidence."},
                )
                assert missing.status_code == 409
            assert (root / "reports" / run_id / "revisions" / "3" / "report.html").is_file()
        finally:
            await app.state.cohorts.close()

    asyncio.run(scenario())


def test_two_real_fixture_personas_produce_reviewed_defect_audit(tmp_path):
    async def scenario():
        root = (
            Path(os.environ["FRICTIONLAB_PHASE6_EVIDENCE"]) / str(uuid4())
            if "FRICTIONLAB_PHASE6_EVIDENCE" in os.environ
            else tmp_path / "cohort"
        )
        payload = read_json(CONFIG_DIRECTORY / "run.example.json")
        payload.update(personas=["impatient_mobile"], journeys=["checkout_review"], repetitions=2)
        resolved = resolve_run(payload)

        async def executor(sampled, **kwargs):
            return await run_persona(sampled, model_factory=SemanticHarness, **kwargs)

        coordinator = CohortCoordinator(root, settings=CohortSettings(workers=2), executor=executor)
        try:
            await coordinator.submit(resolved, variant="dead_button")
            result = await asyncio.wait_for(coordinator.wait(str(resolved.config.id)), timeout=150)
            assert result["run"]["report_revision"] == 2
            assert result["run"]["report_status"] == "ready"
            assert {row["outcome"] for row in result["sessions"]} == {"abandoned_patience"}
            path = latest_report_path(root, coordinator.store, str(resolved.config.id))
            report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
            assert report.scope.phase == 6 and report.report_status == "ready"
            assert report.cohort_results.eligible_sessions == 2
            assert report.findings and all(
                item.detector == "dead_interaction" for item in report.findings
            )
            assert sum(item.affected_sessions for item in report.findings) == 2
            assert report.abandonment_explanations and all(
                item.startswith("I ") for item in report.abandonment_explanations
            )
            assert report.protection.sentinel_requests == 0
            assert report.protection.sentinel_data_unchanged
            assert all(
                (path.parent / ref.path).is_file()
                for item in report.findings
                for ref in item.evidence
            )
            assert (path.parent / "report.html").is_file()
        finally:
            await coordinator.close()

    asyncio.run(scenario())
