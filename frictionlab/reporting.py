"""Deterministic local reports, including partial and unexecuted outcomes."""

from __future__ import annotations

import base64
import html
import json
import os
from pathlib import Path
from uuid import uuid4

from frictionlab.contracts.models import (
    CohortResults,
    ExecutionStatus,
    ProtectionEvent,
    ProtectionSummary,
    ReportScope,
    ReportStatus,
    ReviewSection,
    RunReport,
)


def unexecuted_report(reason, resolved=None, execution_status=ExecutionStatus.BLOCKED):
    if execution_status not in {
        ExecutionStatus.BLOCKED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.INTERRUPTED,
    }:
        raise ValueError("Unexecuted reports require a stopped execution status")
    valid = resolved is not None
    scope = ReportScope(
        build_id=resolved.environment.build_id if valid else None,
        environment_id=resolved.environment.id if valid else None,
        personas=resolved.config.personas if valid else (),
        journeys=resolved.config.journeys if valid else (),
        seed=resolved.config.seed if valid else None,
        configuration_hash=resolved.configuration_hash if valid else None,
    )
    return RunReport(
        run_id=resolved.config.id if valid else uuid4(),
        execution_status=execution_status,
        report_status=ReportStatus.PARTIAL,
        terminal_reason=reason,
        executive_summary="Execution stopped before browser navigation. No website was tested and no UX conclusions were generated.",
        scope=scope,
        protection=ProtectionSummary(
            target_requests=0,
            environment_validated=valid,
            network_boundary_validated=False,
            events=(ProtectionEvent(decision="blocked", layer="configuration", reason=reason),),
            cleanup_outcome="No browser, model process, or external resources were started.",
        ),
        cohort_results=CohortResults(
            requested_sessions=resolved.requested_sessions if valid else 0
        ),
        recommendations=(
            "Resolve the documented configuration issue or finish the browser execution phase before running a cohort.",
            "Require validated replica/network and generated-code isolation before enabling external application targets.",
        ),
        comparison="No baseline/candidate comparison exists because execution did not start.",
        review=ReviewSection(
            status="configuration_reviewed",
            method="Local schema/reference checks only; no browser navigation, network probe, or model call.",
            missing_evidence=(
                "Browser trajectories",
                "Screenshots",
                "Observed UX events",
                "Outcome measurements",
            ),
            limitations=(
                "This report contains configuration review only; autonomous cohort execution is unavailable.",
                "No UX issue, human abandonment cause, or network sandbox guarantee can be inferred from this report.",
            ),
        ),
    )


def blocked_report(reason, resolved=None):
    return unexecuted_report(reason, resolved, ExecutionStatus.BLOCKED)


def write_report(
    report: RunReport,
    artifact_root: Path,
    *,
    prepared_directory=False,
    recover_partial=False,
    output_directory: Path | None = None,
    cohort_root: Path | None = None,
):
    directory = output_directory or artifact_root / str(report.run_id)
    links_root = cohort_root or artifact_root.parent
    if recover_partial and (directory / "report.html").exists():
        raise FileExistsError("A completed report export already exists")
    if prepared_directory and any(
        (directory / f"report.{suffix}").exists() for suffix in ("json", "md", "html")
    ):
        raise FileExistsError("An exported report already exists")
    directory.mkdir(parents=True, exist_ok=prepared_directory or recover_partial)
    payload = report.model_dump(mode="json")
    sections = [
        ("Executive summary", report.executive_summary),
        ("Scope and reproducibility", payload["scope"]),
        ("Website protection", payload["protection"]),
        ("Cohort results", payload["cohort_results"]),
        (
            "Individual trajectories",
            payload["trajectory_index"]
            or payload["trajectories"]
            or "Unavailable: no browser trajectory was recorded.",
        ),
        ("UX findings", payload["findings"] or "None asserted; no observed UX evidence."),
        (
            "Visual evidence and heatmaps",
            {"heatmaps": payload["heatmaps"], "visual_evidence": payload["visual_evidence"]}
            if payload["heatmaps"]
            else payload["visual_evidence"]
            or "Unavailable: no screenshots or interactions were captured.",
        ),
        (
            "Abandonment explanations",
            payload["abandonment_explanations"]
            or "No synthetic abandonment diagnosis was asserted.",
        ),
        ("Recommendations", payload["recommendations"]),
        ("Comparison", report.comparison),
        ("Review and limitations", payload["review"]),
    ]
    if report.scope.phase >= 3:
        sections.insert(
            5,
            (
                "Autonomous planner decisions",
                payload["planner_decisions"]
                or "No model decision occurred; see the terminal reason and setup/protection evidence.",
            ),
        )
    if report.scope.phase >= 4:
        sections.insert(
            6,
            (
                "Observed friction events",
                payload["friction_events"] or "None detected from eligible application actions.",
            ),
        )
        sections.insert(
            7,
            (
                "Patience ledger and abandonment diagnosis",
                {
                    "ledger": payload["patience_ledger"],
                    "diagnosis": payload["abandonment_diagnosis"],
                },
            ),
        )
    if report.scope.phase >= 5:
        sections.insert(
            8,
            (
                "Cohort session results and reports",
                payload["session_summaries"] or "No session reports were produced.",
            ),
        )
    if report.scope.phase >= 6:
        sections.insert(
            5,
            (
                "Conversion milestones and eligible denominators",
                payload["milestone_funnel"] or "No eligible milestone denominator was available.",
            ),
        )
        sections.append(
            (
                "Evidence exclusions and unsupported claims",
                payload["exclusions"] or "No saved evidence was excluded from this audit.",
            )
        )
    markdown = [
        "# FrictionLab run report",
        "",
        f"Run: `{report.run_id}`",
        "",
        f"Execution: **{report.execution_status}**; report: **{report.report_status}**",
        "",
        f"Reason: {html.escape(report.terminal_reason)}",
        "",
    ]
    cards = []
    for title, value in sections:
        if isinstance(value, str):
            markdown.extend([f"## {title}", "", html.escape(value), ""])
            rendered = f"<p>{html.escape(value)}</p>"
        else:
            text = json.dumps(value, indent=2)
            markdown.extend([f"## {title}", "", "```json", text, "```", ""])
            rendered = f"<pre>{html.escape(text)}</pre>"
        cards.append(f"<section><h2>{html.escape(title)}</h2>{rendered}</section>")
    document = """<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
    <title>FrictionLab run report</title><style>body{font:16px system-ui;max-width:960px;
    margin:32px auto;padding:20px;background:#f3f6fb;color:#18253b}section{background:white;
    margin:16px 0;padding:20px;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}
    </style></head><body><h1>FrictionLab run report</h1>"""
    document += f"<p>Run: {report.run_id}; execution: {report.execution_status}; report: {report.report_status}</p>"
    document += f"<p>Reason: {html.escape(report.terminal_reason)}</p>"
    document += "".join(cards)
    if report.session_summaries:
        markdown.extend(["## Open individual session reports", ""])
        document += "<section><h2>Open individual session reports</h2><ul>"
        for item in report.session_summaries:
            relative = os.path.relpath(links_root / item.report_path, directory).replace("\\", "/")
            markdown.append(
                f"- [{item.persona_id} / {item.journey_id} ({item.execution_status})]({relative})"
            )
            document += (
                f'<li><a href="{html.escape(relative, quote=True)}">'
                f"{html.escape(item.persona_id)} / {html.escape(item.journey_id)} "
                f"({html.escape(str(item.execution_status))})</a></li>"
            )
        document += "</ul></section>"
        markdown.append("")
    if report.heatmaps:
        markdown.extend(["## Saved heatmaps", ""])
        document += "<section><h2>Saved heatmaps</h2>"
        for group in report.heatmaps:
            svg = (directory / group.svg_path).resolve()
            if not svg.is_relative_to(directory.resolve()) or not svg.is_file():
                continue
            encoded = base64.b64encode(svg.read_bytes()).decode()
            caption = f"{group.route} · {group.input_mode} · {len(group.points)} clicks · {group.rage_click_clusters} repeated-failure cluster(s)"
            markdown.append(f"- [{caption}]({group.svg_path})")
            document += (
                f"<figure><figcaption>{html.escape(caption)}</figcaption>"
                f'<img style="max-width:100%" alt="Synthetic click heatmap" '
                f'src="data:image/svg+xml;base64,{encoded}"></figure>'
            )
        document += "</section>"
        markdown.append("")
    for ref in report.visual_evidence:
        path = (directory / ref.path).resolve()
        if path.is_relative_to(directory.resolve()) and path.suffix == ".png" and path.is_file():
            encoded = base64.b64encode(path.read_bytes()).decode()
            document += f'<figure><figcaption>{html.escape(ref.path)}</figcaption><img style="max-width:100%" alt="Masked browser evidence" src="data:image/png;base64,{encoded}"></figure>'
    document += "</body></html>"
    for suffix, content in (
        ("json", json.dumps(payload, indent=2)),
        ("md", "\n".join(markdown)),
        ("html", document),
    ):
        final = directory / f"report.{suffix}"
        partial = directory / f"report.{suffix}.partial"
        with partial.open("w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        partial.replace(final)
    return directory
