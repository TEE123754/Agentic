"""Deterministic fixture demonstration, distinct from autonomous persona execution."""

import json

from frictionlab.browser.broker import BrowserBroker
from frictionlab.configuration import CONFIG_DIRECTORY, read_json, resolve_run
from frictionlab.contracts.models import Action


async def demo(variant="healthy", persona_id="impatient_mobile"):
    resolved = resolve_run(read_json(CONFIG_DIRECTORY / "run.example.json"))
    async with BrowserBroker(resolved, variant=variant, persona_id=persona_id) as broker:
        if broker.persona.device.input_mode != "keyboard":
            for _ in range(6):
                if any(c.name == "Start checkout" for c in broker.current.candidates):
                    break
                await broker.act(
                    Action(
                        kind="scroll",
                        observation_id=broker.current.id,
                        direction="down",
                        amount=400,
                    )
                )
            candidate = next(c for c in broker.current.candidates if c.name == "Start checkout")
            await broker.act(
                Action(
                    kind="click",
                    observation_id=broker.current.id,
                    candidate_id=candidate.candidate_id,
                )
            )
            if variant != "dead_button":
                candidate = next(c for c in broker.current.candidates if c.role == "textbox")
                await broker.act(
                    Action(
                        kind="type_text",
                        observation_id=broker.current.id,
                        candidate_id=candidate.candidate_id,
                        text_reference="synthetic_email",
                    )
                )
                candidate = next(
                    c for c in broker.current.candidates if c.name == "Continue to order review"
                )
                await broker.act(
                    Action(
                        kind="click",
                        observation_id=broker.current.id,
                        candidate_id=candidate.candidate_id,
                    )
                )
        else:
            # Tab through controls using actual focus. No programmatic focusing or mouse fallback.
            for _ in range(12):
                if broker.current.focus["id"] == "start":
                    break
                await broker.act(
                    Action(kind="press_key", observation_id=broker.current.id, key="Tab")
                )
            await broker.act(
                Action(kind="press_key", observation_id=broker.current.id, key="Enter")
            )
            await broker.act(Action(kind="press_key", observation_id=broker.current.id, key="Tab"))
            await broker.act(
                Action(kind="press_key", observation_id=broker.current.id, key="Enter")
            )
        await broker.accessibility()
        await broker.act(Action(kind="finish", observation_id=broker.current.id))
    print(
        json.dumps(
            {
                "report_directory": str(broker.directory),
                "report_status": broker.report.report_status,
                "completion": broker.completion,
                "cleanup_errors": broker.cleanup_errors,
            },
            indent=2,
        )
    )
    return 0 if not broker.cleanup_errors and all(broker.completion.values()) else 1
