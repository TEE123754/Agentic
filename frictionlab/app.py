"""Authenticated loopback-only desktop/CLI dashboard."""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from frictionlab.assessment.models import AssessmentRequest
from frictionlab.assessment.report import export_zip
from frictionlab.assessment.service import Assessments, read_settings, save_settings
from frictionlab.credentials import get_key, save_key, storage_available
from frictionlab.planning.inference import InferenceSettings


class Connection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    key: str = Field(min_length=8, max_length=4096)
    model: str = Field(min_length=1, max_length=120)
    remember: bool = False
    share_findings: bool = False
    free_tier_confirmed: bool = False


def connect(root, value):
    settings = InferenceSettings(
        provider=value.provider,
        model=value.model,
        allow_remote=True,
        share_sanitized_state=value.share_findings,
        free_tier_confirmed=value.free_tier_confirmed,
        max_requests=1,
        max_tokens=24000,
        max_retries=0,
        max_runtime_seconds=45,
        request_timeout_seconds=30,
    )
    save_key(value.provider, value.key, remember=value.remember)
    save_settings(root, settings)


def create_app(root, port, *, token=None):
    token = token or secrets.token_urlsafe(32)
    root = Path(root)
    service = Assessments(root)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await service.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.assessments = service
    app.state.token = token
    authorities = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {"http://" + a for a in authorities}

    @app.middleware("http")
    async def boundary(request, call_next):
        if request.headers.get("host") not in authorities:
            return JSONResponse({"detail": "Loopback host required"}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None and origin not in origins:
            return JSONResponse({"detail": "Same-origin request required"}, status_code=403)
        if request.url.path.startswith("/api/") and not secrets.compare_digest(
            request.headers.get("x-frictionlab-token", ""), token
        ):
            return JSONResponse({"detail": "Dashboard authorization required"}, status_code=403)
        try:
            if int(request.headers.get("content-length", "0")) > 15_000_000:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid request size"}, status_code=400)
        # Bound chunked bodies too, before validation retains or echoes any input.
        if request.method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 15_000_000:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            }
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse(
            {"detail": "Invalid input. Check the URL, provider policy and snapshot limits."},
            status_code=422,
        )

    @app.exception_handler(ValueError)
    async def rejected(request, exc):
        return JSONResponse(
            {
                "detail": "Request rejected. Check required acknowledgements, credentials, URL/snapshot format and queue capacity."
            },
            status_code=400,
        )

    @app.get("/")
    def home():
        text = (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(text.replace("__TOKEN__", token))

    @app.get("/assets/{name}")
    def asset(name: str):
        if name not in {"app.js", "app.css"}:
            raise HTTPException(404)
        return Response(
            (Path(__file__).parent / "web" / name).read_bytes(),
            media_type="text/javascript" if name.endswith("js") else "text/css",
        )

    @app.get("/api/settings")
    def settings():
        current = read_settings(root)
        return {
            "provider": current.provider,
            "model": current.model,
            "connected": bool(get_key(current.provider)),
            "secure_storage_available": storage_available(),
            "sharing": current.share_sanitized_state,
        }

    @app.post("/api/settings")
    def configure(value: Connection):
        connect(root, value)
        return {"connected": True, "storage": "native_os" if value.remember else "process_memory"}

    @app.post("/api/assessments", status_code=202)
    async def start(value: AssessmentRequest):
        return {"id": service.submit(value)}

    @app.get("/api/assessments")
    def listing():
        return service.list()

    def existing(id):
        try:
            if not service.path(id).is_dir():
                raise ValueError()
        except ValueError:
            raise HTTPException(404, "Assessment not found") from None

    @app.get("/api/assessments/{id}")
    def status(id: str):
        existing(id)
        return service.status(id)

    @app.post("/api/assessments/{id}/cancel")
    def cancel(id: str):
        existing(id)
        service.cancel(id)
        return {"cancellation_requested": True}

    @app.get("/api/assessments/{id}/report")
    def report(id: str):
        existing(id)
        return service.report(id)

    @app.get("/api/assessments/{id}/export/{format}")
    def export(id: str, format: str):
        existing(id)
        if format not in {"json", "md", "html", "zip"}:
            raise HTTPException(404)
        directory = service.path(id)
        data = (
            export_zip(directory, service.report(id))
            if format == "zip"
            else (directory / ("report." + format)).read_bytes()
        )
        return Response(
            data,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="frictionlab-{id}.{format}"'},
        )

    @app.get("/api/assessments/{id}/evidence/{name}")
    def evidence(id: str, name: str):
        existing(id)
        if name not in service.report(id)["evidence_files"] or Path(name).name != name:
            raise HTTPException(404)
        return Response((service.path(id) / name).read_bytes(), media_type="image/png")

    return app
