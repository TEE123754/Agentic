import asyncio
import json
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

from frictionlab.browser.broker import BrowserBroker
from frictionlab.cognition.runtime import CognitiveRuntime
from frictionlab.configuration import ROOT
from frictionlab.contracts.models import Action, RunReport
from frictionlab.planning.contracts import PlannerStopped, load_limits
from frictionlab.planning.memory import PersonaMemory
from frictionlab.planning.runner import autonomous_cli, run_persona


class SemanticHarness(Model):
    """Deterministic observed-control policy for the Phase 4 boundary, not local Qwen."""

    def __init__(self, runtime, memory, limits, seed, writer):
        super().__init__(model_id="phase4-semantic-acceptance-harness")
        self.memory = memory
        self.seed = seed
        self.writer = writer
        self.records = []
        self.last_fault = None
        self.stopped = threading.Event()
        self.deadline = time.monotonic() + limits.max_runtime_seconds

    def generate(self, messages, **kwargs):
        state = self.memory.state
        controls = state["candidates"]
        start = next((c for c in controls if c["name"] == "Start checkout"), None)
        textbox = next((c for c in controls if c["role"] == "textbox"), None)
        continue_button = next(
            (c for c in controls if c["name"] == "Continue to order review"), None
        )
        typed = any(
            item["kind"] == "type_text" and item["text_reference"] == "synthetic_email"
            for item in state["recent_actions"]
        )
        fields = {"observation_id": state["observation_id"]}
        if textbox and not typed:
            fields.update(
                kind="type_text", candidate_id=textbox["id"], text_reference="synthetic_email"
            )
        elif continue_button:
            fields.update(kind="click", candidate_id=continue_button["id"])
        elif start:
            fields.update(kind="click", candidate_id=start["id"])
        else:
            fields.update(kind="scroll", direction="down", amount=400)
        action = Action(**fields)
        return self.emit(action)

    def emit(self, action):
        state = self.memory.state
        record = {
            "attempt": len(self.records) + 1,
            "seed": self.seed,
            "observation_id": state["observation_id"],
            "status": "valid",
            "inference_seconds": 0.001,
            "decision": {
                "action": action.model_dump(mode="json"),
                "rationale": "Observed control policy",
            },
        }
        self.records.append(record)
        self.writer.json("planner-decisions.json", self.records)
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Observed control policy",
            tool_calls=[
                ChatMessageToolCall(
                    id=str(action.id),
                    type="function",
                    function=ChatMessageToolCallFunction(
                        name="browser_action",
                        arguments={"action": action.model_dump(mode="json")},
                    ),
                )
            ],
        )


class FaultHarness(SemanticHarness):
    category = "model_timeout"

    def generate(self, messages, **kwargs):
        self.last_fault = PlannerStopped(
            self.category,
            "Negative model fault; no website or synthetic churn attribution.",
        )
        raise self.last_fault


def review(broker):
    report = broker.report
    assert broker.closed and not broker.cleanup_errors
    assert report.scope.phase == 4 and report.report_status == "partial"
    assert report.protection.network_boundary_validated
    assert report.protection.sentinel_requests == 0 and report.protection.sentinel_data_unchanged
    assert report.scope.runtime_metadata["generated_python_executed"] is False
    assert report.scope.runtime_metadata["vision_enabled"] is False
    assert all((broker.directory / item.path).is_file() for item in report.visual_evidence)
    for suffix in ("json", "md", "html"):
        assert (broker.directory / f"report.{suffix}").is_file()
    html = (broker.directory / "report.html").read_text(encoding="utf-8")
    assert "Patience ledger and abandonment diagnosis" in html and "<script" not in html
    assert not broker.profile or not Path(broker.profile.name).exists()
    assert broker.runtime.task is broker.runtime.proxy is broker.runtime.sentinel is None
    assert broker.runtime.app.state.fixture.snapshot(broker.run_id)["account_count"] == 0
    return report


def test_matched_dead_checkout_abandons_and_healthy_completes(resolved):
    dead = asyncio.run(
        run_persona(
            resolved,
            persona_id="impatient_mobile",
            journey_id="checkout_review",
            variant="dead_button",
            behavioral=True,
            model_factory=SemanticHarness,
        )
    )
    dead_report = review(dead)
    assert dead_report.execution_status == "completed"
    assert dead_report.cohort_results.outcome_counts == {"abandoned_patience": 1}
    assert dead_report.cohort_results.eligible_sessions == 1
    assert len(dead_report.friction_events) == 1
    assert dead_report.friction_events[0].detector == "dead_interaction"
    assert dead_report.patience_ledger[-1].after == 0
    diagnosis = dead_report.abandonment_diagnosis
    assert diagnosis and diagnosis.first_person in dead_report.abandonment_explanations
    assert diagnosis.terminal_observation_id == dead.current.id
    assert all((dead.directory / ref.path).is_file() for ref in diagnosis.evidence)
    assert not any(dead.completion.values())

    healthy = asyncio.run(
        run_persona(
            resolved,
            persona_id="impatient_mobile",
            journey_id="checkout_review",
            variant="healthy",
            behavioral=True,
            model_factory=SemanticHarness,
        )
    )
    healthy_report = review(healthy)
    assert healthy_report.cohort_results.outcome_counts == {"completed": 1}
    assert all(healthy.completion.values())
    assert not healthy_report.friction_events and not healthy_report.abandonment_diagnosis
    assert not healthy_report.abandonment_explanations
    assert healthy_report.patience_ledger[-1].after >= 55
    assert dead_report.scope.seed == healthy_report.scope.seed == 42
    assert dead_report.scope.build_id == healthy_report.scope.build_id


def test_delayed_application_success_is_not_charged_as_model_or_loading_failure(resolved):
    broker = asyncio.run(
        run_persona(
            resolved,
            persona_id="impatient_mobile",
            journey_id="checkout_review",
            variant="delayed_feedback",
            behavioral=True,
            model_factory=SemanticHarness,
        )
    )
    report = review(broker)
    assert report.cohort_results.outcome_counts == {"completed": 1}
    assert not report.friction_events and not report.abandonment_diagnosis
    assert any(step.application_seconds >= 2.5 for step in report.trajectories)
    assert sum(step.inference_seconds for step in report.trajectories) > 0
    assert all(
        entry.behavioral_delay_seconds == entry.queue_seconds == 0
        for entry in report.patience_ledger
    )


@pytest.mark.parametrize("category", ["model_timeout", "invalid_model_output"])
def test_model_fault_has_partial_report_and_no_abandonment(resolved, category):
    class Harness(FaultHarness):
        pass

    Harness.category = category
    broker = asyncio.run(
        run_persona(
            resolved,
            persona_id="impatient_mobile",
            behavioral=True,
            model_factory=Harness,
        )
    )
    report = review(broker)
    assert report.scope.runtime_metadata["planner_stop_category"] == category
    assert report.execution_status == "failed"
    assert report.cohort_results.eligible_sessions == 0
    assert report.cohort_results.outcome_counts == {"inconclusive_agent_failure": 1}
    assert not report.friction_events and not report.abandonment_diagnosis
    assert not report.abandonment_explanations


def test_generated_code_guard_fails_before_model_browser_or_patience(resolved):
    broker = asyncio.run(run_persona(resolved, behavioral=True, mode="isolated_code"))
    report = broker.report
    assert report.scope.phase == 4 and report.execution_status == "blocked"
    assert report.cohort_results.executed_sessions == 0
    assert not report.friction_events and not report.patience_ledger
    assert report.protection.target_requests == 0
    assert report.scope.runtime_metadata["generated_python_executed"] is False


def test_fixture_control_click_is_blocked_without_ux_penalty(resolved):
    async def scenario():
        async with BrowserBroker(
            resolved,
            persona_id="impatient_mobile",
            artifact_root=ROOT / "artifacts" / "phase4" / "protection-probes",
        ) as broker:
            # Fixture controls are deliberately absent from the grounded candidates.
            assert not any(item.name == "Reset this test run" for item in broker.current.candidates)
            before = broker.current
            cognitive = CognitiveRuntime(broker.persona, broker.run_id, broker.writer)
            blocked = await broker.act(
                Action(kind="click", observation_id=before.id, candidate_id=999)
            )
            assert blocked.result == "blocked"
            entry = cognitive.ingest(blocked, before, broker.current, {"review_heading": False})
            assert entry.kind == "excluded" and entry.after == 55
            assert not cognitive.events and not cognitive.abandoned
        assert broker.report.protection.sentinel_requests == 0
        assert broker.report.protection.sentinel_data_unchanged

    asyncio.run(scenario())


def test_information_only_dialog_is_read_once_in_behavioral_memory(resolved):
    async def scenario():
        async with BrowserBroker(
            resolved,
            persona_id="impatient_mobile",
            artifact_root=ROOT / "artifacts" / "phase4" / "information-probes",
        ) as broker:
            broker.cognitive_runtime = CognitiveRuntime(
                broker.persona, broker.run_id, broker.writer
            )
            memory = PersonaMemory(broker, load_limits())
            await memory.refresh()
            for _ in range(5):
                if any(
                    item["name"] == "Read delivery policy" for item in memory.state["candidates"]
                ):
                    break
                await broker.act(
                    Action(
                        kind="scroll",
                        observation_id=broker.current.id,
                        direction="down",
                        amount=200,
                    )
                )
                await memory.refresh()
            selected = next(
                item
                for item in memory.state["candidates"]
                if item["name"] == "Read delivery policy"
            )
            before = broker.current
            opened = Action(
                kind="click",
                observation_id=before.id,
                candidate_id=selected["id"],
            )
            assert (await broker.act(opened)).result == "progress"
            assert await broker.page.get_by_role("dialog").count() == 1
            assert (
                await broker.page.get_by_role("dialog").locator("input, select, textarea").count()
                == 0
            )
            memory.remember_interaction(before, broker.current, opened, informational_dialog=True)
            await memory.refresh()
            close = next(
                item
                for item in memory.state["candidates"]
                if item["name"] == "Close delivery policy"
            )
            await broker.act(
                Action(
                    kind="click",
                    observation_id=broker.current.id,
                    candidate_id=close["id"],
                )
            )
            state = await memory.refresh()
            assert "Read delivery policy" in state["information_controls_already_read"]
            assert not any(item["name"] == "Read delivery policy" for item in state["candidates"])
            assert any("Returns are accepted" in text for text in state["known_information"])
        assert broker.report.protection.sentinel_requests == 0
        assert broker.report.protection.sentinel_data_unchanged

    asyncio.run(scenario())


def test_behavioral_cli_configuration_rejection_exports_without_execution(monkeypatch, capsys):
    from frictionlab.planning import runner

    def must_not_run(*args, **kwargs):
        raise AssertionError("Rejected settings must stop before browser/model")

    from frictionlab.configuration import ConfigurationRejected

    monkeypatch.setattr(
        runner,
        "resolve_run",
        lambda *args: (_ for _ in ()).throw(ConfigurationRejected(["Invalid configuration"])),
    )
    monkeypatch.setattr(runner, "run_persona", must_not_run)
    assert (
        asyncio.run(
            autonomous_cli(
                "impatient_mobile", "checkout_review", "healthy", "typed_tools", behavioral=True
            )
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    report = RunReport.model_validate_json(
        (Path(payload["report_directory"]) / "report.json").read_text(encoding="utf-8")
    )
    assert report.scope.phase == 4 and report.execution_status == "blocked"
    assert report.cohort_results.executed_sessions == 0 and not report.friction_events
