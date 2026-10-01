"""Run with the wheel installed and python -I, after all construction is complete."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import frictionlab


async def inspect_installed_site(home, executable):
    from playwright.async_api import async_playwright

    requests = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, executable_path=executable)
        try:
            page = await browser.new_page(viewport={"width": 390, "height": 844})
            page.on("request", lambda request: requests.append(request.url))
            await page.goto((home / "site/index.html").as_uri())
            await page.get_by_role("link", name="Explore a sample audit").click()
            await page.get_by_text("FrictionLab portable audit").wait_for()
            await page.goto((home / "site/index.html").as_uri())
            href = await page.get_by_role("link", name="Read the setup guide").get_attribute("href")
            assert (home / "site" / href).resolve().is_file()
        finally:
            await browser.close()
    assert not any(url.startswith(("http://", "https://")) for url in requests)


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
        asyncio.run(inspect_installed_site(home, environment["FRICTIONLAB_BROWSER_PATH"]))
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
                    "installed_landing_sample_navigation": True,
                    "report_review_http_requests": 0,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
