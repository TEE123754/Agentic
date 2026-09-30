"""Review and merge saved Phase 2 evidence without opening any browser or website."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime

from frictionlab.configuration import ROOT

ATTEMPTS = (
    "validation-initial.xml",
    "validation-repair-1.xml",
    "validation-repair-2.xml",
    "validation-repair-3.xml",
    "validation-repair-4.xml",
    "validation-terminal-reports.xml",
)


def main():
    directory = ROOT / "artifacts" / "phase2"
    latest = {}
    attempts = []
    for filename in ATTEMPTS:
        root = ET.parse(directory / filename).getroot()
        cases = list(root.iter("testcase"))
        failures = sum(
            case.find("failure") is not None or case.find("error") is not None for case in cases
        )
        attempts.append(
            {
                "file": filename,
                "checks": len(cases),
                "passed": len(cases) - failures,
                "failed": failures,
                "seconds": sum(
                    float(suite.attrib.get("time", 0)) for suite in root.iter("testsuite")
                ),
            }
        )
        for case in cases:
            latest[(case.attrib["classname"], case.attrib["name"])] = case
    unresolved = sum(
        case.find("failure") is not None or case.find("error") is not None
        for case in latest.values()
    )
    if unresolved:
        raise SystemExit("Unresolved Phase 2 checks remain in saved evidence")
    suites = ET.Element("testsuites")
    suite = ET.SubElement(
        suites,
        "testsuite",
        name="phase2-latest-results",
        tests=str(len(latest)),
        failures="0",
        errors="0",
        skipped="0",
    )
    for key in sorted(latest):
        suite.append(latest[key])
    ET.ElementTree(suites).write(
        directory / "validation.xml", encoding="utf-8", xml_declaration=True
    )
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((directory / "runs").glob("*/report.json"))
    ]
    healthy = {}
    for report in sorted(reports, key=lambda item: item["created_at"]):
        if (
            report["scope"]["runtime_metadata"]["variant"] == "healthy"
            and report["cohort_results"]["outcome_counts"].get("completed") == 1
        ):
            healthy[report["scope"]["personas"][0]] = (
                f"artifacts/phase2/runs/{report['run_id']}/report.html"
            )
    latest_failures = {
        report["terminal_reason"]: f"artifacts/phase2/runs/{report['run_id']}/report.md"
        for report in sorted(reports, key=lambda item: item["created_at"])
        if "FileNotFoundError" in report["terminal_reason"]
        or "Runtime ceiling" in report["terminal_reason"]
    }
    stages = Counter(key[0] for key in latest)
    fixture_files = [
        ROOT / "frictionlab" / "api.py",
        ROOT / "frictionlab" / "fixtures" / "store.py",
        *sorted((ROOT / "frictionlab" / "fixtures" / "web").glob("*")),
    ]
    summary = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "phase": 2,
        "status": "complete_owned_fixture_gate",
        "unique_checks_passed": len(latest),
        "unresolved_checks": unresolved,
        "checks_by_module": dict(stages),
        "attempts": attempts,
        "lint": "Passed consolidated scope after targeted repairs; changed report/broker files also passed",
        "javascript_syntax": "Passed once at phase boundary",
        "model_calls": 0,
        "external_websites_tested": 0,
        "report_count_including_failed_attempts": len(reports),
        "sentinel_requests_across_all_attempts": sum(
            report["protection"]["sentinel_requests"] for report in reports
        ),
        "sentinel_data_unchanged_across_all_attempts": all(
            report["protection"]["sentinel_data_unchanged"] for report in reports
        ),
        "healthy_profile_reports": healthy,
        "terminal_failure_reports": latest_failures,
        "fixture_content_sha256": hashlib.sha256(
            b"".join(path.read_bytes() for path in fixture_files if path.is_file())
        ).hexdigest(),
        "visual_review": "Saved desktop checkout screenshot reviewed; synthetic input is masked; no additional browser run",
        "limitations": [
            "Owned fixture browser/proxy scope only; no OS/container sandbox",
            "External replicas and generated Python remain disabled",
            "Frames, popups, shadow roots, downloads, and real assistive technology are not actionable coverage",
            "Installed Chrome is recorded but can update independently",
            "Reports are partial; autonomous UX findings, heatmaps, and cognitive runtime are later phases",
        ],
    }
    if (
        summary["sentinel_requests_across_all_attempts"]
        or not summary["sentinel_data_unchanged_across_all_attempts"]
    ):
        raise SystemExit("Saved sentinel evidence does not satisfy protection acceptance")
    (directory / "validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
