"""Classify observed interface friction and maintain a bounded synthetic patience ledger."""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from pathlib import Path
from uuid import UUID

from pydantic import Field, model_validator

from frictionlab.browser.state import redact
from frictionlab.configuration import CONFIG_DIRECTORY
from frictionlab.contracts.models import (
    AbandonmentDiagnosis,
    Contract,
    FrictionEvent,
    PatienceEntry,
)

DETECTORS = {
    "dead_interaction",
    "unclear_validation",
    "repeated_failed_correction",
    "navigation_loop",
    "loading_failure",
    "keyboard_trap",
}
EXCLUDED_CONTROLS = {"reset", "switch-variant", "variant"}


class CognitivePolicy(Contract):
    version: int = Field(ge=1, le=1, strict=True)
    base_penalties: dict[str, int]
    progress_credit: int = Field(ge=0, le=10, strict=True)
    max_total_progress_credit: int = Field(ge=0, le=30, strict=True)
    minimum_confidence: float = Field(ge=0.5, le=1, allow_inf_nan=False)
    keyboard_trap_repetitions: int = Field(ge=2, le=4, strict=True)

    @model_validator(mode="after")
    def complete_detectors(self):
        if set(self.base_penalties) != DETECTORS or any(
            not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100
            for value in self.base_penalties.values()
        ):
            raise ValueError("Cognitive penalty settings must cover the six known detectors")
        return self


def load_policy(path: Path | None = None) -> tuple[CognitivePolicy, str]:
    source = path or CONFIG_DIRECTORY / "cognition.json"
    raw = source.read_bytes()
    if len(raw) > 16 * 1024:
        raise ValueError("Cognitive policy exceeds its size limit")
    return CognitivePolicy.model_validate_json(raw), hashlib.sha256(raw).hexdigest()


class CognitiveRuntime:
    """Only broker-confirmed actions can change synthetic patience."""

    def __init__(self, persona, session_id: UUID, writer, policy=None, policy_sha256=None):
        if policy is None:
            policy, policy_sha256 = load_policy()
        self.policy = policy
        self.policy_sha256 = (
            policy_sha256
            or hashlib.sha256(
                json.dumps(policy.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest()
        )
        self.persona = persona
        self.session_id = session_id
        self.writer = writer
        self.initial = persona.behavior.patience_initial
        self.remaining = self.initial
        self.events: list[FrictionEvent] = []
        self.ledger: list[PatienceEntry] = []
        self.credited_milestones: set[str] = set()
        self.total_credit = 0
        self.seen_friction: set[tuple[str, str, str]] = set()
        self.signatures: deque[str] = deque(maxlen=6)
        self.validation_failures: dict[str, int] = {}
        self.corrections: set[str] = set()
        self.keyboard_stalls: dict[tuple[str, str], int] = {}
        self.dialog_active = False
        self.abandoned = False
        self.last_event: FrictionEvent | None = None

    def _target(self, step, before):
        action = step.action
        if action is None:
            return ""
        if action.kind == "press_key":
            return redact(before.focus.get("name", ""))[:120]
        return next(
            (
                redact(candidate.name)[:120]
                for candidate in before.candidates
                if candidate.candidate_id == action.candidate_id
            ),
            "",
        )

    def _classify(self, step, before, after, target, *, dialog_open):
        action = step.action
        if action is None or after is None:
            return None
        if step.result in {"blocked", "agent_error"}:
            return None
        if action.kind == "type_text" and step.result == "progress":
            self.corrections.add("Continue to order review")
        clicked = next((candidate for candidate in before.candidates
                        if candidate.candidate_id == action.candidate_id), None)
        if (action.kind == "click" and step.result == "no_change" and target
                and clicked is not None and clicked.role not in {"textbox", "searchbox"}):
            return (
                "dead_interaction",
                0.94,
                f"The observed {target!r} control produced no visible change within the bounded feedback window.",
            )
        if action.kind in {"click", "press_key"} and step.result == "validation_error":
            feedback = " ".join(after.validation)[:180]
            if target:
                attempts = self.validation_failures.get(target, 0)
                corrected = target in self.corrections
                self.validation_failures[target] = attempts + 1
                self.corrections.discard(target)
                if attempts and corrected:
                    return (
                        "repeated_failed_correction",
                        0.88,
                        f"The form still rejected the observed correction with {feedback!r}.",
                    )
            if feedback.casefold() in {
                "invalid input",
                "invalid",
                "error",
                "please check your details",
            }:
                return (
                    "unclear_validation",
                    0.98,
                    f"The visible validation message {feedback!r} did not identify a correction.",
                )
        if (
            action.kind == "press_key"
            and action.key in {"Tab", "Shift+Tab", "Escape"}
            and dialog_open
            and before.focus == after.focus
            and before.semantic_signature == after.semantic_signature
        ):
            key = (before.semantic_signature, target)
            self.keyboard_stalls[key] = self.keyboard_stalls.get(key, 0) + 1
            if self.keyboard_stalls[key] >= self.policy.keyboard_trap_repetitions:
                return (
                    "keyboard_trap",
                    0.91,
                    f"Repeated {action.key} left the same visible dialog and focus unchanged.",
                )
        if action.kind == "wait" and step.result == "no_change":
            text = (before.semantic_text + " " + after.semantic_text).casefold()
            if any(word in text for word in ("loading", "checking", "please wait")):
                return (
                    "loading_failure",
                    0.78,
                    "The page still showed a pending state after a bounded wait without visible progress.",
                )
        if (
            step.result == "progress"
            and action.kind in {"click", "press_key"}
            and not dialog_open
            and not self.dialog_active
            and before.semantic_signature != after.semantic_signature
            and after.semantic_signature in self.signatures
        ):
            return (
                "navigation_loop",
                0.8,
                "A previously observed page state returned after a different state was reached.",
            )
        return None

    def ingest(self, step, before, after, milestones, *, dialog_open=False):
        """Record one broker-confirmed action; never charge for model or policy failures."""
        if self.abandoned:
            raise RuntimeError("Cognitive session has already stopped")
        if step.action is None or step.observation_before != before.id:
            raise ValueError("Cognitive input must match a grounded broker action")
        if after is not None and step.observation_after != after.id:
            raise ValueError("Cognitive result must match the captured after-observation")
        current = self.remaining
        target = self._target(step, before)
        excluded = step.result in {"blocked", "agent_error"} or (
            before.focus.get("id") in EXCLUDED_CONTROLS and step.action.kind == "press_key"
        )
        detected = (
            None
            if excluded
            else self._classify(step, before, after, target, dialog_open=dialog_open)
        )
        self.dialog_active = dialog_open
        event = None
        reason = "No supported interface friction was observed."
        kind = "unchanged"
        if excluded:
            kind = "excluded"
            reason = "Protection block or agent/tool failure is excluded from synthetic patience."
        elif detected and after is not None and after.evidence:
            detector, confidence, observed = detected
            identity = (detector, before.semantic_signature, target)
            if identity in self.seen_friction:
                kind = "excluded"
                reason = "Repeated planner attempt on the same state; no duplicate UX penalty."
            elif confidence >= self.policy.minimum_confidence:
                self.seen_friction.add(identity)
                weight = self.persona.friction_weights.get(detector, 1.0)
                charge = min(100, math.ceil(self.policy.base_penalties[detector] * weight))
                self.remaining = max(0, self.remaining - charge)
                event = FrictionEvent(
                    detector=detector,
                    session_id=self.session_id,
                    action_id=step.action_id,
                    confidence=confidence,
                    patience_delta=self.remaining - current,
                    evidence=after.evidence,
                    observation_before=before.id,
                    observation_after=after.id,
                    target_name=target,
                    observed_behavior=observed,
                )
                self.events.append(event)
                self.last_event = event
                kind = "penalty" if self.remaining < current else "unchanged"
                reason = (
                    f"Observed {detector}; profile weight {weight:g}."
                    if kind == "penalty"
                    else f"Observed {detector}; profile weight is zero, so no patience was charged."
                )
        newly_verified = {
            key for key, value in milestones.items() if value
        } - self.credited_milestones
        self.credited_milestones.update(newly_verified)
        if (
            kind == "unchanged"
            and newly_verified
            and self.total_credit < self.policy.max_total_progress_credit
        ):
            credit = min(
                self.policy.progress_credit * len(newly_verified),
                self.policy.max_total_progress_credit - self.total_credit,
                100 - self.remaining,
            )
            if credit:
                self.remaining += credit
                self.total_credit += credit
                kind = "progress_credit"
                reason = "Independent journey milestone verified: " + ", ".join(
                    sorted(newly_verified)
                )
        if before.semantic_signature != (after.semantic_signature if after else None):
            self.signatures.append(before.semantic_signature)
        entry = PatienceEntry(
            action_id=step.action_id,
            before=current,
            after=self.remaining,
            delta=self.remaining - current,
            kind=kind,
            event_ids=(event.id,) if event else (),
            reason=reason,
            application_seconds=step.application_seconds,
            inference_seconds=step.inference_seconds,
        )
        self.ledger.append(entry)
        self.abandoned = bool(event and self.remaining == 0 and not all(milestones.values()))
        self.writer.json("friction-events.json", [e.model_dump(mode="json") for e in self.events])
        self.writer.json("patience-ledger.json", [e.model_dump(mode="json") for e in self.ledger])
        self.writer.json(
            "cognitive-state.json",
            {
                "policy_version": self.policy.version,
                "policy_sha256": self.policy_sha256,
                "initial": self.initial,
                "remaining": self.remaining,
                "abandoned": self.abandoned,
                "credited_milestones": sorted(self.credited_milestones),
            },
        )
        return entry

    def diagnosis(self, terminal_observation, *, explainer=None):
        if not self.abandoned or self.last_event is None or terminal_observation is None:
            return None
        event = self.last_event
        if event.detector == "dead_interaction":
            reason = f"I tried {event.target_name!r}, but nothing visible changed."
        elif event.detector == "unclear_validation":
            reason = "I received a validation message that did not tell me what to fix."
        elif event.detector == "keyboard_trap":
            reason = "I could not move focus out of the visible dialog with the keyboard."
        elif event.detector == "loading_failure":
            reason = (
                "I waited while the page still showed a pending state without visible progress."
            )
        elif event.detector == "navigation_loop":
            reason = "I returned to an earlier page state instead of advancing."
        else:
            reason = "I corrected the form, but the observed rejection continued."
        fallback = (
            reason
            + " I stopped this synthetic journey after the recorded interaction exhausted my patience."
        )
        # An optional generator may suggest wording, but unsupported text is never trusted.
        try:
            proposed = explainer(event) if explainer else None
        except Exception:  # noqa: BLE001 -- deterministic fallback is always available
            proposed = None
        if proposed != fallback:
            proposed = fallback
        refs = terminal_observation.evidence or event.evidence
        return AbandonmentDiagnosis(
            first_person=proposed,
            event_ids=tuple(item.id for item in self.events),
            terminal_observation_id=terminal_observation.id,
            evidence=refs,
        )
