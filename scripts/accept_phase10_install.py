"""Run with the wheel installed and python -I, after all construction is complete."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import frictionlab


def main():
    assert "site-packages" in str(Path(frictionlab.__file__).resolve())
    evidence = Path(os.environ["FRICTIONLAB_PHASE10_EVIDENCE"]).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    executable = Path(sys.executable).with_name("frictionlab")
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        home = directory / "workspace"
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("GROQ_API_KEY", None)
        environment.pop("GEMINI_API_KEY", None)
        environment["FRICTIONLAB_HOME"] = str(home)

        def run(*args, success=True):
            completed = subprocess.run(
                [str(executable), *args],
                cwd=directory,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=150,
            )
            assert completed.returncode == (0 if success else 2), (
                completed.stdout + completed.stderr
            )
            return completed.stdout

        assert "0.1.0" in run("--version")
        run("init", str(home))
        assert (home / "site/index.html").is_file() and (home / "configs/agent.json").is_file()
        run("validate", str(home / "configs/run.quickstart.json"))
        diagnostic = json.loads(run("doctor", success=False))
        assert diagnostic["network_requests"] == 0 and not diagnostic["downloads"]
        # This proves installed fixtures, axe, writable paths and terminal reports, no model.
        probe = subprocess.run(
            [str(executable), "browser-demo"],
            cwd=directory,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=150,
        )
        assert probe.returncode == 0, probe.stdout + probe.stderr
        reports = list((home / "artifacts").rglob("report.json"))
        assert reports
        report = json.loads(reports[-1].read_text())
        assert report["protection"]["sentinel_requests"] == 0
        assert report["protection"]["sentinel_data_unchanged"] is True
        (evidence / "installed-cli-review.json").write_text(
            json.dumps(
                {
                    "installed_package": str(Path(frictionlab.__file__).resolve()),
                    "version": frictionlab.__version__,
                    "init_validate_doctor": True,
                    "installed_browser_probe": True,
                    "sentinel_requests": 0,
                    "sentinel_data_unchanged": True,
                    "large_downloads": False,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
