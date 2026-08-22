from __future__ import annotations

from pathlib import Path

import pytest

from controlplane.models import Interaction
from controlplane.service import AssessmentEngine
from controlplane.sim.traffic import generate_corpus


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def corpus() -> list[Interaction]:
    return generate_corpus()


@pytest.fixture(scope="session")
def calibrated_engine(project_root: Path, corpus: list[Interaction]) -> AssessmentEngine:
    engine = AssessmentEngine(project_root)
    engine.calibrate([item for item in corpus if item.split == "calibration"])
    return engine
