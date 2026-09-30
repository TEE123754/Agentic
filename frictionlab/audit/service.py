"""Versioned audit export, recovery, and optional local finding review."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from frictionlab.audit.synthesis import AuditEngine
from frictionlab.contracts.models import RunReport
from frictionlab.reporting import write_report


class FindingReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["confirmed", "dismissed", "requires_investigation"]
    note: str = Field(min_length=1, max_length=2000)


def _revision_directory(root: Path, run_id: str, revision: int):
    return root / "reports" / run_id / "revisions" / str(revision)


def _write_assets(directory: Path, assets: dict[str, bytes]):
    directory.mkdir(parents=True, exist_ok=True)
    for relative, content in assets.items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Audit asset escapes the report revision")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)


def _record_findings(store, run_id: str, report: RunReport):
    for finding in report.findings:
        store.append(
            "finding",
            run_id,
            {
                "kind": finding.detector or "reviewed_finding",
                "finding_id": str(finding.id),
                "revision": report.revision,
                "finding": finding.model_dump(mode="json"),
            },
            event_id=str(uuid5(UUID(run_id), f"finding-event:{finding.id}")),
        )


def finalize_audit(root: Path, store, run_id: str):
    """Return a saved revision 2; preserve revision 1 on every synthesis fault."""
    root = Path(root).resolve()
    run_id = str(UUID(str(run_id)))
    base_path = root / "reports" / run_id / "report.json"
    if not base_path.is_file():
        return None
    directory = _revision_directory(root, run_id, 2)
    try:
        if (directory / "report.html").is_file():
            report = RunReport.model_validate_json(
                (directory / "report.json").read_text(encoding="utf-8")
            )
        else:
            base = RunReport.model_validate_json(base_path.read_text(encoding="utf-8"))
            product = AuditEngine(root, run_id).build(base, store.sessions(run_id))
            report = product.report
            store.append("report_job", run_id, {"revision": 2, "status": "reviewing"})
            _write_assets(directory, product.assets)
            write_report(
                report,
                root / "reports",
                output_directory=directory,
                cohort_root=root,
                recover_partial=True,
            )
        _record_findings(store, run_id, report)
        store.append(
            "report_job",
            run_id,
            {
                "revision": 2,
                "status": str(report.report_status),
                "report_path": str((directory / "report.html").relative_to(root)).replace(
                    "\\", "/"
                ),
            },
        )
        return report
    except Exception as exc:  # noqa: BLE001 -- revision 1 remains downloadable
        store.append(
            "report_job",
            run_id,
            {
                "revision": 2,
                "status": "failed",
                "reason": f"Offline audit synthesis/export failed ({type(exc).__name__}); revision 1 retained.",
            },
        )
        return None


def latest_report_path(root: Path, store, run_id: str, format_name="json", revision=None):
    root = Path(root).resolve()
    rows = store.rows(
        "SELECT revision, status, report_path FROM report_jobs WHERE run_id = ? "
        "ORDER BY revision DESC",
        [str(run_id)],
    )
    for row in rows:
        if revision is not None and row["revision"] != revision:
            continue
        if row["status"] not in {"ready", "partial"} or not row["report_path"]:
            continue
        html_path = (root / row["report_path"]).resolve()
        if not html_path.is_relative_to(root) or not html_path.is_file():
            continue
        requested = html_path.with_name(f"report.{format_name}")
        if requested.is_file():
            return requested
    return None


def review_finding(root: Path, store, run_id: str, finding_id: str, review: FindingReviewInput):
    """Write a new immutable report revision from saved evidence only."""
    root = Path(root).resolve()
    run_id, finding_id = str(UUID(str(run_id))), str(UUID(str(finding_id)))
    current_path = latest_report_path(root, store, run_id, "json")
    if current_path is None:
        raise ValueError("No completed audit report is available for review")
    current = RunReport.model_validate_json(current_path.read_text(encoding="utf-8"))
    if current.revision < 2 or finding_id not in {str(item.id) for item in current.findings}:
        raise ValueError("Finding is absent from the latest reviewed audit")
    data = current.model_dump(mode="json")
    revision = current.revision + 1
    while (_revision_directory(root, run_id, revision) / "report.html").is_file():
        revision += 1
    data["revision"] = revision
    data["created_at"] = datetime.now(UTC).isoformat()
    for item in data["review"]["dispositions"]:
        if item["finding_id"] == finding_id:
            item.update(status=review.status, note=review.note)
    data["review"]["method"] = (
        "Offline evidence validation plus a recorded human finding disposition; no browser or target revisit."
    )
    report = RunReport.model_validate(data)
    destination = _revision_directory(root, run_id, report.revision)
    if destination.exists() and (destination / "report.html").is_file():
        raise ValueError("Report revision already exists; reload the latest report")
    assets = {}
    references = {ref.path for ref in report.visual_evidence}
    references.update(ref.path for finding in report.findings for ref in finding.evidence)
    references.update(group.svg_path for group in report.heatmaps)
    references.update(group.svg_path.replace(".svg", ".json") for group in report.heatmaps)
    for relative in references:
        source = (current_path.parent / relative).resolve()
        if not source.is_relative_to(current_path.parent.resolve()) or not source.is_file():
            raise ValueError("Prior audit asset is missing; human review cannot be exported")
        assets[relative] = source.read_bytes()
    _write_assets(destination, assets)
    store.append("report_job", run_id, {"revision": report.revision, "status": "reviewing"})
    try:
        write_report(
            report,
            root / "reports",
            output_directory=destination,
            cohort_root=root,
            recover_partial=True,
        )
        store.append(
            "report_job",
            run_id,
            {
                "revision": report.revision,
                "status": str(report.report_status),
                "report_path": str((destination / "report.html").relative_to(root)).replace(
                    "\\", "/"
                ),
            },
        )
    except Exception as exc:
        store.append(
            "report_job",
            run_id,
            {
                "revision": report.revision,
                "status": "failed",
                "reason": f"Human review export failed ({type(exc).__name__}); prior revision retained.",
            },
        )
        raise
    return report
