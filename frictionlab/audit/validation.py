"""Validate saved session evidence without opening a browser or target URL."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from frictionlab.browser.evidence import BrowserObservation
from frictionlab.cognition.runtime import DETECTORS
from frictionlab.contracts.models import AuditExclusion, FrictionEvent, RunReport, StepResult

ELIGIBLE_OUTCOMES = {"completed", "abandoned_patience"}
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024


@dataclass
class SessionEvidence:
    row: dict
    report: RunReport
    directory: Path
    input_mode: str
    eligible: bool
    observations: dict[str, BrowserObservation] = field(default_factory=dict)

    @property
    def session_id(self):
        return str(self.report.run_id)

    def file(self, relative: str):
        path = (self.directory / relative).resolve()
        if not path.is_relative_to(self.directory.resolve()) or not path.is_file():
            raise ValueError("Evidence reference is missing or outside its session directory")
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise ValueError("Evidence reference exceeds the offline review size ceiling")
        return path

    def observation(self, identifier):
        key = str(identifier)
        if key not in self.observations:
            path = self.file(f"evidence/{key}.observation.json")
            observation = BrowserObservation.model_validate_json(path.read_text(encoding="utf-8"))
            if str(observation.id) != key:
                raise ValueError("Saved observation ID does not match the trajectory")
            self.observations[key] = observation
        return self.observations[key]


@dataclass(frozen=True)
class VerifiedEvent:
    session: SessionEvidence
    event: FrictionEvent
    step: StepResult
    before: BrowserObservation
    after: BrowserObservation
    target_name: str
    target_role: str


def _relative_report_path(root: Path, run_id: str, row: dict):
    session_id = row["session_id"]
    expected = root / "runs" / run_id / "sessions" / session_id
    actual = (root / (row["report_path"] or "")).resolve()
    if actual != (expected / "report.html").resolve() or not actual.is_file():
        raise ValueError("Session report path is missing or outside its owned directory")
    return expected


def load_session(root: Path, run_id: str, row: dict, manifest: dict):
    directory = _relative_report_path(root, run_id, row)
    report_path = directory / "report.json"
    if not report_path.is_file() or report_path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise ValueError("Session JSON report is missing or oversized")
    report = RunReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    if str(report.run_id) != row["session_id"]:
        raise ValueError("Session report ID does not match the durable session row")
    if report.scope.build_id != manifest["environment"]["build_id"]:
        raise ValueError("Session build does not match the run manifest")
    if row["status"] != str(report.execution_status):
        raise ValueError("Session execution status does not match the durable row")
    # A global health stop may intentionally override a navigated outcome.
    if (
        row["outcome"]
        and row["outcome"] not in report.cohort_results.outcome_counts
        and row["outcome"] != "inconclusive_agent_failure"
    ):
        raise ValueError("Session outcome does not match the durable row")
    profile = manifest["profiles"][row["persona_id"]]
    session = SessionEvidence(
        row=row,
        report=report,
        directory=directory,
        input_mode=profile["device"]["input_mode"],
        eligible=(row["outcome"] in ELIGIBLE_OUTCOMES),
    )
    for ref in report.visual_evidence:
        session.file(ref.path)
    for step in report.trajectories:
        for ref in step.evidence:
            session.file(ref.path)
        session.observation(step.observation_before)
        if step.observation_after:
            session.observation(step.observation_after)
    for event in report.friction_events:
        for ref in event.evidence:
            session.file(ref.path)
    if report.abandonment_diagnosis:
        for ref in report.abandonment_diagnosis.evidence:
            session.file(ref.path)
        session.observation(report.abandonment_diagnosis.terminal_observation_id)
    if session.eligible and (
        report.protection.network_boundary_validated is not True
        or report.protection.sentinel_requests != 0
        or report.protection.sentinel_data_unchanged is not True
        or not report.trajectories
    ):
        raise ValueError("Eligible session lacks verified protection or browser trajectory")
    return session


def validate_event(session: SessionEvidence, event: FrictionEvent):
    if not session.eligible:
        raise ValueError("Only eligible application sessions can support UX findings")
    if str(event.session_id) != session.session_id or event.detector not in DETECTORS:
        raise ValueError("Friction event has an unsupported detector or session")
    steps = {str(step.action_id): step for step in session.report.trajectories}
    step = steps.get(str(event.action_id))
    if step is None or step.action is None or step.result in {"blocked", "agent_error"}:
        raise ValueError("Friction event is not linked to an eligible browser action")
    if (
        event.observation_before != step.observation_before
        or event.observation_after != step.observation_after
    ):
        raise ValueError("Friction event observation IDs do not match its action")
    before = session.observation(step.observation_before)
    after = session.observation(step.observation_after)
    if not {ref.path for ref in event.evidence} <= {ref.path for ref in after.evidence}:
        raise ValueError("Friction evidence was not captured in the after-observation")
    expected = {
        "dead_interaction": ({"click"}, {"no_change"}),
        "unclear_validation": ({"click", "press_key"}, {"validation_error"}),
        "repeated_failed_correction": ({"click", "press_key"}, {"validation_error"}),
        "navigation_loop": ({"click", "press_key"}, {"progress"}),
        "loading_failure": ({"wait"}, {"no_change"}),
        "keyboard_trap": ({"press_key"}, {"no_change"}),
    }[event.detector]
    if step.action.kind not in expected[0] or step.result not in expected[1]:
        raise ValueError("Detector claim conflicts with the browser action result")
    target_name = ""
    target_role = ""
    if step.action.candidate_id is not None:
        candidate = next(
            (item for item in before.candidates if item.candidate_id == step.action.candidate_id),
            None,
        )
        if candidate is None:
            raise ValueError("Friction target is absent from the saved candidate list")
        target_name, target_role = candidate.name, candidate.role
    elif step.action.kind == "press_key":
        target_name, target_role = before.focus.get("name", ""), before.focus.get("role", "")
    if event.target_name != target_name:
        raise ValueError("Friction target name differs from the saved browser observation")
    if (
        event.detector == "dead_interaction"
        and before.semantic_signature != after.semantic_signature
    ):
        raise ValueError("A dead-click claim conflicts with visible state change")
    if event.detector == "loading_failure" and not any(
        word in (before.semantic_text + " " + after.semantic_text).casefold()
        for word in ("loading", "checking", "please wait")
    ):
        raise ValueError("Loading failure has no saved pending-state text")
    if event.detector == "unclear_validation" and not after.validation:
        raise ValueError("Unclear validation has no saved validation message")
    if event.detector == "unclear_validation" and " ".join(after.validation).casefold() not in {
        "invalid input",
        "invalid",
        "error",
        "please check your details",
    }:
        raise ValueError("Validation feedback is not the declared generic message")
    if event.detector == "repeated_failed_correction":
        trajectory = session.report.trajectories
        index = next(i for i, item in enumerate(trajectory) if item.action_id == step.action_id)
        prior_validation = any(item.result == "validation_error" for item in trajectory[:index])
        correction = any(
            item.action and item.action.kind == "type_text" and item.result == "progress"
            for item in trajectory[:index]
        )
        if not prior_validation or not correction:
            raise ValueError("Repeated correction lacks prior rejection and typed correction")
    if event.detector == "navigation_loop":
        if before.semantic_signature == after.semantic_signature:
            raise ValueError("Navigation loop has no intervening page-state change")
        trajectory = session.report.trajectories
        index = next(i for i, item in enumerate(trajectory) if item.action_id == step.action_id)
        prior = {
            session.observation(item.observation_before).semantic_signature
            for item in trajectory[:index]
        }
        if after.semantic_signature not in prior:
            raise ValueError("Navigation loop does not return to a prior saved state")
    if event.detector == "keyboard_trap" and (
        before.focus != after.focus or before.semantic_signature != after.semantic_signature
    ):
        raise ValueError("Keyboard trap claim conflicts with saved focus or page state")
    return VerifiedEvent(session, event, step, before, after, target_name, target_role)


def excluded(kind: str, reason: str, *, session_id=None, event_id=None):
    return AuditExclusion(
        kind=kind,
        reason=reason,
        session_id=UUID(str(session_id)) if session_id else None,
        event_id=UUID(str(event_id)) if event_id else None,
    )
