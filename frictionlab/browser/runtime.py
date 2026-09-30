"""Create and dispose the only permitted execution target: a fresh bundled fixture."""

from __future__ import annotations

import asyncio
import socket
import time

import uvicorn
from fastapi.responses import RedirectResponse, Response

from frictionlab.api import create_app
from frictionlab.protection.gateway import LocalHTTPServer, proxy_handler, sentinel_handler
from frictionlab.protection.policy import FixturePolicy


class OwnedFixture:
    def __init__(self, run_id, variant, limits, artifact_root, *, global_budget=None):
        self.run_id = run_id
        self.variant = variant
        self.limits = limits
        self.global_budget = global_budget
        self.artifact_root = artifact_root
        self.socket = None
        self.task = None
        self.server = None
        self.proxy = None
        self.sentinel = None
        self.policy = None
        self.sentinel_state = {"requests": [], "balance": 100}
        self.cleanup = []
        self.arrivals = []
        self.active_requests = 0
        self.peak_active_requests = 0

    async def start(self):
        self.sentinel = LocalHTTPServer(sentinel_handler(self.sentinel_state)).start()
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.origin = f"http://127.0.0.1:{self.socket.getsockname()[1]}"
        self.app = create_app(artifact_root=self.artifact_root, origin=self.origin)

        @self.app.middleware("http")
        async def arrival_evidence(request, call_next):
            self.arrivals.append(
                {"method": request.method, "path": request.url.path, "at": time.monotonic()}
            )
            self.active_requests += 1
            self.peak_active_requests = max(self.peak_active_requests, self.active_requests)
            try:
                return await call_next(request)
            finally:
                self.active_requests -= 1

        @self.app.get("/favicon.ico")
        def favicon():
            return Response(status_code=204)

        @self.app.get("/fixture/protection/redirect")
        def redirect_probe():
            return RedirectResponse(self.sentinel.origin + "/redirect-target")

        self.server = uvicorn.Server(
            uvicorn.Config(self.app, log_level="error", lifespan="off", access_log=False)
        )
        self.task = asyncio.create_task(self.server.serve(sockets=[self.socket]))
        deadline = asyncio.get_running_loop().time() + 10
        while not self.server.started:
            if self.task.done():
                await self.task
                raise RuntimeError("Owned fixture failed to start")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Owned fixture startup deadline")
            await asyncio.sleep(0.05)
        self.policy = FixturePolicy(
            self.origin,
            self.run_id,
            self.variant,
            self.app.state.fixture,
            self.limits,
            global_budget=self.global_budget,
        )
        self.proxy = LocalHTTPServer(proxy_handler(self.policy)).start()
        return self

    async def close(self):
        if self.policy:
            self.policy.stopped.set()
        if self.proxy:
            await asyncio.to_thread(self.proxy.stop)
            self.proxy = None
        if self.server:
            self.server.should_exit = True
        if self.task:
            await asyncio.wait_for(self.task, timeout=10)
            self.task = None
        if self.socket:
            self.socket.close()
            self.socket = None
        # Reset after ASGI shutdown so no in-flight request can recreate prior state.
        if hasattr(self, "app"):
            try:
                self.app.state.fixture.reset(self.run_id)
                self.cleanup.append("Owned synthetic data reset")
            except KeyError:
                self.cleanup.append("No synthetic namespace was created")
        if self.sentinel:
            await asyncio.to_thread(self.sentinel.stop)
            self.sentinel = None
        self.cleanup.append("Owned fixture, proxy, and sentinel stopped")
