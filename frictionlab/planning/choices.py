"""Short model selections expanded only from the current trusted action schema."""

from itertools import product

from frictionlab.planning.contracts import Decision, PlannerStopped, action_schema

PROTOCOL = "semantic_choice_v1"
INSTRUCTION = (
    "Return ONLY {\"choice\":\"one exact entry from action_choices\"}. "
    "Choose the next permitted action for the goal using current control names and focus. "
    "Do not return an action object, observation ID, explanation or other fields. "
    "For offscreen content prefer scroll:down:600 to avoid many tiny scrolls. "
    "For keyboard input Enter activates the CURRENT focused control; Tab moves away."
)


def available_choices(state):
    result = {}
    for variant in action_schema(state)["properties"]["action"]["anyOf"]:
        properties = variant["properties"]
        kind = properties["kind"]["const"]
        fields = [key for key in properties if key not in {"kind", "observation_id"}]
        values = [properties[key].get("enum", [1000]) for key in fields]
        for selected in product(*values):
            label = ":".join([kind, *(str(value) for value in selected)])
            result[label] = {
                "kind": kind,
                "observation_id": state["observation_id"],
                **dict(zip(fields, selected, strict=True)),
            }
    if not result or len(result) > 512:
        raise PlannerStopped("grounding_failure", "Available action choices exceed their bounds.")
    return result


def expand_choice(payload, choices):
    if (
        not isinstance(payload, dict)
        or set(payload) != {"choice"}
        or not isinstance(payload["choice"], str)
        or payload["choice"] not in choices
    ):
        raise PlannerStopped("invalid_model_output", "Model must select one current permitted action.")
    choice = payload["choice"]
    return Decision(
        action=choices[choice],
        rationale=f"Model selected permitted action {choice}. Description supplied by trusted adapter.",
    )
