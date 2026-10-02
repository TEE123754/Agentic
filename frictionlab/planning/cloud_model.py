"""Bounded BYOK inference; transport never has browser, filesystem or billing tools."""

from __future__ import annotations

import json
import time

from pydantic import ValidationError
from smolagents.models import (
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
)

from frictionlab.planning.cloud_transport import (
    CloudModelRuntime,  # noqa: F401 - Public compatibility export
)
from frictionlab.planning.contracts import Decision, PlannerStopped, action_schema
from frictionlab.planning.inference import safe_text
from frictionlab.planning.local_model import LocalPlannerModel


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
