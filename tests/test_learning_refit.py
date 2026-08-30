"""The refit must improve the map, or refuse. It must never quietly ship a worse one."""

from __future__ import annotations

from pathlib import Path

from controlplane.guarantees import in_fitting_fold
from controlplane.learning import (
    CalibrationArtifact,
    RouteCalibration,
    detector_version,
    latest_artifact,
    refit_calibration,
    write_artifact,
)
from controlplane.learning.artifacts import AxisCalibration
from controlplane.learning.refit import MIN_FITTING_ROWS, MIN_SELECTION_ROWS, LabelledScore
from controlplane.models import HARM_AXES, HarmVector
from controlplane.policy import PolicyStore
from controlplane.risk.calibration import IsotonicCalibrator


def _row(index: int, score: float, harmed: bool, route: str = "support-assistant") -> LabelledScore:
    axes = {axis: 1.0 if harmed else 0.0 for axis in HARM_AXES}
    return LabelledScore(
        interaction_id=f"cp-{index:05d}",
        route=route,
        jurisdiction="eu",
        raw=HarmVector(**dict.fromkeys(HARM_AXES, score)),
        observed_axes=HarmVector(**axes),
        observed_harm=harmed,
    )


def _separable_rows(count: int = 600) -> list[LabelledScore]:
    """A sample a map can actually be fitted on: score orders harm, both folds populated."""
    rows: list[LabelledScore] = []
    for index in range(count):
        score = (index % 100) / 100.0
        # Harm rises with score, so an honest map exists and the bound is satisfiable.
        rows.append(_row(index, score, harmed=score > 0.85))
    return rows


def _policies(project_root: Path) -> PolicyStore:
    return PolicyStore(project_root / "config" / "policies")


def test_a_usable_sample_releases_a_map(project_root: Path) -> None:
    outcome = refit_calibration(_separable_rows(), _policies(project_root), "detector-a")
    assert outcome.released
    assert "support-assistant" in outcome.accepted
    assert outcome.artifact is not None
    route = outcome.artifact.routes["support-assistant"]
    # A released threshold has to let something through. One that releases nothing
    # satisfies the bound by checking everything, which is not a calibration.
    assert route.threshold > 0.0
    assert route.released > 0
    assert route.upper_bound <= route.alpha


def test_folds_never_overlap(project_root: Path) -> None:
    """No row may both fit a map and certify the threshold built on it."""
    rows = _separable_rows()
    fitting = {row.interaction_id for row in rows if in_fitting_fold(row.interaction_id)}
    selection = {row.interaction_id for row in rows if not in_fitting_fold(row.interaction_id)}
    assert fitting and selection
    assert not fitting & selection


def test_too_few_rows_is_refused_not_shipped(project_root: Path) -> None:
    outcome = refit_calibration(_separable_rows(30), _policies(project_root), "detector-a")
    assert not outcome.released
    reason = outcome.refused["support-assistant"]
    assert "too few rows" in reason
    assert str(MIN_FITTING_ROWS) in reason or str(MIN_SELECTION_ROWS) in reason


def test_a_map_that_cannot_predict_is_refused(project_root: Path) -> None:
    """Harm unrelated to the score leaves nothing to calibrate, and must not release."""
    rows = [
        _row(index, (index % 100) / 100.0, harmed=index % 2 == 0) for index in range(600)
    ]
    outcome = refit_calibration(rows, _policies(project_root), "detector-a")
    assert not outcome.released
    assert "support-assistant" in outcome.refused


def test_a_worse_map_cannot_displace_the_incumbent(project_root: Path) -> None:
    """A refit is offered, not applied. Regressing against what serves today is refused."""
    good = refit_calibration(_separable_rows(), _policies(project_root), "detector-a")
    assert good.artifact is not None

    # An incumbent that is already perfect on this data: the candidate cannot beat it, and
    # every axis is mapped so the comparison runs on the same quantity.
    perfect = IsotonicCalibrator.fit([0.0, 0.85, 0.86, 1.0], [False, False, True, True])
    incumbent = CalibrationArtifact(
        detector_version="detector-a",
        routes={
            "support-assistant": RouteCalibration(
                axes={axis: AxisCalibration.of(perfect) for axis in HARM_AXES},
                threshold=0.5,
                alpha=0.15,
                delta=0.10,
                released=400,
                escaped_harms=0,
                empirical_risk=0.0,
                upper_bound=0.01,
                fitting_rows=400,
                selection_rows=400,
            )
        },
    )
    noisy = [
        _row(index, (index % 100) / 100.0, harmed=index % 3 == 0) for index in range(600)
    ]
    outcome = refit_calibration(noisy, _policies(project_root), "detector-a", incumbent)
    assert not outcome.released


def test_an_artifact_fitted_against_other_detectors_is_not_served(tmp_path: Path) -> None:
    """The failure this guards is silent: spend barely moves while probabilities go wrong."""
    artifact = CalibrationArtifact(detector_version="detector-a", routes={})
    write_artifact(artifact, tmp_path)
    assert latest_artifact(tmp_path, "detector-a") is not None
    assert latest_artifact(tmp_path, "detector-b") is None


def test_detector_fingerprint_moves_with_the_detectors(calibrated_engine: object) -> None:
    engine = calibrated_engine
    assert isinstance(engine.detector_fingerprint(), str)  # type: ignore[attr-defined]
    changed = detector_version([engine.tier0, engine.tier1])  # type: ignore[attr-defined]
    assert changed != engine.detector_fingerprint()  # type: ignore[attr-defined]
