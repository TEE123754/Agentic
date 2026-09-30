"""Offline review of one Phase 3 CodeAgent fixture run and its saved reports."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from frictionlab.configuration import ROOT
from frictionlab.contracts.models import RunReport
from frictionlab.planning.worker_gate import REQUIRED_CHECKS

OUTPUT = ROOT / "artifacts" / "phase3"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    findings = []
    gate_path = OUTPUT / "worker-boundary-gate.json"
    expected_image = os.environ.get("FRICTIONLAB_CODE_IMAGE_ID", "")
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.is_file() else None
    if gate is None:
        findings.append("The real-container boundary gate did not produce a passing record.")
    elif (
        gate.get("status") != "passed"
        or set(gate.get("passed_checks", [])) != REQUIRED_CHECKS
        or gate.get("image_id") != expected_image
    ):
        findings.append("The boundary record is incomplete or for a different image.")

    reports = sorted((OUTPUT / "runs").glob("*/report.json"), key=lambda path: path.stat().st_mtime)
    report = None
    report_dir = reports[-1].parent if reports else None
    if report_dir is None:
        findings.append("No terminal CodeAgent report exists. The workflow stopped before that step.")
    else:
        try:
            report = RunReport.model_validate_json(
                (report_dir / "report.json").read_text(encoding="utf-8")
            )
        except Exception as exc:  # noqa: BLE001 -- preserve malformed report diagnosis
            findings.append(f"Terminal report failed schema validation: {type(exc).__name__}: {exc}")

    if report is not None:
        metadata = report.scope.runtime_metadata
        required_metadata = {
            "execution_mode": "isolated_code",
            "generated_python_executed": True,
            "code_worker_started": True,
            "code_worker_image_id": expected_image,
            "planner_worker_drained": True,
        }
        for key, expected in required_metadata.items():
            if metadata.get(key) != expected:
                findings.append(f"{key} was {metadata.get(key)!r}; expected {expected!r}.")
        if report.execution_status != "completed":
            findings.append(f"Journey did not complete: {report.execution_status}: {report.terminal_reason}")
        if not report.planner_decisions or not report.trajectories:
            findings.append("Model decisions or browser trajectories are missing.")
        if report.protection.sentinel_requests != 0 or not report.protection.sentinel_data_unchanged:
            findings.append("Owned live-service sentinel was contacted or changed.")
        if "Owned fixture, proxy, and sentinel stopped" not in report.protection.cleanup_outcome:
            findings.append(f"Cleanup result needs review: {report.protection.cleanup_outcome}")
        if report.report_status not in {"ready", "partial"}:
            findings.append(f"Report finalization status is {report.report_status}.")
        if not report.recommendations or not report.review.method:
            findings.append("Detailed recommendations or review section are missing.")
        for name in ("report.json", "report.md", "report.html"):
            if not (report_dir / name).is_file():
                findings.append(f"Missing {name} export.")
        if report.scope.personas != ("enterprise_evaluator",) or report.scope.journeys != (
            "delivery_information",
        ):
            findings.append("The report describes a different persona or journey.")

    review = {
        "reviewed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if not findings else "failed",
        "scope": "one synthetic enterprise evaluator on bundled healthy fixture",
        "browser_reopened_for_review": False,
        "external_website_requests": 0,
        "worker_image_id": expected_image,
        "gate": str(gate_path.relative_to(ROOT)) if gate else None,
        "report": str((report_dir / "report.html").relative_to(ROOT)) if report_dir else None,
        "execution_status": str(report.execution_status) if report else None,
        "report_status": str(report.report_status) if report else None,
        "planner_decisions": len(report.planner_decisions) if report else 0,
        "browser_steps": len(report.trajectories) if report else 0,
        "sentinel_requests": report.protection.sentinel_requests if report else None,
        "findings": findings,
    }
    (OUTPUT / "code-journey-review.json").write_text(
        json.dumps(review, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Phase 3 CodeAgent fixture review",
        "",
        f"Status: **{review['status']}**. Browser and website were not reopened for review.",
        "",
        f"Worker image: `{expected_image or 'unavailable'}`.",
        f"Terminal report: `{review['report'] or 'unavailable'}`.",
        f"Execution: `{review['execution_status']}`; report: `{review['report_status']}`.",
        f"Decisions: {review['planner_decisions']}; browser steps: {review['browser_steps']}.",
        f"Sentinel requests: {review['sentinel_requests']}.",
        "",
        "## Review findings",
        "",
        *(f"- {item}" for item in findings),
    ]
    if not findings:
        lines.append("- No gate or report inconsistency found in saved evidence.")
    (OUTPUT / "code-journey-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(review, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
