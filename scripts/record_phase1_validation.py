"""Merge saved phase acceptance evidence; never rerun tests or website interactions."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from frictionlab.configuration import ROOT, read_json, resolve_run
from frictionlab.reporting import blocked_report, write_report


def main():
    directory = ROOT / "artifacts" / "phase1"
    sources = (
        "validation-initial.xml",
        "validation-repair.xml",
        "validation-network-guard.xml",
    )
    cases = {}
    attempts = []
    for filename in sources:
        root = ET.parse(directory / filename).getroot()
        count = 0
        errors = 0
        for case in root.iter("testcase"):
            cases[(case.attrib["classname"], case.attrib["name"])] = case
            count += 1
            errors += int(case.find("error") is not None or case.find("failure") is not None)
        attempts.append({"file": filename, "cases": count, "errors": errors})
    failed = sum(
        case.find("error") is not None or case.find("failure") is not None
        for case in cases.values()
    )
    suite = ET.Element(
        "testsuite",
        name="phase1-latest-results",
        tests=str(len(cases)),
        errors=str(failed),
        failures="0",
        skipped="0",
    )
    for key in sorted(cases):
        suite.append(cases[key])
    suites = ET.Element("testsuites")
    suites.append(suite)
    ET.ElementTree(suites).write(
        directory / "validation.xml", encoding="utf-8", xml_declaration=True
    )
    if failed:
        raise SystemExit("Saved Phase 1 evidence still contains unresolved checks")
    resolved = resolve_run(read_json(ROOT / "configs" / "run.example.json"))
    sample = write_report(
        blocked_report(
            "Browser execution is unavailable until the Phase 2 boundary is implemented and validated.",
            resolved,
        ),
        directory / "sample",
    )
    summary = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "phase": 1,
        "status": "complete",
        "unique_checks_passed": len(cases),
        "unresolved_checks": failed,
        "attempts": attempts,
        "lint": "Passed initial scope except two style findings; affected files passed after repair",
        "javascript_syntax": "Passed once at phase boundary",
        "browser_runs": 0,
        "model_calls": 0,
        "tested_external_websites": 0,
        "configuration_hash": resolved.configuration_hash,
        "sample_report": str(sample.relative_to(ROOT)).replace("\\", "/"),
        "limitations": [
            "In-process API acceptance; real browser UI behavior remains Phase 2",
            "Internal Windows event-loop socket pairs allowed; application network/DNS blocked in tests",
            "No validated OS/container boundary; browser execution remains disabled",
            "Fixture data is in memory; durable storage and report recovery remain later phases",
        ],
    }
    (directory / "validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
