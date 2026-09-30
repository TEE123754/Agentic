"""Trusted smolagents tools expose typed broker actions, never raw Playwright or credentials."""

import asyncio
import time
from typing import ClassVar

from pydantic import ValidationError
from smolagents import Tool, ToolCallingAgent
from smolagents.agents import ToolOutput

from frictionlab.contracts.models import Action
from frictionlab.planning.contracts import PlannerStopped


class ToolBridge:
    def __init__(self, broker, memory, limits, loop, cognition=None):
        self.broker = broker
        self.memory = memory
        self.limits = limits
        self.loop = loop
        self.calls = 0
        self.stopped = False
        self.last_fault = None
        self.model = None
        self.repeated_failures = {}
        self.cognition = cognition

    async def dispatch(self, value, *, final=False):
        try:
            if self.stopped or self.broker.closed:
                raise PlannerStopped("cancelled", "Trusted tool dispatch is stopped.")
            if self.calls >= self.limits.max_tool_calls:
                raise PlannerStopped("tool_limit", "Trusted tool-call ceiling reached.")
            self.calls += 1
            try:
                action = Action.model_validate(value)
            except ValidationError as exc:
                raise PlannerStopped(
                    "invalid_tool_arguments", "Browser tool arguments failed the action contract."
                ) from exc
            if self.broker.current is None or action.observation_id != self.broker.current.id:
                raise PlannerStopped(
                    "grounding_failure", "Tool attempted a stale or missing observation."
                )
            if final != (action.kind == "finish"):
                raise PlannerStopped(
                    "invalid_tool_arguments",
                    "Finish must use the independently verified final tool.",
                )
            if action.candidate_id is not None and action.candidate_id not in {
                candidate["id"] for candidate in self.memory.state["candidates"]
            }:
                raise PlannerStopped(
                    "grounding_failure",
                    "Tool selected a candidate outside this profile's observation.",
                )
            if final:
                completion = await self.broker.verify_completion()
                if not completion or not all(completion.values()):
                    raise PlannerStopped(
                        "premature_finish",
                        "Planner requested finish before independent journey criteria passed.",
                    )
            if self.model and (
                self.model.stopped.is_set() or time.monotonic() >= self.model.deadline
            ):
                raise PlannerStopped(
                    "runtime_limit", "Planner deadline reached before tool dispatch."
                )
            label = next(
                (
                    candidate["name"]
                    for candidate in self.memory.state["candidates"]
                    if candidate["id"] == action.candidate_id
                ),
                "",
            )
            retry_key = (action.kind, label, action.key, action.text_reference)
            before = self.broker.current
            result = await self.broker.act(action)
            inference = (
                self.model.records[-1]["inference_seconds"]
                if self.model and self.model.records
                else 0
            )
            if inference:
                result = result.model_copy(update={"inference_seconds": inference})
                self.broker.steps[-1] = result
                self.broker.writer.json(
                    "actions.json", [step.model_dump(mode="json") for step in self.broker.steps]
                )
            completion = (
                await self.broker.verify_completion()
                if result.result not in {"blocked", "agent_error"}
                else {}
            )
            verified = bool(completion) and all(completion.values())
            if self.cognition:
                dialog_open = await self.broker.page.get_by_role("dialog").count() > 0
                self.cognition.ingest(
                    result,
                    before,
                    self.broker.current,
                    completion,
                    dialog_open=dialog_open,
                )
                if self.cognition.abandoned:
                    raise PlannerStopped(
                        "abandoned_patience",
                        "Observed application friction exhausted this synthetic profile's patience; terminal evidence was captured.",
                    )
            if result.result in {"blocked", "agent_error"}:
                category = (
                    "blocked_protection" if result.result == "blocked" else "grounding_failure"
                )
                raise PlannerStopped(category, result.detail)
            if result.result in {"no_change", "validation_error"}:
                self.repeated_failures[retry_key] = self.repeated_failures.get(retry_key, 0) + 1
                if self.repeated_failures[retry_key] > self.broker.persona.behavior.retry_limit:
                    raise PlannerStopped(
                        "action_retry_limit",
                        "Repeated ineffective interaction reached the profile's retry ceiling; no patience or churn diagnosis inferred.",
                    )
            else:
                self.repeated_failures.clear()
            if hasattr(self.memory, "remember_interaction"):
                informational_dialog = False
                if self.cognition and dialog_open:
                    fields = (
                        await self.broker.page.get_by_role("dialog")
                        .locator("input, select, textarea")
                        .count()
                    )
                    informational_dialog = fields == 0
                self.memory.remember_interaction(
                    before,
                    self.broker.current,
                    action,
                    informational_dialog=informational_dialog,
                )
            if verified:
                self.broker.finished = True
            if not final and not verified:
                await self.memory.refresh()
            return {
                "result": result.result,
                "detail": result.detail,
                "completion_verified": verified,
            }
        except PlannerStopped as exc:
            self.last_fault = exc
            raise

    def call(self, action, final=False):
        future = asyncio.run_coroutine_threadsafe(self.dispatch(action, final=final), self.loop)
        # Browser actions and capture have their own limits; the outer runner stops dispatch on timeout.
        return future.result(timeout=60)


class BrowserActionTool(Tool):
    name = "browser_action"
    description = (
        "Apply one validated action to the current observed candidate; no URLs, code, or raw data."
    )
    inputs: ClassVar[dict] = {
        "action": {
            "type": "object",
            "description": "A validated nonterminal Action object bound to the current observation.",
        }
    }
    output_type = "object"

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge

    def forward(self, action: dict) -> dict:
        return self.bridge.call(action)


class VerifiedFinishTool(BrowserActionTool):
    name = "final_answer"
    description = (
        "Finish only after independent journey assertions pass; records terminal evidence."
    )

    def forward(self, action: dict) -> dict:
        return self.bridge.call(action, final=True)


class BoundedPersonaAgent(ToolCallingAgent):
    def __init__(self, model, memory, bridge, limits):
        self.persona_memory = memory
        self.bridge = bridge
        super().__init__(
            tools=[BrowserActionTool(bridge), VerifiedFinishTool(bridge)],
            model=model,
            max_steps=limits.max_steps,
            max_tool_threads=1,
            add_base_tools=False,
            verbosity_level=0,
            step_callbacks=[self.stop_on_error],
        )

    def initialize_system_prompt(self):
        return "Bounded synthetic persona. Only browser_action and verified final_answer are available."

    def write_memory_to_messages(self, summary_mode=False):
        return self.persona_memory.messages

    def execute_tool_call(self, tool_name, arguments):
        if (
            tool_name not in {"browser_action", "final_answer"}
            or not isinstance(arguments, dict)
            or set(arguments) != {"action"}
        ):
            self.bridge.last_fault = PlannerStopped(
                "invalid_tool_arguments", "Unapproved tool name or argument envelope."
            )
            raise self.bridge.last_fault
        return super().execute_tool_call(tool_name, arguments)

    def process_tool_calls(self, chat_message, memory_step):
        if not chat_message.tool_calls or len(chat_message.tool_calls) != 1:
            self.bridge.last_fault = PlannerStopped(
                "invalid_tool_arguments", "Exactly one trusted tool call is required per decision."
            )
            raise self.bridge.last_fault
        for output in super().process_tool_calls(chat_message, memory_step):
            if isinstance(output, ToolOutput) and output.output.get("completion_verified") is True:
                output.is_final_answer = True
            yield output

    def stop_on_error(self, step, **kwargs):
        if step.error is not None:
            raise (
                self.bridge.last_fault
                or self.model.last_fault
                or PlannerStopped(
                    "agent_error",
                    "smolagents stopped after an invalid decision; no retry or churn inference.",
                )
            )

    def provide_final_answer(self, task):
        # Prevent smolagents' default extra generation after exhausting max_steps.
        raise PlannerStopped(
            "step_limit", "Planner step ceiling reached without verified completion."
        )
