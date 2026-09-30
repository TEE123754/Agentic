import asyncio
import json
import re
import threading
import time
from pathlib import Path

import pytest
from smolagents.models import (
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
    Model,
)

from frictionlab.configuration import ROOT
from frictionlab.contracts.models import Action, RunReport
from frictionlab.planning.contracts import AgentLimits, PlannerStopped
from frictionlab.planning.runner import run_persona


def terminal_review(broker):
    report = broker.report
    assert report.scope.phase == 3 and report.report_status == "partial"
    assert broker.closed and not broker.cleanup_errors
    assert report.protection.sentinel_requests == 0 and report.protection.sentinel_data_unchanged
    assert not report.findings and not report.abandonment_explanations
    assert not report.scope.runtime_metadata["generated_python_executed"]
    assert report.scope.runtime_metadata["planner_worker_drained"]
    for suffix in ("json", "md", "html"):
        assert (broker.directory / f"report.{suffix}").is_file()
    document = (broker.directory / "report.html").read_text(encoding="utf-8")
    assert "Autonomous planner decisions" in document and "<script" not in document
    if broker.started_navigation:
        assert report.protection.network_boundary_validated and all(broker.boundary_checks.values())
        assert not Path(broker.profile.name).exists()
        assert broker.runtime.task is broker.runtime.proxy is broker.runtime.sentinel is None
        assert broker.runtime.app.state.fixture.snapshot(broker.run_id)["account_count"] == 0
    return report


@pytest.mark.parametrize(
    "persona,journey",
    [
        ("impatient_mobile", "checkout_review"),
        ("keyboard_low_vision", "keyboard_checkout"),
        ("enterprise_evaluator", "delivery_information"),
    ],
)
def test_healthy_seeded_persona_first_attempt(resolved, persona, journey, request):
    saved_run = request.config.getoption("--phase3-review-saved")
    if saved_run:
        directory = (ROOT / "artifacts" / "phase3" / "runs" / saved_run).resolve()
        assert directory.is_relative_to((ROOT / "artifacts" / "phase3" / "runs").resolve())
        report = RunReport.model_validate_json(
            (directory / "report.json").read_text(encoding="utf-8")
        )
        assert report.scope.personas == (persona,) and report.scope.journeys == (journey,)
        review = json.loads((directory / "evidence" / "review.json").read_text(encoding="utf-8"))
        assert not review["cleanup_errors"] and all(review["boundary_checks"].values())
        assert review["completion"] and all(review["completion"].values())
        assert (
            report.protection.network_boundary_validated
            and report.protection.sentinel_requests == 0
            and report.protection.sentinel_data_unchanged
        )
        assert not report.findings and not report.abandonment_explanations
        assert report.scope.runtime_metadata["planner_worker_drained"]
        assert all((directory / ref.path).is_file() for ref in report.visual_evidence)
        assert all((directory / f"report.{suffix}").is_file() for suffix in ("json", "md", "html"))
        print(f"Offline evidence review only: {saved_run}; no browser or model call.")
    else:
        runtime = request.getfixturevalue("local_runtime")
        broker = asyncio.run(
            run_persona(resolved, persona_id=persona, journey_id=journey, runtime=runtime)
        )
        report = terminal_review(broker)
        directory = broker.directory
        assert all(broker.completion.values()) and broker.finished
    assert report.cohort_results.outcome_counts == {"completed": 1}, report.terminal_reason
    assert report.planner_decisions and all(
        record.status == "valid" for record in report.planner_decisions
    )
    assert all(record.seed == 42 for record in report.planner_decisions)
    assert all(record.input_tokens <= 2800 for record in report.planner_decisions)
    assert sum(step.inference_seconds for step in report.trajectories) > 0
    if persona == "impatient_mobile":
        assert any(
            step.action.kind == "scroll" and step.result == "progress"
            for step in report.trajectories
        )
    assert (
        all(step.action.kind != "click" for step in report.trajectories)
        if persona == "keyboard_low_vision"
        else True
    )
    memory = json.loads(
        (directory / "evidence" / "planner-memory.json").read_text(encoding="utf-8")
    )
    assert len(memory) <= 24
    serialized = json.dumps(memory)
    assert (
        not re.search(r"\b[\w.+-]+@fixture\.invalid\b", serialized)
        and "xpath" not in serialized
        and "state_digest" not in serialized
    )
    assert memory[0]["recent_actions"] == []
    assert not any(
        key in state for state in memory for key in ("dom", "cookies", "network", "screenshots")
    )
    summary_path = ROOT / "artifacts" / "phase3" / f"healthy-{persona}.json"
    summary_path.write_text(
        json.dumps(
            {
                "run_id": str(report.run_id),
                "persona": persona,
                "journey": journey,
                "seed": 42,
                "report": str(directory / "report.html"),
                "decisions": len(report.planner_decisions),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


class FaultModel(Model):
    """Deterministic negative harness, never used for healthy model acceptance."""

    case = "invalid_output"

    def __init__(self, runtime, memory, limits, seed, writer):
        super().__init__(model_id="negative-harness")
        self.memory = memory
        self.records = []
        self.last_fault = None
        self.stopped = threading.Event()
        self.deadline = time.monotonic() + limits.max_runtime_seconds

    def generate(self, messages, **kwargs):
        if self.case in {"runtime", "cancel"}:
            time.sleep(1.5)
        if self.case != "step_limit":
            self.last_fault = PlannerStopped(
                "runtime_limit" if self.stopped.is_set() else "invalid_model_output",
                "Negative harness rejected model output; no UX abandonment.",
            )
            raise self.last_fault
        action = Action(
            kind="wait", observation_id=self.memory.state["observation_id"], timeout_ms=1
        )
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Negative ceiling probe",
            tool_calls=[
                ChatMessageToolCall(
                    id=str(action.id),
                    type="function",
                    function=ChatMessageToolCallFunction(
                        name="browser_action", arguments={"action": action.model_dump(mode="json")}
                    ),
                )
            ],
        )


@pytest.mark.parametrize(
    "case,expected",
    [
        ("invalid_output", "invalid_model_output"),
        ("step_limit", "step_limit"),
        ("runtime", "runtime_limit"),
    ],
)
def test_agent_failure_limits_export_without_abandonment(resolved, case, expected):
    class Harness(FaultModel):
        pass

    Harness.case = case
    broker = asyncio.run(
        run_persona(
            resolved,
            persona_id="enterprise_evaluator",
            model_factory=Harness,
            limits=AgentLimits(max_steps=1, max_runtime_seconds=1 if case == "runtime" else 30),
        )
    )
    report = terminal_review(broker)
    assert report.scope.runtime_metadata["planner_stop_category"] == expected
    assert report.execution_status == "failed"
    assert "completed" not in report.cohort_results.outcome_counts
    assert len(broker.steps) == (1 if case == "step_limit" else 0)


def test_cancellation_stops_model_worker_and_exports(resolved):
    async def run():
        class Harness(FaultModel):
            case = "cancel"

        task = asyncio.create_task(
            run_persona(resolved, model_factory=Harness, persona_id="enterprise_evaluator")
        )
        # Wait for the owned browser startup and in-flight model decision, not a hardcoded blind delay.
        directory = ROOT / "artifacts" / "phase3" / "runs"
        existing = set(directory.glob("*/evidence/planner-memory.json"))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            fresh = set(directory.glob("*/evidence/planner-memory.json")) - existing
            if fresh:
                break
            await asyncio.sleep(0.05)
        assert fresh
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        report_file = next(iter(fresh)).parents[1] / "report.json"
        report = json.loads(report_file.read_text(encoding="utf-8"))
        assert report["execution_status"] == "cancelled"
        assert report["scope"]["runtime_metadata"]["planner_worker_drained"]
        assert (
            report["protection"]["sentinel_requests"] == 0
            and report["protection"]["sentinel_data_unchanged"]
        )
        assert not report["abandonment_explanations"]

    asyncio.run(run())


def test_code_mode_blocked_before_browser_or_model(resolved):
    broker = asyncio.run(run_persona(resolved, mode="isolated_code"))
    report = terminal_review(broker)
    assert report.execution_status == "blocked" and not broker.started_navigation
    assert not report.planner_decisions and report.protection.target_requests == 0
    assert report.scope.runtime_metadata["planner_stop_category"] == "code_isolation_unavailable"


def test_missing_resources_export_factual_phase3_report(resolved, monkeypatch):
    def reject(self):
        raise PlannerStopped("model_setup", "Pinned local model is missing.")

    monkeypatch.setattr(
        "frictionlab.planning.local_model.LocalModelRuntime.check_resources", reject
    )
    broker = asyncio.run(run_persona(resolved))
    report = terminal_review(broker)
    assert report.execution_status == "failed" and report.cohort_results.executed_sessions == 0
    assert report.scope.runtime_metadata["planner_stop_category"] == "model_setup"
    assert "missing" in report.terminal_reason
