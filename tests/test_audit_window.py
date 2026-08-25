from __future__ import annotations

from pathlib import Path

from controlplane.eval.report import AllocatorRun, _audit_coverage, _validate_conformal
from controlplane.guarantees.conformal import ConformalCalibration
from controlplane.models import (
    HarmVector,
    Interaction,
    ReviewRecord,
    ReviewVerdict,
)
from controlplane.service import AssessmentEngine


def _interaction(index: int, *, effects: int) -> Interaction:
    return Interaction(
        interaction_id=f"audit-{index:04d}",
        split="scenario",
        route="finops-agent",
        jurisdiction="eu",
        prompt="Move the balance.",
        response="Transferring now.",
        context_documents=["The balance is INR 100."],
        truth=HarmVector.zeros(),
        tool_calls=[
            {"name": "transfer_funds", "arguments": {"amount": 10 * (slot + 1)}}
            for slot in range(effects)
        ],
    )


def test_effect_coverage_reads_the_whole_chain_not_one_page(
    project_root: Path, tmp_path: Path
) -> None:
    """Reviews share the chain, so a window sized by interaction count loses decisions.

    Sizing the read by ``len(test)`` pushed the oldest decisions off a ``sequence DESC``
    page once reviews were appended alongside them, and every effect on those rows
    vanished from the reported audit coverage.
    """
    engine = AssessmentEngine(
        project_root,
        ledger_path=tmp_path / "audit.db",
        conformal_thresholds={"finops-agent": 0.1},
    )
    ledger = engine.ledger
    assert ledger is not None

    test = [_interaction(index, effects=1) for index in range(8)]
    traces = [engine.assess(item) for item in test]
    # One review per decision: the chain is now twice the interaction count.
    for item in test:
        ledger.append_review(
            ReviewRecord(
                interaction_id=item.interaction_id,
                route="finops-agent",
                reviewer="tester",
                verdict=ReviewVerdict.UPHELD,
                reason_code="checked",
                observed_harm=False,
                system_withheld=True,
                selected_tier=2,
            )
        )

    run = AllocatorRun([], traces, 0.0, 0.0, ledger=ledger)
    audit = _audit_coverage(test, run)

    assert audit["chain_valid"] is True
    assert audit["records"] == 16.0
    assert audit["decisions_recorded"] == 8.0
    assert audit["reviews_recorded"] == 8.0
    assert audit["effects_proposed"] == 8.0
    assert audit["effects_logged"] == 8.0
    assert audit["coverage"] == 1.0


def test_reviews_are_not_counted_as_decisions(project_root: Path, tmp_path: Path) -> None:
    """The chain length and the decision count are different numbers and must read so."""
    engine = AssessmentEngine(
        project_root,
        ledger_path=tmp_path / "kinds.db",
        conformal_thresholds={"finops-agent": 0.1},
    )
    ledger = engine.ledger
    assert ledger is not None
    test = [_interaction(index, effects=0) for index in range(3)]
    traces = [engine.assess(item) for item in test]
    ledger.append_review(
        ReviewRecord(
            interaction_id=test[0].interaction_id,
            route="finops-agent",
            reviewer="tester",
            verdict=ReviewVerdict.OVERTURNED,
            reason_code="over-flagged",
            observed_harm=False,
            system_withheld=True,
            selected_tier=2,
        )
    )
    audit = _audit_coverage(test, AllocatorRun([], traces, 0.0, 0.0, ledger=ledger))
    assert audit["decisions_recorded"] == 3.0
    assert audit["decisions_expected"] == 3.0
    assert audit["records"] == 4.0


def test_a_bound_over_zero_released_rows_is_reported_as_vacuous() -> None:
    """A route the floor covers entirely satisfies the bound by construction.

    Reporting that as `holds` is the same class of defect as an `x / x` coverage
    metric: it reads as evidence about the detector and contains none.
    """
    items = [_interaction(index, effects=0) for index in range(5)]
    scores = {item.interaction_id: 0.4 for item in items}
    calibration = ConformalCalibration(
        route="finops-agent",
        threshold=0.0,
        alpha=0.15,
        delta=0.1,
        released=0,
        escaped_harms=0,
        empirical_risk=0.0,
        upper_bound=0.0,
    )
    result = _validate_conformal(items, {"finops-agent": calibration}, scores)["finops-agent"]
    assert result["released"] == 0.0
    assert result["vacuous"] is True
    assert result["mandatory_coverage"] == 1.0


def test_a_bound_with_released_rows_is_not_vacuous() -> None:
    items = [_interaction(index, effects=0) for index in range(5)]
    scores = {item.interaction_id: 0.1 for item in items}
    calibration = ConformalCalibration(
        route="finops-agent",
        threshold=0.5,
        alpha=0.15,
        delta=0.1,
        released=5,
        escaped_harms=0,
        empirical_risk=0.0,
        upper_bound=0.0,
    )
    result = _validate_conformal(items, {"finops-agent": calibration}, scores)["finops-agent"]
    assert result["vacuous"] is False
    assert result["mandatory_coverage"] == 0.0
    assert result["holds"] is True
