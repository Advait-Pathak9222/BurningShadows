from __future__ import annotations

import pytest

from controlplane.models import ReviewCase, ReviewOutcome, ReviewReason
from controlplane.review import ReviewEconomics, ReviewQueue

ECONOMICS = ReviewEconomics(
    reviewer_cost_per_hour_inr=1200.0,
    minutes_per_case=6.0,
    capacity_minutes_per_hour=120.0,
)


def _case(index: int, *, loss: float, sla: int, route: str = "internal-kb") -> ReviewCase:
    return ReviewCase(
        interaction_id=f"case-{index:04d}",
        route=route,
        reason=ReviewReason.EFFECT_HELD,
        expected_loss_inr=loss,
        review_minutes=ECONOMICS.minutes_per_case,
        review_cost_inr=ECONOMICS.cost_per_case_inr,
        sla_minutes=sla,
    )


def _served(cases: list[ReviewCase], strategy: str, minutes: float) -> list[str]:
    queue = ReviewQueue(ECONOMICS, strategy=strategy)
    for case in cases:
        queue.submit(case)
    return [
        decision.case.interaction_id
        for decision in queue.drain(minutes)
        if decision.outcome is not ReviewOutcome.SHED
    ]


def test_density_serves_the_most_valuable_case_first() -> None:
    cases = [_case(0, loss=10.0, sla=60), _case(1, loss=9000.0, sla=60)]
    assert _served(cases, "density", 6.0) == ["case-0001"]


def test_deadline_serves_the_tightest_sla_first() -> None:
    cases = [_case(0, loss=9000.0, sla=240), _case(1, loss=10.0, sla=15)]
    assert _served(cases, "deadline", 6.0) == ["case-0001"]


def test_the_shipped_rule_puts_deadline_ahead_of_value() -> None:
    """The tradeoff the ablations exist to price: a tight SLA outranks a rich case."""
    cases = [_case(0, loss=9000.0, sla=240), _case(1, loss=10.0, sla=15)]
    assert _served(cases, "deadline_density", 6.0) == ["case-0001"]


def test_fifo_ignores_both() -> None:
    cases = [_case(0, loss=10.0, sla=240), _case(1, loss=9000.0, sla=15)]
    assert _served(cases, "fifo", 6.0) == ["case-0000"]


def test_the_random_null_is_seeded_and_reproducible() -> None:
    """A null that is resampled until it loses is not a null."""
    cases = [_case(index, loss=100.0 * index, sla=60) for index in range(20)]
    assert _served(cases, "random", 30.0) == _served(cases, "random", 30.0)


def test_the_random_null_is_not_arrival_order() -> None:
    cases = [_case(index, loss=100.0, sla=60) for index in range(20)]
    assert _served(cases, "random", 30.0) != _served(cases, "fifo", 30.0)


def test_an_unknown_strategy_is_refused_rather_than_defaulted() -> None:
    """Silently falling back to the shipped rule would make a comparison meaningless."""
    queue = ReviewQueue(ECONOMICS, strategy="whatever")
    queue.submit(_case(0, loss=1.0, sla=60))
    with pytest.raises(ValueError, match="unknown serving strategy"):
        queue.drain(60.0)


def test_every_strategy_serves_the_same_number_of_cases() -> None:
    """Capacity is fixed, so ordering changes who is served and never how many.

    This is what makes the comparison a comparison: any rule that served more would be
    winning on throughput rather than on allocation.
    """
    cases = [
        _case(index, loss=100.0 * (index % 7), sla=15 + 15 * (index % 4))
        for index in range(40)
    ]
    counts = {
        strategy: len(_served(cases, strategy, 60.0))
        for strategy in ("deadline_density", "fifo", "random", "density", "deadline")
    }
    assert len(set(counts.values())) == 1
