"""Versioned calibration artifacts, and the detector identity they are bound to.

A calibration map is a function of the raw detector score. Serve a map fitted against one
detector alongside a different detector and every probability downstream is quietly wrong
— and the failure is invisible in the cost metrics, because spend barely moves. Measured
on this corpus: swapping the isotonic maps for a cruder scaling changed 22.4% of tier
decisions and removed all 80 blocks while total spend stayed within 0.3%.

So an artifact records the detector it was fitted against, and loading refuses a mismatch
rather than leaving it to be noticed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from controlplane.detectors.base import Detector
from controlplane.risk.calibration import IsotonicCalibrator

ARTIFACT_DIR = Path("data") / "learned"
ARTIFACT_PREFIX = "calibration-"


class AxisCalibration(BaseModel):
    """One fitted isotonic map, stored as the knots `IsotonicCalibrator` carries."""

    model_config = ConfigDict(frozen=True)

    upper_bounds: tuple[float, ...]
    probabilities: tuple[float, ...]

    @classmethod
    def of(cls, calibrator: IsotonicCalibrator) -> AxisCalibration:
        return cls(
            upper_bounds=calibrator.upper_bounds, probabilities=calibrator.probabilities
        )

    def calibrator(self) -> IsotonicCalibrator:
        return IsotonicCalibrator(
            upper_bounds=self.upper_bounds, probabilities=self.probabilities
        )


class RouteCalibration(BaseModel):
    """Everything one route needs: a map per axis, and the threshold certified on top."""

    model_config = ConfigDict(frozen=True)

    axes: dict[str, AxisCalibration]
    threshold: float = Field(ge=0.0, le=1.0)
    alpha: float = Field(gt=0.0, lt=1.0)
    delta: float = Field(gt=0.0, lt=1.0)
    released: int = Field(ge=0)
    escaped_harms: int = Field(ge=0)
    empirical_risk: float = Field(ge=0.0, le=1.0)
    upper_bound: float = Field(ge=0.0, le=1.0)
    # Reported so a released map can never be read without knowing how thin it is.
    fitting_rows: int = Field(ge=0)
    selection_rows: int = Field(ge=0)


class CalibrationArtifact(BaseModel):
    """A released set of maps and thresholds, bound to the detector that produced them."""

    model_config = ConfigDict(frozen=True)

    detector_version: str
    routes: dict[str, RouteCalibration]

    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def calibrators(self) -> dict[str, dict[str, IsotonicCalibrator]]:
        return {
            route: {axis: axis_map.calibrator() for axis, axis_map in value.axes.items()}
            for route, value in self.routes.items()
        }

    def thresholds(self) -> dict[str, float]:
        return {route: value.threshold for route, value in self.routes.items()}


def detector_version(detectors: list[Detector]) -> str:
    """Identify the scorers a map was fitted against.

    Today that is detector names and versions. When the pattern pack lands its content
    hash joins this string, so changing a rule invalidates the maps fitted before it.
    """
    parts = sorted(f"{item.name}@{item.version}" for item in detectors)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def write_artifact(artifact: CalibrationArtifact, root: Path) -> Path:
    directory = root / ARTIFACT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ARTIFACT_PREFIX}{artifact.content_hash()}.json"
    path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def latest_artifact(root: Path, expected_detector: str) -> CalibrationArtifact | None:
    """Load the newest released artifact that matches this detector, or nothing.

    A mismatch is not an error and not a warning to be filtered out of a log: it simply
    means no released map applies to the scorer now running, so the caller falls back to
    fitting one. Serving the mismatched map would be the silent failure this module exists
    to prevent.
    """
    directory = root / ARTIFACT_DIR
    if not directory.is_dir():
        return None
    candidates = sorted(
        directory.glob(f"{ARTIFACT_PREFIX}*.json"), key=lambda item: item.stat().st_mtime
    )
    for path in reversed(candidates):
        artifact = CalibrationArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        if artifact.detector_version == expected_detector:
            return artifact
    return None
