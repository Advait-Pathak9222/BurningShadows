from __future__ import annotations

from controlplane.guarantees.conformal import learn_then_test


def test_threshold_relaxes_monotonically_with_alpha() -> None:
    scores = [index / 99 for index in range(100)]
    harmed = [score > 0.60 for score in scores]
    strict = learn_then_test(route="r", scores=scores, harmed=harmed, alpha=0.15, delta=0.1)
    relaxed = learn_then_test(route="r", scores=scores, harmed=harmed, alpha=0.30, delta=0.1)
    assert relaxed.threshold >= strict.threshold
    assert strict.upper_bound <= strict.alpha
    assert relaxed.upper_bound <= relaxed.alpha
