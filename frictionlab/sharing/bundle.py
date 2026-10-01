"""Allowlisted static audit bundle from immutable saved evidence."""

from __future__ import annotations

import base64
import json
import re
import struct
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from frictionlab.contracts.models import RunReport

MAX_BUNDLE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGES = 48
URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
CREDENTIAL = re.compile(
    r"(?i)\b(?:authorization|x-api-key|api[_-]?key|secret|password|access[_-]?token|bearer)\b\s*[:= ]\s*(?:Bearer\s+)?[^\s,;<>\"']+"
)
TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|AIza[A-Za-z0-9_-]{20,})\b"
)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def scrub(value):
    """Redact exported text while preserving report structure and counts."""
    if isinstance(value, str):
        value = URL.sub("[redacted URL]", value)
        value = CREDENTIAL.sub("[redacted credential]", value)
        value = TOKEN.sub("[redacted credential]", value)
        return EMAIL.sub("[redacted email]", value)
    if isinstance(value, list | tuple):
        return [scrub(item) for item in value]
    if isinstance(value, dict):
        return {str(key): scrub(item) for key, item in value.items()}
    return value


def _inside(root: Path, relative: str):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Saved evidence path escapes its run root")
    return path


def _latest_report(root: Path, run_id: str):
    base = root / "reports" / run_id
    candidates = sorted(
        (item for item in (base / "revisions").glob("*/report.json") if item.parent.name.isdigit()),
        key=lambda item: int(item.parent.name),
        reverse=True,
    )
    candidates.append(base / "report.json")
    for path in candidates:
        if path.is_file() and path.with_name("report.html").is_file():
            report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
            if str(report.run_id) == run_id:
                return report, path.parent
    raise ValueError("No complete saved report revision is available")


class _Images:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.assets: dict[str, str] = {}
        self._by_path = {}

    def add(self, path: Path):
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Screenshot path escapes saved cohort evidence")
        if path in self._by_path:
            return self._by_path[path]
        if len(self.assets) >= MAX_IMAGES:
            return None
        if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
            return None
        data = path.read_bytes()
        if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        width, height = struct.unpack(">II", data[16:24])
        if not 1 <= width <= 5000 or not 1 <= height <= 5000:
            return None
        identifier = f"image-{len(self.assets) + 1}"
        self.assets[identifier] = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
        self._by_path[path] = identifier
        return identifier


def build_bundle(cohort_root: Path, run_id: str, *, public_fixture=False):
    """Project saved reports into a bounded, private-by-default viewer format."""
    root = Path(cohort_root).resolve()
    run_id = str(UUID(str(run_id)))
    report, report_dir = _latest_report(root, run_id)
    if public_fixture and (
        report.scope.environment_id != "local_storefront"
        or report.scope.build_id != "storefront-phase1-v1"
        or report.protection.boundary_scope != "owned_fixture_browser_proxy"
    ):
        raise ValueError("Public example exports require the verified bundled fixture")
    images = _Images(root)
    findings = []
    for item in report.findings[:100]:
        evidence = []
        for ref in item.evidence:
            if not ref.path.endswith(".png"):
                continue
            image = images.add(_inside(report_dir, ref.path))
            if image:
                evidence.append(image)
        findings.append(
            {
                "id": str(item.id),
                "title": scrub(item.title),
                "severity": item.severity,
                "observed": scrub(item.observed_behavior),
                "mechanism": scrub(item.inferred_mechanism),
                "affected": item.affected_sessions,
                "eligible": item.eligible_sessions,
                "confidence": item.confidence,
                "profiles": scrub(item.affected_profiles),
                "recommendation": scrub(item.recommendation),
                "verification": scrub(item.verification),
                "evidence": evidence,
            }
        )
    sessions = []
    for item in report.session_summaries[:6]:
        path = _inside(root, item.report_path).with_name("report.json")
        steps = []
        diagnosis = None
        if path.is_file():
            session = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
            if session.run_id != item.session_id:
                raise ValueError("Session report identity does not match its summary")
            diagnosis = (
                scrub(session.abandonment_diagnosis.first_person)
                if session.abandonment_diagnosis
                else None
            )
            evidence_dir = path.parent / "evidence"
            patience = {str(entry.action_id): entry.after for entry in session.patience_ledger}
            for step in session.trajectories[:30]:
                observation_id = step.observation_after or step.observation_before
                image = images.add(evidence_dir / f"{observation_id}.png")
                steps.append(
                    {
                        "action": step.action.kind if step.action else "unknown",
                        "result": step.result,
                        "detail": scrub(step.detail),
                        "patience": patience.get(str(step.action_id)),
                        "image": image,
                    }
                )
        sessions.append(
            {
                "id": str(item.session_id),
                "persona": item.persona_id,
                "journey": item.journey_id,
                "outcome": str(item.outcome) if item.outcome else "inconclusive",
                "steps": steps,
                "diagnosis": diagnosis,
            }
        )
    # Synthesis preserves matching heatmap/screenshot order.
    backgrounds = {}
    for group, ref in zip(report.heatmaps, report.visual_evidence, strict=True):
        if ref.path.endswith(".png"):
            backgrounds[group.id] = images.add(_inside(report_dir, ref.path))
    heatmaps = [
        {
            "id": group.id,
            "route": scrub(group.route),
            "input_mode": group.input_mode,
            "width": group.pixel_width,
            "height": group.pixel_height,
            "background": backgrounds.get(group.id),
            "rage_clusters": group.rage_click_clusters,
            "points": [
                {
                    "x": point.x,
                    "y": point.y,
                    "target": scrub(point.target_name),
                    "result": point.result,
                    "rage": point.rage_cluster,
                }
                for point in group.points
            ],
        }
        for group in report.heatmaps[:30]
    ]
    data = {
        "schema_version": 1,
        "manifest": {
            "run_id": run_id,
            "revision": report.revision,
            "exported_at": datetime.now(UTC).isoformat(),
            "visibility": "public_fixture_example" if public_fixture else "private_local",
            "source": "saved, sanitized fixture audit; no live page contact",
            "limits": [
                "Synthetic cohort evidence only",
                "Screenshots are masked at capture; review before publication",
            ],
        },
        "overview": {
            "summary": scrub(report.executive_summary),
            "execution_status": str(report.execution_status),
            "report_status": str(report.report_status),
            "terminal_reason": scrub(report.terminal_reason),
            "requested": report.cohort_results.requested_sessions,
            "executed": report.cohort_results.executed_sessions,
            "eligible": report.cohort_results.eligible_sessions,
            "outcomes": {
                str(key): value for key, value in report.cohort_results.outcome_counts.items()
            },
            "funnel": [
                {
                    "journey": row.journey_id,
                    "milestone": row.milestone,
                    "passed": row.passed_sessions,
                    "eligible": row.eligible_sessions,
                }
                for row in report.milestone_funnel
            ],
            "protection": {
                "boundary": report.protection.boundary_scope,
                "sentinel_requests": report.protection.sentinel_requests,
                "sentinel_data_unchanged": report.protection.sentinel_data_unchanged,
            },
            "review_status": report.review.status,
            "limitations": scrub(report.review.limitations),
            "exclusions": scrub([item.reason for item in report.exclusions]),
        },
        "findings": findings,
        "sessions": sessions,
        "heatmaps": heatmaps,
        "assets": images.assets,
    }
    if len(json.dumps(data, indent=2, ensure_ascii=True).encode("utf-8")) > MAX_BUNDLE_BYTES:
        raise ValueError("Static bundle exceeds the 20 MiB import limit")
    return data


def export_bundle(cohort_root: Path, run_id: str, output: Path, *, public_fixture=False):
    data = build_bundle(cohort_root, run_id, public_fixture=public_fixture)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    encoded = json.dumps(data, indent=2, ensure_ascii=True)
    (output / "bundle.json").write_text(encoded, encoding="utf-8")
    template = (Path(__file__).parent / "viewer.html").read_text(encoding="utf-8")
    embedded = json.dumps(data, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")
    (output / "index.html").write_text(
        template.replace("__FRICTIONLAB_EMBEDDED_JSON__", embedded), encoding="utf-8"
    )
    return output
