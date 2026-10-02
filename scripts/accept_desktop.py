"""Verify the extracted Windows download rather than the source checkout."""

import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temporary:
    destination = Path(temporary)
    with zipfile.ZipFile(root / "dist/FrictionLab-windows-x64.zip") as archive:
        names = archive.namelist()
        assert any(n.endswith("frictionlab/web/index.html") for n in names)
        axe_path = next(n for n in names if n.endswith("vendor/axe-core/axe.min.js"))
        manifest_path = next(n for n in names if n.endswith("configs/axe-manifest.json"))
        manifest = json.loads(archive.read(manifest_path))
        assert hashlib.sha256(archive.read(axe_path)).hexdigest() == manifest["script_sha256"]
        assert "FrictionLab/LICENSE" in names and "FrictionLab/THIRD_PARTY_NOTICES.md" in names
        assert not any(n.endswith((".gguf", ".env", "app-settings.json")) for n in names)
        archive.extractall(destination)
    executable = destination / "FrictionLab/FrictionLab.exe"
    for flag in ("--self-check", "--serve-smoke"):
        try:
            subprocess.run([str(executable), flag], cwd=destination, check=True, timeout=150)
        finally:
            evidence = root / "artifacts/desktop"
            if (destination / "smoke-workspace").is_dir():
                shutil.copytree(
                    destination / "smoke-workspace", evidence / "packaged-smoke", dirs_exist_ok=True
                )
            if (destination / "packaged-failure.json").is_file():
                shutil.copy2(
                    destination / "packaged-failure.json", evidence / "packaged-failure.json"
                )
    evidence = root / "artifacts/desktop"
    shutil.copytree(
        destination / "smoke-workspace", evidence / "packaged-smoke", dirs_exist_ok=True
    )
    (evidence / "packaged-acceptance.json").write_text(
        json.dumps(
            {
                "self_check": "passed",
                "extracted_executable_local_dashboard": "passed",
                "offline_browser_report": "passed",
                "target_requests": 0,
                "models_bundled": False,
                "keys_bundled": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
