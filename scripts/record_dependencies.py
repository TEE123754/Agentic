"""Record installed metadata without executing an application or test scenario."""

import importlib.metadata
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
records = []
for distribution in importlib.metadata.distributions():
    metadata = distribution.metadata
    records.append({
        "name": metadata["Name"], "version": distribution.version,
        "license_expression": metadata.get("License-Expression"),
        "license": metadata.get("License"),
        "project_urls": metadata.get_all("Project-URL") or [],
    })
(root / "docs" / "dependency-manifest.json").write_text(
    json.dumps(sorted(records, key=lambda r: r["name"].lower()), indent=2), encoding="utf-8"
)
print(f"Recorded {len(records)} installed distributions")

