"""Frozen owned-fixture quality measures; no human-churn inference."""

from __future__ import annotations

import json
from pathlib import Path

from frictionlab.audit.service import latest_report_path
from frictionlab.contracts.models import RunReport, SessionOutcome


def evaluate_fixture_cases(root: Path, store, cases: list[dict]):
    """Score predeclared healthy/defect labels, keeping failures outside churn counts."""
    root = Path(root).resolve()
    rows = []
    for case in cases:
        run_id = case["run_id"]
        path = latest_report_path(root, store, run_id)
        if path is None:
            raise ValueError(f"Missing audited fixture report: {run_id}")
        report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
        missing = []
        refs = 0
        for finding in report.findings:
            for ref in finding.evidence:
                refs += 1
                asset = (path.parent / ref.path).resolve()
                if not asset.is_relative_to(path.parent.resolve()) or not asset.is_file():
                    missing.append(ref.path)
        if case["label"] not in {"healthy", "seeded_blocker"}:
            raise ValueError("Unrecognized frozen fixture label")
        outcome = report.cohort_results.outcome_counts
        rows.append(
            {
                "run_id": run_id,
                "label": case["label"],
                "variant": case["variant"],
                "order": case["order"],
                "requested": report.cohort_results.requested_sessions,
                "eligible": report.cohort_results.eligible_sessions,
                "completed": outcome.get(SessionOutcome.COMPLETED, 0),
                "abandoned_patience": outcome.get(SessionOutcome.ABANDONED_PATIENCE, 0),
                "inconclusive": report.cohort_results.executed_sessions
                - report.cohort_results.eligible_sessions,
                "high_findings": sum(
                    item.severity in {"high", "critical"} for item in report.findings
                ),
                "finding_count": len(report.findings),
                "evidence_references": refs,
                "missing_references": missing,
                "report_ready": str(report.report_status) == "ready",
                "sentinel_requests": report.protection.sentinel_requests,
                "sentinel_data_unchanged": report.protection.sentinel_data_unchanged,
            }
        )
    healthy = [item for item in rows if item["label"] == "healthy"]
    defective = [item for item in rows if item["label"] == "seeded_blocker"]
    healthy_eligible = sum(item["eligible"] for item in healthy)
    high_total = sum(item["high_findings"] for item in rows)
    high_true = sum(item["high_findings"] for item in defective)
    ref_total = sum(item["evidence_references"] for item in rows)
    valid_refs = ref_total - sum(len(item["missing_references"]) for item in rows)
    metrics = {
        "healthy_completion": sum(item["completed"] for item in healthy) / healthy_eligible
        if healthy_eligible
        else None,
        "high_severity_precision": high_true / high_total if high_total else None,
        "seeded_blocker_detection": sum(bool(item["finding_count"]) for item in defective)
        / len(defective)
        if defective
        else None,
        "finding_reference_validity": valid_refs / ref_total if ref_total else None,
        "inconclusive_sessions": sum(item["inconclusive"] for item in rows),
        "report_completeness": sum(item["report_ready"] for item in rows),
        "reports": len(rows),
        "zero_live_sentinel_traffic": all(
            item["sentinel_requests"] == 0 and item["sentinel_data_unchanged"] is True
            for item in rows
        ),
    }
    return {
        "method": "Frozen owned-fixture labels with a deterministic semantic-control planner; not model or human-behavior calibration.",
        "cases": rows,
        "metrics": metrics,
        "targets": {
            "healthy_completion": 0.8,
            "high_severity_precision": 0.9,
            "seeded_blocker_detection": 0.8,
            "finding_reference_validity": 1.0,
        },
        "limitations": [
            "Two fixture variants and one synthetic journey are a narrow sample.",
            "A no-impact claim here is limited to the owned fixture/browser/proxy and observed sentinel.",
            "Mind2Web offline action prediction is reported separately from fixture outcomes.",
        ],
    }


def save_quality_report(path: Path, result: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    metrics = result["metrics"]
    lines = [
        "# Phase 8 frozen fixture quality",
        "",
        result["method"],
        "",
        "| Measure | Result | Target |",
        "|---|---:|---:|",
    ]
    for name, target in result["targets"].items():
        value = metrics[name]
        lines.append(
            f"| {name.replace('_', ' ')} | {value:.1%} | {target:.0%} |"
            if value is not None
            else f"| {name.replace('_', ' ')} | not measured | {target:.0%} |"
        )
    lines.extend(
        [
            "",
            f"Reports: {metrics['reports']}; inconclusive sessions: {metrics['inconclusive_sessions']}; ready reports: {metrics['report_completeness']}.",
            f"Observed zero sentinel traffic and unchanged sentinel data: {metrics['zero_live_sentinel_traffic']}.",
            "",
            "These synthetic results are not human conversion or churn rates.",
            "",
        ]
    )
    path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
