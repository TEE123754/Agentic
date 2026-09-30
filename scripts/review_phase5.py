"""Review stored Phase 5 evidence without reopening any browser or website."""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

from frictionlab.contracts.models import RunReport


def main():
    base = Path(os.environ.get("FRICTIONLAB_PHASE5_EVIDENCE", "artifacts/phase5/validation"))
    base.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 5 offline evidence review",
        "",
        "Review uses saved reports, journal, and DuckDB only; no browser or target request.",
        "",
    ]
    checked = 0
    for root in sorted(base.glob("*/cohorts.duckdb")):
        folder = root.parent
        connection = duckdb.connect(str(root), read_only=True)
        try:
            runs = connection.execute("SELECT run_id, status, report_status FROM runs").fetchall()
            for run_id, status, report_status in runs:
                report_path = folder / "reports" / run_id / "report.json"
                if not report_path.is_file():
                    continue
                report = RunReport.model_validate_json(report_path.read_text())
                assert report.report_status == "partial" and report_status == "partial"
                assert report.cohort_results.requested_sessions == len(report.session_summaries)
                assert report.protection.sentinel_requests == 0
                assert report.protection.sentinel_data_unchanged is True
                assert not report.findings
                for item in report.session_summaries:
                    target = (folder / item.report_path).resolve()
                    assert target.is_relative_to(folder.resolve()) and target.is_file()
                    assert target.with_name("report.json").is_file()
                trace_path = folder / "otel-spans.jsonl"
                assert trace_path.is_file()
                trace_count = sum(
                    1
                    for line in trace_path.read_text().splitlines()
                    if json.loads(line)["name"] == "cohort.session"
                )
                assert trace_count >= 1
                lines += [
                    f"## {run_id}",
                    "",
                    f"- Status: {status}; report: {report_status}",
                    (
                        f"- Sessions: {report.cohort_results.requested_sessions}; "
                        f"executed: {report.cohort_results.executed_sessions}"
                    ),
                    f"- Outcomes: {dict(report.cohort_results.outcome_counts)}",
                    (
                        f"- Synthetic sentinel requests: {report.protection.sentinel_requests}; "
                        "sentinel data unchanged: yes"
                    ),
                    f"- OpenTelemetry session spans: {trace_count}",
                    f"- [Factual report]({folder.name}/reports/{run_id}/report.html)",
                    "",
                ]
                checked += 1
        finally:
            connection.close()
    if not checked:
        lines += ["No complete cohort report was available for review.", ""]
    (base / "validation-review.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if checked else 1


if __name__ == "__main__":
    raise SystemExit(main())
