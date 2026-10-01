"""Bounded BYOK inference; transport never has browser, filesystem or billing tools."""

from __future__ import annotations

import json
import threading
import time

import httpx
from pydantic import ValidationError
from smolagents.models import (
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
)

from frictionlab.planning.contracts import Decision, PlannerStopped, action_schema
from frictionlab.planning.free_service_policy import (
    FreeQuotaPaused,
    FreeServiceBudget,
    FreeServicePolicy,
)
from frictionlab.planning.inference import provider_key, safe_text
from frictionlab.planning.local_model import LocalPlannerModel

ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
}


class CloudModelRuntime:
    is_remote = True

    def __init__(self, settings, *, transport=None):
        self.config = settings
        self.lock = threading.Lock()
        self.budget = FreeServiceBudget(
            FreeServicePolicy(
                enabled=True,
                providers=(settings.provider,),
                max_requests_per_run=settings.max_requests,
                max_tokens_per_run=settings.max_tokens,
                max_retries_per_request=settings.max_retries,
            )
        )
        self.client = None
        self._transport = transport
        self.deadline = None
        self.identities = []
        self.retries = 0

    async def __aenter__(self):
        # Validate before the fixture/browser starts, without logging the value.
        provider_key(self.config.provider)
        self.client = httpx.Client(
            transport=self._transport, trust_env=False, follow_redirects=False
        )
        self.deadline = time.monotonic() + self.config.max_runtime_seconds
        return self

    async def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def provenance(self):
        return {
            "provider": self.config.provider,
            "requested_model": self.config.model,
            "actual_models": sorted(set(self.identities)),
            "requests": self.budget.requests,
            "reserved_tokens": self.budget.tokens,
            "retries": self.retries,
            "quota_paused": self.budget.paused,
            "fallback": "pause",
            "paid_fallback": False,
            "strict_comparable": len(set(self.identities)) == 1,
            "input_disclosure": "sanitized bounded semantic state and persona prompt; no DOM or pixels",
        }

    def complete(self, messages, max_output, deadline):
        if self.client is None or self.deadline is None:
            raise PlannerStopped("model_unavailable", "Remote inference is not initialized")
        deadline = min(deadline, self.deadline)
        input_bytes = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
        if input_bytes > self.config.max_input_bytes:
            raise PlannerStopped(
                "context_limit", "Sanitized provider input exceeds its byte ceiling"
            )
        # Conservative byte-based reservation, including framing; actual usage is also checked.
        reservation = input_bytes + 512 + max_output
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_output,
            "response_format": {"type": "json_object"},
        }
        for attempt in range(self.config.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PlannerStopped(
                    "model_timeout", "Remote inference runtime ceiling reached; paused"
                )
            try:
                self.budget.reserve(self.config.provider, tokens=reservation, retry=attempt)
                if attempt:
                    self.retries += 1
                with self.client.stream(
                    "POST",
                    ENDPOINTS[self.config.provider],
                    headers={"Authorization": "Bearer " + provider_key(self.config.provider)},
                    json=payload,
                    timeout=min(remaining, self.config.request_timeout_seconds),
                ) as response:
                    self.budget.quota_response(response.status_code)
                    if (
                        response.status_code in {502, 503, 504}
                        and attempt < self.config.max_retries
                    ):
                        continue
                    if response.status_code != 200:
                        raise PlannerStopped(
                            "model_provider_error",
                            "Provider rejected inference; paused without behavioral penalty",
                        )
                    chunks = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise PlannerStopped(
                                "model_timeout", "Remote response deadline reached"
                            )
                        chunks.extend(chunk)
                        if len(chunks) > 256000:
                            raise PlannerStopped(
                                "invalid_model_output", "Provider response exceeds its size ceiling"
                            )
                    body = json.loads(chunks)
                usage = body.get("usage", {}).get("total_tokens")
                if not isinstance(usage, int) or isinstance(usage, bool) or usage < 0:
                    raise PlannerStopped(
                        "invalid_model_output", "Provider usage is missing or invalid; paused"
                    )
                if usage > reservation:
                    self.budget.paused = True
                    raise PlannerStopped(
                        "cloud_budget_paused",
                        "Provider usage exceeded conservative reservation; paused",
                    )
                identity = body.get("model")
                if not isinstance(identity, str) or not identity or len(identity) > 120:
                    raise PlannerStopped(
                        "invalid_model_output", "Provider model identity is missing or invalid"
                    )
                self.identities.append(safe_text(identity))
                return body
            except FreeQuotaPaused:
                raise PlannerStopped(
                    "cloud_budget_paused",
                    "Inference quota/budget exhausted; paused, no paid fallback",
                ) from None
            except httpx.TimeoutException:
                raise PlannerStopped(
                    "model_timeout", "Provider timed out; paused without UX abandonment"
                ) from None
            except httpx.HTTPError:
                raise PlannerStopped(
                    "model_provider_error", "Provider transport failed; no behavioral penalty"
                ) from None
        raise PlannerStopped("model_provider_error", "Bounded provider retries exhausted")


class CloudPlannerModel(LocalPlannerModel):
    def __init__(self, runtime, memory, limits, seed, writer):
        super().__init__(runtime, memory, limits, seed, writer)
        self.model_id = runtime.config.model

    def generate(self, messages, **kwargs):
        record = {
            "attempt": len(self.records) + 1,
            "seed": self.seed,
            "observation_id": self.memory.state["observation_id"],
            "status": "pending",
            "inference_seconds": 0,
        }
        started = time.monotonic()
        try:
            if self.stopped.is_set() or time.monotonic() >= self.deadline:
                raise PlannerStopped("runtime_limit", "Planner stopped before requesting inference")
            if len(self.records) >= self.limits.max_steps:
                raise PlannerStopped("step_limit", "Planner step ceiling reached")
            payload = [{"role": m.role.value, "content": safe_text(m.content)} for m in messages]
            payload.append(
                {
                    "role": "system",
                    "content": "Return exactly one JSON object satisfying this schema: "
                    + json.dumps(action_schema(self.memory.state)),
                }
            )
            timeout = min(
                self.limits.request_timeout_seconds, max(0.1, self.deadline - time.monotonic())
            )
            if not self.runtime.lock.acquire(timeout=timeout):
                raise PlannerStopped("model_queue_timeout", "Inference queue deadline reached")
            try:
                body = self.runtime.complete(payload, self.limits.max_output_tokens, self.deadline)
            finally:
                self.runtime.lock.release()
            choice = body["choices"][0]
            content = choice["message"]["content"]
            if (
                not isinstance(content, str)
                or len(content) > 4096
                or choice.get("finish_reason") != "stop"
            ):
                raise PlannerStopped(
                    "invalid_model_output", "Provider decision is incomplete or oversized"
                )
            decision = Decision.model_validate_json(safe_text(content))
            if "id" in json.loads(content)["action"]:
                raise PlannerStopped(
                    "invalid_model_output", "Action IDs belong to the trusted runtime"
                )
            decision = decision.model_copy(
                update={"rationale": safe_text(decision.rationale)[:180]}
            )
            if self.stopped.is_set() or time.monotonic() >= self.deadline:
                raise PlannerStopped("runtime_limit", "Planner stopped before action dispatch")
            record.update(status="valid", decision=decision.model_dump(mode="json"))
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content=decision.rationale,
                tool_calls=[
                    ChatMessageToolCall(
                        id=str(decision.action.id),
                        type="function",
                        function=ChatMessageToolCallFunction(
                            name="final_answer"
                            if decision.action.kind == "finish"
                            else "browser_action",
                            arguments={"action": decision.action.model_dump(mode="json")},
                        ),
                    )
                ],
            )
        except PlannerStopped as exc:
            self.last_fault = exc
            record.update(status="failed", category=exc.category, reason=str(exc))
            raise
        except (ValueError, KeyError, TypeError, IndexError, ValidationError):
            self.last_fault = PlannerStopped(
                "invalid_model_output", "Provider decision rejected; no UX diagnosis inferred"
            )
            record.update(
                status="failed", category=self.last_fault.category, reason=str(self.last_fault)
            )
            raise self.last_fault from None
        finally:
            record["inference_seconds"] = round(time.monotonic() - started, 6)
            self.records.append(record)
            self.writer.json("planner-decisions.json", self.records)
