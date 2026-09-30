"""Deny by default: a known fixture origin, namespace, endpoints, and synthetic payloads."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from urllib.parse import parse_qs, urlsplit

from frictionlab.contracts.models import ProtectionEvent, TrafficLimits, validate_origin


class FixturePolicy:
    def __init__(
        self, origin, run_id, variant, store, limits: TrafficLimits, *, global_budget=None
    ):
        self.origin = validate_origin(origin, loopback=True)
        self.run_id = str(run_id)
        self.variant = variant
        self.store = store
        self.limits = limits
        self.global_budget = global_budget
        self.events = []
        self.traffic = []
        self.active = 0
        self.peak_active = 0
        self._timestamps = deque()
        self._lock = threading.Lock()
        self.stopped = threading.Event()

    def record(self, decision, layer, reason):
        event = ProtectionEvent(decision=decision, layer=layer, reason=reason)
        with self._lock:
            self.events.append(event)

    def reason(self, method, url, body=b"", upgrade=False):
        if self.stopped.is_set():
            return "Execution has stopped"
        if upgrade:
            return "WebSocket and other protocol upgrades are prohibited"
        if any(ord(char) < 32 for char in url) or "\\" in url:
            return "Malformed destination"
        try:
            parsed = urlsplit(url)
            if validate_origin(f"{parsed.scheme}://{parsed.netloc}", loopback=True) != self.origin:
                return "Destination is outside the owned fixture"
            query = parse_qs(parsed.query, strict_parsing=True, max_num_fields=4)
        except ValueError:
            return "Destination is not a declared numeric loopback origin"
        if parsed.fragment or "%" in parsed.path or parsed.username is not None:
            return "Encoded or ambiguous destinations are prohibited"
        if method == "GET":
            if body:
                return "GET requests cannot carry a payload"
            if parsed.path == "/" and query == {"run_id": [self.run_id], "variant": [self.variant]}:
                return None
            if not query and parsed.path in {
                "/assets/app.js",
                "/assets/style.css",
                "/favicon.ico",
                f"/fixture/runs/{self.run_id}",
                "/fixture/protection/redirect",
            }:
                return None
            return "GET endpoint or query is not allowed"
        if method != "POST" or query or len(body) > 1024:
            return "Method, query, or body size is outside the fixture contract"
        try:
            document = json.loads(body)
        except (ValueError, UnicodeError):
            return "Request body must be bounded JSON"
        if not isinstance(document, dict):
            return "Request body must be a JSON object"
        if parsed.path == "/fixture/runs" and document == {
            "run_id": self.run_id,
            "variant": self.variant,
        }:
            return None
        if parsed.path == f"/fixture/runs/{self.run_id}/accounts" and document == {}:
            return None
        if parsed.path == f"/fixture/runs/{self.run_id}/checkout" and set(document) == {"email"}:
            email = document["email"]
            if not isinstance(email, str):
                return "Only declared synthetic text can be submitted"
            allowed = self.store.synthetic_emails(self.run_id) | {"test.user"}
            if email in allowed:
                return None
            return "Checkout payload is not a declared synthetic account or validation fixture"
        return "Endpoint or operation is not permitted in this run"

    def acquire(self):
        """Sliding one-second global rate window and a concurrent-upstream ceiling."""
        shared = self.global_budget
        if shared and not shared.acquire(self.stopped):
            self.record("blocked", "network", shared.stop_reason or "Cohort traffic stopped")
            return False
        while not self.stopped.is_set():
            now = time.monotonic()
            with self._lock:
                while self._timestamps and now - self._timestamps[0] >= 1:
                    self._timestamps.popleft()
                if (
                    self.active < self.limits.concurrency
                    and len(self._timestamps) < self.limits.requests_per_second
                ):
                    self._timestamps.append(now)
                    self.traffic.append(now)
                    self.active += 1
                    self.peak_active = max(self.peak_active, self.active)
                    return True
            self.stopped.wait(0.02)
        if shared:
            shared.release()
        return False

    def release(self):
        with self._lock:
            self.active -= 1
        if self.global_budget:
            self.global_budget.release()

    def observe_upstream(self, status, duration_seconds):
        if self.global_budget:
            self.global_budget.observe_response(status, duration_seconds)

    def metrics(self):
        with self._lock:
            values = list(self.traffic)
            peak = max(
                (sum(0 <= other - stamp < 1 for other in values) for stamp in values), default=0
            )
            return {
                "forwarded_requests": len(values),
                "peak_requests_per_second": peak,
                "peak_concurrent_requests": self.peak_active,
            }
