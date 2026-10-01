"""Resolve local configuration references without contacting any target or provider."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from frictionlab.contracts import EnvironmentPolicy, Journey, Persona, RunConfig

PACKAGE_DIRECTORY = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_DIRECTORY.parent
ASSET_ROOT = SOURCE_ROOT if (SOURCE_ROOT / "configs").is_dir() else PACKAGE_DIRECTORY / "_assets"
ROOT = Path(
    os.environ.get(
        "FRICTIONLAB_HOME", str(SOURCE_ROOT if ASSET_ROOT == SOURCE_ROOT else Path.cwd())
    )
).resolve()
CONFIG_DIRECTORY = ROOT / "configs" if (ROOT / "configs").is_dir() else ASSET_ROOT / "configs"
DEFAULT_ORIGIN = "http://127.0.0.1:8765"


class ConfigurationRejected(ValueError):
    """Contains safe diagnostics only; no rejected input values or credentials."""

    def __init__(self, diagnostics):
        self.diagnostics = tuple(diagnostics)
        super().__init__("; ".join(self.diagnostics))


def safe_validation_errors(exc: ValidationError):
    return tuple(
        f"{'.'.join(str(part) for part in error['loc']) or 'configuration'}: {error['msg']}"
        for error in exc.errors(include_input=False, include_url=False)
    )


def read_json(path: Path):
    try:
        if path.stat().st_size > 64 * 1024:
            raise ConfigurationRejected(("Configuration exceeds the 64 KiB limit",))
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationRejected(
            ("Configuration file is missing or is not valid UTF-8 JSON",)
        ) from exc


def load_reference(directory: Path, group: str, identifier: str, contract):
    root = directory.resolve()
    path = (root / group / f"{identifier}.json").resolve()
    if not path.is_relative_to(root):
        raise ConfigurationRejected(("Configuration reference escapes the registry",))
    if not path.is_file():
        raise ConfigurationRejected((f"Unknown {group} reference",))
    try:
        value = contract.model_validate(read_json(path))
    except ValidationError as exc:
        raise ConfigurationRejected(safe_validation_errors(exc)) from exc
    if value.id != identifier:
        raise ConfigurationRejected(("Registry filename and configuration ID disagree",))
    return value


@dataclass(frozen=True)
class ResolvedRun:
    config: RunConfig
    environment: EnvironmentPolicy
    personas: tuple[Persona, ...]
    journeys: tuple[Journey, ...]
    configuration_hash: str

    @property
    def requested_sessions(self):
        return len(self.personas) * len(self.journeys) * self.config.repetitions


def resolve_run(payload, directory=CONFIG_DIRECTORY, expected_origin=DEFAULT_ORIGIN):
    try:
        config = RunConfig.model_validate(payload)
    except ValidationError as exc:
        raise ConfigurationRejected(safe_validation_errors(exc)) from exc
    environment = load_reference(directory, "environments", config.environment, EnvironmentPolicy)
    if environment.replica_origins != (expected_origin,):
        raise ConfigurationRejected(
            ("Environment origin does not match the bundled fixture server",)
        )
    personas = tuple(
        load_reference(directory, "personas", item, Persona) for item in config.personas
    )
    journeys = tuple(
        load_reference(directory, "journeys", item, Journey) for item in config.journeys
    )
    payload_for_hash = {
        "run": config.model_dump(mode="json", exclude={"id"}),
        "environment": environment.model_dump(mode="json"),
        "personas": [p.model_dump(mode="json") for p in personas],
        "journeys": [j.model_dump(mode="json") for j in journeys],
    }
    digest = hashlib.sha256(json.dumps(payload_for_hash, sort_keys=True).encode()).hexdigest()
    return ResolvedRun(config, environment, personas, journeys, digest)
