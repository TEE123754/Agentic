"""Bounded local job execution with durable progress and terminal partial reports."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from frictionlab.assessment.catalog import catalog
from frictionlab.assessment.models import Check
from frictionlab.assessment.render import render_snapshot
from frictionlab.assessment.report import report_document, write_reports
from frictionlab.assessment.snapshot import capture_url, uploaded_snapshot
from frictionlab.planning.inference import InferenceSettings, safe_text


def read_settings(root):
    path = root / "app-settings.json"
    if not path.is_file():
        return InferenceSettings()
    return InferenceSettings.model_validate_json(path.read_text(encoding="utf-8"))


def save_settings(root, settings):
    root.mkdir(parents=True, exist_ok=True)
    temp = root / "app-settings.json.tmp"
    temp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    temp.replace(root / "app-settings.json")


async def ai_review(checks, settings):
    if settings.provider == "local":
        raise ValueError("Connect your own cloud provider key and select a model first")
    from frictionlab.planning.cloud_transport import CloudModelRuntime

    runtime = CloudModelRuntime(settings.model_copy(update={"max_requests": 1, "max_retries": 0}))
    findings = [
        {
            "id": c.id,
            "title": c.title,
            "severity": c.severity,
            "evidence": c.evidence[:2],
            "recommendation": c.recommendation,
        }
        for c in checks
        if c.status == "failed"
    ][:30]
    if not findings:
        return {
            "status": "skipped",
            "reason": "No failed checks to review; no provider request sent.",
        }
    try:
        await runtime.__aenter__()
        messages = [
            {
                "role": "system",
                "content": "Suggest practical fixes for the supplied verified findings only. Return JSON {advice: [{id: string, recommendation: string}]}. Do not invent findings, scores, execution evidence or claim real user behavior.",
            },
            {"role": "user", "content": safe_text(json.dumps(findings))},
        ]
        response = await asyncio.to_thread(
            runtime.complete, messages, 1200, time.monotonic() + settings.request_timeout_seconds
        )
        suggestions = json.loads(response["choices"][0]["message"]["content"])
        known = {c.id: c for c in checks if c.status == "failed"}
        if not isinstance(suggestions.get("advice"), list) or len(suggestions["advice"]) > 30:
            raise ValueError("Invalid model response")
        for item in suggestions["advice"]:
            if (
                not isinstance(item, dict)
                or item.get("id") not in known
                or not isinstance(item.get("recommendation"), str)
                or len(item["recommendation"]) > 2000
            ):
                raise ValueError("Ungrounded model response")
        for item in suggestions["advice"]:
            known[item["id"]].ai_recommendation = safe_text(item["recommendation"])
        return {
            "status": "complete",
            "scope": "Recommendations only; scores and findings are deterministic.",
            "provenance": runtime.provenance(),
        }
    finally:
        await runtime.close()


class Assessments:
    def __init__(self, root):
        self.root = Path(root)
        self.directory = self.root / "assessments"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.tasks, self.stops = {}, {}
        self.semaphore = asyncio.Semaphore(1)
        self.recover()

    def path(self, id):
        if str(uuid.UUID(id)) != id:
            raise ValueError("Invalid assessment identifier")
        return self.directory / id

    def progress(self, id, status, stage, percent):
        value = {"id": id, "status": status, "stage": stage, "percent": percent}
        path = self.path(id) / "progress.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value), encoding="utf-8")
        temp.replace(path)
        return value

    def recover(self):
        for directory in self.directory.iterdir():
            if not directory.is_dir():
                continue
            try:
                state = self.status(directory.name)
                if state["status"] in {"queued", "running"}:
                    report = self.report(directory.name)
                    report["execution_status"] = "interrupted"
                    report["limitations"].append(
                        "Application stopped before completion. Start a new assessment; this report retains partial evidence."
                    )
                    write_reports(directory, report)
                    self.progress(directory.name, "interrupted", "Stopped before completion", 100)
            except (OSError, ValueError, KeyError):
                continue

    def status(self, id):
        return json.loads((self.path(id) / "progress.json").read_text(encoding="utf-8"))

    def report(self, id):
        return json.loads((self.path(id) / "report.json").read_text(encoding="utf-8"))

    def list(self):
        result = []
        for p in sorted(self.directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[
            :100
        ]:
            try:
                result.append(self.status(p.name))
            except (OSError, ValueError):
                continue
        return result

    def submit(self, request):
        parts = urlsplit(request.url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise ValueError("Enter an HTTP(S) website URL without credentials")
        if sum(not t.done() for t in self.tasks.values()) >= 8:
            raise ValueError("Local queue is full; wait or cancel an assessment")
        id = str(uuid.uuid4())
        self.path(id).mkdir()
        self.stops[id] = threading.Event()
        check = Check(
            id="assessment.execution",
            category=request.categories[0],
            title="Assessment execution",
            status="incomplete",
            confidence=0,
            detail="Assessment is queued or in progress.",
        )
        write_reports(
            self.path(id),
            report_document(
                id,
                request,
                [check],
                {"target_requests": 0, "dispatch_status": "not_started"},
                [],
                [],
                "queued",
                {"status": "not_started"},
            ),
        )
        self.progress(id, "queued", "Waiting for local worker", 0)
        self.tasks[id] = asyncio.create_task(self.execute(id, request))
        return id

    def cancel(self, id):
        if id not in self.stops:
            raise ValueError("Assessment is no longer active")
        self.stops[id].set()

    async def execute(self, id, request):
        stop = self.stops[id]
        checks, limitations, evidence = [], [], []
        acquisition = {"mode": request.mode, "target_requests": 0, "dispatch_status": "not_started"}
        ai = {"status": "disabled"}
        state = "completed"
        try:
            async with self.semaphore:
                if stop.is_set():
                    raise ValueError("Cancelled")
                self.progress(id, "running", "Acquiring permitted evidence", 10)
                snapshot = None
                if request.mode == "snapshot":
                    snapshot = await asyncio.to_thread(uploaded_snapshot, request)
                elif request.mode == "capture":
                    acquisition = {
                        "mode": "approved_capture",
                        "target_requests": None,
                        "dispatch_status": "attempted",
                        "note": "Capture may have dispatched one GET; failure cannot prove zero contact.",
                    }
                    snapshot = await asyncio.to_thread(capture_url, request.url, stop)
                if snapshot:
                    acquisition = snapshot.acquisition
                    limitations += snapshot.limitations
                else:
                    limitations.append(
                        "URL-only mode does not resolve DNS or contact the website. Only URL syntax/scheme checks are available."
                    )
                checks = catalog(request, snapshot)
                self.progress(id, "running", "Checking offline structure and viewports", 35)
                if snapshot and not stop.is_set():
                    more, evidence, limits = await render_snapshot(
                        snapshot, request.categories, self.path(id), stop
                    )
                    checks += more
                    limitations += limits
                self.progress(id, "running", "Reviewing findings and generating report", 80)
                if request.ai_enabled and not stop.is_set():
                    try:
                        ai = await ai_review(checks, read_settings(self.root))
                    except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
                        ai = {
                            "status": "incomplete",
                            "reason": "AI recommendation review failed, key/model setup is missing, or quota was reached. No paid fallback; measured findings are retained.",
                        }
                        limitations.append(ai["reason"])
                if stop.is_set():
                    state = "cancelled"
                    checks.append(
                        Check(
                            id="assessment.cancelled",
                            category=request.categories[0],
                            title="Cancelled assessment",
                            status="incomplete",
                            confidence=0,
                            detail="Operator cancelled before all requested work finished.",
                        )
                    )
        except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
            state = "cancelled" if stop.is_set() else "failed"
            limitations.append(
                "Acquisition or assessment could not finish. Check snapshot format, capture policy, browser installation and local permissions; no rejected inputs or credentials are logged."
            )
            checks += catalog(request)
            checks.append(
                Check(
                    id="assessment.execution",
                    category=request.categories[0],
                    title="Assessment execution",
                    status="incomplete",
                    confidence=0,
                    detail="Assessment failed or was cancelled; results are partial.",
                )
            )
        finally:
            report = report_document(
                id, request, checks, acquisition, limitations, evidence, state, ai
            )
            write_reports(self.path(id), report)
            self.progress(
                id, state, "Report ready" if state == "completed" else "Partial report ready", 100
            )

    async def close(self):
        for stop in self.stops.values():
            stop.set()
        pending = [t for t in self.tasks.values() if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=50)
