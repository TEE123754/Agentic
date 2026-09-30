"""One DuckDB writer backed by an fsynced, replayable JSONL event journal."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import duckdb

SCHEMA = (
    (
        "CREATE TABLE IF NOT EXISTS events (event_id VARCHAR PRIMARY KEY, run_id VARCHAR NOT NULL, "
        "session_id VARCHAR, kind VARCHAR NOT NULL, occurred_at VARCHAR NOT NULL, payload VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS runs (run_id VARCHAR PRIMARY KEY, configuration_hash VARCHAR, "
        "status VARCHAR NOT NULL, report_status VARCHAR NOT NULL, report_revision INTEGER NOT NULL, "
        "manifest_path VARCHAR, created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL, detail VARCHAR)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS sessions (session_id VARCHAR PRIMARY KEY, run_id VARCHAR NOT NULL, "
        "persona_id VARCHAR NOT NULL, journey_id VARCHAR NOT NULL, repetition INTEGER NOT NULL, "
        "seed BIGINT NOT NULL, status VARCHAR NOT NULL, outcome VARCHAR, report_path VARCHAR, "
        "attempt INTEGER NOT NULL, parent_session_id VARCHAR, updated_at VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS steps (event_id VARCHAR PRIMARY KEY, session_id VARCHAR NOT NULL, "
        "step_index INTEGER NOT NULL, action_kind VARCHAR, result VARCHAR, payload VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS friction (event_id VARCHAR PRIMARY KEY, session_id VARCHAR NOT NULL, "
        "detector VARCHAR, confidence DOUBLE, payload VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS milestones (event_id VARCHAR PRIMARY KEY, session_id VARCHAR NOT NULL, "
        "name VARCHAR NOT NULL, passed BOOLEAN NOT NULL, payload VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS artifacts (event_id VARCHAR PRIMARY KEY, session_id VARCHAR NOT NULL, "
        "path VARCHAR NOT NULL, kind VARCHAR NOT NULL, payload VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS model_calls (event_id VARCHAR PRIMARY KEY, session_id VARCHAR NOT NULL, "
        "attempt INTEGER NOT NULL, status VARCHAR NOT NULL, payload VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS findings (event_id VARCHAR PRIMARY KEY, run_id VARCHAR NOT NULL, "
        "session_id VARCHAR, kind VARCHAR NOT NULL, payload VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS trace_spans (event_id VARCHAR PRIMARY KEY, run_id VARCHAR NOT NULL, "
        "session_id VARCHAR, trace_id VARCHAR NOT NULL, span_name VARCHAR NOT NULL, "
        "duration_seconds DOUBLE NOT NULL, payload VARCHAR NOT NULL)"
    ),
    (
        "CREATE TABLE IF NOT EXISTS report_jobs (run_id VARCHAR NOT NULL, revision INTEGER NOT NULL, "
        "status VARCHAR NOT NULL, report_path VARCHAR, updated_at VARCHAR NOT NULL, "
        "PRIMARY KEY (run_id, revision))"
    ),
)


class EventStore:
    """Single-process writer; API readers use this connection under the same lock."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "cohorts.duckdb"
        self.journal_path = self.root / "events.jsonl"
        self.lock = threading.RLock()
        self.connection = duckdb.connect(str(self.path))
        for statement in SCHEMA:
            self.connection.execute(statement)
        self.replay()

    def close(self):
        with self.lock:
            self.connection.close()

    def append(self, kind: str, run_id: str, payload: dict, session_id: str | None = None):
        event = {
            "event_id": str(uuid4()),
            "run_id": str(run_id),
            "session_id": str(session_id) if session_id else None,
            "kind": kind,
            "occurred_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        encoded = (json.dumps(event, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
        if len(encoded) > 256 * 1024:
            raise ValueError("Cohort journal event exceeds its size ceiling")
        with self.lock:
            with self.journal_path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            self._apply(event)
        return event["event_id"]

    def replay(self):
        if not self.journal_path.exists():
            return 0
        count = 0
        with self.lock, self.journal_path.open("rb+") as stream:
            while True:
                offset = stream.tell()
                line = stream.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    stream.truncate(offset)
                    break
                if len(line) > 256 * 1024:
                    raise ValueError("Oversized committed cohort journal event")
                event = json.loads(line)
                if set(event) != {
                    "event_id",
                    "run_id",
                    "session_id",
                    "kind",
                    "occurred_at",
                    "payload",
                }:
                    raise ValueError("Cohort journal contains an invalid event")
                count += self._apply(event)
        return count

    def _apply(self, event: dict):
        db = self.connection
        db.execute("BEGIN TRANSACTION")
        try:
            existing = db.execute(
                "SELECT 1 FROM events WHERE event_id = ?", [event["event_id"]]
            ).fetchone()
            if existing:
                db.execute("COMMIT")
                return 0
            payload = event["payload"]
            serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
            db.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                [
                    event["event_id"],
                    event["run_id"],
                    event["session_id"],
                    event["kind"],
                    event["occurred_at"],
                    serialized,
                ],
            )
            kind = event["kind"]
            rid, sid, at, eid = (
                event["run_id"],
                event["session_id"],
                event["occurred_at"],
                event["event_id"],
            )
            if kind == "run_created":
                db.execute(
                    "INSERT OR IGNORE INTO runs VALUES (?, ?, 'queued', 'pending', 0, ?, ?, ?, ?)",
                    [
                        rid,
                        payload["configuration_hash"],
                        payload["manifest_path"],
                        at,
                        at,
                        serialized,
                    ],
                )
            elif kind == "run_status":
                db.execute(
                    "UPDATE runs SET status = ?, updated_at = ?, detail = ? WHERE run_id = ?",
                    [payload["status"], at, serialized, rid],
                )
            elif kind == "session_queued":
                db.execute(
                    "INSERT OR IGNORE INTO sessions VALUES (?, ?, ?, ?, ?, ?, 'queued', "
                    "NULL, NULL, ?, ?, ?)",
                    [
                        sid,
                        rid,
                        payload["persona_id"],
                        payload["journey_id"],
                        payload["repetition"],
                        payload["seed"],
                        payload.get("attempt", 1),
                        payload.get("parent_session_id"),
                        at,
                    ],
                )
            elif kind == "session_started":
                db.execute(
                    "UPDATE sessions SET status = 'running', updated_at = ? WHERE session_id = ?",
                    [at, sid],
                )
            elif kind == "session_terminal":
                db.execute(
                    "UPDATE sessions SET status = ?, outcome = ?, report_path = ?, "
                    "updated_at = ? WHERE session_id = ?",
                    [
                        payload["status"],
                        payload.get("outcome"),
                        payload.get("report_path"),
                        at,
                        sid,
                    ],
                )
            elif kind == "report_job":
                db.execute(
                    "INSERT INTO report_jobs VALUES (?, ?, ?, ?, ?) ON CONFLICT (run_id, revision) "
                    "DO UPDATE SET status = EXCLUDED.status, report_path = EXCLUDED.report_path, "
                    "updated_at = EXCLUDED.updated_at",
                    [rid, payload["revision"], payload["status"], payload.get("report_path"), at],
                )
                db.execute(
                    "UPDATE runs SET report_status = ?, report_revision = ?, updated_at = ? "
                    "WHERE run_id = ?",
                    [payload["status"], payload["revision"], at, rid],
                )
            elif kind in {
                "step",
                "friction",
                "milestone",
                "artifact",
                "model_call",
                "finding",
                "trace_span",
            }:
                self._apply_detail(kind, eid, rid, sid, payload, serialized)
            elif kind != "cancellation_requested":
                raise ValueError("Unknown cohort journal event kind")
            db.execute("COMMIT")
            return 1
        except Exception:
            db.execute("ROLLBACK")
            raise

    def _apply_detail(self, kind, eid, rid, sid, payload, serialized):
        db = self.connection
        if kind == "step":
            db.execute(
                "INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?)",
                [
                    eid,
                    sid,
                    payload["step_index"],
                    payload.get("action_kind"),
                    payload.get("result"),
                    serialized,
                ],
            )
        elif kind == "friction":
            db.execute(
                "INSERT INTO friction VALUES (?, ?, ?, ?, ?)",
                [eid, sid, payload.get("detector"), payload.get("confidence"), serialized],
            )
        elif kind == "milestone":
            db.execute(
                "INSERT INTO milestones VALUES (?, ?, ?, ?, ?)",
                [eid, sid, payload["name"], payload["passed"], serialized],
            )
        elif kind == "artifact":
            db.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?)",
                [eid, sid, payload["path"], payload["kind"], serialized],
            )
        elif kind == "model_call":
            db.execute(
                "INSERT INTO model_calls VALUES (?, ?, ?, ?, ?)",
                [eid, sid, payload["attempt"], payload["status"], serialized],
            )
        elif kind == "finding":
            db.execute(
                "INSERT INTO findings VALUES (?, ?, ?, ?, ?)",
                [eid, rid, sid, payload["kind"], serialized],
            )
        else:
            db.execute(
                "INSERT INTO trace_spans VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    eid,
                    rid,
                    sid,
                    payload["trace_id"],
                    payload["span_name"],
                    payload["duration_seconds"],
                    serialized,
                ],
            )

    def rows(self, query: str, values=()):
        with self.lock:
            cursor = self.connection.execute(query, list(values))
            names = [field[0] for field in cursor.description]
            return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def run(self, run_id: str):
        rows = self.rows("SELECT * FROM runs WHERE run_id = ?", [str(run_id)])
        return rows[0] if rows else None

    def sessions(self, run_id: str):
        return self.rows(
            "SELECT * FROM sessions WHERE run_id = ? ORDER BY persona_id, "
            "journey_id, repetition, attempt",
            [str(run_id)],
        )

    def unfinished(self):
        return self.rows("SELECT * FROM sessions WHERE status IN ('queued', 'running')")

    def event_count(self, run_id: str):
        return self.rows("SELECT COUNT(*) AS count FROM events WHERE run_id = ?", [str(run_id)])[0][
            "count"
        ]
