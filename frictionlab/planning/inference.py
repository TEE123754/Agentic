"""Local configuration contains policy, never credentials or custom API endpoints."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from frictionlab.configuration import ROOT, ConfigurationRejected, read_json
from frictionlab.contracts.models import Contract
from frictionlab.planning.contracts import PlannerStopped


class InferenceSettings(Contract):
    provider: Literal["local", "groq", "gemini"] = "local"
    model: str = Field(default="", max_length=120, pattern=r"^[a-zA-Z0-9_./:-]*$")
    allow_remote: bool = False
    share_sanitized_state: bool = False
    free_tier_confirmed: bool = False
    max_requests: int = Field(default=24, ge=1, le=100, strict=True)
    max_tokens: int = Field(default=180000, ge=512, le=500000, strict=True)
    max_input_bytes: int = Field(default=20000, ge=512, le=24000, strict=True)
    max_runtime_seconds: int = Field(default=240, ge=1, le=900, strict=True)
    request_timeout_seconds: int = Field(default=30, ge=1, le=45, strict=True)
    max_retries: int = Field(default=0, ge=0, le=2, strict=True)
    fallback: Literal["pause"] = "pause"
    paid_fallback: Literal[False] = False

    @model_validator(mode="after")
    def explicit_remote(self):
        if re.match(r"^(?:gsk_|sk-|gh[pousr]_|AIza)", self.model):
            raise ValueError("Use a model identifier, never a credential")
        if any(
            os.environ.get(name) and self.model == os.environ.get(name)
            for name in ("GROQ_API_KEY", "GEMINI_API_KEY")
        ):
            raise ValueError("A credential cannot be used as a model identifier")
        if self.provider != "local" and not (
            self.model
            and self.allow_remote
            and self.share_sanitized_state
            and self.free_tier_confirmed
        ):
            raise ValueError(
                "Remote inference requires model, input-sharing opt-in and free-tier acknowledgement"
            )
        return self


def load_inference(path: Path | None = None):
    source = Path(path) if path else ROOT / "frictionlab.local.json"
    if path is None and not source.is_file():
        return InferenceSettings()
    try:
        return InferenceSettings.model_validate(read_json(source))
    except (ConfigurationRejected, ValidationError):
        raise PlannerStopped(
            "model_setup", "Inference configuration is invalid; check the documented policy fields"
        ) from None


def provider_key(provider):
    from frictionlab.credentials import get_key

    value = get_key(provider)
    if not value:
        raise PlannerStopped(
            "model_setup", "Connect a provider key in the app or configure your environment"
        )
    return value


def safe_text(value):
    """Known runtime keys and recognizable tokens never enter stored model output."""
    import re

    from frictionlab.credentials import known_keys

    text = str(value)
    for secret in known_keys():
        text = text.replace(secret, "[redacted credential]")
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        secret = os.environ.get(name, "")
        if secret:
            text = text.replace(secret, "[redacted credential]")
    text = re.sub(r"https?://[^\s<>\"']+", "[redacted URL]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted email]", text)
    text = re.sub(r"\b(?:gsk_|sk-|gh[pousr]_|AIza)[A-Za-z0-9_-]{8,}", "[redacted credential]", text)
    return re.sub(
        r"(?i)\b(?:authorization|api[_-]?key|secret|password|token)\s*[:=]\s*(?:Bearer\s+)?[^\s,;<>\"']+",
        "[redacted credential]",
        text,
    )
