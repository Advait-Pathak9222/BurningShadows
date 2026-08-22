from __future__ import annotations

from dataclasses import dataclass
from math import comb


@dataclass(frozen=True)
class ConformalCalibration:
    route: str
    threshold: float
    alpha: float
    delta: float
    released: int
    escaped_harms: int
    empirical_risk: float
    upper_bound: float


def binomial_upper_bound(escaped_harms: int, released: int, delta: float) -> float:
    """Compute a one-sided exact binomial upper confidence bound."""
    if released < 0 or escaped_harms < 0 or escaped_harms > released:
        raise ValueError("escaped harms must lie between zero and released")
    if not 0.0 < delta < 1.0:
        raise ValueError("delta must lie in (0, 1)")
    if released == 0:
        return 0.0
    if escaped_harms >= released:
        return 1.0
    low = escaped_harms / released
    high = 1.0
    for _ in range(60):
        probability = (low + high) / 2.0
        tail = sum(
            comb(released, count) * probability**count * (1.0 - probability) ** (released - count)
            for count in range(escaped_harms + 1)
        )
        if tail > delta:
            low = probability
        else:
            high = probability
    return high


def learn_then_test(
    *,
    route: str,
    scores: list[float],
    harmed: list[bool],
    alpha: float,
    delta: float,
    grid_size: int = 21,
) -> ConformalCalibration:
    """Select the least checking that passes a finite-sample escape-risk test."""
    _validate_inputs(scores, harmed, alpha, delta, grid_size)
    candidates = [index / (grid_size - 1) for index in range(grid_size)]
    corrected_delta = delta / grid_size
    tested = [
        _test_threshold(route, threshold, scores, harmed, alpha, delta, corrected_delta)
        for threshold in candidates
    ]
    passing = [calibration for calibration in tested if calibration.upper_bound <= alpha]

    if passing:
        return max(passing, key=lambda calibration: calibration.threshold)
    return ConformalCalibration(
        route=route,
        threshold=0.0,
        alpha=alpha,
        delta=delta,
        released=0,
        escaped_harms=0,
        empirical_risk=0.0,
        upper_bound=0.0,
    )


def _validate_inputs(
    scores: list[float],
    harmed: list[bool],
    alpha: float,
    delta: float,
    grid_size: int,
) -> None:
    if len(scores) != len(harmed) or not scores:
        raise ValueError("scores and harmed must be non-empty and equally sized")
    if not 0.0 < alpha < 1.0 or not 0.0 < delta < 1.0:
        raise ValueError("alpha and delta must lie in (0, 1)")
    if grid_size < 2:
        raise ValueError("grid_size must be at least two")


def _test_threshold(
    route: str,
    threshold: float,
    scores: list[float],
    harmed: list[bool],
    alpha: float,
    delta: float,
    corrected_delta: float,
) -> ConformalCalibration:
    released_labels = [
        label for score, label in zip(scores, harmed, strict=True) if score < threshold
    ]
    released = len(released_labels)
    escaped = sum(released_labels)
    return ConformalCalibration(
        route=route,
        threshold=threshold,
        alpha=alpha,
        delta=delta,
        released=released,
        escaped_harms=escaped,
        empirical_risk=escaped / released if released else 0.0,
        upper_bound=binomial_upper_bound(escaped, released, corrected_delta),
    )
