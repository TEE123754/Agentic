"""Fail-closed budget policy used by opt-in BYOK transports.

The shipped local defaults enable no remote transport.
"""

from __future__ import annotations

from dataclasses import dataclass


class FreeQuotaPaused(RuntimeError):
    pass


@dataclass(frozen=True)
class FreeServicePolicy:
    enabled: bool = False
    paid_fallback: bool = False
    local_fallback: bool = True
    providers: tuple[str, ...] = ()
    max_requests_per_run: int = 0
    max_tokens_per_run: int = 0
    max_retries_per_request: int = 0

    def __post_init__(self):
        if self.paid_fallback:
            raise ValueError("Paid model fallback is prohibited")
        if not self.local_fallback:
            raise ValueError("An explicit local fallback is required")
        if (
            any(
                value < 0
                for value in (
                    self.max_requests_per_run,
                    self.max_tokens_per_run,
                    self.max_retries_per_request,
                )
            )
            or self.max_retries_per_request > 2
        ):
            raise ValueError("Free-service budgets and retry ceiling are invalid")
        if self.enabled and (
            not self.providers or not self.max_requests_per_run or not self.max_tokens_per_run
        ):
            raise ValueError("Opt-in requires named providers and nonzero hard ceilings")


class FreeServiceBudget:
    def __init__(self, policy: FreeServicePolicy):
        self.policy = policy
        self.requests = 0
        self.tokens = 0
        self.paused = False
        self.providers_used: list[str] = []

    def reserve(self, provider: str, *, tokens: int, retry: int = 0):
        if not self.policy.enabled or self.paused:
            raise FreeQuotaPaused("Cloud inference is disabled or quota-paused; use local fallback")
        if provider not in self.policy.providers or tokens < 0 or retry < 0:
            raise ValueError("Provider or token reservation is invalid")
        if retry > self.policy.max_retries_per_request:
            self.paused = True
            raise FreeQuotaPaused("Free retry ceiling reached; use local fallback")
        if (
            self.requests + 1 > self.policy.max_requests_per_run
            or self.tokens + tokens > self.policy.max_tokens_per_run
        ):
            self.paused = True
            raise FreeQuotaPaused("Free request/token ceiling reached; use local fallback")
        self.requests += 1
        self.tokens += tokens
        self.providers_used.append(provider)

    def quota_response(self, status_code: int):
        if status_code == 429:
            self.paused = True
            raise FreeQuotaPaused("Provider reported free-tier exhaustion; use local fallback")

    @property
    def strict_comparable(self):
        return len(set(self.providers_used)) <= 1
