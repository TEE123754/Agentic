"""Local fixture API with opt-in, owned-fixture cohort execution."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from frictionlab import __version__
from frictionlab.audit.service import FindingReviewInput, latest_report_path
from frictionlab.configuration import (
    CONFIG_DIRECTORY,
    DEFAULT_ORIGIN,
    ROOT,
    ConfigurationRejected,
    resolve_run,
)
from frictionlab.contracts.models import FIXTURE_BUILD, RunReport, validate_origin
from frictionlab.dashboard.read_model import catalog, list_runs, progress
from frictionlab.fixtures.store import (
    CheckoutInput,
    CreateFixtureRun,
    FixtureStore,
    Integration,
    MockInput,
    SentinelInput,
)
from frictionlab.reporting import blocked_report, write_report

ASSETS = Path(__file__).parent / "fixtures" / "web"


def create_app(
    config_directory=CONFIG_DIRECTORY,
    artifact_root=None,
    origin=DEFAULT_ORIGIN,
    *,
    enable_cohorts=False,
    cohort_root=None,
    cohort_settings=None,
    cohort_executor=None,
):
    validate_origin(origin, loopback=True)
    coordinator = None
    if enable_cohorts:
        from frictionlab.cohorts.coordinator import CohortCoordinator, CohortSettings

        coordinator = CohortCoordinator(
            cohort_root, settings=cohort_settings or CohortSettings(), executor=cohort_executor
        )

    @asynccontextmanager
    async def lifespan(_app):
        if coordinator:
            await coordinator.start()
        try:
            yield
        finally:
            if coordinator:
                await coordinator.close()

    app = FastAPI(title="FrictionLab", version=__version__, lifespan=lifespan)
    app.state.cohorts = coordinator
    app.state.fixture = FixtureStore()
    app.state.artifact_root = (
        Path(artifact_root) if artifact_root else ROOT / "artifacts" / "phase1" / "runs"
    )
    app.state.origin = origin

    def require_namespace(run_id):
        try:
            return app.state.fixture.snapshot(run_id)
        except KeyError as exc:
            raise HTTPException(404, "Fixture namespace does not exist") from exc

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "phase": 6 if coordinator else 2,
            "build_id": FIXTURE_BUILD,
            "execution_enabled": bool(coordinator),
        }

    @app.get("/")
    def storefront():
        return FileResponse(ASSETS / "index.html", media_type="text/html")

    @app.get("/assets/{name}")
    def asset(name: Literal["app.js", "style.css"]):
        return FileResponse(
            ASSETS / name, media_type="text/javascript" if name.endswith(".js") else "text/css"
        )

    @app.post("/configuration/review")
    def review_configuration(payload: dict):
        try:
            resolved = resolve_run(payload, config_directory, origin)
        except ConfigurationRejected as exc:
            return persist_blocked_report(str(exc))
        return {
            "configuration_valid": True,
            "execution_enabled": bool(coordinator),
            "configuration_hash": resolved.configuration_hash,
            "requested_sessions": resolved.requested_sessions,
            "environment": resolved.environment.id,
            "message": "Configuration validated for the owned-fixture cohort."
            if coordinator
            else "Configuration validated locally. Autonomous cohort execution is unavailable.",
        }

    def persist_blocked_report(reason, resolved=None):
        report = blocked_report(reason, resolved)
        try:
            write_report(report, app.state.artifact_root)
        except FileExistsError as exc:
            raise HTTPException(
                409, "A report already exists for this run ID; use a new run ID"
            ) from exc
        return JSONResponse(
            status_code=409,
            content={
                "configuration_valid": resolved is not None,
                "execution_enabled": False,
                "report": report.model_dump(mode="json"),
                "downloads": {
                    fmt: f"/reports/{report.run_id}/{fmt}" for fmt in ("json", "md", "html")
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        if request.url.path in {"/runs", "/configuration/review"}:
            return persist_blocked_report(
                "Run request must contain a valid JSON configuration object."
            )
        # Never echo submitted synthetic credentials or rejected body values.
        return JSONResponse(
            status_code=422, content={"detail": "Request does not match the endpoint contract"}
        )

    @app.post("/runs")
    async def start_run(
        payload: dict,
        variant: Literal[
            "healthy",
            "generic_validation",
            "dead_button",
            "delayed_feedback",
            "hidden_shipping",
            "focus_trap",
        ] = "healthy",
    ):
        try:
            resolved = resolve_run(payload, config_directory, origin)
        except ConfigurationRejected as exc:
            return persist_blocked_report(str(exc))
        if coordinator:
            try:
                result = await coordinator.submit(resolved, variant=variant)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            return JSONResponse(status_code=202, content=result)
        return persist_blocked_report(
            "Autonomous cohorts are unavailable until planning, isolated workers, and orchestration are implemented. The Phase 2 browser demo supports only owned local fixtures.",
            resolved,
        )

    @app.get("/dashboard/catalog")
    def dashboard_catalog():
        result = catalog(config_directory)
        result["execution_enabled"] = bool(coordinator)
        if coordinator:
            result["workers"] = coordinator.settings.workers
            result["max_cohort_sessions"] = coordinator.settings.max_sessions
        return result

    @app.get("/dashboard/runs")
    def dashboard_runs():
        return list_runs(coordinator.store) if coordinator else {"runs": []}

    @app.get("/dashboard/runs/{run_id}/progress")
    def dashboard_progress(run_id: UUID):
        result = progress(coordinator.root, coordinator.store, str(run_id)) if coordinator else None
        if result is None:
            raise HTTPException(404, "Cohort does not exist")
        return result

    def session_report(run_id: UUID, session_id: UUID):
        if not coordinator or not coordinator.store.run(str(run_id)):
            raise HTTPException(404, "Cohort does not exist")
        row = next(
            (
                item
                for item in coordinator.store.sessions(str(run_id))
                if item["session_id"] == str(session_id)
            ),
            None,
        )
        if row is None or not row["report_path"]:
            raise HTTPException(404, "Session report is not available")
        directory = coordinator.root / "runs" / str(run_id) / "sessions" / str(session_id)
        expected = (directory / "report.html").resolve()
        actual = (coordinator.root / row["report_path"]).resolve()
        if actual != expected or not actual.is_file():
            raise HTTPException(404, "Session report is not available")
        report_path = directory / "report.json"
        if not report_path.is_file():
            raise HTTPException(404, "Session report is not available")
        return directory, RunReport.model_validate_json(report_path.read_text(encoding="utf-8"))

    @app.get("/dashboard/runs/{run_id}/sessions/{session_id}/report")
    def dashboard_session_report(run_id: UUID, session_id: UUID):
        _, report = session_report(run_id, session_id)
        return report.model_dump(mode="json")

    @app.get("/dashboard/runs/{run_id}/sessions/{session_id}/observations/{observation_id}")
    def dashboard_observation(run_id: UUID, session_id: UUID, observation_id: UUID):
        directory, report = session_report(run_id, session_id)
        known = {step.observation_before for step in report.trajectories}
        known.update(
            step.observation_after for step in report.trajectories if step.observation_after
        )
        if observation_id not in known:
            raise HTTPException(404, "Observation is not part of this session")
        path = directory / "evidence" / f"{observation_id}.observation.json"
        if not path.is_file() or path.stat().st_size > 256 * 1024:
            raise HTTPException(404, "Observation is unavailable")
        from frictionlab.browser.evidence import BrowserObservation

        value = BrowserObservation.model_validate_json(path.read_text(encoding="utf-8"))
        if value.id != observation_id:
            raise HTTPException(404, "Observation is unavailable")
        return {
            "id": str(value.id),
            "route": value.route,
            "viewport": value.viewport.model_dump(mode="json"),
            "focus": value.focus,
            "validation": list(value.validation),
            "semantic_text": value.semantic_text[:2000],
            "screenshot_available": any(
                ref.path == f"evidence/{observation_id}.png" for ref in value.evidence
            ),
        }

    @app.get("/dashboard/runs/{run_id}/sessions/{session_id}/screenshots/{observation_id}")
    def dashboard_screenshot(run_id: UUID, session_id: UUID, observation_id: UUID):
        directory, report = session_report(run_id, session_id)
        known = {step.observation_before for step in report.trajectories}
        known.update(
            step.observation_after for step in report.trajectories if step.observation_after
        )
        if observation_id not in known:
            raise HTTPException(404, "Screenshot is not part of this session")
        path = directory / "evidence" / f"{observation_id}.png"
        if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
            raise HTTPException(404, "Screenshot is unavailable")
        return FileResponse(path, media_type="image/png")

    @app.get("/dashboard/reports/{run_id}/heatmaps/{group_id}")
    def dashboard_heatmap(run_id: UUID, group_id: str):
        if not coordinator:
            raise HTTPException(404, "Audit is unavailable")
        report_path = latest_report_path(coordinator.root, coordinator.store, str(run_id))
        if report_path is None:
            raise HTTPException(404, "Audit is unavailable")
        report = RunReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        group = next((item for item in report.heatmaps if item.id == group_id), None)
        if group is None:
            raise HTTPException(404, "Heatmap is unavailable")
        path = (report_path.parent / group.svg_path).resolve()
        if not path.is_relative_to(report_path.parent.resolve()) or not path.is_file():
            raise HTTPException(404, "Heatmap is unavailable")
        return FileResponse(
            path,
            media_type="image/svg+xml",
            headers={"Content-Security-Policy": "default-src 'none'; img-src data:"},
        )

    @app.get("/dashboard/reports/{run_id}/evidence/{name}")
    def dashboard_finding_evidence(run_id: UUID, name: str):
        if not coordinator or "/" in name or "\\" in name:
            raise HTTPException(404, "Evidence is unavailable")
        report_path = latest_report_path(coordinator.root, coordinator.store, str(run_id))
        if report_path is None:
            raise HTTPException(404, "Evidence is unavailable")
        report = RunReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        relative = f"evidence/{name}"
        allowed = {ref.path for finding in report.findings for ref in finding.evidence}
        allowed.update(ref.path for ref in report.visual_evidence)
        if relative not in allowed:
            raise HTTPException(404, "Evidence is unavailable")
        path = (report_path.parent / relative).resolve()
        if not path.is_relative_to(report_path.parent.resolve()) or not path.is_file():
            raise HTTPException(404, "Evidence is unavailable")
        media = "image/png" if path.suffix == ".png" else "text/plain"
        return FileResponse(
            path, media_type=media, headers={"Content-Security-Policy": "default-src 'none'"}
        )

    @app.get("/runs/{run_id}")
    def cohort_status(run_id: UUID):
        result = coordinator.status(str(run_id)) if coordinator else None
        if result is None:
            raise HTTPException(404, "Cohort does not exist")
        return result

    @app.post("/runs/{run_id}/cancel")
    async def cancel_cohort(run_id: UUID):
        if not coordinator:
            raise HTTPException(404, "Cohort does not exist")
        try:
            return await coordinator.cancel(str(run_id))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/runs/{run_id}/sessions/{session_id}/cancel")
    async def cancel_session(run_id: UUID, session_id: UUID):
        if not coordinator:
            raise HTTPException(404, "Cohort does not exist")
        try:
            return await coordinator.cancel(str(run_id), str(session_id))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/runs/{run_id}/sessions/{session_id}/retry")
    async def retry_interrupted(run_id: UUID, session_id: UUID):
        if not coordinator:
            raise HTTPException(404, "Cohort does not exist")
        try:
            result = await coordinator.retry_interrupted(str(run_id), str(session_id))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return JSONResponse(status_code=202, content=result)

    @app.get("/reports/{run_id}/{format_name}")
    def report_download(run_id: UUID, format_name: Literal["json", "md", "html"]):
        path = app.state.artifact_root / str(run_id) / f"report.{format_name}"
        if coordinator and not path.is_file() and coordinator.store.run(str(run_id)):
            path = latest_report_path(coordinator.root, coordinator.store, str(run_id), format_name)
        if path is None or not path.is_file():
            raise HTTPException(404, "Report does not exist")
        media = {"json": "application/json", "md": "text/markdown", "html": "text/html"}[
            format_name
        ]
        return FileResponse(path, media_type=media, filename=f"frictionlab-{run_id}.{format_name}")

    @app.get("/reports/{run_id}/revisions/{revision}/{format_name}")
    def report_revision(run_id: UUID, revision: int, format_name: Literal["json", "md", "html"]):
        if not coordinator or revision < 1:
            raise HTTPException(404, "Report revision does not exist")
        path = latest_report_path(
            coordinator.root, coordinator.store, str(run_id), format_name, revision=revision
        )
        if path is None or not path.is_file():
            raise HTTPException(404, "Report revision does not exist")
        media = {"json": "application/json", "md": "text/markdown", "html": "text/html"}[
            format_name
        ]
        return FileResponse(path, media_type=media, filename=f"frictionlab-{run_id}.{format_name}")

    @app.post("/runs/{run_id}/findings/{finding_id}/review")
    async def review_audit_finding(run_id: UUID, finding_id: UUID, body: FindingReviewInput):
        if not coordinator:
            raise HTTPException(404, "Cohort does not exist")
        try:
            report = await coordinator.review_finding(str(run_id), str(finding_id), body)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "run_id": str(run_id),
            "revision": report.revision,
            "report_status": str(report.report_status),
            "review": report.review.model_dump(mode="json"),
        }

    @app.post("/fixture/runs")
    def create_fixture_run(body: CreateFixtureRun):
        try:
            return app.state.fixture.create(body.run_id, body.variant)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/fixture/runs/{run_id}")
    def fixture_state(run_id: UUID):
        return require_namespace(run_id)

    @app.post("/fixture/runs/{run_id}/accounts")
    def account(run_id: UUID):
        require_namespace(run_id)
        return app.state.fixture.account(run_id)

    @app.post("/fixture/runs/{run_id}/checkout")
    def checkout(run_id: UUID, body: CheckoutInput):
        require_namespace(run_id)
        value = app.state.fixture.checkout(run_id, body.email)
        return JSONResponse(status_code=200 if value["ok"] else 422, content=value)

    @app.post("/fixture/runs/{run_id}/integration/{integration}")
    def integration(run_id: UUID, integration: Integration, body: MockInput):
        require_namespace(run_id)
        return app.state.fixture.mock(run_id, integration, body.operation)

    @app.post("/fixture/runs/{run_id}/reset")
    def reset(run_id: UUID):
        require_namespace(run_id)
        return app.state.fixture.reset(run_id)

    @app.post("/fixture/runs/{run_id}/order")
    def prohibited_order(run_id: UUID):
        require_namespace(run_id)
        raise HTTPException(403, "Orders are prohibited; the fixture ends at order review")

    @app.post("/fixture/sentinel/attempt")
    def sentinel_attempt(body: SentinelInput):
        return JSONResponse(
            status_code=403, content=app.state.fixture.reject_sentinel(body.destination)
        )

    return app
