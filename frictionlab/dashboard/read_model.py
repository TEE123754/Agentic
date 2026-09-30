"""Bounded, read-only dashboard projections from owned cohort artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from frictionlab.configuration import load_reference
from frictionlab.contracts.models import EnvironmentPolicy, Journey, Persona


def catalog(directory: Path):
    environment = load_reference(directory, "environments", "local_storefront", EnvironmentPolicy)
    profiles = [
        load_reference(directory, "personas", path.stem, Persona)
        for path in sorted((directory / "personas").glob("*.json"))
    ]
    journeys = [
        load_reference(directory, "journeys", path.stem, Journey)
        for path in sorted((directory / "journeys").glob("*.json"))
    ]
    return {
        "environment": {
            "id": environment.id,
            "origin": environment.replica_origins[0],
            "build_id": environment.build_id,
            "scope": environment.execution_scope,
            "data_mode": environment.data_mode,
            "mocks": list(environment.integration_mocks),
            "prohibited_operations": list(environment.prohibited_operations),
            "limits": environment.limits.model_dump(mode="json"),
            "isolation": environment.isolation.model_dump(mode="json"),
        },
        "profiles": [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "viewport": item.device.viewport.model_dump(mode="json"),
                "input_mode": item.device.input_mode,
            }
            for item in profiles
        ],
        "journeys": [
            {
                "id": item.id,
                "description": item.goal,
                "completion": [criterion.id for criterion in item.completion],
            }
            for item in journeys
        ],
        "max_cohort_sessions": 6,
    }


def list_runs(store, limit=30):
    rows = store.rows(
        "SELECT run_id, status, report_status, report_revision, created_at, updated_at "
        "FROM runs ORDER BY created_at DESC LIMIT ?",
        [limit],
    )
    return {"runs": rows}


def _read_small_json(path: Path, limit=256 * 1024):
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def progress(root: Path, store, run_id: str):
    run_id = str(UUID(str(run_id)))
    run = store.run(run_id)
    if run is None:
        return None
    started = store.rows(
        "SELECT session_id, MIN(occurred_at) AS started_at FROM events "
        "WHERE run_id = ? AND kind = 'session_started' GROUP BY session_id",
        [run_id],
    )
    started_at = {row["session_id"]: row["started_at"] for row in started}
    now = datetime.now(UTC)
    sessions = []
    for row in store.sessions(run_id):
        sid = row["session_id"]
        evidence = root / "runs" / run_id / "sessions" / sid / "evidence"
        actions = _read_small_json(evidence / "actions.json") or []
        cognition = _read_small_json(evidence / "cognitive-state.json") or {}
        last = actions[-1] if isinstance(actions, list) and actions else {}
        started_text = started_at.get(sid)
        elapsed = None
        if started_text:
            end = now if row["status"] == "running" else datetime.fromisoformat(row["updated_at"])
            elapsed = max(0, round((end - datetime.fromisoformat(started_text)).total_seconds(), 1))
        sessions.append(
            {
                "session_id": sid,
                "persona_id": row["persona_id"],
                "journey_id": row["journey_id"],
                "status": row["status"],
                "outcome": row["outcome"],
                "elapsed_seconds": elapsed,
                "step_count": len(actions) if isinstance(actions, list) else 0,
                "last_action": last.get("action", {}).get("kind")
                if isinstance(last, dict)
                else None,
                "last_result": last.get("result") if isinstance(last, dict) else None,
                "patience_remaining": cognition.get("remaining"),
            }
        )
    return {
        "run_id": run_id,
        "execution_status": run["status"],
        "report_status": run["report_status"],
        "report_revision": run["report_revision"],
        "sessions": sessions,
    }
