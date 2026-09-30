"""Export the shared Pydantic contracts without running a test or model."""

import json
from pathlib import Path

from frictionlab.browser.evidence import BrowserObservation, CoordinateSpace
from frictionlab.contracts import models
from frictionlab.planning.contracts import AgentLimits, Decision


def main():
    directory = Path(__file__).resolve().parents[1] / "docs" / "schemas"
    directory.mkdir(parents=True, exist_ok=True)
    count = 0
    for name in sorted(vars(models)):
        contract = getattr(models, name)
        if (
            isinstance(contract, type)
            and issubclass(contract, models.Contract)
            and contract is not models.Contract
        ):
            (directory / f"{name}.schema.json").write_text(
                json.dumps(contract.model_json_schema(), indent=2), encoding="utf-8"
            )
            count += 1
    for contract in (BrowserObservation, CoordinateSpace, AgentLimits, Decision):
        (directory / f"{contract.__name__}.schema.json").write_text(
            json.dumps(contract.model_json_schema(), indent=2), encoding="utf-8"
        )
        count += 1
    print(f"Exported {count} contract schemas")


if __name__ == "__main__":
    main()
