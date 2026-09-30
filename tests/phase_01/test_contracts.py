from uuid import uuid4

import pytest
from pydantic import ValidationError

from frictionlab.configuration import resolve_run
from frictionlab.contracts.models import (
    Action,
    Candidate,
    CohortResults,
    EvidenceRef,
    Finding,
    Journey,
    Observation,
    RunReport,
)
from frictionlab.reporting import blocked_report


def test_browser_candidates_cannot_cross_observation_or_target():
    observation_id = uuid4()
    candidate = Candidate(
        candidate_id=1,
        observation_id=observation_id,
        target_id="target-one",
        role="button",
        name="Continue",
        visible=True,
        enabled=True,
        bounds=(0, 0, 100, 40),
    )
    kwargs = {
        "id": observation_id,
        "target_id": "target-one",
        "viewport": {"width": 390, "height": 844},
        "route": "/",
        "semantic_text": "Continue",
        "candidates": [candidate],
    }
    assert Observation(**kwargs).candidates[0].candidate_id == 1
    for change in (
        {"id": uuid4()},
        {"target_id": "target-two"},
        {"candidates": [candidate, candidate]},
    ):
        with pytest.raises(ValidationError):
            Observation(**(kwargs | change))


@pytest.mark.parametrize(
    "arguments",
    [
        {"kind": "click"},
        {"kind": "click", "candidate_id": 1, "key": "Enter"},
        {"kind": "type_text", "candidate_id": 1, "text": "secret"},
        {"kind": "wait", "timeout_ms": 10001},
        {"kind": "press_key", "key": "Control+W"},
    ],
)
def test_action_arguments_are_bounded_and_no_raw_credentials(arguments):
    with pytest.raises(ValidationError):
        Action(observation_id=uuid4(), **arguments)


def test_synthetic_text_reference_and_completion_action():
    action = Action(
        kind="type_text", observation_id=uuid4(), candidate_id=1, text_reference="synthetic_email"
    )
    assert action.text_reference == "synthetic_email"
    assert Action(kind="finish", observation_id=uuid4()).kind == "finish"


@pytest.mark.parametrize("path", ["../secret.png", "C:/secret.png", "/secret.png", "a\\secret.png"])
def test_evidence_cannot_escape_bundle(path):
    with pytest.raises(ValidationError):
        EvidenceRef(path=path, kind="screenshot")


@pytest.mark.parametrize(
    "path", ["//production.example.invalid", "/\\production.example.invalid", "/\n//production"]
)
def test_browser_normalization_cannot_escape_relative_journey(payload, path):
    document = resolve_run(payload).journeys[0].model_dump()
    document["start_path"] = path
    with pytest.raises(ValidationError):
        Journey.model_validate(document)


def test_outcome_denominators_and_evidence_are_required():
    with pytest.raises(ValidationError):
        CohortResults(
            requested_sessions=2,
            executed_sessions=1,
            eligible_sessions=1,
            outcome_counts={"completed": 2},
        )
    with pytest.raises(ValidationError):
        CohortResults(requested_sessions=1, executed_sessions=0, eligible_sessions=1)
    kwargs = {
        "title": "Dead interaction",
        "severity": "high",
        "observed_behavior": "No response",
        "inferred_mechanism": "Missing handler",
        "confidence": 0.7,
        "affected_sessions": 2,
        "eligible_sessions": 1,
        "evidence": [{"path": "events.json", "kind": "event"}],
        "recommendation": "Connect the button",
        "verification": "Check response",
    }
    with pytest.raises(ValidationError):
        Finding(**kwargs)
    with pytest.raises(ValidationError):
        Finding(**(kwargs | {"affected_sessions": 1, "evidence": []}))


def test_report_cannot_be_ready_without_evidence_review():
    report = blocked_report("Execution unavailable").model_dump(mode="json")
    report["report_status"] = "ready"
    with pytest.raises(ValidationError, match="ready report"):
        RunReport.model_validate(report)


def test_review_cannot_reference_nonexistent_findings():
    report = blocked_report("Execution unavailable").model_dump(mode="json")
    report["review"]["dispositions"] = [
        {"finding_id": str(uuid4()), "status": "confirmed", "note": "Review"},
    ]
    with pytest.raises(ValidationError, match="dispositions"):
        RunReport.model_validate(report)
