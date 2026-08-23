from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from controlplane.economics.allocator import allocate_verification, expected_loss_averted_inr
from controlplane.models import (
    DetectionBundle,
    EvidenceRegime,
    HarmVector,
    RoutePolicy,
    TierEconomics,
)


def _policy(consequence: float) -> RoutePolicy:
    return RoutePolicy(
        route="test",
        jurisdiction="test",
        review_sla_minutes=30,
        alpha=0.2,
        delta=0.1,
        hourly_budget_inr=1.0,
        text_latency_slo_ms=10,
        effect_latency_slo_ms=100,
        retention_days=1,
        consent_required=False,
        human_review_required_for=[],
        consequence_inr={axis: consequence for axis in HarmVector.zeros().values_by_name()},
        policy_version="test",
        policy_hash="test",
    )


def _bundle(risk: float) -> DetectionBundle:
    harm = HarmVector(
        hallucination=risk,
        pii_leak=0,
        bias=0,
        unsafe_content=0,
        injection_or_exfil=0,
    )
    return DetectionBundle(
        harm=harm,
        evidence_regime=EvidenceRegime.GROUNDED,
        signals=[],
        latency_ms=1,
    )


def _tier() -> TierEconomics:
    return TierEconomics(
        tier=1,
        catch_rate=HarmVector(
            hallucination=0.8,
            pii_leak=0.8,
            bias=0.8,
            unsafe_content=0.8,
            injection_or_exfil=0.8,
        ),
        verification_cost_inr=1,
        delay_cost_inr=0,
    )


@given(
    risk=st.floats(min_value=0, max_value=1, allow_nan=False),
    low=st.floats(min_value=0, max_value=10_000, allow_nan=False),
    increment=st.floats(min_value=0, max_value=10_000, allow_nan=False),
)
def test_expected_loss_is_monotone_in_consequence(
    risk: float, low: float, increment: float
) -> None:
    bundle = _bundle(risk)
    assert expected_loss_averted_inr(bundle, _policy(low), _tier()) <= expected_loss_averted_inr(
        bundle, _policy(low + increment), _tier()
    )


@given(
    risk=st.floats(min_value=0, max_value=1, allow_nan=False),
    low_lambda=st.floats(min_value=0, max_value=100, allow_nan=False),
    increment=st.floats(min_value=0, max_value=100, allow_nan=False),
)
def test_raising_shadow_price_never_enables_a_check(
    risk: float, low_lambda: float, increment: float
) -> None:
    arguments = {
        "interaction_id": "property",
        "bundle": _bundle(risk),
        "policy": _policy(10),
        "tiers": [_tier()],
        "conformal_threshold": 1.0,
        "tool_calls": [],
    }
    low = allocate_verification(**arguments, shadow_price=low_lambda)
    high = allocate_verification(**arguments, shadow_price=low_lambda + increment)
    assert not (low.selected_tier is None and high.selected_tier is not None)
