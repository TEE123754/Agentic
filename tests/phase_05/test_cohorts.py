import asyncio
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx

from frictionlab.api import create_app
from frictionlab.browser.broker import BrowserBroker
from frictionlab.cohorts.coordinator import CohortCoordinator, CohortSettings
from frictionlab.cohorts.persistence import EventStore
from frictionlab.cohorts.traffic import SharedTrafficBudget
from frictionlab.configuration import CONFIG_DIRECTORY, read_json, resolve_run
from frictionlab.contracts.models import Action, RunReport
from frictionlab.reporting import unexecuted_report


def configuration(
    *, personas=("impatient_mobile", "enterprise_evaluator"), journey="checkout_review"
):
    data = read_json(CONFIG_DIRECTORY / "run.example.json")
    data["personas"] = list(personas)
    data["journeys"] = [journey]
    return resolve_run(data)


def test_journal_replay_deduplicates_and_truncates_only_uncommitted_tail(tmp_path):
    root = tmp_path / "cohorts"
    store = EventStore(root)
    run_id = str(configuration().config.id)
    sid = str(configuration().config.id)
    store.append("run_created", run_id, {"configuration_hash": "abc", "manifest_path": "m"})
    store.append(
        "session_queued",
        run_id,
        {
            "persona_id": "impatient_mobile",
            "journey_id": "checkout_review",
            "repetition": 0,
            "seed": 42,
        },
        sid,
    )
    committed = store.event_count(run_id)
    store.close()
    with (root / "events.jsonl").open("ab") as stream:
        stream.write(b'{"event_id":"partial"')
    restored = EventStore(root)
    assert restored.event_count(run_id) == committed == 2
    assert len(restored.sessions(run_id)) == 1
    assert restored.replay() == 0
    assert (root / "events.jsonl").read_bytes().endswith(b"\n")
    restored.close()


def test_global_traffic_budget_and_health_stop():
    budget = SharedTrafficBudget(
        requests_per_second=2, concurrency=1, max_wait_seconds=5, unhealthy_responses=2
    )
    stopped = threading.Event()
    assert budget.acquire(stopped)
    admitted = []
    thread = threading.Thread(
        target=lambda: (admitted.append(budget.acquire(stopped)), budget.release())
    )
    thread.start()
    thread.join(timeout=0.1)
    assert not admitted
    budget.release()
    thread.join(timeout=3)
    assert admitted == [True]
    assert budget.metrics()["peak_concurrent_requests"] == 1
    assert budget.metrics()["peak_requests_per_second"] <= 2
    budget.observe_response(503, 0.1)
    budget.observe_response(502, 0.1)
    assert budget.stop_reason and not budget.acquire(stopped)


def test_cohort_health_stop_cancels_workers_without_churn_claim(tmp_path):
    async def scenario():
        entered = asyncio.Event()

        async def waiting_executor(*_args, **_kwargs):
            entered.set()
            await asyncio.Event().wait()

        resolved = configuration(personas=("impatient_mobile",))
        coordinator = CohortCoordinator(tmp_path / "phase5", executor=waiting_executor)
        try:
            await coordinator.submit(resolved)
            await asyncio.wait_for(entered.wait(), timeout=5)
            run_id = str(resolved.config.id)
            budget = coordinator.budgets[run_id]
            budget.observe_response(503, 0.1)
            budget.observe_response(502, 0.1)
            result = await asyncio.wait_for(coordinator.wait(run_id), timeout=10)
            assert result["run"]["status"] == "failed"
            assert result["sessions"][0]["status"] == "failed"
            report = RunReport.model_validate_json(
                (coordinator.root / "reports" / run_id / "report.json").read_text()
            )
            assert report.cohort_results.executed_sessions == 0
            assert not report.abandonment_explanations and not report.findings
            assert "contaminated" in report.terminal_reason
        finally:
            await coordinator.close()

    asyncio.run(scenario())


def test_two_browser_workers_isolate_state_cancel_and_export_partial_report(tmp_path):
    async def scenario():
        root = (
            Path(os.environ["FRICTIONLAB_PHASE5_EVIDENCE"]) / str(uuid4())
            if "FRICTIONLAB_PHASE5_EVIDENCE" in os.environ
            else tmp_path / "phase5"
        )
        resolved = configuration()
        ready = asyncio.Event()
        seen = {}
        brokers = {}

        async def executor(
            sampled,
            *,
            persona_id,
            journey_id,
            variant,
            artifact_root,
            global_budget,
            session_id,
            **_kwargs,
        ):
            async with BrowserBroker(
                sampled,
                persona_id=persona_id,
                journey_id=journey_id,
                variant=variant,
                artifact_root=artifact_root,
                global_budget=global_budget,
                session_id=session_id,
            ) as broker:
                brokers[persona_id] = broker
                seen[persona_id] = (
                    str(broker.run_id),
                    broker.text_values["synthetic_email"],
                    str(broker.profile.name),
                )
                if len(seen) == 2:
                    ready.set()
                await ready.wait()
                if persona_id == "impatient_mobile":
                    await asyncio.Event().wait()
                else:
                    for kind, name in (
                        ("click", "Start checkout"),
                        ("type_text", "textbox"),
                        ("click", "Continue to order review"),
                    ):
                        chosen = next(
                            c
                            for c in broker.current.candidates
                            if c.name == name or name == "textbox" and c.role == name
                        )
                        action = Action(
                            kind=kind,
                            observation_id=broker.current.id,
                            candidate_id=chosen.candidate_id,
                            text_reference="synthetic_email" if kind == "type_text" else None,
                        )
                        await broker.act(action)
                    assert all((await broker.verify_completion()).values())
                    await broker.act(Action(kind="finish", observation_id=broker.current.id))
            return broker

        coordinator = CohortCoordinator(root, settings=CohortSettings(workers=2), executor=executor)
        try:
            await coordinator.submit(resolved)
            await asyncio.wait_for(ready.wait(), timeout=90)
            run_id = str(resolved.config.id)
            mobile = next(
                row
                for row in coordinator.status(run_id)["sessions"]
                if row["persona_id"] == "impatient_mobile"
            )
            await coordinator.cancel(run_id, mobile["session_id"])
            status = await asyncio.wait_for(coordinator.wait(run_id), timeout=120)
            rows = {row["persona_id"]: row for row in status["sessions"]}
            assert rows["impatient_mobile"]["status"] == "cancelled"
            assert rows["enterprise_evaluator"]["outcome"] == "completed"
            assert len({value[0] for value in seen.values()}) == 2
            assert len({value[1] for value in seen.values()}) == 2
            assert len({value[2] for value in seen.values()}) == 2
            for broker in brokers.values():
                assert broker.closed and not broker.cleanup_errors
                assert not Path(broker.profile.name).exists()
                assert broker.runtime.sentinel_state == {"requests": [], "balance": 100}
                assert (
                    broker.runtime.app.state.fixture.snapshot(broker.run_id)["account_count"] == 0
                )
            metrics = status["traffic"]
            assert metrics["peak_requests_per_second"] <= 2
            assert metrics["peak_concurrent_requests"] <= 1
            assert status["run"]["report_status"] == "partial"
            report = RunReport.model_validate_json(
                (root / "reports" / run_id / "report.json").read_text()
            )
            assert report.cohort_results.requested_sessions == 2
            assert report.cohort_results.outcome_counts == {"completed": 1, "cancelled": 1}
            assert report.report_status == "partial" and not report.findings
            assert (root / "reports" / run_id / "report.html").is_file()
            assert (root / "otel-spans.jsonl").is_file()
            assert coordinator.store.rows("SELECT COUNT(*) AS n FROM steps")[0]["n"] >= 3
            assert coordinator.store.rows("SELECT COUNT(*) AS n FROM milestones")[0]["n"] >= 1
            assert coordinator.store.rows("SELECT COUNT(*) AS n FROM trace_spans")[0]["n"] >= 2
        finally:
            await coordinator.close()

    asyncio.run(scenario())


def test_interrupted_journal_recovers_once_without_inventing_churn(tmp_path):
    async def scenario():
        async def stopped_executor(sampled, *, session_id, **_kwargs):
            report = unexecuted_report(
                "Fresh retry attempt ended before navigation.", sampled, "failed"
            )
            payload = report.model_dump(mode="json")
            payload["run_id"] = str(session_id)
            return SimpleNamespace(report=RunReport.model_validate(payload), completion={})

        root = tmp_path / "phase5"
        resolved = configuration(personas=("impatient_mobile",))
        seed_coordinator = CohortCoordinator(root)
        spec = seed_coordinator._specs(resolved)[0]
        run_id = str(resolved.config.id)
        manifest = root / "runs" / run_id / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps(
                {
                    "configuration": resolved.config.model_dump(mode="json"),
                    "environment": resolved.environment.model_dump(mode="json"),
                    "variant": "healthy",
                    "sessions": [spec.__dict__],
                }
            )
        )
        seed_coordinator.store.append(
            "run_created",
            run_id,
            {
                "configuration_hash": resolved.configuration_hash,
                "manifest_path": str(manifest.relative_to(root)),
            },
        )
        seed_coordinator.store.append("report_job", run_id, {"revision": 1, "status": "pending"})
        seed_coordinator.store.append("session_queued", run_id, spec.__dict__, spec.session_id)
        seed_coordinator.store.append("session_started", run_id, {}, spec.session_id)
        await seed_coordinator.close()
        incomplete = root / "reports" / run_id
        incomplete.mkdir(parents=True)
        (incomplete / "report.json").write_text("{incomplete export", encoding="utf-8")
        app = create_app(
            enable_cohorts=True,
            cohort_root=root,
            artifact_root=tmp_path / "blocked",
            cohort_executor=stopped_executor,
        )
        restored = app.state.cohorts
        try:
            await restored.start()
            status = restored.status(run_id)
            assert status["run"]["status"] == "interrupted"
            assert status["sessions"][0]["status"] == "interrupted"
            assert status["run"]["report_status"] == "partial"
            report = RunReport.model_validate_json(
                (root / "reports" / run_id / "report.json").read_text()
            )
            assert report.cohort_results.executed_sessions == 0
            assert not report.abandonment_explanations and not report.findings
            count = status["event_count"]
            await restored.recover()
            assert restored.status(run_id)["event_count"] == count
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
            ) as client:
                response = await client.post(f"/runs/{run_id}/sessions/{spec.session_id}/retry")
                assert response.status_code == 202
                retry = response.json()
                duplicate = await client.post(f"/runs/{run_id}/sessions/{spec.session_id}/retry")
                assert duplicate.status_code == 409
            retry_id = retry["run"]["run_id"]
            retry_status = await restored.wait(retry_id)
            child = retry_status["sessions"][0]
            assert child["attempt"] == 2
            assert child["parent_session_id"] == spec.session_id
            assert child["seed"] == spec.seed
            assert retry_status["run"]["report_status"] == "partial"
            assert restored.status(run_id)["event_count"] == count
        finally:
            await restored.close()

    asyncio.run(scenario())


def test_api_rejects_external_scope_and_exposes_run_control(tmp_path):
    async def scenario():
        async def executor(sampled, *, session_id, **_kwargs):
            await asyncio.sleep(0.2)
            report = unexecuted_report(
                "Synthetic worker reached a controlled stop.", sampled, "failed"
            )
            payload = report.model_dump(mode="json")
            payload["run_id"] = str(session_id)
            return SimpleNamespace(report=RunReport.model_validate(payload), completion={})

        root = tmp_path / "phase5"
        app = create_app(
            enable_cohorts=True,
            cohort_root=root,
            artifact_root=tmp_path / "blocked",
            cohort_executor=executor,
        )
        resolved = configuration(personas=("impatient_mobile",))
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
            ) as client:
                unsafe = resolved.config.model_dump(mode="json")
                unsafe["environment"] = "production"
                blocked = await client.post("/runs", json=unsafe)
                assert blocked.status_code == 409
                started = await client.post("/runs", json=resolved.config.model_dump(mode="json"))
                assert started.status_code == 202
                run_id = str(resolved.config.id)
                assert (await client.get(f"/runs/{run_id}")).status_code == 200
                assert (await client.post(f"/runs/{run_id}/cancel")).status_code == 200
                await app.state.cohorts.wait(run_id)
                report = await client.get(f"/reports/{run_id}/html")
                assert report.status_code == 200
                assert "partial" in report.text
        finally:
            await app.state.cohorts.close()

    asyncio.run(scenario())
