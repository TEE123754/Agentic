"""Offline review of the saved Phase 7 owned-fixture dashboard walkthrough."""

from __future__ import annotations

import json
import os
from pathlib import Path

from frictionlab.contracts.models import RunReport


def main():
    base = Path(os.environ.get("FRICTIONLAB_PHASE7_EVIDENCE", "artifacts/phase7/validation"))
    base.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 7 offline dashboard review",
        "",
        "Saved fixture report, linked evidence, and dashboard screenshot only.",
        "",
    ]
    reviewed = 0
    for path in sorted(base.glob("*/reports/*/revisions/4/report.json")):
        run_root = path.parents[4]
        report = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
        manifest = json.loads(
            (run_root / "runs" / str(report.run_id) / "manifest.json").read_text()
        )
        assert manifest["environment"]["replica_origins"] == ["http://127.0.0.1:8765"]
        assert report.revision == 4 and report.report_status == "ready"
        assert report.review.dispositions[0].status == "confirmed"
        assert report.findings and report.heatmaps and report.trajectory_index
        assert report.protection.sentinel_requests == 0
        assert report.protection.sentinel_data_unchanged is True
        assert (run_root / "dashboard.png").is_file()
        for finding in report.findings:
            assert finding.recommendation and finding.verification
            assert all((path.parent / ref.path).is_file() for ref in finding.evidence)
        for group in report.heatmaps:
            assert (path.parent / group.svg_path).is_file()
        lines.extend(
            [
                f"## Run {report.run_id}",
                "",
                f"- Execution/report/revision: {report.execution_status} / {report.report_status} / {report.revision}",
                f"- Sessions: {report.cohort_results.executed_sessions}/{report.cohort_results.requested_sessions} executed; {report.cohort_results.eligible_sessions} eligible",
                f"- Findings: {len(report.findings)}; heatmaps: {len(report.heatmaps)}; human disposition: confirmed",
                f"- Protection: {report.protection.sentinel_requests} sentinel requests; data unchanged",
                f"- [Dashboard screenshot]({(run_root / 'dashboard.png').relative_to(base).as_posix()})",
                f"- [Reviewed report]({path.with_name('report.html').relative_to(base).as_posix()})",
                "",
            ]
        )
        reviewed += 1
    if not reviewed:
        lines.append("No reviewed dashboard report was found.")
    result = "\n".join(lines)
    (base / "validation-review.md").write_text(result, encoding="utf-8")
    print(result)
    return 0 if reviewed else 1


if __name__ == "__main__":
    raise SystemExit(main())
