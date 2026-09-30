"""Cohort-wide request backpressure and fixture health stop, shared by all proxies."""

from __future__ import annotations

import threading
import time
from collections import deque


class SharedTrafficBudget:
    def __init__(
        self,
        *,
        requests_per_second=2,
        concurrency=1,
        max_wait_seconds=10,
        unhealthy_responses=2,
        slow_response_seconds=5,
    ):
        self.requests_per_second = requests_per_second
        self.concurrency = concurrency
        self.max_wait_seconds = max_wait_seconds
        self.unhealthy_responses = unhealthy_responses
        self.slow_response_seconds = slow_response_seconds
        self.lock = threading.Condition()
        self.timestamps = deque()
        self.active = 0
        self.peak_active = 0
        self.traffic = []
        self.wait_seconds = 0.0
        self.failures = 0
        self.slow = 0
        self.stop_reason = None

    def acquire(self, stopped):
        started = time.monotonic()
        with self.lock:
            while not stopped.is_set() and self.stop_reason is None:
                now = time.monotonic()
                while self.timestamps and now - self.timestamps[0] >= 1:
                    self.timestamps.popleft()
                if (
                    self.active < self.concurrency
                    and len(self.timestamps) < self.requests_per_second
                ):
                    self.timestamps.append(now)
                    self.traffic.append(now)
                    self.active += 1
                    self.peak_active = max(self.peak_active, self.active)
                    self.wait_seconds += now - started
                    return True
                if now - started > self.max_wait_seconds:
                    self.stop_reason = "Cohort-wide request queue exceeded its safe wait ceiling"
                    self.lock.notify_all()
                    return False
                self.lock.wait(timeout=0.02)
        return False

    def release(self):
        with self.lock:
            if self.active <= 0:
                raise RuntimeError("Shared traffic release without an acquired slot")
            self.active -= 1
            self.lock.notify_all()

    def observe_response(self, status, duration_seconds):
        with self.lock:
            self.failures += int(status >= 500)
            self.slow += int(duration_seconds > self.slow_response_seconds)
            if self.failures >= self.unhealthy_responses or self.slow >= self.unhealthy_responses:
                self.stop_reason = (
                    "Owned fixture health threshold exceeded; cohort results contaminated"
                )
                self.lock.notify_all()

    def stop(self, reason):
        with self.lock:
            self.stop_reason = reason
            self.lock.notify_all()

    def metrics(self):
        with self.lock:
            stamps = list(self.traffic)
            peak = max(
                (sum(0 <= other - stamp < 1 for other in stamps) for stamp in stamps), default=0
            )
            return {
                "forwarded_requests": len(stamps),
                "peak_requests_per_second": peak,
                "peak_concurrent_requests": self.peak_active,
                "queue_wait_seconds": round(self.wait_seconds, 6),
                "upstream_failures": self.failures,
                "slow_responses": self.slow,
                "stop_reason": self.stop_reason,
            }
