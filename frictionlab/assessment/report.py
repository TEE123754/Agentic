"""Self-contained, escaped exports. Uploaded source and credentials are excluded."""

import html
import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO

from frictionlab.assessment.models import scores
from frictionlab.planning.inference import safe_text


def report_document(run_id, request, checks, acquisition, limitations, evidence, state, ai):
    ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues = sorted(
        [c.model_dump() for c in checks if c.status == "failed"], key=lambda c: ranks[c["severity"]]
    )
    value = {
        "schema_version": "assessment-v1",
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "execution_status": state,
        "target": "Submitted website URL (not retained)",
        "mode": request.mode,
        "selected_categories": request.categories,
        "scores": scores(checks, request.categories),
        "summary": {
            s: sum(c.status == s for c in checks)
            for s in ("passed", "failed", "skipped", "incomplete")
        },
        "issues": issues,
        "checks": [c.model_dump() for c in checks],
        "acquisition": acquisition,
        "evidence_files": evidence,
        "ai_review": ai,
        "limitations": limitations
        + [
            "Scores cover only executed checks. Missing coverage must not be interpreted as passing or release approval.",
            "Automated structural checks and synthetic personas cannot establish actual user churn, WCAG compliance or application security.",
            "Browser isolation alone cannot prevent production side effects. Dynamic testing requires a verified replica with isolated data and integrations.",
            "Screenshots can contain document content; review them before sharing. Uploaded source and API keys are excluded from exports.",
        ],
    }
    return json.loads(safe_text(json.dumps(value, ensure_ascii=False)))


def markdown(report):
    lines = [
        "# FrictionLab website assessment",
        f"Run: {report['run_id']} | Execution: {report['execution_status']}",
        f"Overall score: {report['scores']['overall'] if report['scores']['overall'] is not None else 'Unassessed'} | Coverage: {report['scores']['coverage']}%",
        report["scores"]["method"],
        "## Category scores",
    ]
    for cat, row in report["scores"]["categories"].items():
        lines.append(
            f"- {cat}: {row['score'] if row['score'] is not None else 'Unassessed'}; coverage {row['coverage']}%; confidence {row['confidence']}"
        )
    lines += [
        "## Check summary",
        ", ".join(f"{s}: {n}" for s, n in report["summary"].items()),
        "## Issues",
    ]
    for c in report["issues"]:
        lines += [
            f"### {c['severity'].upper()}: {c['title']}",
            c["detail"],
            "Evidence: " + "; ".join(c["evidence"]),
            "Reproduction: " + "; ".join(c["reproduction"]),
            "Recommendation: " + c["recommendation"],
        ]
        if c["ai_recommendation"]:
            lines.append("AI suggestion (requires review): " + c["ai_recommendation"])
    lines.append("## All checks")
    lines += [
        f"- {c['status'].upper()} / {c['category']} / {c['title']}: {c['detail']}"
        for c in report["checks"]
    ]
    lines += [
        "## Acquisition",
        json.dumps(report["acquisition"]),
        "## AI review",
        json.dumps(report["ai_review"]),
        "## Limitations",
    ]
    lines += ["- " + v for v in report["limitations"]]
    return "\n\n".join(lines) + "\n"


def write_reports(directory, report):
    text = markdown(report)
    html_text = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>FrictionLab report</title><style>body{max-width:1000px;margin:40px auto;padding:20px;font:16px system-ui;color:#17243a}pre{white-space:pre-wrap;line-height:1.6}</style><body><pre>'
        + html.escape(text)
        + "</pre></body></html>"
    )
    for name, content in (
        ("report.json", json.dumps(report, indent=2)),
        ("report.md", text),
        ("report.html", html_text),
    ):
        temp = directory / (name + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(directory / name)


def export_zip(directory, report):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("report.json", "report.md", "report.html", *report["evidence_files"]):
            path = directory / name
            if path.parent == directory and path.is_file():
                archive.write(path, name)
    return output.getvalue()
