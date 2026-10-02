"""Verify candidate content before it is published as a GitHub Release."""

import tarfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheel = next((root / "dist").glob("frictionlab-*.whl"))
source = next((root / "dist").glob("frictionlab-*.tar.gz"))
with zipfile.ZipFile(wheel) as archive:
    wheel_names = archive.namelist()
with tarfile.open(source) as archive:
    source_names = archive.getnames()
for names in (wheel_names, source_names):
    for required in (
        "frictionlab/app.py",
        "frictionlab/desktop.py",
        "frictionlab/web/index.html",
        "vendor/axe-core/axe.min.js",
        "docs/local-assessment.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
    ):
        if not any(name.endswith(required) for name in names):
            raise ValueError("Release archive is missing a required product asset")
    if any(
        name.endswith((".gguf", ".env", "app-settings.json")) or "/artifacts/" in name
        for name in names
    ):
        raise ValueError("Release archive contains local runtime data")
print(f"Wheel {len(wheel_names)} files; source {len(source_names)} files; contents verified")
