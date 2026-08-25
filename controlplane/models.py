from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

HARM_AXES: Final = (
    "hallucination",
    "pii_leak",
    "bias",
    "unsafe_content",
    "injection_or_exfil",
)


class HarmVector(BaseModel):
    """Represent overlapping harm probabilities without forcing one label."""

    model_config = ConfigDict(frozen=True)

    hallucination: float = Field(ge=0.0, le=1.0)
    pii_leak: float = Field(ge=0.0, le=1.0)
    bias: float = Field(ge=0.0, le=1.0)
    unsafe_content: float = Field(ge=0.0, le=1.0)
    injection_or_exfil: float = Field(ge=0.0, le=1.0)

    @classmethod
    def zeros(cls) -> HarmVector:
        return cls(
            hallucination=0.0,
            pii_leak=0.0,
            bias=0.0,
            unsafe_content=0.0,
            injection_or_exfil=0.0,
        )

    def values_by_name(self) -> dict[str, float]:
        # model_dump() here cost ~25 full serialisations per allocation decision.
        return {axis: float(getattr(self, axis)) for axis in HARM_AXES}

    def maximum(self) -> float:
        return max(float(getattr(self, axis)) for axis in HARM_AXES)

    def has_harm(self, threshold: float = 0.5) -> bool:
        return any(float(getattr(self, axis)) >= threshold for axis in HARM_AXES)


class LabelledSpan(BaseModel):
    """Ground truth for one clause of a response, by character offset."""

    model_config = ConfigDict(frozen=True)

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    harm: HarmVector


class EvidenceRegime(StrEnum):
    GROUNDED = "grounded"
    ESTIMABLE = "ungrounded_but_estimable"
    UNVERIFIABLE = "unverifiable"


class EffectClass(StrEnum):
    READ = "read"
    REVERSIBLE_WRITE = "reversible_write"
    IRREVERSIBLE_WRITE = "irreversible_write"
    FINANCIAL = "financial"
    EXTERNAL_FACING = "external_facing"


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, str | int | float | bool]
    effect_class: EffectClass | None = None


class Interaction(BaseModel):
    interaction_id: str
    split: Literal["calibration", "test", "scenario"]
    route: str
    jurisdiction: str = "eu"
    prompt: str
    response: str
    context_documents: list[str] = Field(default_factory=list)
    comparison_samples: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    truth: HarmVector = Field(default_factory=HarmVector.zeros)
    # Where the harm actually sits. Emitted by the generator from its own construction,
    # never inferred from detector agreement.
    spans: list[LabelledSpan] = Field(default_factory=list)
    shifted: bool = False


class DetectorSignal(BaseModel):
    name: str
    tier: int = Field(ge=0, le=2)
    scores: HarmVector
    latency_ms: float = Field(ge=0.0)
    evidence: list[str] = Field(default_factory=list)


class DetectionBundle(BaseModel):
    harm: HarmVector
    evidence_regime: EvidenceRegime
    signals: list[DetectorSignal]
    latency_ms: float = Field(ge=0.0)


class PreflightDecision(BaseModel):
    allowed: bool
    reasons: list[str]
    prompt_risk: HarmVector
    policy_version: str
    policy_hash: str
    latency_ms: float = Field(ge=0.0)


class RoutePolicy(BaseModel):
    route: str
    jurisdiction: str
    review_sla_minutes: int = Field(gt=0)
    alpha: float = Field(gt=0.0, lt=1.0)
    delta: float = Field(gt=0.0, lt=1.0)
    hourly_budget_inr: float = Field(gt=0.0)
    text_latency_slo_ms: float = Field(gt=0.0)
    effect_latency_slo_ms: float = Field(gt=0.0)
    retention_days: int = Field(ge=0)
    consent_required: bool
    human_review_required_for: list[EffectClass]
    consequence_inr: dict[str, float]
    policy_version: str
    policy_hash: str


class ReviewReason(StrEnum):
    UNVERIFIABLE = "unverifiable"
    EFFECT_HELD = "effect_held"
    BLOCKED = "blocked"


class ReviewCase(BaseModel):
    """One decision waiting on a person, priced in reviewer minutes."""

    model_config = ConfigDict(frozen=True)

    interaction_id: str
    route: str
    reason: ReviewReason
    expected_loss_inr: float = Field(ge=0.0)
    review_minutes: float = Field(gt=0.0)
    review_cost_inr: float = Field(ge=0.0)
    sla_minutes: int = Field(gt=0)
    # Minutes from the start of the traffic window. Without this the queue treats a whole
    # window of arrivals as landing at once and charges the last case served a wait equal
    # to the entire window, which made every SLA figure an upper bound rather than a
    # measurement. A case cannot be worked before it exists.
    arrived_at_minutes: float = Field(default=0.0, ge=0.0)

    @property
    def value_density(self) -> float:
        """Expected loss per reviewer minute; the queue's ordering key."""
        return self.expected_loss_inr / self.review_minutes


class ReviewOutcome(StrEnum):
    REVIEWED = "reviewed"
    SHED = "shed"
    BREACHED_SLA = "breached_sla"


class ReviewDecision(BaseModel):
    """What the queue did with a case, and what it cost."""

    model_config = ConfigDict(frozen=True)

    case: ReviewCase
    outcome: ReviewOutcome
    wait_minutes: float = Field(ge=0.0)
    spend_inr: float = Field(ge=0.0)


class ReviewVerdict(StrEnum):
    UPHELD = "upheld"
    OVERTURNED = "overturned"
    ESCALATED = "escalated"


class ReviewRecord(BaseModel):
    """A reviewer's decision on one case, and the label it produced."""

    model_config = ConfigDict(frozen=True)

    interaction_id: str
    route: str
    reviewer: str
    verdict: ReviewVerdict
    reason_code: str
    # What the reviewer determined was actually true, which is the label the system learns from.
    observed_harm: bool
    system_withheld: bool
    selected_tier: int | None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TierEconomics(BaseModel):
    tier: int = Field(ge=0, le=2)
    catch_rate: HarmVector
    verification_cost_inr: float = Field(ge=0.0)
    delay_cost_inr: float = Field(ge=0.0)


Verdict = Literal["allow", "annotate", "hold", "abstain", "block"]


class TierDecision(BaseModel):
    tier: int | None
    benefit_inr: float
    adjusted_cost_inr: float
    net_value_inr: float
    selected: bool
    reason: str


class DecisionTrace(BaseModel):
    interaction_id: str
    route: str
    jurisdiction: str
    verdict: Verdict
    reason: str
    harm: HarmVector
    evidence_regime: EvidenceRegime
    selected_tier: int | None
    forced_by_conformal: bool
    conformal_threshold: float
    conformal_alpha: float
    shadow_price: float
    expected_loss_inr: float
    assurance_spend_inr: float
    tier_decisions: list[TierDecision]
    effect_actions: list[str]
    policy_version: str
    policy_hash: str
    detector_latency_ms: float
    # `conformal_threshold` above is the threshold actually applied. When a session has
    # accumulated risk it sits below the fitted one, which is recorded separately so the
    # trace shows both the certified floor and the stricter bar this turn was held to.
    session_id: str | None = None
    session_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    fitted_conformal_threshold: float | None = None
    degraded: bool = False
    admission_mode: Literal["unbounded", "normal", "degraded"] = "unbounded"
    queue_wait_ms: float = Field(default=0.0, ge=0.0)
    mandatory_assessment_completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
