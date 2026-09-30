"""Review saved Phase 4 acceptance records without rerunning a browser or model."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from frictionlab.configuration import ROOT
from frictionlab.contracts.models import RunReport


def main():
    directory = ROOT / "artifacts" / "phase4"
    batches = [
        "validation-initial.xml",
        "validation-repair-1-event-chain.xml",
        "validation-repair-2-boundaries.xml",
        "validation-repair-3-guard.xml",
        "validation-repair-4-dialog-attribution.xml",
        "validation-repair-5-information-memory.xml",
    ]
    checks = {}
    attempts = []
    for name in batches:
        suite = ET.parse(directory / name).getroot()
        selected = suite.findall(".//testcase")
        failures = 0
        for case in selected:
            key = (case.attrib["classname"], case.attrib["name"])
            failed = any(case.find(label) is not None for label in ("failure", "error", "skipped"))
            failures += failed
            checks[key] = not failed
        attempts.append({"file": name, "selected_checks": len(selected), "failed": failures})
    merged = ET.Element("testsuite", name="phase4-latest-distinct", tests=str(len(checks)))
    for (module, name), passed in sorted(checks.items()):
        case = ET.SubElement(merged, "testcase", classname=module, name=name)
        if not passed:
            ET.SubElement(case, "failure", message="Latest selected check failed")
    ET.ElementTree(merged).write(
        directory / "validation.xml", encoding="utf-8", xml_declaration=True
    )
    reports = [
        (path.parent, RunReport.model_validate_json(path.read_text(encoding="utf-8")))
        for path in sorted((directory / "runs").glob("*/report.json"))
    ]
    missing = []
    for folder, report in reports:
        for suffix in ("json", "md", "html"):
            if not (folder / f"report.{suffix}").is_file():
                missing.append(str(folder / f"report.{suffix}"))
        for ref in (
            report.visual_evidence
            + (report.abandonment_diagnosis.evidence if report.abandonment_diagnosis else ())
            + tuple(ref for event in report.friction_events for ref in event.evidence)
        ):
            if not (folder / ref.path).is_file():
                missing.append(str(folder / ref.path))
        event_ids = {event.id for event in report.friction_events}
        if any(not set(entry.event_ids) <= event_ids for entry in report.patience_ledger):
            missing.append(str(folder / "report.json") + " has an unlinked patience event")
        document = (folder / "report.html").read_text(encoding="utf-8")
        if (
            "<script" in document.lower()
            or "Patience ledger and abandonment diagnosis" not in document
        ):
            missing.append(str(folder / "report.html") + " missing offline section/CSP review")
    report_by_id = {folder.name: (folder, report) for folder, report in reports}
    accepted_ids = {
        "dead_button": "4c5b90ab-630d-4444-b8c8-9f44718c56f1",
        "healthy": "7bb91b99-f9a3-46dd-a1e6-fbfe8eb202f8",
        "delayed_feedback": "1a51736c-0f7b-49db-ac01-ae58e59c7002",
    }
    by_variant = {name: report_by_id.get(uid) for name, uid in accepted_ids.items()}
    dead = by_variant.get("dead_button")
    healthy = by_variant.get("healthy")
    delayed = by_variant.get("delayed_feedback")
    healthy_faults = [
        report
        for _, report in reports
        if report.scope.runtime_metadata.get("planner_stop_category")
        in {"model_timeout", "invalid_model_output"}
    ]
    initialized = [report for _, report in reports if report.protection.network_boundary_validated]
    protection_probes = [
        RunReport.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((directory / "protection-probes").glob("*/report.json"))
    ]
    information_probes = [
        RunReport.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((directory / "information-probes").glob("*/report.json"))
    ]
    raw_qwen = report_by_id.get("88d69f16-357d-44bd-8061-cd6b447a32e2")
    repaired_qwen = report_by_id.get("13e8b5a3-e09f-487a-8ee1-c6432d63c4ae")
    qwen_repair = bool(
        raw_qwen
        and repaired_qwen
        and raw_qwen[1].cohort_results.outcome_counts.get("timed_out") == 1
        and not raw_qwen[1].abandonment_diagnosis
        and [event.detector for event in raw_qwen[1].friction_events]
        == ["navigation_loop", "navigation_loop"]
        and repaired_qwen[1].cohort_results.outcome_counts.get("abandoned_patience") == 1
        and [event.detector for event in repaired_qwen[1].friction_events] == ["dead_interaction"]
        and repaired_qwen[1].abandonment_diagnosis is not None
        and repaired_qwen[1].protection.sentinel_requests == 0
        and repaired_qwen[1].protection.sentinel_data_unchanged is True
    )
    zero_protection = all(
        report.protection.sentinel_requests == 0
        and report.protection.sentinel_data_unchanged is True
        for report in initialized
    )
    matched = bool(
        dead
        and healthy
        and dead[1].cohort_results.outcome_counts.get("abandoned_patience") == 1
        and healthy[1].cohort_results.outcome_counts.get("completed") == 1
        and dead[1].scope.seed == healthy[1].scope.seed
        and dead[1].scope.build_id == healthy[1].scope.build_id
        and dead[1].abandonment_diagnosis
        and dead[1].patience_ledger[-1].after == 0
        and not healthy[1].abandonment_diagnosis
    )
    delayed_clean = bool(
        delayed
        and delayed[1].cohort_results.outcome_counts.get("completed") == 1
        and not delayed[1].friction_events
    )
    fault_clean = len(healthy_faults) == 2 and all(
        not report.abandonment_diagnosis
        and not report.abandonment_explanations
        and report.cohort_results.eligible_sessions == 0
        for report in healthy_faults
    )
    gate = (
        len(checks) == 109
        and all(checks.values())
        and len(reports) == 10
        and not missing
        and matched
        and delayed_clean
        and fault_clean
        and zero_protection
        and len(protection_probes) == 1
        and protection_probes[0].protection.sentinel_requests == 0
        and protection_probes[0].protection.sentinel_data_unchanged is True
        and len(information_probes) == 1
        and information_probes[0].protection.sentinel_requests == 0
        and information_probes[0].protection.sentinel_data_unchanged is True
        and qwen_repair
    )
    summary = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "phase": 4,
        "status": "verified_fixture_cognition_gate"
        if gate
        else "incomplete_fixture_cognition_gate",
        "unique_checks": len(checks),
        "unique_checks_passed": sum(checks.values()),
        "unresolved_checks": [
            f"{module}::{name}" for (module, name), passed in checks.items() if not passed
        ],
        "attempts": attempts,
        "matched_dead_abandoned_healthy_completed": matched,
        "delayed_success_without_friction": delayed_clean,
        "model_faults_without_abandonment": fault_clean,
        "real_qwen_defect_repair_verified": qwen_repair,
        "terminal_reports": len(reports),
        "retained_harness_failure_report": "artifacts/phase4/runs/1b6ca486-535d-4a71-a610-e104fc4cc5a5/report.html",
        "retained_contaminated_qwen_report": "artifacts/phase4/runs/88d69f16-357d-44bd-8061-cd6b447a32e2/report.html",
        "reports_with_missing_artifacts": missing,
        "initialized_boundary_reports": len(initialized),
        "targeted_protection_probe_reports": len(protection_probes),
        "information_memory_probe_reports": len(information_probes),
        "sentinel_zero_and_unchanged_all_initialized": zero_protection,
        "report_paths": {
            variant: f"artifacts/phase4/runs/{item[0].name}/report.html"
            for variant, item in by_variant.items()
        },
        "real_qwen_phase4_defect_attempts": 2,
        "real_qwen_phase4_defect_successes_after_repair": int(qwen_repair),
        "real_qwen_repaired_report": "artifacts/phase4/runs/13e8b5a3-e09f-487a-8ee1-c6432d63c4ae/report.html",
        "acceptance_model": "deterministic semantic-control smolagents harness for exact arithmetic; two actual local Qwen defect attempts retained separately",
        "generated_python_executed": False,
        "external_websites_tested": 0,
        "remaining": [
            "Calibrate detector weights and false positives on broader fixtures and human review; one real Qwen success is not a completion rate",
            "Complete Phase 3 OS/container code worker before generated Python or external replicas",
            "Phase 5 cohort orchestration and durable persistence",
            "Phase 6 aggregated findings, recommendations, and heatmaps",
        ],
    }
    (directory / "validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
