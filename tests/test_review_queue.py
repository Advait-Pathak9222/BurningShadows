from __future__ import annotations

import pytest

from controlplane.models import (
    DecisionTrace,
    EvidenceRegime,
    HarmVector,
    ReviewCase,
    ReviewOutcome,
    ReviewReason,
    RoutePolicy,
    Verdict,
)
from controlplane.review import ReviewEconomics, ReviewQueue, case_from_trace

ECONOMICS = ReviewEconomics(
    reviewer_cost_per_hour_inr=1200.0, minutes_per_case=6.0, capacity_minutes_per_hour=120.0
)


def _policy(route: str, sla: int) -> RoutePolicy:
    return RoutePolicy(
        route=route,
        jurisdiction="eu",
        review_sla_minutes=sla,
        alpha=0.15,
        delta=0.1,
        hourly_budget_inr=100.0,
        text_latency_slo_ms=100,
        effect_latency_slo_ms=1000,
        retention_days=30,
        consent_required=False,
        human_review_required_for=[],
        consequence_inr=dict.fromkeys(HarmVector.zeros().values_by_name(), 1000.0),
        policy_version="test",
        policy_hash="test",
    )


def _trace(
    verdict: Verdict, route: str = "support-assistant", loss: float = 100.0
) -> DecisionTrace:
    return DecisionTrace(
        interaction_id=f"{route}-{verdict}-{loss:.0f}",
        route=route,
        jurisdiction="eu",
        verdict=verdict,
        reason="synthetic",
        harm=HarmVector.zeros(),
        evidence_regime=EvidenceRegime.GROUNDED,
        selected_tier=None,
        forced_by_conformal=False,
        conformal_threshold=0.1,
        conformal_alpha=0.15,
        shadow_price=0.0,
        expected_loss_inr=loss,
        assurance_spend_inr=0.0,
        tier_decisions=[],
        effect_actions=[],
        policy_version="test",
        policy_hash="test",
        detector_latency_ms=0.0,
    )


def _case(route: str, sla: int, loss: float) -> ReviewCase:
    case = case_from_trace(_trace("abstain", route, loss), _policy(route, sla), ECONOMICS)
    assert case is not None
    return case


@pytest.mark.parametrize("verdict", ["allow", "annotate"])
def test_settled_verdicts_raise_no_case(verdict: Verdict) -> None:
    """A person is pulled in only where the system declined to decide alone."""
    assert case_from_trace(_trace(verdict), _policy("support-assistant", 30), ECONOMICS) is None


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        ("abstain", ReviewReason.UNVERIFIABLE),
        ("hold", ReviewReason.EFFECT_HELD),
        ("block", ReviewReason.BLOCKED),
    ],
)
def test_undecided_verdicts_raise_a_case(verdict: Verdict, reason: ReviewReason) -> None:
    case = case_from_trace(_trace(verdict), _policy("support-assistant", 30), ECONOMICS)
    assert case is not None
    assert case.reason is reason
    assert case.review_cost_inr == pytest.approx(120.0)


def test_a_review_costs_far_more_than_the_dearest_automated_check() -> None:
    """The premise of budgeting attention separately: 120 INR against 3.20."""
    assert ECONOMICS.cost_per_case_inr / 3.20 > 30


def test_capacity_is_never_exceeded() -> None:
    queue = ReviewQueue(ECONOMICS)
    for index in range(50):
        queue.submit(_case("internal-kb", 240, float(index)))
    decisions = queue.drain(minutes_available=30.0)
    served = [d for d in decisions if d.outcome is not ReviewOutcome.SHED]
    assert sum(d.case.review_minutes for d in served) <= 30.0
    assert len(decisions) == 50


def test_shed_cases_cost_nothing() -> None:
    queue = ReviewQueue(ECONOMICS)
    for index in range(10):
        queue.submit(_case("internal-kb", 240, float(index)))
    decisions = queue.drain(minutes_available=6.0)
    shed = [d for d in decisions if d.outcome is ReviewOutcome.SHED]
    assert shed
    assert all(d.spend_inr == 0.0 for d in shed)


def test_the_tightest_deadline_is_served_first() -> None:
    """Ordering by value alone lets a 15-minute finops case sit behind richer slow ones."""
    queue = ReviewQueue(ECONOMICS)
    queue.submit(_case("internal-kb", 240, 10_000.0))
    queue.submit(_case("finops-agent", 15, 10.0))
    decisions = queue.drain(minutes_available=6.0)
    served = [d for d in decisions if d.outcome is not ReviewOutcome.SHED]
    assert len(served) == 1
    assert served[0].case.route == "finops-agent"


def test_value_density_breaks_ties_within_a_deadline() -> None:
    queue = ReviewQueue(ECONOMICS)
    queue.submit(_case("support-assistant", 30, 5.0))
    queue.submit(_case("support-assistant", 30, 900.0))
    decisions = queue.drain(minutes_available=6.0)
    served = [d for d in decisions if d.outcome is not ReviewOutcome.SHED]
    assert served[0].case.expected_loss_inr == 900.0


def test_more_reviewers_shorten_the_wait() -> None:
    solo = ReviewEconomics(1200.0, 6.0, 60.0)
    pair = ReviewEconomics(1200.0, 6.0, 120.0)
    waits = []
    for economics in (solo, pair):
        queue = ReviewQueue(economics)
        for index in range(5):
            queue.submit(_case("internal-kb", 240, float(index)))
        decisions = queue.drain(minutes_available=30.0)
        waits.append(max(d.wait_minutes for d in decisions))
    assert waits[1] < waits[0]
