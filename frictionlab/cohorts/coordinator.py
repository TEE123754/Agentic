"""Bounded owned-fixture cohorts with durable event and partial-report finalization."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from frictionlab.audit.service import finalize_audit
from frictionlab.audit.service import review_finding as save_finding_review
from frictionlab.cohorts.persistence import EventStore
from frictionlab.cohorts.tracing import local_tracer
from frictionlab.cohorts.traffic import SharedTrafficBudget
from frictionlab.configuration import ROOT, ResolvedRun, resolve_run
from frictionlab.contracts.models import RunReport
from frictionlab.planning.local_model import LocalModelRuntime
from frictionlab.planning.runner import run_persona
from frictionlab.reporting import unexecuted_report, write_report


@dataclass(frozen=True)
class CohortSettings:
    workers: int = 1
    max_sessions: int = 6
    max_active_runs: int = 1
    max_run_seconds: int = 900

    def __post_init__(self):
        if not 1 <= self.workers <= 2 or not 1 <= self.max_sessions <= 6:
            raise ValueError("Cohort worker/session counts exceed the local resource cap")
        if self.max_active_runs != 1:
            raise ValueError("Only one owned cohort may run at a time")
        if not 30 <= self.max_run_seconds <= 1800:
            raise ValueError("Cohort runtime must remain within the local resource cap")


@dataclass(frozen=True)
class SessionSpec:
    session_id: str
    persona_id: str
    journey_id: str
    repetition: int
    seed: int
    attempt: int = 1
    parent_session_id: str | None = None


class CohortCoordinator:
    def __init__(self, root: Path | None = None, *, settings=None, executor=None):
        self.root = Path(root or ROOT / "artifacts" / "phase5").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = EventStore(self.root)
        self.trace_provider, self.tracer = local_tracer(self.root)
        self.trace_ids = {}
        self.settings = settings or CohortSettings()
        self.executor = executor or run_persona
        self.tasks = {}
        self.session_tasks = {}
        self.cancelled_sessions = set()
        self.cancelled_runs = set()
        self.interrupting_runs = set()
        self.budgets = {}
        self.started = False
        self._submit_lock = asyncio.Lock()

    async def start(self):
        if self.started:
            return
        self.started = True
        await self.recover()

    async def close(self):
        for run_id, task in list(self.tasks.items()):
            if not task.done():
                self.interrupting_runs.add(run_id)
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.trace_provider.shutdown()
        self.store.close()

    def _specs(self, resolved: ResolvedRun):
        namespace = UUID(str(resolved.config.id))
        return [
            SessionSpec(
                str(uuid5(namespace, f"{persona}:{journey}:{repetition}:1")),
                persona,
                journey,
                repetition,
                (resolved.config.seed + index) % (2**32),
            )
            for index, (persona, journey, repetition) in enumerate(
                (p, j, r)
                for r in range(resolved.config.repetitions)
                for p in resolved.config.personas
                for j in resolved.config.journeys
            )
        ]

    async def submit(
        self, resolved: ResolvedRun, *, variant="healthy", parent_session_id=None, attempt=1
    ):
        await self.start()
        if variant not in {
            "healthy",
            "generic_validation",
            "dead_button",
            "delayed_feedback",
            "hidden_shipping",
            "focus_trap",
        }:
            raise ValueError("Unknown owned fixture variant")
        if resolved.requested_sessions > self.settings.max_sessions:
            raise ValueError("Cohort exceeds the configured six-session local cap")
        run_id = str(resolved.config.id)
        async with self._submit_lock:
            if self.store.run(run_id):
                raise ValueError("Run ID already exists; create a fresh run")
            if parent_session_id and self.store.rows(
                "SELECT 1 FROM sessions WHERE parent_session_id = ?", [str(parent_session_id)]
            ):
                raise ValueError("An interrupted session already has a retry attempt")
            if (
                sum(not task.done() for task in self.tasks.values())
                >= self.settings.max_active_runs
            ):
                raise ValueError("A cohort is already active; bounded queue is full")
            specs = self._specs(resolved)
            if parent_session_id is not None:
                if len(specs) != 1 or attempt < 2:
                    raise ValueError("A retry must contain exactly one new session attempt")
                specs = [
                    replace(specs[0], attempt=attempt, parent_session_id=str(parent_session_id))
                ]
            directory = self.root / "runs" / run_id
            directory.mkdir(parents=True, exist_ok=False)
            manifest = {
                "run_id": run_id,
                "configuration": resolved.config.model_dump(mode="json"),
                "configuration_hash": resolved.configuration_hash,
                "environment": resolved.environment.model_dump(mode="json"),
                "variant": variant,
                "profiles": {p.id: p.model_dump(mode="json") for p in resolved.personas},
                "journeys": {j.id: j.model_dump(mode="json") for j in resolved.journeys},
                "sessions": [spec.__dict__ for spec in specs],
                "model": json.loads((ROOT / "configs" / "resource-manifest.json").read_text())[
                    "model"
                ]["revision"],
                "detector_policy": json.loads((ROOT / "configs" / "cognition.json").read_text())[
                    "version"
                ],
                "workers": self.settings.workers,
                "scope": "bundled_fixture_only",
            }
            _atomic_json(directory / "manifest.json", manifest)
            self.store.append(
                "run_created",
                run_id,
                {
                    "configuration_hash": resolved.configuration_hash,
                    "manifest_path": str((directory / "manifest.json").relative_to(self.root)),
                },
            )
            self.store.append("report_job", run_id, {"revision": 1, "status": "pending"})
            for spec in specs:
                self.store.append("session_queued", run_id, spec.__dict__, spec.session_id)
            task = asyncio.create_task(self._execute_run(resolved, specs, variant))
            self.tasks[run_id] = task
        return self.status(run_id)

    async def retry_interrupted(self, run_id, session_id):
        prior = self.store.run(str(run_id))
        if not prior:
            raise KeyError("Cohort does not exist")
        row = next(
            (
                row
                for row in self.store.sessions(str(run_id))
                if row["session_id"] == str(session_id)
            ),
            None,
        )
        if row is None:
            raise KeyError("Session does not belong to this cohort")
        if row["status"] != "interrupted":
            raise ValueError("Only an interrupted session may be retried")
        manifest = json.loads(
            (self.root / "runs" / str(run_id) / "manifest.json").read_text(encoding="utf-8")
        )
        payload = manifest["configuration"].copy()
        payload.update(
            id=str(uuid4()),
            personas=[row["persona_id"]],
            journeys=[row["journey_id"]],
            repetitions=1,
            seed=row["seed"],
        )
        resolved = resolve_run(
            payload, expected_origin=manifest["environment"]["replica_origins"][0]
        )
        return await self.submit(
            resolved,
            variant=manifest["variant"],
            parent_session_id=str(session_id),
            attempt=row["attempt"] + 1,
        )

    def status(self, run_id):
        run = self.store.run(str(run_id))
        if not run:
            return None
        sessions = self.store.sessions(str(run_id))
        return {
            "run": run,
            "sessions": sessions,
            "event_count": self.store.event_count(str(run_id)),
            "trace_path": "otel-spans.jsonl",
            "traffic": self.budgets[str(run_id)].metrics() if str(run_id) in self.budgets else None,
        }

    async def wait(self, run_id):
        task = self.tasks.get(str(run_id))
        if task:
            await asyncio.shield(task)
        return self.status(run_id)

    async def review_finding(self, run_id, finding_id, review):
        if self.store.run(str(run_id)) is None:
            raise KeyError("Cohort does not exist")
        async with self._submit_lock:
            return save_finding_review(self.root, self.store, run_id, finding_id, review)

    async def cancel(self, run_id, session_id=None):
        run_id = str(run_id)
        run = self.store.run(run_id)
        if not run:
            raise KeyError("Cohort does not exist")
        if run["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            raise ValueError("Cohort already reached a terminal state")
        if session_id:
            session_id = str(session_id)
            row = next(
                (row for row in self.store.sessions(run_id) if row["session_id"] == session_id),
                None,
            )
            if row is None:
                raise KeyError("Session does not belong to this cohort")
            if row["status"] not in {"queued", "running"}:
                raise ValueError("Session already reached a terminal state")
            if session_id in self.cancelled_sessions:
                return self.status(run_id)
            self.cancelled_sessions.add(session_id)
            task = self.session_tasks.get(session_id)
            if task and not task.done():
                task.cancel()
        else:
            if run_id in self.cancelled_runs:
                return self.status(run_id)
            self.cancelled_runs.add(run_id)
            for row in self.store.sessions(run_id):
                task = self.session_tasks.get(row["session_id"])
                if task and not task.done():
                    task.cancel()
        self.store.append(
            "cancellation_requested",
            run_id,
            {"session_id": session_id, "scope": "session" if session_id else "run"},
            session_id,
        )
        return self.status(run_id)

    async def _execute_run(self, resolved, specs, variant):
        run_id = str(resolved.config.id)
        budget = SharedTrafficBudget(
            requests_per_second=resolved.environment.limits.requests_per_second,
            concurrency=resolved.environment.limits.concurrency,
        )
        self.budgets[run_id] = budget
        queue = asyncio.Queue(maxsize=self.settings.max_sessions)
        for spec in specs:
            queue.put_nowait(spec)
        runtime = None
        reason = None
        monitor = None
        self.store.append("run_status", run_id, {"status": "running"})
        try:
            if self.executor is run_persona:
                runtime = LocalModelRuntime(self.root / "runs" / run_id / "model")
                await runtime.__aenter__()

            async def worker():
                while not queue.empty():
                    spec = queue.get_nowait()
                    try:
                        if (
                            budget.stop_reason
                            or run_id in self.cancelled_runs
                            or (spec.session_id in self.cancelled_sessions)
                        ):
                            await self._unstarted_session(
                                resolved,
                                spec,
                                "cancelled" if not budget.stop_reason else "failed",
                                budget.stop_reason or "Cohort session cancelled before navigation.",
                            )
                        else:
                            task = asyncio.create_task(
                                self._execute_session(resolved, spec, variant, runtime, budget)
                            )
                            self.session_tasks[spec.session_id] = task
                            try:
                                await task
                            except asyncio.CancelledError:
                                if run_id not in self.interrupting_runs:
                                    await self._recover_cancelled_session(resolved, spec)
                                else:
                                    await self._recover_interrupted_session(resolved, spec)
                            finally:
                                self.session_tasks.pop(spec.session_id, None)
                    finally:
                        queue.task_done()

            workers = [asyncio.create_task(worker()) for _ in range(self.settings.workers)]

            async def watch_health():
                deadline = time.monotonic() + self.settings.max_run_seconds
                while any(not worker_task.done() for worker_task in workers):
                    if time.monotonic() >= deadline:
                        budget.stop("Cohort-wide runtime ceiling exceeded; results contaminated")
                    if budget.stop_reason:
                        for session_task in list(self.session_tasks.values()):
                            session_task.cancel()
                        return
                    await asyncio.sleep(0.05)

            monitor = asyncio.create_task(watch_health())
            try:
                await asyncio.gather(*workers)
            except asyncio.CancelledError:
                reason = "Cohort process stopped during execution."
                self.interrupting_runs.add(run_id)
                for task in self.session_tasks.values():
                    task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
            if budget.stop_reason:
                reason = budget.stop_reason
        except Exception as exc:  # noqa: BLE001 -- terminal reports must survive model startup faults
            reason = f"Cohort infrastructure failed ({type(exc).__name__}); no UX inference."
        finally:
            if monitor:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
            if runtime:
                try:
                    await runtime.close()
                except Exception as exc:  # noqa: BLE001 -- preserve the terminal report
                    reason = f"Shared model cleanup failed ({type(exc).__name__}); no UX inference."
            for spec in specs:
                row = next(
                    row
                    for row in self.store.sessions(run_id)
                    if row["session_id"] == spec.session_id
                )
                if row["status"] in {"queued", "running"}:
                    await self._unstarted_session(
                        resolved,
                        spec,
                        "interrupted"
                        if run_id in self.interrupting_runs
                        else "cancelled"
                        if run_id in self.cancelled_runs
                        else "failed",
                        reason or "Session stopped without a terminal result; no UX inference.",
                    )
            try:
                self._finalize(resolved, budget, reason)
            except Exception as exc:  # noqa: BLE001 -- journal retains a recoverable report job
                self.store.append("report_job", run_id, {"revision": 1, "status": "failed"})
                self.store.append(
                    "run_status",
                    run_id,
                    {
                        "status": "failed",
                        "reason": f"Report export failed ({type(exc).__name__}); retry on restart.",
                    },
                )
            else:
                finalize_audit(self.root, self.store, run_id)

    async def _execute_session(self, resolved, spec, variant, runtime, budget):
        run_id = str(resolved.config.id)
        sid = spec.session_id
        with self.tracer.start_as_current_span(
            "cohort.session",
            attributes={
                "run.id": run_id,
                "session.id": sid,
                "persona.id": spec.persona_id,
                "journey.id": spec.journey_id,
                "session.seed": spec.seed,
            },
        ) as span:
            self.trace_ids[sid] = f"{span.get_span_context().trace_id:032x}"
            self.store.append("session_started", run_id, {}, sid)
            started = time.monotonic()
            sampled = replace(
                resolved, config=resolved.config.model_copy(update={"seed": spec.seed})
            )
            root = self.root / "runs" / run_id / "sessions"
            try:
                broker = await self.executor(
                    sampled,
                    persona_id=spec.persona_id,
                    journey_id=spec.journey_id,
                    variant=variant,
                    runtime=runtime,
                    behavioral=True,
                    artifact_root=root,
                    global_budget=budget,
                    session_id=UUID(sid),
                )
                report = broker.report
                completion = getattr(broker, "completion", {})
            except asyncio.CancelledError:
                span.set_attribute("session.status", "cancelled_or_interrupted")
                raise
            except Exception as exc:  # noqa: BLE001 -- make every session terminal
                report = self._partial_session_report(
                    sampled,
                    spec,
                    "failed",
                    f"Session worker failed ({type(exc).__name__}); no UX diagnosis inferred.",
                )
                completion = {}
            span.set_attribute("session.status", str(report.execution_status))
            for index, step in enumerate(report.trajectories):
                span.add_event(
                    "browser.action",
                    {"step.index": index, "action.id": str(step.action_id), "result": step.result},
                )
            for decision in report.planner_decisions:
                span.add_event(
                    "model.decision", {"attempt": decision.attempt, "status": decision.status}
                )
            for event in report.friction_events:
                span.add_event(
                    "friction.detected", {"detector": event.detector, "event.id": str(event.id)}
                )
            self._record_session(resolved, spec, report, completion, started)

    def _session_directory(self, run_id, session_id):
        return self.root / "runs" / run_id / "sessions" / session_id

    def _partial_session_report(self, resolved, spec, status, reason):
        run_id = str(resolved.config.id)
        path = self._session_directory(run_id, spec.session_id) / "report.json"
        if path.is_file():
            return RunReport.model_validate_json(path.read_text(encoding="utf-8"))
        base = unexecuted_report(reason, resolved, status)
        data = base.model_dump(mode="json")
        data["run_id"] = spec.session_id
        data["scope"].update(
            phase=5, personas=[spec.persona_id], journeys=[spec.journey_id], seed=spec.seed
        )
        data["cohort_results"]["requested_sessions"] = 1
        data["executive_summary"] = (
            f"Synthetic {spec.persona_id} session stopped before navigation: {reason}"
        )
        report = RunReport.model_validate(data)
        directory = self._session_directory(run_id, spec.session_id)
        write_report(report, directory.parent, prepared_directory=directory.exists())
        return report

    async def _unstarted_session(self, resolved, spec, status, reason):
        report = self._partial_session_report(resolved, spec, status, reason)
        self._record_session(resolved, spec, report, {}, time.monotonic())

    async def _recover_cancelled_session(self, resolved, spec):
        budget = self.budgets.get(str(resolved.config.id))
        contaminated = budget.stop_reason if budget else None
        report = self._partial_session_report(
            resolved,
            spec,
            "failed" if contaminated else "cancelled",
            contaminated or "Synthetic session cancelled; no UX inference.",
        )
        self._record_session(resolved, spec, report, {}, time.monotonic())

    async def _recover_interrupted_session(self, resolved, spec):
        report = self._partial_session_report(
            resolved,
            spec,
            "interrupted",
            "Synthetic session interrupted; restart as a new attempt.",
        )
        self._record_session(resolved, spec, report, {}, time.monotonic())

    def _record_session(self, resolved, spec, report, completion, started):
        run_id = str(resolved.config.id)
        sid = spec.session_id
        if self.store.rows(
            "SELECT 1 FROM sessions WHERE session_id = ? AND status NOT IN ('queued', 'running')",
            [sid],
        ):
            return
        directory = self._session_directory(run_id, sid)
        if not (directory / "report.json").is_file():
            write_report(report, directory.parent, prepared_directory=directory.exists())
        relative = str(
            (self._session_directory(run_id, sid) / "report.html").relative_to(self.root)
        ).replace("\\", "/")
        outcome = next(iter(report.cohort_results.outcome_counts), None)
        if self.budgets.get(run_id) and self.budgets[run_id].stop_reason:
            outcome = (
                "inconclusive_agent_failure" if report.cohort_results.executed_sessions else None
            )
        self.store.append(
            "session_terminal",
            run_id,
            {
                "status": str(report.execution_status),
                "outcome": outcome,
                "report_path": relative,
            },
            sid,
        )
        trace_id = self.trace_ids.get(sid, UUID(sid).hex)
        self.store.append(
            "trace_span",
            run_id,
            {
                "trace_id": trace_id,
                "span_name": "cohort.session",
                "duration_seconds": round(time.monotonic() - started, 6),
                "status": str(report.execution_status),
            },
            sid,
        )
        for index, step in enumerate(report.trajectories):
            self.store.append(
                "step",
                run_id,
                {
                    "step_index": index,
                    "action_kind": step.action.kind if step.action else None,
                    "result": step.result,
                    "detail": step.detail,
                    "action_id": str(step.action_id),
                },
                sid,
            )
            self.store.append(
                "trace_span",
                run_id,
                {
                    "trace_id": trace_id,
                    "span_name": "browser.action",
                    "duration_seconds": step.application_seconds,
                    "step_index": index,
                },
                sid,
            )
        for event in report.friction_events:
            self.store.append("friction", run_id, event.model_dump(mode="json"), sid)
        for name, passed in completion.items():
            self.store.append("milestone", run_id, {"name": name, "passed": bool(passed)}, sid)
        for ref in report.visual_evidence:
            self.store.append(
                "artifact",
                run_id,
                {"path": relative.rsplit("/", 1)[0] + "/" + ref.path, "kind": ref.kind},
                sid,
            )
        for decision in report.planner_decisions:
            self.store.append(
                "model_call",
                run_id,
                {
                    "attempt": decision.attempt,
                    "status": decision.status,
                    "inference_seconds": decision.inference_seconds,
                    "category": decision.category,
                },
                sid,
            )
            self.store.append(
                "trace_span",
                run_id,
                {
                    "trace_id": trace_id,
                    "span_name": "model.decision",
                    "duration_seconds": decision.inference_seconds,
                    "attempt": decision.attempt,
                },
                sid,
            )

    def _finalize(self, resolved, budget, reason, status_override=None):
        run_id = str(resolved.config.id)
        sessions = self.store.sessions(run_id)
        counts = Counter(row["outcome"] for row in sessions if row["outcome"])
        executed = sum(counts.values())
        interrupted = run_id in self.interrupting_runs
        cancelled = run_id in self.cancelled_runs
        status = status_override or (
            "interrupted"
            if interrupted
            else "failed"
            if budget.stop_reason or reason
            else ("cancelled" if cancelled else "completed")
        )
        self.store.append("run_status", run_id, {"status": status, "reason": reason})
        report_path = self.root / "reports" / run_id / "report.html"
        if report_path.is_file():
            self.store.append(
                "report_job",
                run_id,
                {
                    "revision": 1,
                    "status": "partial",
                    "report_path": str(report_path.relative_to(self.root)).replace("\\", "/"),
                },
            )
            return
        base = unexecuted_report(
            reason or "Cohort sessions reached terminal states on owned fixtures.",
            resolved,
            status if status != "completed" else "failed",
        )
        data = base.model_dump(mode="json")
        data["scope"]["phase"] = 5
        data["scope"]["runtime_metadata"].update(
            {
                "workers": self.settings.workers,
                "session_reports": len(sessions),
                "global_peak_requests_per_second": budget.metrics()["peak_requests_per_second"],
                "global_peak_concurrent_requests": budget.metrics()["peak_concurrent_requests"],
            }
        )
        data["execution_status"] = status
        data["report_status"] = "partial"
        data["terminal_reason"] = (
            reason or "All owned-fixture cohort sessions reached terminal states."
        )
        data["executive_summary"] = (
            f"{len(sessions)} independent synthetic sessions were scheduled on the owned fixture; "
            f"{executed} navigated. Outcomes: {dict(counts)}. "
            f"Global traffic peak: {budget.metrics()['peak_requests_per_second']} requests/s. "
            "This is a factual Phase 5 summary, not a calibrated UX audit."
        )
        data["cohort_results"] = {
            "requested_sessions": len(sessions),
            "executed_sessions": executed,
            "eligible_sessions": counts["completed"] + counts["abandoned_patience"],
            "outcome_counts": dict(counts),
        }
        data["session_summaries"] = []
        individual = []
        for row in sessions:
            path = row["report_path"]
            if path:
                individual.append(path)
                session_report = _read_session(self.root, row)
                milestones = self.store.rows(
                    "SELECT name FROM milestones WHERE session_id = ? AND passed = true",
                    [row["session_id"]],
                )
                data["session_summaries"].append(
                    {
                        "session_id": row["session_id"],
                        "persona_id": row["persona_id"],
                        "journey_id": row["journey_id"],
                        "repetition": row["repetition"],
                        "seed": row["seed"],
                        "attempt": row["attempt"],
                        "parent_session_id": row["parent_session_id"],
                        "execution_status": row["status"],
                        "outcome": row["outcome"],
                        "steps": len(session_report.trajectories),
                        "friction_events": len(session_report.friction_events),
                        "model_calls": len(session_report.planner_decisions),
                        "passed_milestones": [item["name"] for item in milestones],
                        "report_path": path,
                    }
                )
        data["recommendations"] = [
            "Review individual session reports: " + ", ".join(individual[:6]),
            "Implement Phase 6 evidence grouping, calibrated findings, and heatmaps before UX claims.",
        ]
        data["review"].update(
            status="evidence_reviewed",
            method="Journal, DuckDB projections, and immutable individual reports reviewed offline.",
            missing_evidence=["Phase 6 aggregate findings and heatmaps"],
            limitations=[
                "Only the bundled local fixture is supported.",
                "A partial factual report does not establish calibrated churn or UX severity.",
                *([reason] if reason else []),
            ],
        )
        data["protection"].update(
            sentinel_requests=0
            if executed == 0
            else sum(
                _read_session(self.root, row).protection.sentinel_requests or 0
                for row in sessions
                if row["report_path"]
            ),
            sentinel_data_unchanged=all(
                _read_session(self.root, row).protection.sentinel_data_unchanged is not False
                for row in sessions
                if row["report_path"]
            ),
            target_requests=sum(
                _read_session(self.root, row).protection.target_requests
                for row in sessions
                if row["report_path"]
            ),
            network_boundary_validated=executed > 0
            and not budget.stop_reason
            and all(
                _read_session(self.root, row).protection.network_boundary_validated
                for row in sessions
                if row["outcome"]
            ),
            boundary_scope="owned_fixture_browser_proxy" if executed else "unvalidated",
            traffic_metrics={
                "forwarded_requests": budget.metrics()["forwarded_requests"],
                "peak_requests_per_second": budget.metrics()["peak_requests_per_second"],
                "peak_concurrent_requests": budget.metrics()["peak_concurrent_requests"],
            },
            cleanup_outcome="Individual session reports record run-owned cleanup; no shared data reset.",
        )
        report = RunReport.model_validate(data)
        self.store.append("report_job", run_id, {"revision": 1, "status": "reviewing"})
        folder = write_report(report, self.root / "reports", recover_partial=True)
        self.store.append(
            "report_job",
            run_id,
            {
                "revision": 1,
                "status": "partial",
                "report_path": str((folder / "report.html").relative_to(self.root)).replace(
                    "\\", "/"
                ),
            },
        )

    async def recover(self):
        pending = self.store.unfinished()
        for row in pending:
            manifest = self.root / "runs" / row["run_id"] / "manifest.json"
            if not manifest.is_file():
                continue
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            expected_origin = payload["environment"]["replica_origins"][0]
            resolved = resolve_run(payload["configuration"], expected_origin=expected_origin)
            spec = next(
                SessionSpec(**item)
                for item in payload["sessions"]
                if item["session_id"] == row["session_id"]
            )
            await self._recover_interrupted_session(resolved, spec)
        incomplete = self.store.rows(
            "SELECT run_id FROM runs WHERE report_status NOT IN ('partial', 'ready')"
        )
        pending_runs = {row["run_id"] for row in pending}
        for run_id in {row["run_id"] for row in pending + incomplete}:
            manifest = self.root / "runs" / run_id / "manifest.json"
            if not manifest.is_file():
                continue
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            resolved = resolve_run(
                payload["configuration"],
                expected_origin=payload["environment"]["replica_origins"][0],
            )
            prior_status = self.store.run(run_id)["status"]
            if run_id in pending_runs:
                self.interrupting_runs.add(run_id)
            self._finalize(
                resolved,
                SharedTrafficBudget(),
                "Previous process stopped; unfinished sessions were marked interrupted."
                if run_id in pending_runs
                else "Recovered pending report export.",
                status_override=prior_status
                if run_id not in pending_runs
                and prior_status in {"completed", "failed", "cancelled", "interrupted"}
                else None,
            )
        terminal = self.store.rows(
            "SELECT run_id, report_revision, report_status FROM runs "
            "WHERE status IN ('completed', 'failed', 'cancelled', 'interrupted')"
        )
        for row in terminal:
            if row["report_revision"] < 2 or (
                row["report_revision"] == 2 and row["report_status"] not in {"ready", "partial"}
            ):
                finalize_audit(self.root, self.store, row["run_id"])


def _read_session(root, row):
    path = root / row["report_path"]
    path = path.with_name("report.json")
    return RunReport.model_validate_json(path.read_text(encoding="utf-8"))


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
