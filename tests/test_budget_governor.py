from __future__ import annotations

import pytest

from controlplane.economics import BudgetGovernor


def _governor(**overrides: float | int) -> BudgetGovernor:
    kwargs: dict[str, float | int] = {
        "budget_inr": 100.0,
        "rows_expected": 100,
        "floor_rate_inr": 0.20,
    }
    kwargs.update(overrides)
    return BudgetGovernor(**kwargs)  # type: ignore[arg-type]


def test_discretionary_spending_stops_before_it_eats_the_floor() -> None:
    """The defect this exists to fix: lambda alone let the allocator spend 3.75x its budget.

    The floor is not discretionary, so its cost has to be reserved rather than competed for.
    """
    governor = _governor(budget_inr=100.0, rows_expected=100, floor_rate_inr=0.20)
    assert not governor.mandatory_only()

    # 80 rupees committed with 50 rows left reserves 10, which still fits inside 100.
    governor.committed_inr = 80.0
    governor.rows_served = 50
    assert not governor.mandatory_only()

    # 92 committed plus the same 10 reserved would breach it.
    governor.committed_inr = 92.0
    assert governor.mandatory_only()


def test_the_reservation_covers_the_row_about_to_be_served() -> None:
    governor = _governor(rows_expected=10, floor_rate_inr=1.0)
    assert governor.rows_remaining == 10
    governor.commit(0.0)
    assert governor.rows_remaining == 9


def test_a_budget_below_the_floor_is_reported_infeasible_not_enforced() -> None:
    """An infeasible budget must never be resolved by skipping a mandatory check.

    The governor says so and keeps going; raising the budget or relaxing alpha is the
    operator's call.
    """
    starved = _governor(budget_inr=10.0, rows_expected=100, floor_rate_inr=0.20)
    assert not starved.feasible
    assert starved.mandatory_only()

    exact = _governor(budget_inr=20.0, rows_expected=100, floor_rate_inr=0.20)
    assert exact.feasible


def test_commit_accumulates_spend_and_rows() -> None:
    governor = _governor()
    governor.commit(1.5)
    governor.commit(2.5)
    assert governor.committed_inr == pytest.approx(4.0)
    assert governor.rows_served == 2


def test_rejects_incoherent_configuration() -> None:
    with pytest.raises(ValueError):
        _governor(budget_inr=-1.0)
    with pytest.raises(ValueError):
        _governor(rows_expected=0)
    with pytest.raises(ValueError):
        _governor(floor_rate_inr=-0.1)
    with pytest.raises(ValueError):
        _governor().commit(-1.0)
