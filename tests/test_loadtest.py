from __future__ import annotations

from controlplane.eval.runtime_report import _percentile


def test_percentile_has_no_synthetic_value_for_an_empty_sample() -> None:
    assert _percentile([], 99) is None


def test_percentile_uses_the_nearest_rank_tail() -> None:
    values = [4.0, 1.0, 3.0, 2.0]

    assert _percentile(values, 50) == 2.0
    assert _percentile(values, 99) == 4.0
