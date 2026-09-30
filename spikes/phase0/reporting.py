"""Detailed offline reports for both successful and failed phase acceptance attempts."""

from __future__ import annotations

import base64
import html
import json


def write_report(directory, report):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    sections = {
        "Executive summary": {
            "phase": "0: single local integration spike",
            "result": report["result"],
            "error": report.get("error"),
            "purpose": "Validate shared-target grounding and local model-selected browser action",
        },
        "Scope and reproducibility": report["scope"],
        "Website protection": report["protection"],
        "Acceptance and cohort results": report["checks"],
        "Individual trajectory": report["trajectory"],
        "UX findings": {
            "findings": [],
            "reason": "UX detection and multi-profile behavior are later phases; no UX defects inferred from this spike",
        },
        "Abandonment explanations": {
            "status": "not assessed", "reason": "Cognitive runtime begins in Phase 4"
        },
        "Metrics": report["metrics"],
        "Recommendations": report["recommendations"],
        "Comparison": {"status": "not applicable", "reason": "No baseline/candidate UX comparison in Phase 0"},
        "Review and limitations": report["review"],
        "Cleanup": report["cleanup"],
    }
    markdown = ["# Phase 0 validation report", "", f"Run: `{report['run_id']}`", ""]
    cards = []
    for title, value in sections.items():
        content = json.dumps(value, indent=2)
        markdown += [f"## {title}", "", "```json", content, "```", ""]
        cards.append(f"<section><h2>{html.escape(title)}</h2><pre>{html.escape(content)}</pre></section>")
    markdown += ["## Visual evidence", ""]
    for filename in ("before.png", "after.png"):
        path = directory / filename
        if path.exists():
            markdown += [f"![{filename}]({filename})", ""]
            encoded = base64.b64encode(path.read_bytes()).decode()
            cards.append(f'<section><h2>{filename}</h2><img alt="{filename}" src="data:image/png;base64,{encoded}"></section>')
        else:
            markdown += [f"Missing: {filename}", ""]
    (directory / "report.md").write_text("\n".join(markdown), encoding="utf-8")
    document = """<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
    <title>Phase 0 validation report</title><style>
    body{font:16px system-ui;max-width:1000px;margin:32px auto;padding:20px;background:#f5f7fb;color:#18263b}
    section{background:white;padding:20px;margin:16px 0;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}
    img{max-width:100%;height:auto}h1{font-size:30px}</style></head><body><h1>Phase 0 validation report</h1>"""
    document += f"<p>Run: {html.escape(report['run_id'])}</p>" + "".join(cards) + "</body></html>"
    (directory / "report.html").write_text(document, encoding="utf-8")

