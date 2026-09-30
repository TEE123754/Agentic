"""Deterministic, offline cohort audit from validated session evidence."""

from __future__ import annotations

import base64
import hashlib
import html
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

from frictionlab.audit.validation import (
    SessionEvidence,
    VerifiedEvent,
    excluded,
    load_session,
    validate_event,
)
from frictionlab.contracts.models import (
    EvidenceRef,
    Finding,
    HeatmapGroup,
    HeatmapPoint,
    MilestoneFunnel,
    ReviewDisposition,
    RunReport,
    TrajectoryEntry,
)

POLICY_VERSION = 1
EXPECTED_REPEATED_CONTROLS = {
    "next",
    "previous",
    "increase",
    "decrease",
    "load more",
    "add item",
    "remove item",
}
REMEDIATION = {
    "dead_interaction": (
        "Make the observed control produce immediate visible feedback, a clear disabled state, or a recoverable error.",
        "Repeat the same synthetic journey and verify that activating the control changes the saved visible state or gives an actionable error within the bounded feedback window.",
    ),
    "unclear_validation": (
        "Name the invalid field and the correction in visible, accessible validation text.",
        "Submit the same invalid synthetic value and verify that the field-specific correction appears in both the screenshot and accessibility snapshot.",
    ),
    "repeated_failed_correction": (
        "Preserve the corrected input and make a second rejection identify the remaining requirement.",
        "Enter the documented synthetic correction and verify that the next result either advances or clearly names the unresolved requirement.",
    ),
    "navigation_loop": (
        "Make the next-step control retain progress or explain why the journey returns to an earlier state.",
        "Repeat the same action sequence and verify that a previously visited page state is not revisited without a clear explanation.",
    ),
    "loading_failure": (
        "Give the pending operation a bounded completion, retry, or actionable failure state.",
        "Repeat the bounded wait and verify that the pending state resolves or presents a recoverable error.",
    ),
    "keyboard_trap": (
        "Restore a predictable keyboard focus path and a working dialog escape action.",
        "Navigate the dialog with Tab, Shift+Tab, and Escape and verify the saved focus and dialog state change as expected.",
    ),
}
TITLES = {
    "dead_interaction": "Control gives no visible response",
    "unclear_validation": "Validation does not explain the correction",
    "repeated_failed_correction": "Corrected input is rejected again",
    "navigation_loop": "Journey returns to an earlier state",
    "loading_failure": "Pending state does not resolve",
    "keyboard_trap": "Keyboard focus remains trapped",
}


@dataclass(frozen=True)
class AuditProduct:
    report: RunReport
    assets: dict[str, bytes]
    verified_event_ids: frozenset[str]


def context_key(build_id, observation, input_mode):
    viewport = observation.viewport
    return (
        build_id,
        observation.route,
        observation.semantic_signature,
        viewport.width,
        viewport.height,
        input_mode,
    )


def _key_id(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


class AuditEngine:
    def __init__(self, root: Path, run_id: str):
        self.root = Path(root).resolve()
        self.run_id = str(UUID(str(run_id)))
        self.manifest = json.loads(
            (self.root / "runs" / self.run_id / "manifest.json").read_text(encoding="utf-8")
        )
        self.assets: dict[str, bytes] = {}
        self.exclusions = []

    def build(self, base: RunReport, rows: list[dict]):
        if str(base.run_id) != self.run_id:
            raise ValueError("Audit base report ID differs from the cohort manifest")
        sessions: list[SessionEvidence] = []
        verified: list[VerifiedEvent] = []
        contexts: dict[tuple, set[str]] = defaultdict(set)
        for row in rows:
            try:
                session = load_session(self.root, self.run_id, row, self.manifest)
            except Exception as exc:  # noqa: BLE001 -- unsupported evidence is excluded
                self.exclusions.append(
                    excluded(
                        "session",
                        f"Session evidence rejected: {type(exc).__name__}: {exc}",
                        session_id=row["session_id"],
                    )
                )
                continue
            sessions.append(session)
            if not session.eligible:
                self.exclusions.append(
                    excluded(
                        "session",
                        f"Outcome {row['outcome'] or row['status']} is outside the UX denominator.",
                        session_id=session.session_id,
                    )
                )
                continue
            build = self.manifest["environment"]["build_id"]
            for observation in session.observations.values():
                contexts[context_key(build, observation, session.input_mode)].add(
                    session.session_id
                )
            for event in session.report.friction_events:
                try:
                    verified.append(validate_event(session, event))
                except Exception as exc:  # noqa: BLE001 -- do not publish unsupported claims
                    self.exclusions.append(
                        excluded(
                            "event",
                            f"Friction event rejected: {type(exc).__name__}: {exc}",
                            session_id=session.session_id,
                            event_id=event.id,
                        )
                    )
        findings = self._findings(verified, contexts)
        heatmaps, heatmap_refs = self._heatmaps(sessions)
        funnel = self._funnel(base, sessions)
        trajectory_index = self._trajectory_index(sessions)
        known_events = {str(item.event.id) for item in verified}
        explanations = []
        for session in sessions:
            diagnosis = session.report.abandonment_diagnosis
            if not session.eligible or diagnosis is None:
                continue
            if not {str(item) for item in diagnosis.event_ids} <= known_events:
                self.exclusions.append(
                    excluded(
                        "event",
                        "Abandonment diagnosis references an unverified friction event.",
                        session_id=session.session_id,
                    )
                )
            else:
                explanations.append(diagnosis.first_person)
        incomplete = (
            base.execution_status != "completed"
            or any(item.kind in {"session", "event"} for item in self.exclusions)
            or not any(session.eligible for session in sessions)
        )
        missing = []
        if base.execution_status != "completed":
            missing.append("Run did not complete; some browser journeys are unavailable.")
        if self.exclusions:
            missing.append(f"{len(self.exclusions)} session/event exclusions require review.")
        if not any(session.eligible for session in sessions):
            missing.append("No protected, executed session is eligible for UX synthesis.")
        data = base.model_dump(mode="json")
        data["revision"] = 2
        data["created_at"] = datetime.now(UTC).isoformat()
        data["scope"]["phase"] = 6
        data["scope"]["runtime_metadata"].update(
            {
                "audit_policy_version": POLICY_VERSION,
                "verified_friction_events": len(verified),
                "excluded_evidence_items": len(self.exclusions),
                "heatmap_groups": len(heatmaps),
                "model_generated_findings": False,
            }
        )
        data["report_status"] = "partial" if incomplete else "ready"
        data["executive_summary"] = (
            f"{base.cohort_results.executed_sessions}/{base.cohort_results.requested_sessions} "
            f"synthetic sessions navigated the owned fixture; "
            f"{base.cohort_results.eligible_sessions} were eligible for UX synthesis. "
            f"{len(findings)} evidence-supported finding(s), {len(heatmaps)} compatible "
            f"heatmap group(s), and {len(self.exclusions)} exclusion(s) were recorded. "
            "These are synthetic observations, not measured human churn or business impact."
        )
        data["findings"] = [item.model_dump(mode="json") for item in findings]
        data["heatmaps"] = [item.model_dump(mode="json") for item in heatmaps]
        data["exclusions"] = [item.model_dump(mode="json") for item in self.exclusions]
        data["milestone_funnel"] = [item.model_dump(mode="json") for item in funnel]
        data["trajectory_index"] = [item.model_dump(mode="json") for item in trajectory_index]
        data["visual_evidence"] = [item.model_dump(mode="json") for item in heatmap_refs]
        data["abandonment_explanations"] = explanations
        data["recommendations"] = [item.recommendation for item in findings] or [
            "No supported cohort friction finding was established; inspect session reports and exclusions before changing the interface."
        ]
        data["review"].update(
            status="evidence_reviewed",
            method="Deterministic offline validation of saved reports, actions, observations, screenshots, protection, and journal outcomes; no target revisit or model synthesis.",
            missing_evidence=missing,
            limitations=[
                "Only the bundled fixture and synthetic personas were evaluated.",
                "Detector confidence and synthetic reproduction rates are not human behavior estimates.",
                "Remediation names interface behavior, not unobserved source files or business impact.",
            ],
            dispositions=[
                ReviewDisposition(
                    finding_id=item.id,
                    status="requires_investigation",
                    note="Automated evidence review passed; human confirmation remains optional.",
                ).model_dump(mode="json")
                for item in findings
            ],
        )
        report = RunReport.model_validate(data)
        self._validate_output(report, known_events, sessions)
        return AuditProduct(report, self.assets, frozenset(known_events))

    def _copy_evidence(self, session: SessionEvidence, ref):
        source = session.file(ref.path)
        destination = f"evidence/{session.session_id}-{source.name}"
        self.assets[destination] = source.read_bytes()
        return EvidenceRef(path=destination, kind=ref.kind)

    def _findings(self, events: list[VerifiedEvent], contexts: dict[tuple, set[str]]):
        groups: dict[tuple, list[VerifiedEvent]] = defaultdict(list)
        for item in events:
            context = context_key(
                self.manifest["environment"]["build_id"], item.before, item.session.input_mode
            )
            groups[(*context, item.event.detector, item.target_role, item.target_name)].append(item)
        findings = []
        for key, items in sorted(groups.items(), key=lambda pair: str(pair[0])):
            context = key[:6]
            affected = sorted({item.session.session_id for item in items})
            eligible = sorted(contexts[context])
            if not affected or not set(affected) <= set(eligible):
                continue
            detector, target = key[6], key[8]
            rate = len(affected) / len(eligible)
            confidence = min(item.event.confidence for item in items)
            abandoned = any(item.session.row["outcome"] == "abandoned_patience" for item in items)
            impact = (
                3
                if abandoned
                else 2
                if detector in {"keyboard_trap", "loading_failure", "repeated_failed_correction"}
                else 1
            )
            score = impact * rate * confidence
            severity = "high" if score >= 2 else "medium" if score >= 0.75 else "low"
            evidence = []
            for item in items[:2]:
                selected = [
                    ref
                    for ref in item.event.evidence
                    if ref.path.endswith((".png", ".observation.json", ".aria.txt"))
                ]
                evidence.extend(self._copy_evidence(item.session, ref) for ref in selected[:3])
            unique_refs = list(dict.fromkeys(ref.path for ref in evidence))
            evidence = [next(ref for ref in evidence if ref.path == path) for path in unique_refs]
            if not evidence:
                continue
            observed = _observed_fact(detector, target, items[0])
            rationale = (
                f"Synthetic impact tier {impact}; {len(affected)}/{len(eligible)} eligible "
                f"sessions reproduced the observed event; minimum detector confidence {confidence:.2f}."
            )
            group_id = _key_id(key)
            findings.append(
                Finding(
                    id=uuid5(UUID(self.run_id), f"finding:{group_id}"),
                    title=(TITLES[detector] + (f": {target}" if target else ""))[:160],
                    severity=severity,
                    observed_behavior=observed,
                    inferred_mechanism=_inferred_mechanism(detector),
                    confidence=confidence,
                    affected_sessions=len(affected),
                    eligible_sessions=len(eligible),
                    evidence=tuple(evidence),
                    recommendation=REMEDIATION[detector][0],
                    verification=REMEDIATION[detector][1],
                    detector=detector,
                    route=key[1],
                    page_state_signature=key[2],
                    target_name=target,
                    viewport={"width": key[3], "height": key[4]},
                    input_mode=key[5],
                    affected_session_ids=tuple(UUID(item) for item in affected),
                    eligible_session_ids=tuple(UUID(item) for item in eligible),
                    event_ids=tuple(item.event.id for item in items),
                    affected_profiles=tuple(
                        sorted({item.session.row["persona_id"] for item in items})
                    ),
                    reproduction_rate=rate,
                    severity_rationale=rationale,
                    confidence_basis="Minimum confidence of validated deterministic detector events; not calibrated against human outcomes.",
                )
            )
        return sorted(
            findings,
            key=lambda item: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3}[item.severity],
                -item.reproduction_rate,
                str(item.id),
            ),
        )

    def _heatmaps(self, sessions: list[SessionEvidence]):
        point_groups: dict[tuple, list[HeatmapPoint]] = defaultdict(list)
        screenshots: dict[tuple, tuple[SessionEvidence, EvidenceRef, int, int]] = {}
        rage_counts: dict[tuple, int] = defaultdict(int)
        for session in sessions:
            if not session.eligible:
                continue
            repeated = _rage_actions(session)
            for step in session.report.trajectories:
                action = step.action
                if (
                    action is None
                    or action.kind != "click"
                    or step.result not in {"progress", "no_change", "validation_error"}
                ):
                    continue
                before = session.observation(step.observation_before)
                candidate = next(
                    (
                        item
                        for item in before.candidates
                        if item.candidate_id == action.candidate_id
                    ),
                    None,
                )
                if candidate is None:
                    self.exclusions.append(
                        excluded(
                            "action",
                            "Click candidate missing from saved observation.",
                            session_id=session.session_id,
                        )
                    )
                    continue
                screenshot = next(
                    (ref for ref in before.evidence if ref.path.endswith(".png")), None
                )
                if screenshot is None:
                    continue
                x, y, width, height = candidate.bounds
                px, py = before.coordinates.css_to_pixel(x + width / 2, y + height / 2)
                if not (
                    0 <= px < before.coordinates.pixel_width
                    and 0 <= py < before.coordinates.pixel_height
                ):
                    self.exclusions.append(
                        excluded(
                            "action",
                            "Click coordinate lies outside the captured viewport.",
                            session_id=session.session_id,
                        )
                    )
                    continue
                key = context_key(
                    self.manifest["environment"]["build_id"], before, session.input_mode
                )
                point_groups[key].append(
                    HeatmapPoint(
                        session_id=UUID(session.session_id),
                        action_id=step.action_id,
                        x=round(px, 2),
                        y=round(py, 2),
                        target_name=candidate.name,
                        result=step.result,
                        rage_cluster=str(step.action_id) in repeated,
                    )
                )
                screenshots.setdefault(
                    key,
                    (
                        session,
                        screenshot,
                        before.coordinates.pixel_width,
                        before.coordinates.pixel_height,
                    ),
                )
            for key, count in repeated.values():
                rage_counts[key] += count
        groups = []
        refs = []
        for key, points in sorted(point_groups.items(), key=lambda pair: str(pair[0])):
            group_id = _key_id(key)
            session, screenshot, pixel_width, pixel_height = screenshots[key]
            screenshot_ref = self._copy_evidence(session, screenshot)
            refs.append(screenshot_ref)
            svg_path = f"heatmaps/{group_id}.svg"
            self.assets[svg_path] = _svg_heatmap(
                pixel_width, pixel_height, self.assets[screenshot_ref.path], points
            )
            self.assets[f"heatmaps/{group_id}.json"] = json.dumps(
                [point.model_dump(mode="json") for point in points], indent=2
            ).encode()
            groups.append(
                HeatmapGroup(
                    id=group_id,
                    build_id=key[0],
                    route=key[1],
                    page_state_signature=key[2],
                    viewport={"width": key[3], "height": key[4]},
                    pixel_width=pixel_width,
                    pixel_height=pixel_height,
                    input_mode=key[5],
                    points=tuple(points),
                    rage_click_clusters=rage_counts[key],
                    svg_path=svg_path,
                )
            )
        return groups, refs

    def _funnel(self, base: RunReport, sessions: list[SessionEvidence]):
        eligible = [session for session in sessions if session.eligible]
        summaries = {str(item.session_id): item for item in base.session_summaries}
        result = []
        for journey_id, journey in self.manifest["journeys"].items():
            same = [session for session in eligible if session.row["journey_id"] == journey_id]
            for criterion in journey["completion"]:
                passed = sum(
                    criterion["id"] in summaries[session.session_id].passed_milestones
                    for session in same
                    if session.session_id in summaries
                )
                result.append(
                    MilestoneFunnel(
                        journey_id=journey_id,
                        milestone=criterion["id"],
                        eligible_sessions=len(same),
                        passed_sessions=passed,
                        pass_rate=passed / len(same) if same else None,
                    )
                )
        return result

    def _trajectory_index(self, sessions: list[SessionEvidence]):
        result = []
        for session in sessions:
            for index, step in enumerate(session.report.trajectories):
                result.append(
                    TrajectoryEntry(
                        session_id=UUID(session.session_id),
                        step_index=index,
                        action_id=step.action_id,
                        action_kind=step.action.kind if step.action else "",
                        result=step.result,
                        detail=step.detail,
                        observation_before=step.observation_before,
                        observation_after=step.observation_after,
                        application_seconds=step.application_seconds,
                        inference_seconds=step.inference_seconds,
                        session_report_path=session.row["report_path"],
                    )
                )
        return result

    def _validate_output(self, report, verified_ids, sessions):
        known_sessions = {session.session_id for session in sessions}
        known_actions = {
            str(step.action_id) for session in sessions for step in session.report.trajectories
        }
        for finding in report.findings:
            if not {str(item) for item in finding.event_ids} <= verified_ids:
                raise ValueError("Published finding references an unverified event")
            if not {str(item) for item in finding.affected_session_ids} <= known_sessions:
                raise ValueError("Published finding references an unknown session")
            for ref in finding.evidence:
                if ref.path not in self.assets:
                    raise ValueError("Published finding references an absent local asset")
        for group in report.heatmaps:
            if group.svg_path not in self.assets:
                raise ValueError("Heatmap SVG is absent")
            for point in group.points:
                if (
                    str(point.session_id) not in known_sessions
                    or str(point.action_id) not in known_actions
                ):
                    raise ValueError("Heatmap point is not backed by a saved browser action")
        for item in report.trajectory_index:
            if (
                str(item.session_id) not in known_sessions
                or str(item.action_id) not in known_actions
            ):
                raise ValueError("Trajectory index contains an unknown action")
        for ref in report.visual_evidence:
            if ref.path not in self.assets:
                raise ValueError("Report visual evidence is absent")


def _rage_actions(session: SessionEvidence):
    steps = session.report.trajectories
    repeated: dict[str, tuple[tuple, int]] = {}
    index = 0
    while index < len(steps):
        step = steps[index]
        action = step.action
        if (
            action is None
            or action.kind != "click"
            or step.result not in {"no_change", "validation_error"}
        ):
            index += 1
            continue
        before = session.observation(step.observation_before)
        candidate = next(
            (item for item in before.candidates if item.candidate_id == action.candidate_id), None
        )
        if candidate is None or candidate.name.casefold().strip() in EXPECTED_REPEATED_CONTROLS:
            index += 1
            continue
        key = context_key(session.report.scope.build_id, before, session.input_mode)
        end = index + 1
        while end < len(steps):
            other = steps[end]
            if (
                other.action is None
                or other.action.kind != "click"
                or other.result not in {"no_change", "validation_error"}
            ):
                break
            observation = session.observation(other.observation_before)
            selected = next(
                (
                    item
                    for item in observation.candidates
                    if item.candidate_id == other.action.candidate_id
                ),
                None,
            )
            if (
                selected is None
                or selected.name != candidate.name
                or context_key(session.report.scope.build_id, observation, session.input_mode)
                != key
            ):
                break
            end += 1
        if end - index >= 3:
            for included in steps[index:end]:
                repeated[str(included.action_id)] = (key, 0)
            repeated[str(step.action_id)] = (key, 1)
        index = end
    return repeated


def _svg_heatmap(width, height, screenshot: bytes, points: list[HeatmapPoint]):
    image_data = base64.b64encode(screenshot).decode()
    circles = []
    for point in points:
        color = "#df1b42" if point.rage_cluster else "#1764d5"
        label = html.escape(f"{point.target_name}: {point.result}")
        circles.append(
            f'<circle cx="{point.x:.2f}" cy="{point.y:.2f}" r="14" '
            f'fill="{color}" fill-opacity="0.5" stroke="white" stroke-width="2">'
            f"<title>{label}</title></circle>"
        )
    document = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><title>Saved synthetic click heatmap</title>'
        f'<image width="{width}" height="{height}" href="data:image/png;base64,{image_data}"/>'
        + "".join(circles)
        + "</svg>"
    )
    return document.encode()


def _observed_fact(detector, target, item: VerifiedEvent):
    control = repr(target) if target else "The observed control"
    if detector == "dead_interaction":
        return f"{control} was activated, and the next saved observation showed no visible change."
    if detector == "unclear_validation":
        return (
            f"{control} produced visible validation feedback: {item.after.validation[0][:180]!r}."
        )
    if detector == "repeated_failed_correction":
        return f"After a correction, {control} produced another saved validation result."
    if detector == "keyboard_trap":
        return "Repeated keyboard navigation left the visible dialog and focus unchanged."
    if detector == "loading_failure":
        return "A bounded wait ended while saved page text still indicated a pending operation."
    return "A previously saved page state returned after a different state was reached."


def _inferred_mechanism(detector):
    return {
        "dead_interaction": "The control may lack feedback or a functioning transition in this fixture state.",
        "unclear_validation": "The validation wording may leave the required correction unclear.",
        "repeated_failed_correction": "The form may not preserve or explain a corrected value.",
        "navigation_loop": "Navigation may return users to an earlier state without explaining why.",
        "loading_failure": "The pending operation may lack a bounded completion or recovery path.",
        "keyboard_trap": "Keyboard focus handling may prevent escape from the observed dialog.",
    }[detector]
