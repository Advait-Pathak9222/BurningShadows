from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from controlplane.ledger import LedgerStore
from controlplane.models import DecisionTrace, EvidenceRegime, HarmVector


def _trace(index: int) -> DecisionTrace:
    return DecisionTrace(
        interaction_id=f"concurrent-{index:04d}",
        route="support-assistant",
        jurisdiction="eu",
        verdict="allow",
        reason="synthetic",
        harm=HarmVector.zeros(),
        evidence_regime=EvidenceRegime.GROUNDED,
        selected_tier=None,
        forced_by_conformal=False,
        conformal_threshold=0.1,
        conformal_alpha=0.1,
        shadow_price=0.0,
        expected_loss_inr=0.0,
        assurance_spend_inr=0.0,
        tier_decisions=[],
        effect_actions=[],
        policy_version="test",
        policy_hash="test",
        detector_latency_ms=0.0,
    )


def test_concurrent_appends_keep_the_chain_intact(tmp_path: Path) -> None:
    """Two threads reading the same previous hash would fork the chain permanently."""
    ledger = LedgerStore(tmp_path / "concurrent.db")
    appends = 64
    with ThreadPoolExecutor(max_workers=8) as pool:
        digests = list(pool.map(lambda index: ledger.append(_trace(index)), range(appends)))

    assert len(set(digests)) == appends, "duplicate record hashes mean a forked chain"
    chain_ok, counted = ledger.verify()
    assert counted == appends
    assert chain_ok, "hash chain broke under concurrent appends"
