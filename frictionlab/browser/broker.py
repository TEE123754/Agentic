"""Trusted observe → validate → act → verify broker for disposable bundled fixtures."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import logging
import os
import socket
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from frictionlab.browser.accessibility import inspect_accessibility
from frictionlab.browser.evidence import BrowserObservation, CoordinateSpace, EvidenceWriter
from frictionlab.browser.runtime import OwnedFixture
from frictionlab.browser.state import (
    INIT,
    READ,
    attribute_shape,
    fingerprint,
    redact,
    semantic_signature,
)
from frictionlab.configuration import PACKAGE_DIRECTORY, ROOT
from frictionlab.contracts.models import (
    Action,
    Candidate,
    CohortResults,
    ProtectionSummary,
    ReportScope,
    ReviewSection,
    RunReport,
    StepResult,
    Viewport,
)
from frictionlab.grounding.adapter import GroundingAdapter, ObservationSession
from frictionlab.reporting import write_report

LOGGER = logging.getLogger(__name__)
VARIANTS = {
    "healthy",
    "generic_validation",
    "dead_button",
    "delayed_feedback",
    "hidden_shipping",
    "focus_trap",
}


class ActionRejected(ValueError):
    pass


def free_port():
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


class BrowserBroker:
    def __init__(
        self,
        resolved,
        *,
        variant="healthy",
        persona_id=None,
        journey_id=None,
        artifact_root=None,
        response_timeout_seconds=4,
        report_transform=None,
        global_budget=None,
        session_id=None,
    ):
        if variant not in VARIANTS:
            raise ValueError("Unknown controlled fixture variant")
        self.resolved = resolved
        self.persona = next(
            p for p in resolved.personas if p.id == (persona_id or resolved.personas[0].id)
        )
        self.journey = next(
            j for j in resolved.journeys if j.id == (journey_id or resolved.journeys[0].id)
        )
        self.variant = variant
        self.viewport = self.persona.device.viewport
        self.run_id = UUID(str(session_id)) if session_id else uuid4()
        self.artifact_root = (
            Path(artifact_root) if artifact_root else ROOT / "artifacts" / "phase2" / "runs"
        )
        self.directory = self.artifact_root / str(self.run_id)
        self.writer = EvidenceWriter(self.directory / "evidence")
        self.runtime = OwnedFixture(
            self.run_id,
            variant,
            resolved.environment.limits,
            self.artifact_root,
            global_budget=global_budget,
        )
        self.response_timeout = min(max(response_timeout_seconds, 0.1), 10)
        self.context = None
        self.playwright = None
        self.session = None
        self.profile = None
        self.page = None
        self.current = None
        self.registry = {}
        self.observations = []
        self.steps = []
        self.network = []
        self.pending_requests = set()
        self.coverage = {"Frame, popup, shadow-root, and download actions are not supported"}
        self.pending_tasks = set()
        self.cleanup_errors = []
        self.closed = False
        self.finished = False
        self.cancelled = False
        self.failed = False
        self.failure_reason = ""
        self.stage = "created"
        self.timed_out = False
        self.watchdog = None
        self.boundary_checks = {}
        self.started = time.monotonic()
        self.started_navigation = False
        self._lock = asyncio.Lock()
        self.report_transform = report_transform

    async def __aenter__(self):
        try:
            await asyncio.wait_for(self.start(), timeout=45)
            return self
        except BaseException as exc:
            self.failed = True
            self.failure_reason = f"Browser startup failed at {self.stage} ({type(exc).__name__})."
            await self.close()
            raise

    async def __aexit__(self, kind, error, traceback):
        self.failed = self.failed or kind is not None and kind is not asyncio.CancelledError
        self.cancelled = self.cancelled or kind is asyncio.CancelledError
        if error is not None and kind is not asyncio.CancelledError:
            self.failure_reason = (
                f"Browser session failed at {self.stage} ({type(error).__name__})."
            )
        await self.close()

    def deadline(self):
        if self.closed or self.cancelled:
            raise ActionRejected("Browser session is closed or cancelled")
        if time.monotonic() - self.started >= self.resolved.environment.limits.max_runtime_seconds:
            raise ActionRejected("Run runtime ceiling reached")

    def background(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.pending_tasks.add(task)
        task.add_done_callback(self.pending_tasks.discard)

    async def start(self):
        self.deadline()
        self.stage = "owned fixture startup"
        await self.runtime.start()
        self.stage = "local browser executable lookup"
        self.browser_path = Path(
            os.environ.get(
                "FRICTIONLAB_BROWSER_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            )
        )
        if not self.browser_path.is_file():
            raise FileNotFoundError(
                "Configure a locally installed Chromium browser; no automatic download occurs"
            )
        profiles = ROOT / ".runtime" / "browsers"
        profiles.mkdir(parents=True, exist_ok=True)
        self.profile = tempfile.TemporaryDirectory(prefix="phase2-", dir=profiles)
        cdp_port = free_port()
        self.playwright = await async_playwright().start()
        self.stage = "browser launch"
        viewport = self.viewport.model_dump()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile.name,
            executable_path=str(self.browser_path),
            env={
                key: value
                for key, value in os.environ.items()
                if key.upper()
                in {
                    "PATH",
                    "HOME",
                    "USERPROFILE",
                    "SYSTEMROOT",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "LANG",
                    "LC_ALL",
                    "LD_LIBRARY_PATH",
                }
            },
            headless=True,
            viewport=viewport,
            device_scale_factor=1,
            has_touch=self.persona.device.input_mode == "touch",
            is_mobile=self.persona.device.input_mode == "touch",
            service_workers="block",
            accept_downloads=False,
            proxy={"server": self.runtime.proxy.origin, "bypass": "<-loopback>"},
            args=[
                f"--remote-debugging-port={cdp_port}",
                "--remote-debugging-address=127.0.0.1",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-sync",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-quic",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
            ],
        )
        self.browser_version = self.context.browser.version
        self.stage = "browser policy setup"
        self.context.set_default_timeout(5000)
        await self.context.add_init_script(INIT)

        async def route_handler(route):
            request = route.request
            body = request.post_data_buffer or b""
            reason = self.runtime.policy.reason(request.method, request.url, body)
            self.network.append(
                {
                    "method": request.method,
                    "type": request.resource_type,
                    "path": urlsplit(request.url).path,
                    "decision": "blocked" if reason else "allowed",
                }
            )
            if reason:
                self.runtime.policy.record("blocked", "browser", reason)
                await route.abort("blockedbyclient")
            else:
                self.pending_requests.add(request)
                await route.continue_()

        async def websocket_handler(route):
            self.runtime.policy.record(
                "blocked", "browser", "WebSocket connection rejected before upstream connection"
            )
            await route.close(code=1008, reason="Fixture-only policy")

        await self.context.route("**/*", route_handler)
        await self.context.route_web_socket("**/*", websocket_handler)
        self.page = self.context.pages[0]
        self.page.on("requestfinished", lambda request: self.pending_requests.discard(request))
        self.page.on("requestfailed", lambda request: self.pending_requests.discard(request))
        self.context.on("page", lambda page: self.background(self.close_popup(page)))
        self.page.on(
            "frameattached",
            lambda frame: self.coverage.add("Frame detected; grounding remains top-level only"),
        )
        self.page.on("download", lambda download: self.background(download.cancel()))
        self.page.on("dialog", lambda dialog: self.background(dialog.dismiss()))
        self.devtools = await self.context.new_cdp_session(self.page)
        info = await self.devtools.send("Target.getTargetInfo")
        self.target_id = info["targetInfo"]["targetId"]
        if self.persona.device.zoom_percent != 100:
            await self.devtools.send(
                "Emulation.setPageScaleFactor",
                {"pageScaleFactor": self.persona.device.zoom_percent / 100},
            )
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"http://127.0.0.1:{cdp_port}/json/version")
            response.raise_for_status()
        self.session = ObservationSession(response.json()["webSocketDebuggerUrl"], self.target_id)
        await self.session.start()
        self.adapter = GroundingAdapter(self.session)
        self.stage = "fixture navigation"
        url = f"{self.runtime.origin}/?run_id={self.run_id}&variant={self.variant}"
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        self.started_navigation = True
        if self.persona.device.zoom_percent != 100:
            await self.devtools.send(
                "Emulation.setPageScaleFactor",
                {"pageScaleFactor": self.persona.device.zoom_percent / 100},
            )
        await self.page.get_by_role("button", name="Start checkout", exact=True).wait_for()
        await self.page.wait_for_function(
            "document.getElementById('start').disabled === false", timeout=15000
        )
        emails = self.runtime.app.state.fixture.synthetic_emails(self.run_id)
        if len(emails) != 1:
            raise RuntimeError("Fixture did not create exactly one synthetic account")
        self.text_values = {"synthetic_email": next(iter(emails)), "invalid_email": "test.user"}
        self.stage = "network protection checks"
        await self.validate_boundary()
        self.stage = "initial evidence capture"
        await self.observe()
        self.stage = "ready"
        self.watchdog = asyncio.create_task(self.enforce_runtime())

    async def enforce_runtime(self):
        remaining = self.resolved.environment.limits.max_runtime_seconds - (
            time.monotonic() - self.started
        )
        await asyncio.sleep(max(0, remaining))
        self.timed_out = True
        if self.runtime.policy:
            self.runtime.policy.stopped.set()
        await self.close()

    async def close_popup(self, page):
        self.coverage.add("Popup detected and closed; popup actions unsupported")
        self.runtime.policy.record("blocked", "browser", "Additional browser page closed")
        await page.close()

    async def validate_boundary(self):
        async with httpx.AsyncClient(proxy=self.runtime.proxy.origin, trust_env=False) as client:
            forbidden = await client.post(
                self.runtime.sentinel.origin + "/independent-proxy-probe", json={"synthetic": True}
            )
            redirect = await client.get(self.runtime.origin + "/fixture/protection/redirect")
            forbidden_order = await client.get(
                f"{self.runtime.origin}/fixture/runs/{self.run_id}/order"
            )
        self.boundary_checks["independent_proxy_denial"] = forbidden.status_code == 403
        self.boundary_checks["redirect_denied_before_following"] = redirect.status_code == 403
        self.boundary_checks["operation_denied_even_with_get"] = forbidden_order.status_code == 403
        result = await self.page.evaluate(
            """async origin => {
          const image = new Image(); image.src = origin + '/image';
          const frame = document.createElement('iframe'); frame.src = origin + '/frame';
          frame.hidden = true; document.body.appendChild(frame);
          fetch(origin + '/api', {method:'POST',body:'synthetic'}).catch(() => {});
          navigator.sendBeacon(origin + '/beacon', 'synthetic');
          const ws = new WebSocket(origin.replace('http:', 'ws:') + '/socket'); ws.onerror = () => {};
          let swBlocked = false;
          try {swBlocked = !(await navigator.serviceWorker.register('/sw.js'));} catch {swBlocked = true;}
          await new Promise(resolve => setTimeout(resolve, 400));
          image.src = ''; frame.remove(); ws.close();
          return {swBlocked, registrations: (await navigator.serviceWorker.getRegistrations()).length};
        }""",
            self.runtime.sentinel.origin,
        )
        self.boundary_checks["service_workers_disabled"] = (
            result["swBlocked"] and result["registrations"] == 0
        )
        self.runtime.policy.record(
            "blocked", "browser", "Service worker registration disabled for this context"
        )
        self.boundary_checks["browser_requests_blocked"] = (
            len([item for item in self.network if item["decision"] == "blocked"]) >= 4
        )
        self.boundary_checks["websocket_blocked"] = any(
            "WebSocket" in event.reason for event in self.runtime.policy.events
        )
        self.boundary_checks["sentinel_zero_requests"] = not self.runtime.sentinel_state["requests"]
        self.boundary_checks["sentinel_data_unchanged"] = (
            self.runtime.sentinel_state["balance"] == 100
        )
        self.writer.json("boundary-checks.json", self.boundary_checks)
        if not all(self.boundary_checks.values()):
            raise RuntimeError(
                "Owned fixture browser/proxy boundary failed its mandatory startup checks"
            )

    async def observe(self, *, terminal=False):
        if not terminal:
            self.deadline()
        if self.page.url != f"{self.runtime.origin}/?run_id={self.run_id}&variant={self.variant}":
            raise ActionRejected("Current page is outside the allowed fixture document")
        state = await self.page.evaluate(READ)
        nodes, timing = await self.adapter.extract(self.page)
        observation_id = uuid4()
        candidates = tuple(
            Candidate(
                candidate_id=node.candidate_id,
                observation_id=observation_id,
                target_id=self.target_id,
                name=redact(node.name),
                role=node.role,
                visible=True,
                enabled=True,
                bounds=node.bounds,
            )
            for node in nodes.values()
        )
        observation = BrowserObservation(
            id=observation_id,
            target_id=self.target_id,
            route=urlsplit(self.page.url).path,
            viewport=self.viewport,
            candidates=candidates,
            semantic_text=redact(state["visible_text"])[:16000],
            document_id=state["document_id"],
            mutation_epoch=state["mutation_epoch"],
            state_digest=fingerprint(state),
            semantic_signature=semantic_signature(state),
            focus={key: redact(value) for key, value in state["focus"].items()},
            validation=tuple(redact(value) for value in state["validation"] if value),
            frame_urls=tuple(redact(frame.url) for frame in self.page.frames),
            coverage_gaps=tuple(sorted(self.coverage)),
            coordinates=CoordinateSpace(**state["coordinates"]),
            extraction_timing_ms=timing,
        )
        observation = await self.writer.capture(self.page, observation)
        # Screenshot masking is temporary. Bind the registry to the clean, current state.
        after = await self.page.evaluate(READ)
        if (
            state["document_id"] != after["document_id"]
            or state["dom"] != after["dom"]
            or state["inputs"] != after["inputs"]
        ):
            self.writer.json(
                f"{observation.id}.capture-drift.json",
                {
                    "document_changed": state["document_id"] != after["document_id"],
                    "inputs_changed": state["inputs"] != after["inputs"],
                    "before_attributes": attribute_shape(state["dom"]),
                    "after_attributes": attribute_shape(after["dom"]),
                },
            )
            self.registry = {}
            self.current = None
            raise ActionRejected("Application changed during evidence capture; observe again")
        observation = observation.model_copy(
            update={"state_digest": fingerprint(after), "mutation_epoch": after["mutation_epoch"]}
        )
        self.writer.json(f"{observation.id}.observation.json", observation.model_dump(mode="json"))
        self.current = observation
        self.registry = nodes
        self.observations.append(observation)
        return observation

    async def resize(self, viewport: Viewport):
        self.deadline()
        await self.page.set_viewport_size(viewport.model_dump())
        self.viewport = viewport
        self.registry = {}
        self.current = None
        return await self.observe()

    def candidate_at_pixel(self, x, y, observation_id: UUID):
        if self.current is None or self.current.id != observation_id:
            raise ActionRejected("Visual grounding requires the current observation")
        css_x, css_y = self.current.coordinates.pixel_to_css(x, y)
        matches = [
            candidate.candidate_id
            for candidate in self.current.candidates
            if candidate.bounds[0] <= css_x < candidate.bounds[0] + candidate.bounds[2]
            and candidate.bounds[1] <= css_y < candidate.bounds[1] + candidate.bounds[3]
        ]
        if len(matches) != 1:
            raise ActionRejected(
                "Visual coordinate must identify exactly one observed interactive candidate"
            )
        return matches[0]

    async def verify_candidate(self, candidate_id):
        node = self.registry.get(candidate_id)
        if node is None or node.target_id != self.target_id:
            raise ActionRejected("Candidate is unknown or belongs to another target")
        locator = self.page.locator("xpath=" + node.xpath)
        handle = await locator.element_handle()
        if handle is None or not await handle.is_visible() or not await handle.is_enabled():
            raise ActionRejected("Candidate no longer resolves to a visible enabled element")
        resolved = await self.devtools.send(
            "DOM.resolveNode", {"backendNodeId": node.backend_node_id}
        )
        object_id = resolved["object"]["objectId"]
        try:
            check = await self.devtools.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": object_id,
                    "functionDeclaration": "function(xpath) {return this.isConnected && this === document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;}",
                    "arguments": [{"value": node.xpath}],
                    "returnByValue": True,
                },
            )
            if check.get("exceptionDetails") or check["result"].get("value") is not True:
                raise ActionRejected("Candidate backend identity changed")
        finally:
            await self.devtools.send("Runtime.releaseObject", {"objectId": object_id})
        return node, handle

    async def wait_effect(self, previous):
        deadline = time.monotonic() + self.response_timeout
        changed_at = None
        last_signature = previous.semantic_signature
        while time.monotonic() < deadline:
            state = await self.page.evaluate(READ)
            signature = semantic_signature(state)
            if signature != last_signature:
                changed_at = time.monotonic()
                last_signature = signature
            if (
                signature != previous.semantic_signature
                and not self.pending_requests
                and changed_at is not None
                and time.monotonic() - changed_at >= 0.25
            ):
                return
            await asyncio.sleep(0.1)

    async def act(self, action: Action):
        async with self._lock:
            self.stage = f"{action.kind} action"
            before = self.current
            started = time.monotonic()
            status = "no_change"
            detail = "No visible application change within the bounded observation window"
            try:
                self.deadline()
                if before is None or action.observation_id != before.id:
                    raise ActionRejected("Stale observation ID; capture a new observation")
                if self.finished:
                    raise ActionRejected("Terminal capture already requested")
                if len(self.steps) >= self.resolved.environment.limits.max_steps:
                    self.finished = True
                    raise ActionRejected("Action step ceiling reached")
                state = await self.page.evaluate(READ)
                if fingerprint(state) != before.state_digest:
                    raise ActionRejected(
                        "Document, DOM, input, viewport, or scroll state changed after observation"
                    )
                node = handle = None
                if action.candidate_id is not None:
                    node, handle = await self.verify_candidate(action.candidate_id)
                if action.kind == "click":
                    if await handle.get_attribute("id") in {
                        "reset",
                        "switch-variant",
                        "variant",
                    }:
                        raise ActionRejected(
                            "Fixture control operations cannot be activated by an agent"
                        )
                    if self.persona.device.input_mode == "keyboard":
                        raise ActionRejected("Keyboard-only profiles cannot click or tap")
                    if self.persona.device.input_mode == "touch":
                        await handle.tap()
                    else:
                        await handle.click()
                    await self.wait_effect(before)
                elif action.kind == "type_text":
                    if action.text_reference not in self.text_values or node.input_type not in {
                        "email",
                        "text",
                    }:
                        raise ActionRejected(
                            "Text input requires an approved synthetic reference and text control"
                        )
                    text = self.text_values[action.text_reference]
                    if self.persona.device.input_mode == "keyboard":
                        if not await handle.evaluate("el => el === document.activeElement"):
                            raise ActionRejected(
                                "Keyboard text input requires the candidate to be focused"
                            )
                        await self.page.keyboard.press("Control+A")
                        await self.page.keyboard.insert_text(text)
                    else:
                        await handle.fill(text)
                    status, detail = "progress", "Declared synthetic text entered"
                elif action.kind == "press_key":
                    focus = await self.page.evaluate("document.activeElement?.id || ''")
                    if focus in {"reset", "switch-variant", "variant"} and action.key in {
                        "Enter",
                        "Space",
                    }:
                        raise ActionRejected(
                            "Fixture control operations cannot be activated by an agent"
                        )
                    await self.page.keyboard.press(action.key)
                    if action.key in {"Enter", "Space", "Escape"}:
                        await self.wait_effect(before)
                elif action.kind == "scroll":
                    movement = await self.page.evaluate(
                        "amount => {const before = [scrollX, scrollY]; window.scrollBy(0, amount); return {before, after: [scrollX, scrollY]};}",
                        action.amount * (1 if action.direction == "down" else -1),
                    )
                    if movement["before"] != movement["after"]:
                        status, detail = "progress", "Viewport moved; new visible content captured"
                elif action.kind == "wait":
                    await asyncio.sleep(action.timeout_ms / 1000)
                elif action.kind == "finish":
                    self.finished = True
                    status, detail = (
                        "progress",
                        "Terminal evidence captured; completion is independently verified",
                    )
                self.registry = {}
                after = await self.observe()
                if after.validation and after.validation != before.validation:
                    status, detail = (
                        "validation_error",
                        "New visible validation feedback was captured",
                    )
                elif after.semantic_signature != before.semantic_signature:
                    status, detail = "progress", "Visible application state changed"
                elif action.kind == "press_key" and after.focus != before.focus:
                    status, detail = "progress", "Keyboard focus changed"
            except ActionRejected as exc:
                status, detail = "blocked", str(exc)
                self.runtime.policy.record("blocked", "action", detail)
                after = (
                    await self.observe(terminal=True)
                    if self.page and not self.page.is_closed()
                    else None
                )
            except PlaywrightError as exc:
                status, detail = (
                    "agent_error",
                    f"Browser operation failed ({type(exc).__name__}); no abandonment inferred",
                )
                self.registry = {}
                after = (
                    await self.observe(terminal=True)
                    if self.page and not self.page.is_closed()
                    else None
                )
            result = StepResult(
                action_id=action.id,
                action=action,
                observation_before=before.id if before else action.observation_id,
                observation_after=after.id if after else None,
                result=status,
                detail=detail,
                application_seconds=time.monotonic() - started,
                evidence=after.evidence if after else (),
            )
            self.steps.append(result)
            self.writer.json("actions.json", [step.model_dump(mode="json") for step in self.steps])
            return result

    async def verify_completion(self):
        results = {}
        for criterion in self.journey.completion:
            if criterion.kind == "heading_visible":
                locator = self.page.get_by_role(
                    "heading", name=criterion.value, exact=criterion.exact
                )
                results[criterion.id] = await locator.count() == 1 and await locator.is_visible()
            elif criterion.kind == "text_visible":
                locator = self.page.get_by_text(criterion.value, exact=criterion.exact)
                results[criterion.id] = await locator.count() == 1 and await locator.is_visible()
            else:
                results[criterion.id] = urlsplit(self.page.url).path == criterion.value
        return results

    async def accessibility(self):
        result = await inspect_accessibility(self.page)
        self.writer.json("accessibility.json", result)
        await self.observe()
        return result

    async def cancel(self):
        self.cancelled = True
        if self.runtime.policy:
            self.runtime.policy.stopped.set()
        await self.close()

    async def close(self):
        if self.closed:
            return
        if self.watchdog and self.watchdog is not asyncio.current_task():
            self.watchdog.cancel()
            await asyncio.gather(self.watchdog, return_exceptions=True)
        if self.runtime.policy:
            self.runtime.policy.stopped.set()
        self.completion = {}
        if self.page and not self.page.is_closed():
            try:
                self.completion = await self.verify_completion()
                await self.observe(terminal=True)
            except Exception as exc:  # noqa: BLE001 -- cleanup must continue and retain failures
                self.cleanup_errors.append(f"Terminal capture: {type(exc).__name__}")
        self.closed = True
        for label, resource in (
            ("Grounding CDP", self.session),
            ("Browser context", self.context),
            ("Playwright", self.playwright),
        ):
            if resource:
                try:
                    await asyncio.wait_for(
                        resource.close() if label == "Browser context" else resource.stop(),
                        timeout=15,
                    )
                except Exception as exc:  # noqa: BLE001 -- attempt all remaining cleanup
                    self.cleanup_errors.append(f"{label}: {type(exc).__name__}")
        for task in self.pending_tasks:
            task.cancel()
        if self.pending_tasks:
            await asyncio.gather(*self.pending_tasks, return_exceptions=True)
        try:
            await self.runtime.close()
        except Exception as exc:  # noqa: BLE001 -- persist a partial report even when teardown fails
            self.cleanup_errors.append(f"Owned runtime: {type(exc).__name__}")
        if self.profile:
            try:
                if (
                    not Path(self.profile.name)
                    .resolve()
                    .is_relative_to((ROOT / ".runtime" / "browsers").resolve())
                ):
                    raise ValueError("Browser profile escapes the owned runtime directory")
                self.profile.cleanup()
            except Exception as exc:  # noqa: BLE001 -- preserve teardown failure evidence
                self.cleanup_errors.append(f"Browser profile: {type(exc).__name__}")
        self.finalize()

    def finalize(self):
        policy = self.runtime.policy
        traffic = policy.metrics() if policy else {}
        state = self.runtime.sentinel_state
        checks = self.boundary_checks | {
            "sentinel_zero_at_end": not state["requests"],
            "sentinel_data_unchanged_at_end": state["balance"] == 100,
            "cleanup_succeeded": not self.cleanup_errors,
        }
        self.writer.json("network.json", self.network)
        self.writer.json("upstream-arrivals.json", self.runtime.arrivals)
        self.writer.json(
            "review.json",
            {
                "boundary_checks": checks,
                "completion": self.completion,
                "cleanup_errors": self.cleanup_errors,
                "cleanup": self.runtime.cleanup,
            },
        )
        self.writer.json(
            "configuration.json",
            {
                "run": self.resolved.config.model_dump(mode="json"),
                "environment": self.resolved.environment.model_dump(mode="json"),
                "persona": self.persona.model_dump(mode="json"),
                "journey": self.journey.model_dump(mode="json"),
            },
        )
        executed = int(self.started_navigation)
        completed = bool(self.completion) and all(self.completion.values())
        outcome = (
            "timed_out"
            if self.timed_out
            else "cancelled"
            if self.cancelled
            else "inconclusive_agent_failure"
            if self.failed or self.cleanup_errors
            else "completed"
            if completed
            else "blocked_protection"
            if any(step.result == "blocked" for step in self.steps)
            else "inconclusive_agent_failure"
        )
        status = (
            "cancelled"
            if self.cancelled
            else "failed"
            if self.failed or self.cleanup_errors or self.timed_out
            else "completed"
        )
        metadata = {
            "variant": self.variant,
            "browser_executable": str(getattr(self, "browser_path", "unavailable")),
            "browser_version": getattr(self, "browser_version", "unavailable"),
            "replica_runtime_origin": getattr(self.runtime, "origin", "not_started"),
            "input_mode": self.persona.device.input_mode,
            "zoom_percent": self.persona.device.zoom_percent,
            "viewport_width": self.persona.device.viewport.width,
            "viewport_height": self.persona.device.viewport.height,
            "duration_seconds": round(time.monotonic() - self.started, 3),
            **{
                name: importlib.metadata.version(name)
                for name in ("playwright", "browser-use", "cdp-use")
            },
        }
        fixture_files = [
            PACKAGE_DIRECTORY / "api.py",
            PACKAGE_DIRECTORY / "fixtures" / "store.py",
            *sorted((PACKAGE_DIRECTORY / "fixtures" / "web").glob("*")),
        ]
        metadata["fixture_content_sha256"] = hashlib.sha256(
            b"".join(path.read_bytes() for path in fixture_files if path.is_file())
        ).hexdigest()
        terminal_reason = self.failure_reason or (
            "Runtime ceiling reached; the watchdog stopped the owned browser session."
            if self.timed_out
            else "Emergency cancellation stopped the owned browser session."
            if self.cancelled
            else "All independent journey completion criteria passed; deterministic probe complete."
            if completed
            else "Probe closed without satisfying every journey criterion; no synthetic abandonment inferred."
        )
        missing_refs = [
            ref.path
            for observation in self.observations
            for ref in observation.evidence
            if not (self.directory / ref.path).is_file()
            or (self.directory / ref.path).stat().st_size == 0
        ]
        report = RunReport(
            run_id=self.run_id,
            execution_status=status,
            report_status="partial",
            terminal_reason=terminal_reason,
            executive_summary=f"Captured {len(self.observations)} observations and {len(self.steps)} actions against the owned {self.variant} fixture. Completion criteria {'passed' if completed else 'were not all satisfied'}. No human churn or cognitive diagnosis is asserted.",
            scope=ReportScope(
                phase=2,
                build_id=self.resolved.environment.build_id,
                environment_id=self.resolved.environment.id,
                personas=(self.persona.id,),
                journeys=(self.journey.id,),
                seed=self.resolved.config.seed,
                configuration_hash=self.resolved.configuration_hash,
                runtime_metadata=metadata,
            ),
            protection=ProtectionSummary(
                target_requests=traffic.get("forwarded_requests", 0),
                environment_validated=True,
                network_boundary_validated=bool(self.boundary_checks) and all(checks.values()),
                boundary_scope="owned_fixture_browser_proxy",
                events=tuple(policy.events) if policy else (),
                cleanup_outcome="; ".join(
                    self.cleanup_errors or self.runtime.cleanup or ["Nothing started"]
                ),
                traffic_metrics=traffic,
                sentinel_requests=len(state["requests"]),
                sentinel_data_unchanged=state["balance"] == 100,
            ),
            cohort_results=CohortResults(
                requested_sessions=1,
                executed_sessions=executed,
                eligible_sessions=0,
                outcome_counts={outcome: 1} if executed else {},
            ),
            trajectories=tuple(self.steps),
            visual_evidence=tuple(
                ref for obs in self.observations for ref in obs.evidence if ref.kind == "screenshot"
            ),
            recommendations=(
                "Implement the Phase 3 isolated planner before autonomous journey execution.",
                "Use the saved observations, timing, focus, and validation records for later friction detector implementation.",
                "Keep external replicas and generated code disabled until an OS/container boundary is validated.",
            ),
            comparison="No matched baseline/candidate UX comparison was performed.",
            review=ReviewSection(
                status="evidence_reviewed",
                method="Deterministic completion/protection checks and stored evidence only; no repeat browser run.",
                missing_evidence=(
                    "Autonomous behavioral cohort",
                    "Calibrated UX findings and heatmaps",
                )
                + tuple(missing_refs)
                + (
                    ("Browser evidence unavailable because startup did not complete",)
                    if not self.observations
                    else ()
                ),
                limitations=tuple(sorted(self.coverage))
                + (
                    "Owned fixture/proxy controls are not an OS/container sandbox.",
                    "Keyboard emulation and automated axe-core signals do not simulate a real screen reader.",
                    "Installed Chrome can update independently of the pinned Python dependencies.",
                ),
            ),
        )
        if self.report_transform:
            report = self.report_transform(report)
        self.report = report
        write_report(report, self.artifact_root, prepared_directory=True)
