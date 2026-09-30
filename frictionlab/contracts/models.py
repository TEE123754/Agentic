"""Validated contracts shared by the API, runner, and future report pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
NonEmpty = Annotated[str, Field(min_length=1, max_length=2000)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
FIXTURE_BUILD = "storefront-phase1-v1"


def validate_relative_path(value: str):
    parsed = urlsplit(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(char) < 32 for char in value)
        or parsed.netloc
        or parsed.scheme
    ):
        raise ValueError(
            "Use an application-relative path without backslashes or control characters"
        )
    return value


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SessionOutcome(StrEnum):
    COMPLETED = "completed"
    ABANDONED_PATIENCE = "abandoned_patience"
    ABANDONED_REQUIREMENT = "abandoned_requirement_unmet"
    AGENT_FAILURE = "inconclusive_agent_failure"
    BLOCKED_ENVIRONMENT = "blocked_environment"
    BLOCKED_PROTECTION = "blocked_protection"
    PAUSED_QUOTA = "paused_quota"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ReportStatus(StrEnum):
    PENDING = "pending"
    REVIEWING = "reviewing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


class Viewport(Contract):
    width: int = Field(ge=320, le=3840, strict=True)
    height: int = Field(ge=480, le=2160, strict=True)


class Device(Contract):
    viewport: Viewport
    input_mode: Literal["mouse", "touch", "keyboard"]
    zoom_percent: int = Field(default=100, ge=100, le=400, strict=True)
    observation_mode: Literal["visible", "semantic_keyboard"] = "visible"


class Behavior(Contract):
    patience_initial: int = Field(ge=1, le=100, strict=True)
    retry_limit: int = Field(ge=0, le=5, strict=True)
    reading_budget_words_per_state: int = Field(ge=20, le=2000, strict=True)
    exploration_tendency: Probability
    required_information: tuple[Identifier, ...] = ()


class Persona(Contract):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: NonEmpty
    version: int = Field(default=1, ge=1, strict=True)
    device: Device
    behavior: Behavior
    friction_weights: dict[Identifier, Annotated[float, Field(ge=0, le=3, allow_inf_nan=False)]]

    @model_validator(mode="after")
    def keyboard_observation(self):
        if (
            self.device.observation_mode == "semantic_keyboard"
            and self.device.input_mode != "keyboard"
        ):
            raise ValueError("Semantic keyboard observation requires keyboard input")
        if not self.friction_weights:
            raise ValueError("At least one friction weight is required")
        return self


class CompletionCriterion(Contract):
    id: Identifier
    kind: Literal["heading_visible", "text_visible", "route_matches"]
    value: NonEmpty
    exact: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def relative_route(self):
        if self.kind == "route_matches":
            validate_relative_path(self.value)
        return self


class Journey(Contract):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=120)]
    goal: NonEmpty
    start_path: str = "/"
    completion: tuple[CompletionCriterion, ...] = Field(min_length=1, max_length=20)
    prohibited_operations: tuple[
        Literal["place_order", "real_payment", "external_dispatch", "delete_user"], ...
    ]

    @field_validator("start_path")
    @classmethod
    def local_path(cls, value):
        return validate_relative_path(value)

    @model_validator(mode="after")
    def bounded_journey(self):
        if len({c.id for c in self.completion}) != len(self.completion):
            raise ValueError("Completion criterion IDs must be unique")
        if (
            "place_order" not in self.prohibited_operations
            or "real_payment" not in self.prohibited_operations
        ):
            raise ValueError("Initial journeys must prohibit orders and real payments")
        return self


def validate_origin(value: str, loopback: bool = False):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use a plain HTTP(S) origin without credentials, paths, or queries")
    port = parsed.port
    if loopback and (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or port is None):
        raise ValueError(
            "Phase 1 permits only the numeric loopback HTTP fixture with an explicit port"
        )
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Origin port is invalid")
    return value.rstrip("/")


class IsolationEvidence(Contract):
    boundary: Literal["bundled_fixture_only"]
    separate_database: bool = Field(strict=True)
    disposable_data: bool = Field(strict=True)
    no_live_credentials: bool = Field(strict=True)
    external_integrations_mocked: bool = Field(strict=True)

    @model_validator(mode="after")
    def complete_evidence(self):
        if not all(
            (
                self.separate_database,
                self.disposable_data,
                self.no_live_credentials,
                self.external_integrations_mocked,
            )
        ):
            raise ValueError("All fixture isolation requirements must be satisfied")
        return self


class TrafficLimits(Contract):
    concurrency: int = Field(default=1, ge=1, le=2, strict=True)
    requests_per_second: int = Field(default=2, ge=1, le=10, strict=True)
    max_steps: int = Field(default=30, ge=1, le=100, strict=True)
    max_runtime_seconds: int = Field(default=300, ge=10, le=1800, strict=True)


class EnvironmentPolicy(Contract):
    id: Identifier
    execution_scope: Literal["bundled_fixture"]
    build_id: Literal["storefront-phase1-v1"]
    replica_origins: tuple[str, ...] = Field(min_length=1, max_length=1)
    dependency_origins: tuple[str, ...] = ()
    blocked_live_origins: tuple[str, ...] = Field(min_length=1)
    data_mode: Literal["synthetic_only"]
    credential_reference: Annotated[str, Field(pattern=r"^fixture://[a-z0-9_-]{1,64}$")]
    integration_mocks: tuple[
        Literal["payment", "email", "sms", "webhook", "inventory", "analytics"], ...
    ]
    isolation: IsolationEvidence
    service_workers: Literal["blocked"] = "blocked"
    cleanup_scope: Literal["run_owned_data_only"]
    limits: TrafficLimits
    prohibited_operations: tuple[
        Literal["place_order", "real_payment", "external_dispatch", "delete_user"], ...
    ]

    @field_validator("replica_origins")
    @classmethod
    def local_origins(cls, values):
        return tuple(validate_origin(v, loopback=True) for v in values)

    @field_validator("blocked_live_origins")
    @classmethod
    def blocked_origins(cls, values):
        return tuple(validate_origin(v) for v in values)

    @model_validator(mode="after")
    def fail_closed(self):
        if self.dependency_origins:
            raise ValueError("Phase 1 fixtures have no network dependencies")
        if set(self.replica_origins) & set(self.blocked_live_origins):
            raise ValueError("A blocked live origin cannot be a replica origin")
        required_mocks = {"payment", "email", "sms", "webhook", "inventory", "analytics"}
        if set(self.integration_mocks) != required_mocks or len(self.integration_mocks) != 6:
            raise ValueError("Every external integration must have exactly one local mock")
        required_blocks = {"place_order", "real_payment", "external_dispatch", "delete_user"}
        if set(self.prohibited_operations) != required_blocks:
            raise ValueError("Every prohibited operation must be blocked")
        return self


class RunConfig(Contract):
    id: UUID = Field(default_factory=uuid4)
    environment: Identifier
    personas: tuple[Identifier, ...] = Field(min_length=1, max_length=3)
    journeys: tuple[Identifier, ...] = Field(min_length=1, max_length=3)
    repetitions: int = Field(default=1, ge=1, le=5, strict=True)
    seed: int = Field(default=42, ge=0, le=2**32 - 1, strict=True)
    artifact_directory: Literal["artifacts/phase1"] = "artifacts/phase1"

    @model_validator(mode="after")
    def unique_references(self):
        if len(set(self.personas)) != len(self.personas) or len(set(self.journeys)) != len(
            self.journeys
        ):
            raise ValueError("Profile and journey references must be unique")
        return self


class EvidenceRef(Contract):
    path: str = Field(min_length=1, max_length=240)
    kind: Literal["screenshot", "aria", "dom", "event", "trace", "configuration"]

    @field_validator("path")
    @classmethod
    def relative_artifact(cls, value):
        path = PurePosixPath(value)
        if "\\" in value or ":" in value or path.is_absolute() or ".." in path.parts:
            raise ValueError("Evidence must refer to a local relative artifact path")
        return value


class Candidate(Contract):
    candidate_id: int = Field(ge=1, strict=True)
    observation_id: UUID
    target_id: NonEmpty
    role: Annotated[str, Field(min_length=1, max_length=60)]
    name: Annotated[str, Field(max_length=500)]
    visible: bool = Field(strict=True)
    enabled: bool = Field(strict=True)
    bounds: tuple[float, float, float, float]

    @field_validator("bounds")
    @classmethod
    def positive_box(cls, value):
        import math

        if not all(math.isfinite(v) for v in value) or value[2] < 0 or value[3] < 0:
            raise ValueError("Candidate bounds must be finite with non-negative dimensions")
        return value


class Observation(Contract):
    id: UUID = Field(default_factory=uuid4)
    target_id: NonEmpty
    route: NonEmpty
    viewport: Viewport
    candidates: tuple[Candidate, ...]
    semantic_text: str = Field(max_length=16000)
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def same_observation(self):
        if any(
            c.observation_id != self.id or c.target_id != self.target_id for c in self.candidates
        ):
            raise ValueError("Every candidate must belong to this observation and browser target")
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Candidate IDs must be unique within an observation")
        return self


class Action(Contract):
    id: UUID = Field(default_factory=uuid4)
    kind: Literal["click", "type_text", "press_key", "scroll", "wait", "finish"]
    observation_id: UUID
    candidate_id: int | None = Field(default=None, ge=1, strict=True)
    text_reference: Identifier | None = None
    key: Literal["Tab", "Shift+Tab", "Enter", "Space", "Escape", "ArrowUp", "ArrowDown"] | None = (
        None
    )
    direction: Literal["up", "down"] | None = None
    amount: int | None = Field(default=None, ge=1, le=800, strict=True)
    timeout_ms: int | None = Field(default=None, ge=1, le=10000, strict=True)

    @model_validator(mode="after")
    def tool_arguments(self):
        arguments = {"candidate_id", "text_reference", "key", "direction", "amount", "timeout_ms"}
        required = {
            "click": {"candidate_id"},
            "type_text": {"candidate_id", "text_reference"},
            "press_key": {"key"},
            "scroll": {"direction", "amount"},
            "wait": {"timeout_ms"},
            "finish": set(),
        }[self.kind]
        supplied = {name for name in arguments if getattr(self, name) is not None}
        if supplied != required:
            raise ValueError("Tool arguments do not match the chosen action")
        return self


class StepResult(Contract):
    action_id: UUID
    action: Action | None = None
    observation_before: UUID
    observation_after: UUID | None = None
    result: Literal["progress", "no_change", "validation_error", "blocked", "agent_error"]
    application_seconds: float = Field(ge=0, allow_inf_nan=False)
    inference_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    detail: str = Field(default="", max_length=2000)
    evidence: tuple[EvidenceRef, ...] = ()


class PlannerDecisionRecord(Contract):
    attempt: int = Field(ge=1, strict=True)
    seed: int = Field(ge=0, strict=True)
    observation_id: UUID
    status: Literal["pending", "valid", "failed"]
    inference_seconds: float = Field(ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0)
    raw_output: str = Field(default="", max_length=4096)
    usage: dict[str, int] = Field(default_factory=dict)
    decision: dict[str, object] | None = None
    category: str | None = None
    reason: str | None = None


class FrictionEvent(Contract):
    id: UUID = Field(default_factory=uuid4)
    detector: Identifier
    session_id: UUID
    action_id: UUID
    confidence: Probability
    patience_delta: int = Field(ge=-100, le=0, strict=True)
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)
    observation_before: UUID | None = None
    observation_after: UUID | None = None
    target_name: str = Field(default="", max_length=120)
    observed_behavior: str = Field(default="", max_length=500)
    source: Literal["observed_application"] = "observed_application"


class PatienceEntry(Contract):
    action_id: UUID
    before: int = Field(ge=0, le=100, strict=True)
    after: int = Field(ge=0, le=100, strict=True)
    delta: int = Field(ge=-100, le=100, strict=True)
    kind: Literal["penalty", "progress_credit", "unchanged", "excluded"]
    event_ids: tuple[UUID, ...] = ()
    reason: NonEmpty
    application_seconds: float = Field(ge=0, allow_inf_nan=False)
    inference_seconds: float = Field(ge=0, allow_inf_nan=False)
    queue_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    behavioral_delay_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def arithmetic(self):
        if self.after - self.before != self.delta:
            raise ValueError("Patience ledger delta must match before and after")
        if self.kind == "penalty" and (self.delta >= 0 or not self.event_ids):
            raise ValueError("A patience penalty needs a negative delta and evidence event")
        if self.kind == "progress_credit" and self.delta <= 0:
            raise ValueError("Progress credit must be positive")
        if self.kind in {"unchanged", "excluded"} and self.delta != 0:
            raise ValueError("Unchanged or excluded steps cannot adjust patience")
        return self


class AbandonmentDiagnosis(Contract):
    first_person: NonEmpty
    event_ids: tuple[UUID, ...] = Field(min_length=1)
    terminal_observation_id: UUID
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)
    method: Literal["deterministic_evidence_template"] = "deterministic_evidence_template"

    @field_validator("first_person")
    @classmethod
    def first_person_form(cls, value):
        if not value.startswith("I "):
            raise ValueError("Synthetic diagnosis must be written in first person")
        return value


class ProtectionEvent(Contract):
    id: UUID = Field(default_factory=uuid4)
    decision: Literal["allowed", "blocked"]
    layer: Literal["configuration", "action", "browser", "network", "cleanup"]
    reason: NonEmpty
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Finding(Contract):
    id: UUID = Field(default_factory=uuid4)
    title: Annotated[str, Field(min_length=1, max_length=160)]
    severity: Literal["critical", "high", "medium", "low"]
    observed_behavior: NonEmpty
    inferred_mechanism: NonEmpty
    confidence: Probability
    affected_sessions: int = Field(ge=1, strict=True)
    eligible_sessions: int = Field(ge=1, strict=True)
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)
    recommendation: NonEmpty
    verification: NonEmpty

    @model_validator(mode="after")
    def valid_denominator(self):
        if self.affected_sessions > self.eligible_sessions:
            raise ValueError("Affected sessions cannot exceed the eligible denominator")
        return self


class ReviewDisposition(Contract):
    finding_id: UUID
    status: Literal["confirmed", "dismissed", "requires_investigation"]
    note: NonEmpty


class ReportScope(Contract):
    phase: Literal[1, 2, 3, 4, 5] = 1
    build_id: str | None = None
    environment_id: str | None = None
    personas: tuple[str, ...] = ()
    journeys: tuple[str, ...] = ()
    seed: int | None = None
    configuration_hash: str | None = None
    runtime_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class CohortResults(Contract):
    requested_sessions: int = Field(default=0, ge=0, strict=True)
    executed_sessions: int = Field(default=0, ge=0, strict=True)
    eligible_sessions: int = Field(default=0, ge=0, strict=True)
    outcome_counts: dict[SessionOutcome, Annotated[int, Field(ge=0, strict=True)]] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def consistent_counts(self):
        if not self.eligible_sessions <= self.executed_sessions <= self.requested_sessions:
            raise ValueError("Eligible/executed/requested session counts are inconsistent")
        if sum(self.outcome_counts.values()) != self.executed_sessions:
            raise ValueError("Outcome counts must account for executed sessions exactly")
        return self


class CohortSessionSummary(Contract):
    session_id: UUID
    persona_id: Identifier
    journey_id: Identifier
    repetition: int = Field(ge=0, strict=True)
    seed: int = Field(ge=0, le=2**32 - 1, strict=True)
    execution_status: ExecutionStatus
    outcome: SessionOutcome | None = None
    steps: int = Field(ge=0, strict=True)
    friction_events: int = Field(ge=0, strict=True)
    model_calls: int = Field(ge=0, strict=True)
    passed_milestones: tuple[str, ...] = ()
    report_path: str

    @field_validator("report_path")
    @classmethod
    def safe_report_path(cls, value):
        path = PurePosixPath(value)
        if (
            "\\" in value
            or ":" in value
            or path.is_absolute()
            or ".." in path.parts
            or not value.endswith("/report.html")
        ):
            raise ValueError("Session report must use an owned relative HTML path")
        return value


class ProtectionSummary(Contract):
    target_requests: int = Field(default=0, ge=0, strict=True)
    environment_validated: bool = Field(default=False, strict=True)
    network_boundary_validated: bool = Field(default=False, strict=True)
    events: tuple[ProtectionEvent, ...]
    cleanup_outcome: NonEmpty
    boundary_scope: Literal["unvalidated", "owned_fixture_browser_proxy"] = "unvalidated"
    traffic_metrics: dict[str, int] = Field(default_factory=dict)
    sentinel_requests: int | None = Field(default=None, ge=0, strict=True)
    sentinel_data_unchanged: bool | None = Field(default=None, strict=True)


class ReviewSection(Contract):
    status: Literal["configuration_reviewed", "not_reviewed", "evidence_reviewed"]
    method: NonEmpty
    missing_evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    dispositions: tuple[ReviewDisposition, ...] = ()


class RunReport(Contract):
    run_id: UUID
    revision: int = Field(default=1, ge=1, strict=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    execution_status: ExecutionStatus
    report_status: ReportStatus
    terminal_reason: NonEmpty
    executive_summary: NonEmpty
    scope: ReportScope
    protection: ProtectionSummary
    cohort_results: CohortResults
    session_summaries: tuple[CohortSessionSummary, ...] = ()
    trajectories: tuple[StepResult, ...] = ()
    planner_decisions: tuple[PlannerDecisionRecord, ...] = ()
    friction_events: tuple[FrictionEvent, ...] = ()
    patience_ledger: tuple[PatienceEntry, ...] = ()
    abandonment_diagnosis: AbandonmentDiagnosis | None = None
    findings: tuple[Finding, ...] = ()
    visual_evidence: tuple[EvidenceRef, ...] = ()
    abandonment_explanations: tuple[str, ...] = ()
    recommendations: tuple[str, ...]
    comparison: NonEmpty
    review: ReviewSection

    @model_validator(mode="after")
    def reviewed_report(self):
        finding_ids = {finding.id for finding in self.findings}
        disposition_ids = [item.finding_id for item in self.review.dispositions]
        if len(finding_ids) != len(self.findings):
            raise ValueError("Finding IDs must be unique")
        if (
            len(set(disposition_ids)) != len(disposition_ids)
            or not set(disposition_ids) <= finding_ids
        ):
            raise ValueError("Review dispositions must reference unique findings in this report")
        if self.report_status == ReportStatus.READY and (
            self.execution_status in {ExecutionStatus.QUEUED, ExecutionStatus.RUNNING}
            or self.review.status != "evidence_reviewed"
            or self.review.missing_evidence
            or set(disposition_ids) != finding_ids
        ):
            raise ValueError(
                "A ready report requires terminal execution and complete evidence review"
            )
        if self.abandonment_diagnosis:
            known = {event.id for event in self.friction_events}
            if not set(self.abandonment_diagnosis.event_ids) <= known:
                raise ValueError("Abandonment diagnosis must reference recorded friction events")
            if self.cohort_results.outcome_counts.get(SessionOutcome.ABANDONED_PATIENCE) != 1:
                raise ValueError("Abandonment diagnosis requires a patience outcome")
        return self
