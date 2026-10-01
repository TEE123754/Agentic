"""Saved-evidence matched comparison with explicit comparability checks."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from frictionlab.audit.service import latest_report_path
from frictionlab.contracts.models import RunReport, SessionOutcome


def _findings(report):
    return {(item.detector or "", item.route, item.target_name): item for item in report.findings}


def _session_key(item):
    return item.persona_id, item.journey_id, item.repetition, item.seed


def _read(root: Path, store, run_id: str):
    run_id = str(UUID(run_id))
    path = latest_report_path(root, store, run_id)
    manifest = root / "runs" / run_id / "manifest.json"
    if path is None or not manifest.is_file():
        raise ValueError("Both matched runs need saved reports and manifests")
    return (
        RunReport.model_validate_json(path.read_text(encoding="utf-8")),
        json.loads(manifest.read_text(encoding="utf-8")),
        path.parent,
    )


def _evidence_status(report, directory):
    missing = []
    for finding in report.findings:
        for ref in finding.evidence:
            path = (directory / ref.path).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file():
                missing.append(str(ref.path))
    return {
        "finding_references": sum(len(item.evidence) for item in report.findings),
        "missing": missing,
    }


def _inference_identities(root, report):
    """Prefer actual session provenance over a requested model label in a manifest."""
    identities = {}
    for summary in report.session_summaries:
        path = (root / summary.report_path).with_name("report.json").resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Matched comparison needs each saved session report")
        session = RunReport.model_validate_json(path.read_text(encoding="utf-8"))
        metadata = session.scope.runtime_metadata
        inference = metadata.get("inference")
        if inference:
            inference = json.loads(inference)
            models = inference.get("actual_models", [])
            if not inference.get("strict_comparable") or len(models) != 1:
                raise ValueError(
                    "Mixed or unverified inference identity excludes strict comparison"
                )
            identities[_session_key(summary)] = (
                inference.get("provider"),
                tuple(models),
                metadata.get("model_sha256"),
                metadata.get("model_revision"),
            )
    return identities


def compare_runs(root: Path, store, baseline_id: str, candidate_id: str):
    """Compare two immutable audited runs without opening a browser or target URL."""
    root = Path(root).resolve()
    if baseline_id == candidate_id:
        raise ValueError("Select distinct baseline and candidate runs")
    baseline, base_manifest, base_dir = _read(root, store, baseline_id)
    candidate, next_manifest, next_dir = _read(root, store, candidate_id)
    equal_fields = (
        "configuration_hash",
        "environment",
        "profiles",
        "journeys",
        "model",
        "detector_policy",
        "workers",
        "scope",
    )
    mismatches = [
        field for field in equal_fields if base_manifest.get(field) != next_manifest.get(field)
    ]
    base_specs = [
        {key: item[key] for key in ("persona_id", "journey_id", "repetition", "seed")}
        for item in base_manifest["sessions"]
    ]
    next_specs = [
        {key: item[key] for key in ("persona_id", "journey_id", "repetition", "seed")}
        for item in next_manifest["sessions"]
    ]
    if base_specs != next_specs:
        mismatches.append("sampled_sessions")
    if mismatches:
        raise ValueError("Runs are not matched: " + ", ".join(mismatches))
    if _inference_identities(root, baseline) != _inference_identities(root, candidate):
        raise ValueError("Actual provider/model identities do not match")
    if baseline.revision < 2 or candidate.revision < 2:
        raise ValueError("Both runs need completed audit revisions")
    base_sessions = {_session_key(item): item for item in baseline.session_summaries}
    next_sessions = {_session_key(item): item for item in candidate.session_summaries}
    if base_sessions.keys() != next_sessions.keys():
        raise ValueError("Saved session samples do not match")
    paired = []
    for key in sorted(base_sessions):
        old, new = base_sessions[key], next_sessions[key]
        paired.append(
            {
                "persona_id": key[0],
                "journey_id": key[1],
                "repetition": key[2],
                "seed": key[3],
                "baseline_outcome": str(old.outcome) if old.outcome else None,
                "candidate_outcome": str(new.outcome) if new.outcome else None,
                "baseline_eligible": old.outcome
                in {
                    SessionOutcome.COMPLETED,
                    SessionOutcome.ABANDONED_PATIENCE,
                    SessionOutcome.ABANDONED_REQUIREMENT,
                },
                "candidate_eligible": new.outcome
                in {
                    SessionOutcome.COMPLETED,
                    SessionOutcome.ABANDONED_PATIENCE,
                    SessionOutcome.ABANDONED_REQUIREMENT,
                },
            }
        )
    base_findings, next_findings = _findings(baseline), _findings(candidate)

    def describe(keys, source):
        return [
            {
                "detector": key[0],
                "route": key[1],
                "target": key[2],
                "title": source[key].title,
                "severity": source[key].severity,
                "confidence": source[key].confidence,
            }
            for key in sorted(keys)
        ]

    base_protection = baseline.protection
    next_protection = candidate.protection
    return {
        "baseline_run_id": str(baseline.run_id),
        "candidate_run_id": str(candidate.run_id),
        "baseline_variant": base_manifest["variant"],
        "candidate_variant": next_manifest["variant"],
        "matched": True,
        "model": base_manifest["model"],
        "detector_policy": base_manifest["detector_policy"],
        "paired_sessions": paired,
        "raw_counts": {
            "baseline": baseline.cohort_results.model_dump(mode="json"),
            "candidate": candidate.cohort_results.model_dump(mode="json"),
        },
        "completion_delta": candidate.cohort_results.outcome_counts.get(SessionOutcome.COMPLETED, 0)
        - baseline.cohort_results.outcome_counts.get(SessionOutcome.COMPLETED, 0),
        "resolved_findings": describe(base_findings.keys() - next_findings.keys(), base_findings),
        "new_findings": describe(next_findings.keys() - base_findings.keys(), next_findings),
        "persistent_findings": describe(base_findings.keys() & next_findings.keys(), next_findings),
        "report_completeness": {
            "baseline": {
                "status": str(baseline.report_status),
                "missing_evidence": list(baseline.review.missing_evidence),
                **_evidence_status(baseline, base_dir),
            },
            "candidate": {
                "status": str(candidate.report_status),
                "missing_evidence": list(candidate.review.missing_evidence),
                **_evidence_status(candidate, next_dir),
            },
        },
        "protection": {
            "declared_boundary": base_manifest["environment"]["isolation"]["boundary"],
            "baseline_observed": {
                "scope": base_protection.boundary_scope,
                "sentinel_requests": base_protection.sentinel_requests,
                "sentinel_data_unchanged": base_protection.sentinel_data_unchanged,
            },
            "candidate_observed": {
                "scope": next_protection.boundary_scope,
                "sentinel_requests": next_protection.sentinel_requests,
                "sentinel_data_unchanged": next_protection.sentinel_data_unchanged,
            },
        },
        "limitations": [
            "Synthetic fixture cohorts, not human conversion or churn estimates.",
            "Only observed supported browser/fixture traffic is covered by the sentinel.",
        ],
    }
