from __future__ import annotations

import pytest

from controlplane.guarantees.conformal import binomial_upper_bound, learn_then_test


def test_threshold_relaxes_monotonically_with_alpha() -> None:
    scores = [index / 99 for index in range(100)]
    harmed = [score > 0.60 for score in scores]
    strict = learn_then_test(route="r", scores=scores, harmed=harmed, alpha=0.15, delta=0.1)
    relaxed = learn_then_test(route="r", scores=scores, harmed=harmed, alpha=0.30, delta=0.1)
    assert relaxed.threshold >= strict.threshold
    assert strict.upper_bound <= strict.alpha
    assert relaxed.upper_bound <= relaxed.alpha


def test_bound_survives_a_corpus_larger_than_the_shipped_one() -> None:
    """The direct binomial form overflowed once a route released a few thousand rows.

    `comb(trials, count)` is an exact Python int, and past roughly a thousand trials it
    exceeds the float range before the probability factors can scale it back down. The
    shipped corpus peaks at 475 released rows on one route, so nothing caught this until
    the bound was fitted on 5,083 rows of real traffic.
    """
    assert binomial_upper_bound(362, 5083, 0.0047619) == pytest.approx(0.081082, abs=1e-5)
    # Comfortably past where the old implementation raised OverflowError.
    assert 0.0 < binomial_upper_bound(3000, 50000, 0.0047619) < 1.0


def test_bound_tightens_with_more_evidence_at_a_fixed_rate() -> None:
    """More rows at the same empirical rate must certify a tighter bound, and the bound
    must never fall below the rate it is bounding."""
    previous = 1.0
    for released in (100, 1_000, 10_000):
        bound = binomial_upper_bound(released // 20, released, 0.05)
        assert bound > 0.05
        assert bound < previous
        previous = bound
