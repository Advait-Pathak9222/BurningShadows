from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    index: int
    risk_score: float
    verification_cost_inr: float


def check_none(candidates: list[Candidate]) -> set[int]:
    return set()


def check_all(candidates: list[Candidate]) -> set[int]:
    return {candidate.index for candidate in candidates}


def fixed_rate(candidates: list[Candidate], spend_limit_inr: float) -> set[int]:
    """Spend on the highest raw detector scores, with no route economics.

    This is the steelman of current practice: it ranks the whole test set at once,
    so it sees scores the online allocator has not observed yet. Giving the baseline
    that advantage keeps the comparison honest when the allocator wins.
    """
    ranked = sorted(candidates, key=lambda candidate: candidate.risk_score, reverse=True)
    selected: set[int] = set()
    spent = 0.0
    for candidate in ranked:
        if spent + candidate.verification_cost_inr <= spend_limit_inr + 1e-9:
            selected.add(candidate.index)
            spent += candidate.verification_cost_inr
    return selected
