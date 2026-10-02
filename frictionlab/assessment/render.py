"""Render only synthetic-origin resources. Never navigate to the submitted URL."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

from frictionlab.assessment.models import Check
from frictionlab.assessment.snapshot import mime, safe_document
from frictionlab.browser.accessibility import inspect_accessibility


def browser_path():
    explicit = os.environ.get("FRICTIONLAB_BROWSER_PATH")
    candidates = [explicit] if explicit else []
    candidates += [
        shutil.which(name) for name in ("google-chrome", "chromium", "chromium-browser", "msedge")
    ]
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(env):
            candidates += [
                str(Path(os.environ[env]) / suffix)
                for suffix in (
                    "Google/Chrome/Application/chrome.exe",
                    "Microsoft/Edge/Application/msedge.exe",
                )
            ]
    candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    return next((p for p in candidates if p and Path(p).is_file()), None)


async def render_snapshot(snapshot, categories, directory, stop):
    checks, evidence, blocked = [], [], []

    def add(id, category, title, status, detail, severity=None, observations=None):
        if category in categories:
            checks.append(
                Check(
                    id=id,
                    category=category,
                    title=title,
                    status=status,
                    severity=severity,
                    confidence=0.65 if status in {"passed", "failed"} else 0,
                    detail=detail,
                    evidence=observations or [],
                    reproduction=["Open the same offline snapshot at the recorded viewport."],
                    recommendation="Review the corresponding offline screenshot and fix the layout or accessibility rule; verify again on an isolated interactive replica.",
                )
            )

    if not any(c in categories for c in ("responsiveness", "accessibility")):
        return checks, evidence, []
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            options = {
                "headless": True,
                "args": [
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--no-first-run",
                    "--disable-features=MediaRouter",
                    "--host-resolver-rules=MAP * ~NOTFOUND",
                ],
            }
            executable = browser_path()
            if executable:
                options["executable_path"] = executable
            browser = await pw.chromium.launch(**options)
            try:
                context = await browser.new_context(
                    java_script_enabled=False,
                    offline=True,
                    service_workers="block",
                    accept_downloads=False,
                    permissions=[],
                )

                async def route(request_route):
                    url = urlsplit(request_route.request.url)
                    path = unquote(url.path).lstrip("/") or "index.html"
                    if (
                        url.scheme != "https"
                        or url.netloc != "snapshot.invalid"
                        or path not in snapshot.files
                    ):
                        blocked.append("Resource excluded from the offline bundle")
                        await request_route.abort()
                        return
                    content = snapshot.files[path]
                    if path.endswith((".html", ".htm")):
                        content = safe_document(content.decode("utf-8", errors="replace")).encode()
                    await request_route.fulfill(
                        status=200,
                        body=content,
                        content_type=mime(path),
                        headers={
                            "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src 'none'; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'",
                            "X-DNS-Prefetch-Control": "off",
                            "X-Content-Type-Options": "nosniff",
                        },
                    )

                await context.route("**/*", route)
                page = await context.new_page()
                await page.goto(
                    "https://snapshot.invalid/index.html", wait_until="load", timeout=15000
                )
                for width in (360, 768, 1440):
                    if stop.is_set():
                        raise RuntimeError("Cancelled")
                    await page.set_viewport_size({"width": width, "height": 900})
                    await page.screenshot(
                        path=str(directory / f"viewport-{width}.png"),
                        full_page=False,
                        timeout=15000,
                    )
                    evidence.append(f"viewport-{width}.png")
                    dimensions = await page.evaluate(
                        "({viewport: innerWidth, content: document.documentElement.scrollWidth})"
                    )
                    overflow = dimensions["content"] > dimensions["viewport"] + 2
                    add(
                        f"responsiveness.width-{width}",
                        "responsiveness",
                        f"Horizontal overflow at {width}px",
                        "failed" if overflow else "passed",
                        "Static copy only; absent external assets can change the result.",
                        "medium" if overflow else None,
                        [
                            f"Viewport {width}px; content {dimensions['content']}px",
                            f"viewport-{width}.png",
                        ],
                    )
                if "accessibility" in categories:
                    result = await inspect_accessibility(page)
                    for violation in result["violations"]:
                        add(
                            "accessibility.axe-" + violation["id"],
                            "accessibility",
                            violation["help"],
                            "failed",
                            "Offline axe-core rule violation; not a compliance conclusion.",
                            "high"
                            if violation.get("impact") in {"serious", "critical"}
                            else "medium",
                            [
                                f"Rule {violation['id']}; affected nodes {len(violation['nodes'])}",
                                "viewport-1440.png",
                            ],
                        )
                    add(
                        "accessibility.axe",
                        "accessibility",
                        "Automated axe-core scan",
                        "incomplete" if result["incomplete"] else "passed",
                        f"axe-core {result['version']}; violations {len(result['violations'])}; rules requiring review {len(result['incomplete'])}. A scan completion does not mean all rules passed.",
                    )
                await context.close()
            finally:
                await browser.close()
    except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
        for cat in ("responsiveness", "accessibility"):
            add(
                cat + ".renderer",
                cat,
                "Offline browser inspection",
                "incomplete",
                "Browser inspection failed or was cancelled. Install Chrome/Edge or explicitly install Playwright Chromium. No target navigation occurred.",
            )
    limits = (
        [
            f"Blocked or unavailable snapshot resources: {len(blocked)}. Layout/contrast confidence is limited."
        ]
        if blocked
        else []
    )
    if blocked:
        for c in checks:
            if c.status in {"passed", "failed"}:
                c.confidence = 0.4
    return checks, evidence, limits
