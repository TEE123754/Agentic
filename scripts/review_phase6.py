"""Review saved Phase 6 reports and local evidence without a browser or network."""

from __future__ import annotations

import json
import os
from pathlib import Path

from frictionlab.contracts.models import RunReport


def main():
    base = Path(os.environ.get("FRICTIONLAB_PHASE6_EVIDENCE", "artifacts/phase6/validation"))
    base.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 6 offline audit review",
        "",
        "Saved evidence only; no browser, target URL, or model inference was opened.",
        "",
    ]
    reviewed = 0
    for path in sorted(base.glob("*/reports/*/revisions/2/report.json")):
        report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
        assert report.scope.phase == 6 and report.report_status == "ready"
        assert report.protection.sentinel_requests == 0
        assert report.protection.sentinel_data_unchanged is True
        assert report.review.status == "evidence_reviewed" and not report.review.missing_evidence
        assert report.findings and report.heatmaps and report.trajectory_index
        for finding in report.findings:
            assert finding.event_ids and finding.affected_session_ids
            assert finding.affected_sessions <= finding.eligible_sessions
            assert finding.recommendation and finding.verification
            assert all((path.parent / ref.path).is_file() for ref in finding.evidence)
        for group in report.heatmaps:
            assert (path.parent / group.svg_path).is_file()
            assert all(
                0 <= point.x < group.pixel_width and 0 <= point.y < group.pixel_height
                for point in group.points
            )
        html = path.with_name("report.html").read_text(encoding="utf-8")
        assert "data:image/svg+xml;base64," in html and 'src="http' not in html
        assert "Evidence exclusions" in html and "Conversion milestones" in html
        lines.extend(
            [
                f"## Run {report.run_id}",
                "",
                f"- Execution/report: {report.execution_status} / {report.report_status}, revision {report.revision}",
                f"- Sessions: {report.cohort_results.executed_sessions}/{report.cohort_results.requested_sessions} executed; {report.cohort_results.eligible_sessions} eligible",
                f"- Outcomes: {json.dumps({str(k): v for k, v in report.cohort_results.outcome_counts.items()})}",
                f"- Findings: {len(report.findings)}; heatmaps: {len(report.heatmaps)}; exclusions: {len(report.exclusions)}",
                f"- Protection: {report.protection.sentinel_requests} sentinel requests; data unchanged",
                f"- [Offline HTML report]({path.relative_to(base).as_posix().replace('report.json', 'report.html')})",
                "",
            ]
        )
        reviewed += 1
    if reviewed == 0:
        lines.extend(["No ready Phase 6 report was available for offline review.", ""])
    result = "\n".join(lines)
    (base / "validation-review.md").write_text(result, encoding="utf-8")
    print(result)
    return 0 if reviewed else 1


if __name__ == "__main__":
    raise SystemExit(main())
