from __future__ import annotations

from pathlib import Path

from controlplane.models import Interaction
from controlplane.service import AssessmentEngine
from controlplane.sim.traffic import generate_corpus


def _harm_rate(rows: list[Interaction]) -> float:
    return sum(row.truth.has_harm() for row in rows) / len(rows)


def test_evidence_availability_carries_no_label_information(
    corpus: list[Interaction],
) -> None:
    """The first corpus leaked harm through missing sources; hold that gap shut."""
    grounded = [row for row in corpus if row.context_documents]
    ungrounded = [row for row in corpus if not row.context_documents]
    assert abs(_harm_rate(grounded) - _harm_rate(ungrounded)) < 0.06


def test_absent_sources_do_not_predict_harm(corpus: list[Interaction]) -> None:
    test_rows = [row for row in corpus if row.split == "test"]
    flagged = [row for row in test_rows if not row.context_documents]
    precision = sum(row.truth.has_harm() for row in flagged) / len(flagged)
    assert precision < _harm_rate(test_rows) + 0.06


def test_harm_is_a_minority_event(corpus: list[Interaction]) -> None:
    assert 0.08 < _harm_rate(corpus) < 0.30


def test_splits_are_disjoint_and_similarly_distributed(
    corpus: list[Interaction],
) -> None:
    calibration = [row for row in corpus if row.split == "calibration"]
    test_rows = [row for row in corpus if row.split == "test"]
    assert not {row.interaction_id for row in calibration} & {
        row.interaction_id for row in test_rows
    }
    assert abs(_harm_rate(calibration) - _harm_rate(test_rows)) < 0.05


def test_response_surface_is_not_a_lookup_table(corpus: list[Interaction]) -> None:
    assert len({row.response for row in corpus}) > 200


def test_detection_is_imperfect_in_both_directions(
    corpus: list[Interaction], calibrated_engine: AssessmentEngine
) -> None:
    """Perfect separation means the fixture is being measured, not the detector."""
    test_rows = [row for row in corpus if row.split == "test"]
    threshold = calibrated_engine.conformal_thresholds
    flagged = [
        row
        for row in test_rows
        if calibrated_engine.detect(row).harm.maximum() >= threshold[row.route]
    ]
    missed = [
        row
        for row in test_rows
        if row.truth.has_harm()
        and calibrated_engine.detect(row).harm.maximum() < threshold[row.route]
    ]
    false_positives = [row for row in flagged if not row.truth.has_harm()]
    assert missed, "no harm is ever missed, so the corpus is separable by construction"
    assert false_positives, "nothing clean is ever flagged, so precision is unmeasurable"


def test_generation_is_byte_reproducible(project_root: Path) -> None:
    """Committed results are only meaningful if the corpus they describe regenerates."""
    committed = (project_root / "data" / "interactions.jsonl").read_text(encoding="utf-8")
    regenerated = "\n".join(item.model_dump_json() for item in generate_corpus()) + "\n"
    assert regenerated == committed
