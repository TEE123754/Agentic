"""Read only saved Phase 8 quality, comparison, and Mind2Web summaries."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main():
    base = Path(os.environ.get("FRICTIONLAB_PHASE8_EVIDENCE", "artifacts/phase8/validation"))
    base.mkdir(parents=True, exist_ok=True)
    lines = ["# Phase 8 offline evidence review", ""]
    checked = 0
    for quality_path in sorted(base.glob("*/quality.json")):
        root = quality_path.parent
        result = json.loads(quality_path.read_text(encoding="utf-8"))
        comparisons = json.loads((root / "comparisons.json").read_text(encoding="utf-8"))
        metrics = result["metrics"]
        assert len(result["cases"]) == 4 and len(comparisons) == 2
        assert all(metrics[key] >= target for key, target in result["targets"].items())
        assert metrics["inconclusive_sessions"] == 0
        assert metrics["report_completeness"] == 4
        assert metrics["zero_live_sentinel_traffic"] is True
        assert (root / "comparison-dashboard.png").is_file()
        for comparison in comparisons:
            assert comparison["matched"] and comparison["completion_delta"] == 1
            assert comparison["resolved_findings"] and not comparison["new_findings"]
            for side in ("baseline", "candidate"):
                assert comparison["report_completeness"][side]["status"] == "ready"
                assert not comparison["report_completeness"][side]["missing"]
                observed = comparison["protection"][f"{side}_observed"]
                assert observed["sentinel_requests"] == 0
                assert observed["sentinel_data_unchanged"] is True
        lines.extend(
            [
                f"## Frozen fixture batch {root.name}",
                "",
                "- Four ready reports, two seed-matched defect → healthy comparisons in opposite orders.",
                f"- Healthy completion: {metrics['healthy_completion']:.0%}; high-severity precision: {metrics['high_severity_precision']:.0%}; seeded-blocker detection: {metrics['seeded_blocker_detection']:.0%}; evidence-reference validity: {metrics['finding_reference_validity']:.0%}.",
                "- Each healthy candidate completed one more synthetic checkout-review journey and resolved the seeded finding.",
                "- Zero observed sentinel requests; seeded sentinel data unchanged.",
                f"- [Quality report]({quality_path.with_suffix('.md').relative_to(base).as_posix()})",
                f"- [Comparison dashboard]({(root / 'comparison-dashboard.png').relative_to(base).as_posix()})",
                "",
            ]
        )
        checked += 1
    smoke = base / "mind2web-smoke.json"
    if smoke.is_file():
        info = json.loads(smoke.read_text(encoding="utf-8"))
        assert info["split"] == "train" and info["metrics"]["steps"] > 0
        lines.extend(
            [
                "## Mind2Web loader smoke",
                "",
                f"- Pinned revision `{info['revision']}`; SHA-256 checked train shard `{info['file']}`.",
                f"- {info['metrics']['tasks']} tasks, {info['metrics']['steps']} steps; candidate/action lexical-reference scoring recorded separately.",
                "- This is a train-shard integration diagnostic, not held-out model accuracy or human UX calibration.",
                "",
            ]
        )
    output = base / "validation-review.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output.read_text(encoding="utf-8"))
    return 0 if checked and smoke.is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
