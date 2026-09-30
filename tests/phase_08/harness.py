"""Deterministic semantic-control model for the owned-fixture audit gate."""

import threading
import time

from smolagents.models import (
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
    Model,
)

from frictionlab.contracts.models import Action


class SemanticHarness(Model):
    def __init__(self, runtime, memory, limits, seed, writer):
        super().__init__(model_id="phase6-semantic-acceptance-harness")
        self.memory = memory
        self.seed = seed
        self.writer = writer
        self.records = []
        self.last_fault = None
        self.stopped = threading.Event()
        self.deadline = time.monotonic() + limits.max_runtime_seconds

    def generate(self, messages, **kwargs):
        state = self.memory.state
        controls = state["candidates"]
        start = next((item for item in controls if item["name"] == "Start checkout"), None)
        textbox = next((item for item in controls if item["role"] == "textbox"), None)
        continue_button = next(
            (item for item in controls if item["name"] == "Continue to order review"), None
        )
        typed = any(
            item["kind"] == "type_text" and item["text_reference"] == "synthetic_email"
            for item in state["recent_actions"]
        )
        fields = {"observation_id": state["observation_id"]}
        if textbox and not typed:
            fields.update(
                kind="type_text", candidate_id=textbox["id"], text_reference="synthetic_email"
            )
        elif continue_button:
            fields.update(kind="click", candidate_id=continue_button["id"])
        elif start:
            fields.update(kind="click", candidate_id=start["id"])
        else:
            fields.update(kind="scroll", direction="down", amount=400)
        action = Action(**fields)
        record = {
            "attempt": len(self.records) + 1,
            "seed": self.seed,
            "observation_id": state["observation_id"],
            "status": "valid",
            "inference_seconds": 0.001,
            "decision": {
                "action": action.model_dump(mode="json"),
                "rationale": "Observed deterministic control",
            },
        }
        self.records.append(record)
        self.writer.json("planner-decisions.json", self.records)
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="Observed deterministic control",
            tool_calls=[
                ChatMessageToolCall(
                    id=str(action.id),
                    type="function",
                    function=ChatMessageToolCallFunction(
                        name="browser_action",
                        arguments={"action": action.model_dump(mode="json")},
                    ),
                )
            ],
        )
