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
from frictionlab.configuration import (
    CONFIG_DIRECTORY,
    DEFAULT_ORIGIN,
    ROOT,
    ConfigurationRejected,
    resolve_run,
)
from frictionlab.contracts.models import FIXTURE_BUILD, validate_origin
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
            "phase": 5 if coordinator else 2,
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

    @app.get("/reports/{run_id}/{format_name}")
    def report_download(run_id: UUID, format_name: Literal["json", "md", "html"]):
        path = app.state.artifact_root / str(run_id) / f"report.{format_name}"
        if coordinator and not path.is_file() and coordinator.store.run(str(run_id)):
            path = coordinator.root / "reports" / str(run_id) / f"report.{format_name}"
        if not path.is_file():
            raise HTTPException(404, "Report does not exist")
        media = {"json": "application/json", "md": "text/markdown", "html": "text/html"}[
            format_name
        ]
        return FileResponse(path, media_type=media, filename=f"frictionlab-{run_id}.{format_name}")

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
