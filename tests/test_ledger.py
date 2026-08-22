from __future__ import annotations

import sqlite3
from pathlib import Path

from controlplane.models import HarmVector, Interaction
from controlplane.service import AssessmentEngine


def test_hash_chain_detects_tampering(project_root: Path, tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.db"
    engine = AssessmentEngine(project_root, ledger_path=ledger_path)
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
