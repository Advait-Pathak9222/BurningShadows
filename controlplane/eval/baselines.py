from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    index: int
    risk_score: float
    expected_loss_inr: float
    verification_cost_inr: float
    mandatory: bool

    @property
    def value_density(self) -> float:
        return self.expected_loss_inr / max(self.verification_cost_inr, 1e-9)


def check_none(candidates: list[Candidate]) -> set[int]:
    return set()


def check_all(candidates: list[Candidate]) -> set[int]:
    return {candidate.index for candidate in candidates}


def fixed_rate(candidates: list[Candidate], spend_limit_inr: float) -> set[int]:
    """Spend on the highest raw detector scores without route economics."""
    return _fill(candidates, spend_limit_inr, key=lambda candidate: candidate.risk_score)


def economic_allocator(candidates: list[Candidate], spend_limit_inr: float) -> set[int]:
    """Honor the guarantee floor, then fill remaining budget by value density."""
    selected = {candidate.index for candidate in candidates if candidate.mandatory}
    spent = sum(
        candidate.verification_cost_inr for candidate in candidates if candidate.index in selected
    )
    remaining = max(0.0, spend_limit_inr - spent)
    optional = [candidate for candidate in candidates if candidate.index not in selected]
    return selected | _fill(optional, remaining, key=lambda candidate: candidate.value_density)


def _fill(
    candidates: list[Candidate],
    spend_limit_inr: float,
    *,
    key: Callable[[Candidate], float],
) -> set[int]:
    ranked = sorted(candidates, key=key, reverse=True)
    selected: set[int] = set()
    spent = 0.0
    for candidate in ranked:
        if spent + candidate.verification_cost_inr <= spend_limit_inr + 1e-9:
            selected.add(candidate.index)
            spent += candidate.verification_cost_inr
    return selected
