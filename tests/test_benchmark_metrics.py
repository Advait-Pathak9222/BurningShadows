from __future__ import annotations

from math import isnan

import pytest

from controlplane.eval.benchmark_metrics import (
    average_precision,
    best_f1_threshold,
    flag_everything_f1,
    operating_point,
    rank_auc,
    spearman,
    within_band,
)


def test_auc_is_one_for_perfect_separation_and_half_for_none() -> None:
    assert rank_auc([False, False, True, True], [0.1, 0.2, 0.8, 0.9]) == pytest.approx(1.0)
    assert rank_auc([False, True, False, True], [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.5)


def test_auc_uses_mid_ranks_for_ties() -> None:
    """Optimistic tie handling would score this 1.0 and flatter every lexical detector.

    Two positives and two negatives all at 0.5, plus one clean split: the tied block must
    contribute 0.5, not 1.0.
    """
    assert rank_auc([False, True], [0.5, 0.5]) == pytest.approx(0.5)
    assert rank_auc([False, False, True, True], [0.1, 0.5, 0.5, 0.9]) == pytest.approx(0.875)


def test_auc_is_nan_when_a_class_is_missing() -> None:
    assert isnan(rank_auc([True, True], [0.1, 0.2]))
    assert isnan(rank_auc([False, False], [0.1, 0.2]))


def test_average_precision_matches_a_hand_computed_case() -> None:
    """Ranked P T P T: precision at the two hits is 1/2 and 2/4, each over a recall step
    of 1/2, so AP = 0.5 * 0.5 + 0.5 * 0.5 = 0.5."""
    labels = [False, True, False, True]
    scores = [0.9, 0.8, 0.7, 0.6]
    assert average_precision(labels, scores) == pytest.approx(0.5)


def test_average_precision_is_one_for_perfect_ranking() -> None:
    assert average_precision([True, True, False, False], [0.9, 0.8, 0.2, 0.1]) == (
        pytest.approx(1.0)
    )


def test_average_precision_pools_ties_rather_than_ordering_within_them() -> None:
    """A detector that emits one constant score has produced no ranking at all, so its
    AUPRC must be the base rate -- not the 1.0 that an arbitrary within-tie order gives."""
    labels = [True, False, True, False]
    assert average_precision(labels, [0.5] * 4) == pytest.approx(0.5)


def test_operating_point_reports_the_full_confusion_summary() -> None:
    point = operating_point([True, True, False, False], [0.9, 0.4, 0.8, 0.1], 0.5)
    assert point.flagged == 2
    assert point.precision == pytest.approx(0.5)
    assert point.recall == pytest.approx(0.5)
    assert point.f1 == pytest.approx(0.5)
    assert point.false_positive_rate == pytest.approx(0.5)


def test_a_threshold_above_every_score_flags_nothing_and_is_degenerate() -> None:
    point = operating_point([True, False], [0.4, 0.1], 0.9)
    assert point.flagged == 0
    assert point.f1 == 0.0
    assert point.is_degenerate


def test_best_f1_threshold_is_chosen_on_the_split_it_is_given() -> None:
    labels = [False, False, True, True]
    scores = [0.1, 0.2, 0.8, 0.9]
    threshold = best_f1_threshold(labels, scores)
    assert operating_point(labels, scores, threshold).f1 == pytest.approx(1.0)


def test_spearman_is_one_for_a_monotone_rescaling() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert spearman(values, [10.0, 20.0, 30.0, 40.0]) == pytest.approx(1.0)
    assert spearman(values, [4.0, 3.0, 2.0, 1.0]) == pytest.approx(-1.0)


def test_spearman_is_nan_when_either_side_is_constant() -> None:
    """A constant side has no ranking to correlate. Returning 1.0 there would have made
    the degenerate corpora in docs/results/allocation-regime.md look like a perfect
    relationship rather than an absent one.
    """
    assert isnan(spearman([1.0, 2.0, 3.0], [5.0, 5.0, 5.0]))


def test_within_band_is_nan_safe() -> None:
    assert within_band(0.9, 0.86, 0.941)
    assert not within_band(0.5, 0.86, 0.941)
    assert not within_band(float("nan"), 0.0, 1.0)


def test_flagging_everything_is_reported_as_degenerate() -> None:
    """The check that caught our own Aegis result.

    At a 66% base rate a flag-everything policy scores F1 0.796, above the 0.62 published
    for Llama Guard Base. Our lexical detectors flagged 100% of Aegis rows and scored
    exactly that null, which without this check reads as a respectable number.
    """
    labels = [True] * 66 + [False] * 34
    point = operating_point(labels, [0.5] * 100, 0.1)
    assert point.flagged == 100
    assert point.is_degenerate
    assert point.f1 == pytest.approx(flag_everything_f1(labels), abs=1e-9)


def test_flag_everything_f1_is_the_base_rate_null() -> None:
    assert flag_everything_f1([True] * 50 + [False] * 50) == pytest.approx(2 / 3)
    assert flag_everything_f1([True] * 66 + [False] * 34) == pytest.approx(0.7952, abs=1e-4)
    assert flag_everything_f1([True] * 7 + [False] * 93) == pytest.approx(0.1308, abs=1e-4)


def test_a_real_operating_point_is_not_degenerate() -> None:
    point = operating_point([True, True, False, False], [0.9, 0.4, 0.8, 0.1], 0.5)
    assert not point.is_degenerate
