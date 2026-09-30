"""Execution settings and model output are validated before any tool dispatch."""

from typing import Literal

from pydantic import Field, model_validator

from frictionlab.configuration import CONFIG_DIRECTORY, read_json
from frictionlab.contracts.models import Action, Contract


class AgentLimits(Contract):
    mode: Literal["typed_tools"] = "typed_tools"
    max_steps: int = Field(default=24, ge=1, le=30, strict=True)
    max_tool_calls: int = Field(default=24, ge=1, le=30, strict=True)
    max_runtime_seconds: int = Field(default=240, ge=1, le=300, strict=True)
    request_timeout_seconds: int = Field(default=45, ge=1, le=60, strict=True)
    max_input_tokens: int = Field(default=2800, ge=100, le=3000, strict=True)
    max_output_tokens: int = Field(default=256, ge=96, le=384, strict=True)
    max_memory_characters: int = Field(default=10000, ge=1000, le=12000, strict=True)
    recent_actions: int = Field(default=6, ge=1, le=8, strict=True)
    provider_retries: Literal[0] = 0
    vision_enabled: Literal[False] = False

    @model_validator(mode="after")
    def input_output_budget(self):
        if self.max_input_tokens + self.max_output_tokens + 512 > 4096:
            raise ValueError("Input, output, and template reserve exceed the pinned context")
        return self


class Decision(Contract):
    action: Action
    rationale: str = Field(min_length=1, max_length=180)


class PlannerStopped(RuntimeError):
    def __init__(self, category, reason):
        super().__init__(reason)
        self.category = category


def load_limits():
    return AgentLimits.model_validate(read_json(CONFIG_DIRECTORY / "agent.json"))


def action_schema(state):
    """Dynamic grammar restricts IDs; Pydantic and the broker remain authoritative."""
    candidate_ids = [candidate["id"] for candidate in state["candidates"]]
    variants = []
    fields = {
        "candidate_id": {"type": "integer", "enum": candidate_ids},
        "text_reference": {"type": "string", "enum": ["synthetic_email", "invalid_email"]},
        "key": {
            "type": "string",
            "enum": ["Tab", "Shift+Tab", "Enter", "Space", "Escape", "ArrowUp", "ArrowDown"],
        },
        "direction": {"type": "string", "enum": ["up", "down"]},
        "amount": {"type": "integer", "enum": [200, 400, 600]},
        "timeout_ms": {"type": "integer", "minimum": 1, "maximum": 2000},
    }
    operations = {
        "click": ["candidate_id"],
        "type_text": ["candidate_id", "text_reference"],
        "press_key": ["key"],
        "scroll": ["direction", "amount"],
        "wait": ["timeout_ms"],
        "finish": [],
    }
    for kind, required in operations.items():
        completed = bool(state.get("milestones")) and all(state["milestones"].values())
        if completed and kind != "finish" or not completed and kind == "finish":
            continue
        if kind == "click" and state["input_mode"] == "keyboard":
            continue
        if kind == "press_key" and state["input_mode"] != "keyboard":
            continue
        if "candidate_id" in required and not candidate_ids:
            continue
        current_fields = dict(fields)
        if kind == "type_text":
            text_ids = [
                candidate["id"]
                for candidate in state["candidates"]
                if candidate["role"] == "textbox"
                and (state["input_mode"] != "keyboard" or candidate.get("focused"))
            ]
            if not text_ids:
                continue
            current_fields["candidate_id"] = {"type": "integer", "enum": text_ids}
        if kind == "press_key" and not any(
            candidate.get("focused") for candidate in state["candidates"]
        ):
            current_fields["key"] = {"type": "string", "enum": ["Tab", "Shift+Tab", "Escape"]}
        if kind == "press_key":
            used = state.get("focus", {}).get("used_keys_in_this_state", [])
            keys = [
                key
                for key in current_fields["key"]["enum"]
                if key not in used
                and not (key in {"Enter", "Space"} and "activate" in used)
                and not (key == "Escape" and state.get("focus", {}).get("dialog_open") is False)
            ]
            if not keys:
                continue
            current_fields["key"] = {"type": "string", "enum": keys}
        properties = {
            "kind": {"type": "string", "const": kind},
            "observation_id": {"type": "string", "const": state["observation_id"]},
        }
        properties.update({key: current_fields[key] for key in required})
        variants.append(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
                "required": list(properties),
            }
        )
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "action": {"anyOf": variants},
            "rationale": {"type": "string", "minLength": 1, "maxLength": 180},
        },
        "required": ["action", "rationale"],
    }
