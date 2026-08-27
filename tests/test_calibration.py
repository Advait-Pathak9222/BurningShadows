from __future__ import annotations

import pytest

from controlplane.risk.calibration import IsotonicCalibrator, expected_calibration_error


def test_tied_scores_pool_into_one_block() -> None:
    """Isotonic regression must pool equal x-values before pool-adjacent-violators runs.

    Feeding ties in one row at a time leaves separate equal-x blocks that PAVA will not
    merge, because a run of negatives followed by positives is not a monotonicity
    violation. `predict` then returns the first block whose upper bound covers the score
    -- the zero-probability one -- so a tied score always calibrated to its worst tie
    group. A synthetic detector with raw AUC 0.9893 came out of calibration at 0.5000.
    """
    scores = [0.1] * 10 + [0.9] * 10
    labels = [False] * 10 + [False] * 2 + [True] * 8
    calibrator = IsotonicCalibrator.fit(scores, labels)

    assert calibrator.predict(0.1) == pytest.approx(0.0)
    # 8 of the 10 rows at 0.9 are positive, so that block must carry 0.8, not 0.0.
    assert calibrator.predict(0.9) == pytest.approx(0.8)


def test_a_separating_discrete_detector_survives_calibration() -> None:
    """The end-to-end property the tie bug broke: ranking must be preserved.

    Real detectors emit ties constantly -- rule hits, quantised outputs, bounded
    lexical scores -- so this is the common case, not an edge case.
    """
    calibrator = IsotonicCalibrator.fit([0.2] * 50 + [0.8] * 50, [False] * 50 + [True] * 50)
    assert calibrator.predict(0.8) > calibrator.predict(0.2)
    assert calibrator.predict(0.8) == pytest.approx(1.0)
    assert calibrator.predict(0.2) == pytest.approx(0.0)


def test_probabilities_are_monotone_in_the_score() -> None:
    scores = [index / 100 for index in range(100)]
    labels = [score > 0.6 for score in scores]
    calibrator = IsotonicCalibrator.fit(scores, labels)
    predictions = [calibrator.predict(score) for score in scores]
    assert predictions == sorted(predictions)


def test_predictions_stay_inside_the_unit_interval() -> None:
    calibrator = IsotonicCalibrator.fit([0.0, 0.5, 1.0], [False, True, True])
    for score in (-5.0, 0.0, 0.25, 0.5, 0.75, 1.0, 5.0):
        assert 0.0 <= calibrator.predict(score) <= 1.0


def test_fit_rejects_mismatched_or_empty_input() -> None:
    with pytest.raises(ValueError):
        IsotonicCalibrator.fit([], [])
    with pytest.raises(ValueError):
        IsotonicCalibrator.fit([0.1, 0.2], [True])


def test_expected_calibration_error_is_zero_for_a_perfect_map() -> None:
    assert expected_calibration_error([0.0] * 10 + [1.0] * 10, [False] * 10 + [True] * 10) == (
        pytest.approx(0.0)
    )
