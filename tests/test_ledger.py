from __future__ import annotations

import sqlite3
from pathlib import Path

from controlplane.models import HarmVector, Interaction, ReviewRecord, ReviewVerdict
from controlplane.service import AssessmentEngine


def test_hash_chain_detects_tampering(project_root: Path, tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.db"
    # Thresholds are supplied directly: this test is about chain integrity, not fitting.
    engine = AssessmentEngine(
        project_root,
        ledger_path=ledger_path,
        conformal_thresholds={"support-assistant": 0.1},
    )
    for index in range(2):
        engine.assess(
            Interaction(
                interaction_id=f"ledger-{index}",
                split="scenario",
                route="support-assistant",
                jurisdiction="eu",
                prompt="What is the fee?",
                response="The fee is ₹499.",
                context_documents=["The fee is ₹499."],
                truth=HarmVector.zeros(),
            )
        )
    assert engine.ledger is not None
    assert engine.ledger.verify() == (True, 2)
    with sqlite3.connect(ledger_path) as connection:
        connection.execute("UPDATE decisions SET record_json = '{}' WHERE sequence = 1")
        connection.commit()
    assert engine.ledger.verify() == (False, 1)


def test_tampering_with_a_review_breaks_the_chain(project_root: Path, tmp_path: Path) -> None:
    """Overrides share the decision chain, so an edited override is detectable too."""
    ledger_path = tmp_path / "review.db"
    engine = AssessmentEngine(
        project_root,
        ledger_path=ledger_path,
        conformal_thresholds={"support-assistant": 0.1},
    )
    assert engine.ledger is not None
    engine.ledger.append_review(
        ReviewRecord(
            interaction_id="reviewed-0001",
            route="support-assistant",
            reviewer="tester",
            verdict=ReviewVerdict.OVERTURNED,
            reason_code="no harm found, over-flagged",
            observed_harm=False,
            system_withheld=True,
            selected_tier=2,
        )
    )
    assert engine.ledger.verify() == (True, 1)
    with sqlite3.connect(ledger_path) as connection:
        connection.execute(
            "UPDATE decisions SET record_json = replace(record_json, 'overturned', 'upheld')"
        )
        connection.commit()
    assert engine.ledger.verify() == (False, 1)
