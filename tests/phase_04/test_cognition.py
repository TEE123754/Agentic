import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from frictionlab.cognition.runtime import CognitivePolicy, CognitiveRuntime, load_policy
from frictionlab.configuration import CONFIG_DIRECTORY
from frictionlab.contracts.models import (
    Action,
    Candidate,
    EvidenceRef,
    PatienceEntry,
    Persona,
    RunReport,
    StepResult,
)
from frictionlab.reporting import unexecuted_report


class Writer:
    def __init__(self):
        self.saved = {}

    def json(self, name, value):
        self.saved[name] = value


def persona(name="impatient_mobile"):
    return Persona.model_validate_json(
        (CONFIG_DIRECTORY / "personas" / f"{name}.json").read_text(encoding="utf-8")
    )


def observation(signature="product", *, name="Start checkout", validation=(), focus=None, text=""):
    identity = uuid4()
    return SimpleNamespace(
        id=identity,
        semantic_signature=signature,
        semantic_text=text,
        validation=validation,
        focus=focus or {"name": "", "id": "", "tag": "body"},
        candidates=(
            Candidate(
                candidate_id=1,
                observation_id=identity,
                target_id="owned-page",
                role="button",
                name=name,
                visible=True,
                enabled=True,
                bounds=(10, 10, 100, 30),
            ),
        ),
        evidence=(EvidenceRef(path=f"evidence/{identity}.png", kind="screenshot"),),
    )


def step(
    before,
    after,
    *,
    kind="click",
    result="no_change",
    key=None,
    candidate=1,
    app=4.1,
    inference=0.7,
):
    arguments = {"kind": kind, "observation_id": before.id}
    if kind == "click":
        arguments["candidate_id"] = candidate
    if kind == "type_text":
        arguments.update(candidate_id=candidate, text_reference="synthetic_email")
    if kind == "press_key":
        arguments["key"] = key
    if kind == "wait":
        arguments["timeout_ms"] = 100
    action = Action(**arguments)
    return StepResult(
        action_id=action.id,
        action=action,
        observation_before=before.id,
        observation_after=after.id,
        result=result,
        application_seconds=app,
        inference_seconds=inference,
        evidence=after.evidence,
    )


def cognitive(name="impatient_mobile"):
    writer = Writer()
    return CognitiveRuntime(persona(name), uuid4(), writer), writer


def test_dead_interaction_exhausts_mobile_patience_and_links_terminal_evidence():
    runtime, writer = cognitive()
    before, after = observation(), observation()
    action = step(before, after)
    entry = runtime.ingest(action, before, after, {"review": False})
    assert entry.kind == "penalty" and (entry.before, entry.delta, entry.after) == (55, -55, 0)
    assert runtime.abandoned and len(runtime.events) == 1
    event = runtime.events[0]
    assert event.action_id == action.action_id and event.confidence >= 0.9
    diagnosis = runtime.diagnosis(after)
    assert diagnosis.first_person.startswith("I tried 'Start checkout'")
    assert diagnosis.event_ids == (event.id,) and diagnosis.terminal_observation_id == after.id
    assert writer.saved["cognitive-state.json"]["remaining"] == 0
    assert writer.saved["friction-events.json"][0]["evidence"]
    with pytest.raises(RuntimeError, match="already stopped"):
        runtime.ingest(action, before, after, {"review": False})


def test_duplicate_planner_retry_is_excluded_and_progress_credit_is_once():
    runtime, _ = cognitive("enterprise_evaluator")
    before, after = observation(), observation()
    first = runtime.ingest(step(before, after), before, after, {"review": False})
    second = runtime.ingest(step(before, after), before, after, {"review": False})
    assert (first.before, first.after) == (90, 50)
    assert second.kind == "excluded" and second.after == 50 and len(runtime.events) == 1
    progress = runtime.ingest(
        step(before, after, kind="wait", result="progress"),
        before,
        after,
        {"review": True},
    )
    assert progress.kind == "progress_credit" and progress.after == 54
    repeated = runtime.ingest(
        step(before, after, kind="wait", result="progress"),
        before,
        after,
        {"review": True},
    )
    assert repeated.after == 54 and repeated.delta == 0


def test_zero_profile_weight_records_evidence_without_a_penalty():
    configured = persona().model_copy(
        update={"friction_weights": persona().friction_weights | {"dead_interaction": 0.0}}
    )
    runtime = CognitiveRuntime(configured, uuid4(), Writer())
    before, after = observation(), observation()
    entry = runtime.ingest(step(before, after), before, after, {"review": False})
    assert entry.kind == "unchanged" and entry.delta == 0 and entry.after == 55
    assert runtime.events[0].patience_delta == 0 and not runtime.abandoned


def test_generic_validation_and_actual_correction_receive_distinct_evidence():
    runtime, _ = cognitive()
    before = observation("checkout", name="Continue to order review")
    invalid = observation(
        "checkout-validation", name="Continue to order review", validation=("Invalid input",)
    )
    first = runtime.ingest(
        step(before, invalid, result="validation_error"),
        before,
        invalid,
        {"review": False},
    )
    assert first.delta == -28 and runtime.events[-1].detector == "unclear_validation"
    typed = observation("corrected", name="Continue to order review")
    runtime.ingest(
        step(invalid, typed, kind="type_text", result="progress"),
        invalid,
        typed,
        {"review": False},
    )
    invalid_again = observation(
        "corrected-validation", name="Continue to order review", validation=("Invalid input",)
    )
    second = runtime.ingest(
        step(typed, invalid_again, result="validation_error"),
        typed,
        invalid_again,
        {"review": False},
    )
    assert second.delta == -24 and runtime.events[-1].detector == "repeated_failed_correction"
    assert second.after == 3


def test_navigation_loop_and_loading_failure_require_observed_state():
    loop, _ = cognitive("enterprise_evaluator")
    a = observation("A")
    b = observation("B")
    back = observation("A")
    loop.ingest(step(a, b, result="progress"), a, b, {"review": False})
    loop.ingest(step(b, back, result="progress"), b, back, {"review": False})
    assert [e.detector for e in loop.events] == ["navigation_loop"]
    loading, _ = cognitive()
    waiting = observation("loading", text="Checking synthetic details...")
    same = observation("loading", text="Checking synthetic details...")
    loading.ingest(step(waiting, same, kind="wait"), waiting, same, {"review": False})
    assert loading.events[-1].detector == "loading_failure"
    delayed, _ = cognitive()
    done = observation("review", text="Order review")
    delayed.ingest(
        step(waiting, done, kind="wait", result="progress"),
        waiting,
        done,
        {"review": True},
    )
    assert not delayed.events and delayed.remaining == 59


def test_opening_and_closing_information_dialog_is_not_ux_navigation_loop():
    runtime, _ = cognitive()
    page = observation("product", name="Read delivery policy")
    dialog = observation("delivery-dialog", name="Close delivery policy")
    for _ in range(3):
        runtime.ingest(
            step(page, dialog, result="progress"),
            page,
            dialog,
            {"review": False},
            dialog_open=True,
        )
        runtime.ingest(
            step(dialog, page, result="progress"),
            dialog,
            page,
            {"review": False},
            dialog_open=False,
        )
    assert not runtime.events and runtime.remaining == 55


def test_keyboard_trap_requires_repeated_stall_in_visible_dialog():
    runtime, _ = cognitive("keyboard_low_vision")
    focus = {"name": "Delivery details", "id": "delivery-dialog", "tag": "dialog"}
    before = observation("dialog", focus=focus)
    after = observation("dialog", focus=focus)
    for _ in range(2):
        runtime.ingest(
            step(before, after, kind="press_key", key="Tab"),
            before,
            after,
            {"review": False},
            dialog_open=True,
        )
    assert len(runtime.events) == 1 and runtime.events[0].detector == "keyboard_trap"
    assert runtime.remaining == 11
    runtime.ingest(
        step(before, after, kind="press_key", key="Escape"),
        before,
        after,
        {"review": False},
        dialog_open=False,
    )
    assert runtime.remaining == 11


@pytest.mark.parametrize("result", ["blocked", "agent_error"])
def test_protection_and_agent_errors_do_not_charge_patience(result):
    runtime, _ = cognitive()
    before, after = observation(), observation()
    entry = runtime.ingest(step(before, after, result=result), before, after, {"review": False})
    assert entry.kind == "excluded" and entry.delta == 0 and runtime.remaining == 55
    assert not runtime.events and runtime.diagnosis(after) is None


def test_explanation_failure_uses_validated_evidence_template():
    runtime, _ = cognitive()
    before, after = observation(), observation()
    runtime.ingest(step(before, after), before, after, {"review": False})

    def broken(_):
        raise TimeoutError("Optional generator failed")

    diagnosis = runtime.diagnosis(after, explainer=broken)
    assert diagnosis and diagnosis.method == "deterministic_evidence_template"
    assert diagnosis.first_person.startswith("I ") and diagnosis.event_ids


def test_abandonment_diagnosis_keeps_full_observed_event_chain():
    runtime, _ = cognitive()
    before = observation("checkout", name="Continue to order review")
    invalid = observation("invalid", name="Continue to order review", validation=("Invalid input",))
    runtime.ingest(
        step(before, invalid, result="validation_error"),
        before,
        invalid,
        {"review": False},
    )
    dead_before = observation("product", name="Start checkout")
    dead_after = observation("product", name="Start checkout")
    runtime.ingest(step(dead_before, dead_after), dead_before, dead_after, {"review": False})
    diagnosis = runtime.diagnosis(dead_after)
    assert runtime.abandoned and len(runtime.events) == 2
    assert diagnosis.event_ids == tuple(event.id for event in runtime.events)


def test_policy_and_ledger_contracts_reject_unsupported_arithmetic():
    policy, digest = load_policy()
    assert policy.version == 1 and len(digest) == 64
    payload = json.loads((CONFIG_DIRECTORY / "cognition.json").read_text(encoding="utf-8"))
    payload["base_penalties"].pop("dead_interaction")
    with pytest.raises(ValueError, match="six known detectors"):
        CognitivePolicy.model_validate(payload)
    with pytest.raises(ValueError, match="delta"):
        PatienceEntry(
            action_id=uuid4(),
            before=10,
            after=9,
            delta=0,
            kind="unchanged",
            reason="Mismatch",
            application_seconds=0,
            inference_seconds=0,
        )


def test_report_rejects_unbacked_abandonment_diagnosis():
    template = unexecuted_report("Offline contract check").model_dump(mode="json")
    template["scope"]["phase"] = 4
    template["cohort_results"].update(
        requested_sessions=1,
        executed_sessions=1,
        eligible_sessions=1,
        outcome_counts={"abandoned_patience": 1},
    )
    template["abandonment_diagnosis"] = {
        "first_person": "I stopped.",
        "event_ids": [str(uuid4())],
        "terminal_observation_id": str(uuid4()),
        "evidence": [{"path": "evidence/terminal.png", "kind": "screenshot"}],
    }
    with pytest.raises(ValueError, match="recorded friction events"):
        RunReport.model_validate(template)
