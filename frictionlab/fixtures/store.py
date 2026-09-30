"""Run-scoped synthetic accounts, defects, and in-memory integration mocks."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID, uuid5

from pydantic import Field

from frictionlab.contracts.models import Contract

Variant = Literal[
    "healthy",
    "generic_validation",
    "dead_button",
    "delayed_feedback",
    "hidden_shipping",
    "focus_trap",
]
Integration = Literal["payment", "email", "sms", "webhook", "inventory", "analytics"]


class Defects(Contract):
    generic_validation: bool = False
    dead_button: bool = False
    delayed_feedback: bool = False
    hidden_shipping: bool = False
    focus_trap: bool = False


class CreateFixtureRun(Contract):
    run_id: UUID
    variant: Variant = "healthy"


class CheckoutInput(Contract):
    email: str = Field(max_length=160)


class MockInput(Contract):
    operation: str = Field(min_length=1, max_length=60)


class SentinelInput(Contract):
    destination: str = Field(min_length=1, max_length=240)


@dataclass
class FixtureState:
    variant: str
    counter: int = 0
    accounts: list[dict] = field(default_factory=list)
    checkout_attempts: list[dict] = field(default_factory=list)
    mock_events: list[dict] = field(default_factory=list)


class FixtureStore:
    def __init__(self):
        self._runs = {}
        self._lock = threading.RLock()
        self.sentinel_attempts = []

    def create(self, run_id: UUID, variant: str):
        with self._lock:
            if run_id in self._runs:
                if self._runs[run_id].variant != variant:
                    raise ValueError("Reset or create a new namespace before changing the variant")
            else:
                self._runs[run_id] = FixtureState(variant=variant)
            return self.snapshot(run_id)

    def _state(self, run_id):
        if run_id not in self._runs:
            raise KeyError("Fixture namespace does not exist")
        return self._runs[run_id]

    def snapshot(self, run_id):
        with self._lock:
            state = self._state(run_id)
            defects = Defects(**({state.variant: True} if state.variant != "healthy" else {}))
            return {
                "run_id": str(run_id),
                "variant": state.variant,
                "defects": defects.model_dump(),
                "account_count": len(state.accounts),
                "checkout_attempt_count": len(state.checkout_attempts),
                "mock_events": [event.copy() for event in state.mock_events],
                "real_orders": 0,
                "external_dispatches": 0,
            }

    def account(self, run_id):
        with self._lock:
            state = self._state(run_id)
            state.counter += 1
            account = {
                "id": str(uuid5(run_id, f"account-{state.counter}")),
                "email": f"test-{run_id.hex}-{state.counter:04d}@fixture.invalid",
                "synthetic": True,
            }
            state.accounts.append(account)
            return account.copy()

    def synthetic_emails(self, run_id):
        with self._lock:
            state = self._runs.get(UUID(str(run_id)))
            return {account["email"] for account in state.accounts} if state else set()

    def checkout(self, run_id, email):
        with self._lock:
            state = self._state(run_id)
            valid = re.fullmatch(r"[a-zA-Z0-9._+-]+@fixture\.invalid", email) is not None
            state.checkout_attempts.append({"email_valid": valid})
            if not state.checkout_attempts[-1]["email_valid"]:
                if state.variant == "generic_validation":
                    return {"ok": False, "message": "Invalid input"}
                return {
                    "ok": False,
                    "message": "Enter a synthetic email ending in @fixture.invalid.",
                    "field": "email",
                }
            state.mock_events.append(
                {
                    "integration": "analytics",
                    "operation": "checkout_review",
                    "mock": True,
                    "external_dispatch": False,
                }
            )
            return {
                "ok": True,
                "state": "order_review",
                "product_price": 65,
                "shipping": 5,
                "total": 70,
                "order_placed": False,
            }

    def mock(self, run_id, integration, operation):
        with self._lock:
            state = self._state(run_id)
            event = {
                "integration": integration,
                "operation": operation,
                "mock": True,
                "external_dispatch": False,
            }
            state.mock_events.append(event)
            return event.copy()

    def reset(self, run_id):
        with self._lock:
            state = self._state(run_id)
            self._runs[run_id] = FixtureState(variant=state.variant)
            return self.snapshot(run_id)

    def reject_sentinel(self, destination):
        with self._lock:
            self.sentinel_attempts.append({"destination": destination, "decision": "blocked"})
            return {
                "decision": "blocked",
                "delivered_requests": 0,
                "attempt_count": len(self.sentinel_attempts),
            }
