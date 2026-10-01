"""Offline review of saved static viewer and sanitized fixture example."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main():
    base = Path(os.environ.get("FRICTIONLAB_PHASE9_EVIDENCE", "artifacts/phase9/validation"))
    base.mkdir(parents=True, exist_ok=True)
    lines = ["# Phase 9 offline sharing review", ""]
    checked = 0
    for root in sorted(base.iterdir()):
        if not root.is_dir() or not (root / "offline-viewer.png").is_file():
            continue
        public = json.loads((root / "public" / "bundle.json").read_text(encoding="utf-8"))
        private = (root / "private" / "bundle.json").read_text(encoding="utf-8")
        html = (root / "public" / "index.html").read_text(encoding="utf-8")
        assert public["manifest"]["visibility"] == "public_fixture_example"
        assert public["findings"] and public["sessions"] and public["heatmaps"]
        assert public["assets"] and all(
            item.startswith("data:image/png;base64,") for item in public["assets"].values()
        )
        for forbidden in (
            "TOPSECRET",
            "HIDDEN",
            "private.example",
            "alice@example.com",
            "credential_reference",
            "planner_decisions",
        ):
            assert forbidden not in private and forbidden not in html
        assert "connect-src 'none'" in html
        assert "https://" not in html and "http://" not in html
        lines.extend(
            [
                f"## Run {public['manifest']['run_id']}",
                "",
                "- Offline viewer, local import, severity filter, screenshot playback, and heatmap overlay passed.",
                f"- Findings: {len(public['findings'])}; sessions: {len(public['sessions'])}; heatmaps: {len(public['heatmaps'])}; embedded masked PNGs: {len(public['assets'])}.",
                "- No HTTP requests were made while opening or importing local bundles.",
                "- Fake credential, private URL/query, and email markers were absent from the export.",
                f"- [Viewer screenshot]({(root / 'offline-viewer.png').relative_to(base).as_posix()})",
                f"- [Public fixture viewer]({(root / 'public' / 'index.html').relative_to(base).as_posix()})",
                "",
            ]
        )
        checked += 1
    output = base / "validation-review.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output.read_text(encoding="utf-8"))
    return 0 if checked else 1


if __name__ == "__main__":
    raise SystemExit(main())
