import asyncio
import json
import threading
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from smolagents.models import ChatMessage, MessageRole

from frictionlab.contracts.models import StepResult
from frictionlab.planning.contracts import AgentLimits, PlannerStopped, action_schema
from frictionlab.planning.local_model import (
    LocalModelRuntime,
    LocalPlannerModel,
    launch_environment,
)
from frictionlab.planning.tools import BoundedPersonaAgent, ToolBridge


class Writer:
    def __init__(self):
        self.files = {}

    def json(self, name, value):
        self.files[name] = value


def model_state():
    return {
        "observation_id": str(uuid4()),
        "input_mode": "mouse",
        "candidates": [{"id": 7, "name": "Start", "role": "button"}],
    }


class FakeRuntime:
    def __init__(self, content, tokens=10, error=None):
        self.lock = threading.Lock()
        self.content = content
        self.tokens = tokens
        self.error = error
        self.requests = []

    def post(self, path, payload, timeout):
        self.requests.append((path, payload))
        if self.error:
            raise self.error
        if path == "/apply-template":
            return {"prompt": "bounded template"}
        if path == "/tokenize":
            return {"tokens": [1] * self.tokens}
        return {
            "choices": [{"message": {"content": self.content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 30},
        }


def adapter(content, *, tokens=10, error=None, limits=None):
    state = model_state()
    memory = SimpleNamespace(state=state)
    runtime = FakeRuntime(content(state) if callable(content) else content, tokens, error)
    writer = Writer()
    model = LocalPlannerModel(runtime, memory, limits or AgentLimits(), 42, writer)
    messages = [ChatMessage(role=MessageRole.USER, content="bounded state")]
    return model, runtime, writer, messages


@pytest.mark.parametrize(
    "content",
    [
        "print('unsafe')",
        "{}",
        '{"action":{"kind":"exec"},"rationale":"run code"}',
        '{"action":{"kind":"wait","observation_id":"bad","timeout_ms":1},"rationale":"wait"}',
        lambda state: json.dumps(
            {
                "action": {
                    "kind": "type_text",
                    "observation_id": state["observation_id"],
                    "candidate_id": 7,
                    "text_reference": "real_password",
                },
                "rationale": "unsafe reference",
                "url": "https://production.invalid",
            }
        ),
        lambda state: json.dumps(
            {
                "action": {
                    "kind": "wait",
                    "observation_id": state["observation_id"],
                    "timeout_ms": 1,
                    "id": str(uuid4()),
                },
                "rationale": "override identity",
            }
        ),
    ],
)
def test_malformed_output_is_recorded_and_never_executed(content):
    model, _, writer, messages = adapter(content)
    with pytest.raises(PlannerStopped) as error:
        model.generate(messages)
    assert error.value.category == "invalid_model_output"
    assert writer.files["planner-decisions.json"][0]["status"] == "failed"
    assert model.last_fault is error.value


def test_valid_local_response_becomes_one_framework_tool_call():
    model, runtime, writer, messages = adapter(
        lambda state: json.dumps(
            {
                "action": {
                    "kind": "click",
                    "observation_id": state["observation_id"],
                    "candidate_id": 7,
                },
                "rationale": "Start the assigned goal",
            }
        )
    )
    result = model.generate(messages)
    assert len(result.tool_calls) == 1 and result.tool_calls[0].function.name == "browser_action"
    assert runtime.requests[-1][1]["seed"] == 42
    assert runtime.requests[-1][1]["chat_template_kwargs"]["enable_thinking"] is False
    assert writer.files["planner-decisions.json"][0]["input_tokens"] == 10


def test_context_ceiling_stops_before_inference():
    model, runtime, _, messages = adapter("{}", tokens=3001)
    with pytest.raises(PlannerStopped, match="token ceiling"):
        model.generate(messages)
    assert len(runtime.requests) == 2


def test_model_timeout_has_no_retry():
    model, runtime, _, messages = adapter("{}", error=httpx.ReadTimeout("timeout"))
    with pytest.raises(PlannerStopped) as error:
        model.generate(messages)
    assert error.value.category == "model_timeout" and len(runtime.requests) == 1


def test_memory_watchdog_failure_is_not_a_generic_provider_error():
    model, runtime, _, messages = adapter("{}", error=httpx.ReadError("closed"))
    runtime.memory_exceeded = True
    with pytest.raises(PlannerStopped) as error:
        model.generate(messages)
    assert error.value.category == "model_memory_limit" and len(runtime.requests) == 1


def test_native_environment_cannot_enable_credentials_or_builtin_agent_tools(monkeypatch):
    monkeypatch.setenv("LLAMA_ARG_TOOLS", "all")
    monkeypatch.setenv("LLAMA_ARG_AGENT", "true")
    monkeypatch.setenv("HF_TOKEN", "private-token")
    environment = launch_environment()
    assert (
        "LLAMA_ARG_TOOLS" not in environment
        and "LLAMA_ARG_AGENT" not in environment
        and "HF_TOKEN" not in environment
    )


def test_successful_keyboard_transition_memory_preserves_ineffective_retry_keys():
    from frictionlab.planning.memory import PersonaMemory

    memory = PersonaMemory.__new__(PersonaMemory)
    memory.broker = SimpleNamespace(
        persona=SimpleNamespace(device=SimpleNamespace(input_mode="keyboard"))
    )
    memory.state = {"focus": {"name": "Observed control"}}
    memory.keyboard_transitions = set()
    before = SimpleNamespace(semantic_signature="state", focus={"name": "Observed control"})
    after = SimpleNamespace(semantic_signature="new state", focus={"name": "New control"})
    memory.remember_interaction(before, after, SimpleNamespace(kind="press_key", key="Enter"))
    state = model_state()
    state.update(input_mode="keyboard", focus={"used_keys_in_this_state": ["activate"]})
    state["candidates"][0]["focused"] = True
    variants = action_schema(state)["properties"]["action"]["anyOf"]
    keys = next(
        choice for choice in variants if choice["properties"]["kind"]["const"] == "press_key"
    )["properties"]["key"]["enum"]
    assert "Enter" not in keys and "Space" not in keys and "Tab" in keys
    assert ("state", "Observed control", "activate") in memory.keyboard_transitions
    memory.remember_interaction(before, before, SimpleNamespace(kind="press_key", key="Tab"))
    assert ("state", "Observed control", "Tab") not in memory.keyboard_transitions


def test_keyboard_historical_facts_cannot_offer_closed_dialog_escape():
    from frictionlab.planning.memory import keyboard_facts

    facts = keyboard_facts(
        '- paragraph: Delivery takes 3 days. - dialog "Delivery": - button "Close delivery policy" - paragraph: Returns take 30 days.'
    )
    assert "Delivery takes 3 days." in facts and "Returns take 30 days." in facts
    assert "Close delivery policy" not in facts and "dialog" not in facts
    state = model_state()
    state.update(input_mode="keyboard", focus={"dialog_open": False})
    state["candidates"][0]["focused"] = True
    variants = action_schema(state)["properties"]["action"]["anyOf"]
    keys = next(
        choice for choice in variants if choice["properties"]["kind"]["const"] == "press_key"
    )["properties"]["key"]["enum"]
    assert "Escape" not in keys and "Enter" in keys


def test_stopped_adapter_does_not_contact_provider():
    model, runtime, _, messages = adapter("{}")
    model.stopped.set()
    with pytest.raises(PlannerStopped):
        model.generate(messages)
    assert not runtime.requests


def test_dynamic_schema_cannot_offer_keyboard_click_or_external_navigation():
    state = model_state()
    state["input_mode"] = "keyboard"
    state["candidates"].append({"id": 8, "role": "textbox", "name": "Email", "focused": True})
    schema = action_schema(state)
    choices = schema["properties"]["action"]["anyOf"]
    kinds = {choice["properties"]["kind"]["const"] for choice in choices}
    assert kinds == {"type_text", "press_key", "scroll", "wait"}
    assert all(choice["additionalProperties"] is False for choice in choices)


def test_finish_only_offered_after_verified_completion():
    state = model_state()
    state["milestones"] = {"goal": True}
    choices = action_schema(state)["properties"]["action"]["anyOf"]
    assert [choice["properties"]["kind"]["const"] for choice in choices] == ["finish"]
    state["milestones"]["goal"] = False
    assert all(
        choice["properties"]["kind"]["const"] != "finish"
        for choice in action_schema(state)["properties"]["action"]["anyOf"]
    )


def test_empty_touch_viewport_offers_scroll_or_wait():
    state = model_state()
    state.update(input_mode="touch", candidates=[], milestones={"goal": False})
    choices = action_schema(state)["properties"]["action"]["anyOf"]
    assert {choice["properties"]["kind"]["const"] for choice in choices} == {"scroll", "wait"}


def test_known_information_is_perceived_and_bounded():
    from frictionlab.planning.memory import PersonaMemory

    memory = PersonaMemory.__new__(PersonaMemory)
    memory.known_information = {}
    for number in range(6):
        memory.remember(f"Previously perceived state {number}")
    assert len(memory.known_information) == 4
    assert list(memory.known_information.values()) == [
        f"Previously perceived state {number}" for number in (2, 3, 4, 5)
    ]
    assert "Previously perceived state 0" not in memory.known_information


def test_trusted_completion_stops_without_another_model_decision():
    async def run():
        broker = FakeBroker(completed=True)
        bridge = bridge_for(broker)
        result = await bridge.dispatch(
            {"kind": "click", "observation_id": str(broker.current.id), "candidate_id": 7}
        )
        assert result["completion_verified"] and broker.finished
        assert len(broker.steps) == 1

    asyncio.run(run())


def test_keyboard_activation_requires_observed_focus_and_typing_requires_textbox():
    state = model_state()
    state["input_mode"] = "keyboard"
    variants = action_schema(state)["properties"]["action"]["anyOf"]
    keys = next(
        choice for choice in variants if choice["properties"]["kind"]["const"] == "press_key"
    )["properties"]["key"]["enum"]
    assert "Enter" not in keys and "Space" not in keys
    assert not any(choice["properties"]["kind"]["const"] == "type_text" for choice in variants)
    state["candidates"].append({"id": 8, "role": "textbox", "name": "Email", "focused": True})
    variants = action_schema(state)["properties"]["action"]["anyOf"]
    typing = next(
        choice for choice in variants if choice["properties"]["kind"]["const"] == "type_text"
    )
    assert typing["properties"]["candidate_id"]["enum"] == [8]


@pytest.mark.parametrize(
    "setting",
    [
        {"mode": "isolated_code"},
        {"vision_enabled": True},
        {"provider_retries": 1},
        {"max_steps": 100},
        {"max_input_tokens": 3000, "max_output_tokens": 600},
    ],
)
def test_unsupported_or_unbounded_settings_rejected(setting):
    with pytest.raises(ValidationError):
        AgentLimits.model_validate(setting)


def test_missing_model_is_a_setup_failure(monkeypatch):
    runtime = LocalModelRuntime()
    runtime.resources["model"]["local_path"] = "models/missing.gguf"
    with pytest.raises(PlannerStopped) as error:
        runtime.check_resources()
    assert error.value.category == "model_setup" and runtime.process is None


class FakeBroker:
    def __init__(self, *, result="progress", completed=False):
        self.current = SimpleNamespace(id=uuid4())
        self.closed = False
        self.persona = SimpleNamespace(behavior=SimpleNamespace(retry_limit=2))
        self.steps = []
        self.writer = Writer()
        self.result = result
        self.completed = completed

    async def verify_completion(self):
        return {"goal": self.completed}

    async def act(self, action):
        step = StepResult(
            action=action,
            action_id=action.id,
            observation_before=action.observation_id,
            observation_after=action.observation_id,
            result=self.result,
            application_seconds=0,
            detail="Captured fake application outcome",
        )
        self.steps.append(step)
        return step


def bridge_for(broker, limits=None):
    async def refresh():
        pass

    memory = SimpleNamespace(
        state={"candidates": [{"id": 7, "name": "Observed control"}]}, messages=[], refresh=refresh
    )
    return ToolBridge(broker, memory, limits or AgentLimits(), asyncio.get_running_loop())


@pytest.mark.parametrize(
    "case,category",
    [
        ("stale", "grounding_failure"),
        ("missing_candidate", "grounding_failure"),
        ("invalid_arguments", "invalid_tool_arguments"),
        ("early_finish", "premature_finish"),
        ("finish_wrong_tool", "invalid_tool_arguments"),
        ("stopped", "cancelled"),
    ],
)
def test_tool_rejections_precede_browser_action(case, category):
    async def run():
        broker = FakeBroker()
        bridge = bridge_for(broker)
        value = {"kind": "click", "observation_id": str(broker.current.id), "candidate_id": 7}
        final = False
        if case == "stale":
            value["observation_id"] = str(uuid4())
        elif case == "missing_candidate":
            value["candidate_id"] = 999
        elif case == "invalid_arguments":
            value["url"] = "https://production.invalid/"
        elif case in {"early_finish", "finish_wrong_tool"}:
            value = {"kind": "finish", "observation_id": str(broker.current.id)}
            final = case == "early_finish"
        else:
            bridge.stopped = True
        with pytest.raises(PlannerStopped) as error:
            await bridge.dispatch(value, final=final)
        assert error.value.category == category and not broker.steps

    asyncio.run(run())


def test_tool_limit_prevents_additional_application_action():
    async def run():
        broker = FakeBroker()
        bridge = bridge_for(broker, AgentLimits(max_tool_calls=1))
        action = {"kind": "click", "observation_id": str(broker.current.id), "candidate_id": 7}
        await bridge.dispatch(action)
        with pytest.raises(PlannerStopped) as error:
            await bridge.dispatch(action)
        assert error.value.category == "tool_limit" and len(broker.steps) == 1

    asyncio.run(run())


def test_profile_retry_ceiling_stops_without_churn_claim():
    async def run():
        broker = FakeBroker(result="no_change")
        bridge = bridge_for(broker)
        action = {"kind": "click", "observation_id": str(broker.current.id), "candidate_id": 7}
        await bridge.dispatch(action)
        await bridge.dispatch(action)
        with pytest.raises(PlannerStopped) as error:
            await bridge.dispatch(action)
        assert error.value.category == "action_retry_limit" and len(broker.steps) == 3

    asyncio.run(run())


def test_framework_rejects_prompt_requested_unapproved_tool():
    async def run():
        broker = FakeBroker()
        bridge = bridge_for(broker)
        model, _, _, _ = adapter("{}")
        agent = BoundedPersonaAgent(model, bridge.memory, bridge, AgentLimits())
        with pytest.raises(PlannerStopped):
            agent.execute_tool_call("python_interpreter", {"code": "open('secret')"})
        assert not broker.steps and set(agent.tools) == {"browser_action", "final_answer"}

    asyncio.run(run())


def test_multiple_tool_calls_cannot_mutate_browser():
    async def run():
        broker = FakeBroker()
        bridge = bridge_for(broker)
        model, _, _, _ = adapter("{}")
        agent = BoundedPersonaAgent(model, bridge.memory, bridge, AgentLimits())
        message = SimpleNamespace(tool_calls=[1, 2])
        with pytest.raises(PlannerStopped):
            list(agent.process_tool_calls(message, None))
        assert not broker.steps

    asyncio.run(run())
