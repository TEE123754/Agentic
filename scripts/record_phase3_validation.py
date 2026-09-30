"""Merge saved checks and review retained autonomous outcomes without reopening any website."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime

from frictionlab.configuration import ROOT


def main():
    directory = ROOT / "artifacts" / "phase3"
    latest = {}
    attempts = []
    files = [
        directory / "validation-initial.xml",
        *sorted(directory.glob("validation-repair-*.xml")),
    ]
    for path in files:
        if not path.is_file():
            continue
        root = ET.parse(path).getroot()
        cases = list(root.iter("testcase"))
        failed = sum(
            case.find("failure") is not None or case.find("error") is not None for case in cases
        )
        attempts.append({"file": path.name, "checks": len(cases), "failed": failed})
        for case in cases:
            latest[(case.attrib["classname"], case.attrib["name"])] = case
    unresolved = [
        "::".join(key)
        for key, case in latest.items()
        if case.find("failure") is not None or case.find("error") is not None
    ]
    suite = ET.Element(
        "testsuite",
        name="phase3-latest-distinct-checks",
        tests=str(len(latest)),
        failures=str(len(unresolved)),
    )
    for case in latest.values():
        suite.append(case)
    ET.ElementTree(suite).write(
        directory / "validation.xml", encoding="unicode", xml_declaration=True
    )
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((directory / "runs").glob("*/report.json"))
    ]
    healthy = sorted(
        [
            report
            for report in reports
            if report["planner_decisions"]
            and report["scope"]["runtime_metadata"].get("model_repository") == "Qwen/Qwen3-4B-GGUF"
            and report["scope"]["runtime_metadata"].get("model_owned_by_session") is False
            and report["scope"]["runtime_metadata"].get("variant") == "healthy"
        ],
        key=lambda report: report["created_at"],
    )
    successes = sum(
        report["cohort_results"]["outcome_counts"].get("completed", 0) for report in healthy
    )
    zero_sentinel = all(
        (
            report["protection"]["sentinel_requests"] == 0
            and report["protection"]["sentinel_data_unchanged"]
        )
        if report["protection"]["sentinel_requests"] is not None
        else report["cohort_results"]["executed_sessions"] == 0
        and report["protection"]["target_requests"] == 0
        for report in reports
    )
    latest_profile = {report["scope"]["personas"][0]: report for report in healthy}
    latest_successes = sum(
        report["cohort_results"]["outcome_counts"].get("completed", 0)
        for report in latest_profile.values()
    )
    initial_successes = sum(
        report["cohort_results"]["outcome_counts"].get("completed", 0) for report in healthy[:3]
    )
    gate = len(latest_profile) == 3 and latest_successes == 3 and not unresolved and zero_sentinel
    summary = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "phase": 3,
        "status": "verified_typed_tools_fixture_gate_after_repairs"
        if gate
        else "incomplete_typed_tools_fixture_gate",
        "generated_code_gate": "unmet: no OS/container runtime; generated Python disabled",
        "full_phase3_status": "partial: generated-code/container execution remains unimplemented",
        "unique_checks": len(latest),
        "unique_checks_passed": len(latest) - len(unresolved),
        "unresolved_checks": unresolved,
        "attempts": attempts,
        "checks_by_module": dict(Counter(key[0] for key in latest)),
        "provisional_threshold": "3/3 first seeded healthy sessions; all negative checks",
        "initial_threshold_met": initial_successes == 3 and len(healthy) >= 3,
        "initial_healthy_successes": initial_successes,
        "initial_healthy_attempts": min(3, len(healthy)),
        "latest_repaired_profile_successes": latest_successes,
        "latest_repaired_profiles": len(latest_profile),
        "successful_runs_repeated_for_privacy_harness_repair": 0,
        "latest_profile_reports": {
            persona: f"artifacts/phase3/runs/{report['run_id']}/report.html"
            for persona, report in latest_profile.items()
        },
        "healthy_model_attempts": len(healthy),
        "healthy_model_successes": successes,
        "healthy_outcomes": [
            {
                "run_id": report["run_id"],
                "persona": report["scope"]["personas"][0],
                "journey": report["scope"]["journeys"][0],
                "seed": report["scope"]["seed"],
                "outcomes": report["cohort_results"]["outcome_counts"],
                "decisions": len(report["planner_decisions"]),
                "reason": report["terminal_reason"],
                "inference_seconds": report["scope"]["runtime_metadata"]["model_inference_seconds"],
                "report": f"artifacts/phase3/runs/{report['run_id']}/report.html",
            }
            for report in healthy
        ],
        "terminal_reports_including_failures": len(reports),
        "sentinel_requests_all_attempts": sum(
            report["protection"]["sentinel_requests"] or 0 for report in reports
        ),
        "sentinel_data_unchanged_all_attempts": zero_sentinel,
        "unexecuted_reports_without_started_sentinel": sum(
            report["protection"]["sentinel_requests"] is None for report in reports
        ),
        "external_websites_tested": 0,
        "generated_python_executed": False,
        "vision_calls": 0,
        "model_decisions": sum(len(report["planner_decisions"]) for report in reports),
        "lint": "See phase3-validation.md for recorded acceptance status",
        "reports_reviewed_offline": True,
        "acceptance_interpretation": "Initial model failures are retained. Latest per-profile results reflect explicit implementation repairs, not a first-pass 3/3 rate or calibrated conversion estimate.",
        "remaining": [
            "Implement and validate OS/container worker before generated Python or external replicas",
            "Phase 4 friction/patience runtime",
            "Phase 5 cohorts/persistence",
            "Later evidence-based UX findings, heatmaps, dashboard, and calibration",
        ],
    }
    (directory / "validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
