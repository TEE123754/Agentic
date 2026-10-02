"""Build on the disposable Windows runner; no bundled models or secrets."""

import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
command = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onedir",
    "--name",
    "FrictionLab",
    "--collect-all",
    "playwright",
    "--add-data",
    f"{root / 'frictionlab/web'};frictionlab/web",
    "--add-data",
    f"{root / 'configs'};frictionlab/_assets/configs",
    "--add-data",
    f"{root / 'vendor'};frictionlab/_assets/vendor",
    "--exclude-module",
    "torch",
    "--exclude-module",
    "transformers",
    "--exclude-module",
    "streamlit",
    "--exclude-module",
    "smolagents",
    str(root / "scripts/desktop_entry.py"),
]
subprocess.run(command, cwd=root, check=True)
output = root / "dist/FrictionLab"
for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"):
    shutil.copy2(root / name, output / name)
shutil.copy2(root / "docs/local-assessment.md", output / "LOCAL-SETUP.md")
licenses = output / "licenses"
licenses.mkdir(exist_ok=True)
records = []
for d in importlib.metadata.distributions():
    records.append(
        {
            "name": d.metadata["Name"],
            "version": d.version,
            "license": d.metadata.get("License-Expression") or d.metadata.get("License"),
        }
    )
    for file in d.files or []:
        if any(
            part.lower() in {"licenses", "license", "copying", "copyright"}
            or part.lower().startswith(("license.", "copying."))
            for part in file.parts
        ):
            source = Path(d.locate_file(file))
            if source.is_file():
                destination = licenses / d.metadata["Name"] / str(file).replace("..", "_")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
(licenses / "dependency-metadata.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
archive = Path(
    shutil.make_archive(
        str(root / "dist/FrictionLab-windows-x64"),
        "zip",
        root_dir=root / "dist",
        base_dir="FrictionLab",
    )
)
(root / "dist/DESKTOP-SHA256SUMS").write_text(
    hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n", encoding="utf-8"
)
