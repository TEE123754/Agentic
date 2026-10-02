"""Assessment contracts: unknown coverage never becomes a passing check."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CATEGORIES = (
    "functionality",
    "usability",
    "accessibility",
    "responsiveness",
    "performance",
    "security",
)
Category = Literal[
    "functionality", "usability", "accessibility", "responsiveness", "performance", "security"
]


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    categories: list[Category] = Field(
        default_factory=lambda: list(CATEGORIES), min_length=1, max_length=6
    )
    mode: Literal["url_only", "snapshot", "capture"] = "url_only"
    html: str | None = Field(default=None, max_length=2_000_000)
    bundle_b64: str | None = Field(default=None, max_length=14_000_000)
    capture_authorized: bool = False
    ai_enabled: bool = False

    @model_validator(mode="after")
    def boundaries(self):
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Select each category once")
        if any(ord(c) < 32 for c in self.url):
            raise ValueError("URL contains invalid control characters")
        if self.mode == "capture" and not self.capture_authorized:
            raise ValueError(
                "Capture requires acknowledgement of the read-only endpoint and possible server effects"
            )
        if self.mode == "snapshot" and bool(self.html) == bool(self.bundle_b64):
            raise ValueError("Provide exactly one HTML document or ZIP snapshot")
        if self.mode != "snapshot" and (self.html is not None or self.bundle_b64 is not None):
            raise ValueError("Snapshot content requires snapshot mode")
        return self


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    category: Category
    title: str
    status: Literal["passed", "failed", "skipped", "incomplete"]
    severity: Literal["critical", "high", "medium", "low"] | None = None
    confidence: float = Field(default=1, ge=0, le=1)
    weight: int = Field(default=1, ge=1, le=5)
    detail: str
    evidence: list[str] = Field(default_factory=list)
    reproduction: list[str] = Field(default_factory=list)
    recommendation: str = ""
    ai_recommendation: str | None = None

    @model_validator(mode="after")
    def severity_matches(self):
        if (self.status == "failed") != (self.severity is not None):
            raise ValueError("Only a failed check has issue severity")
        return self


def scores(checks, selected):
    rows = {}
    for category in selected:
        items = [c for c in checks if c.category == category]
        graded = [c for c in items if c.status in {"passed", "failed"}]
        total = sum(c.weight for c in graded)
        rows[category] = {
            "score": round(100 * sum(c.weight for c in graded if c.status == "passed") / total)
            if total
            else None,
            "coverage": round(100 * len(graded) / len(items)) if items else 0,
            "confidence": round(sum(c.confidence for c in graded) / len(graded), 2)
            if graded
            else None,
            "counts": {
                status: sum(c.status == status for c in items)
                for status in ("passed", "failed", "skipped", "incomplete")
            },
        }
    graded = [c for c in checks if c.status in {"passed", "failed"}]
    weight = sum(c.weight for c in graded)
    return {
        "overall": round(100 * sum(c.weight for c in graded if c.status == "passed") / weight)
        if weight
        else None,
        "coverage": round(100 * len(graded) / len(checks)) if checks else 0,
        "categories": rows,
        "method": "Weighted pass fraction of executed checks only. Skipped/incomplete checks do not pass. Read coverage alongside every score; this is not a production readiness or human churn score.",
    }
