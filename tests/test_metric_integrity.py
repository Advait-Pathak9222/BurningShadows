from __future__ import annotations

from controlplane.eval.metrics import EvaluationRow, summarize


def test_policy_report_excludes_uncontrolled_latency_and_exchange_rate() -> None:
    row = EvaluationRow(
        interaction_id="metric",
        policy="fixture",
        route="internal-kb",
        checked=True,
        true_harm=False,
        caught=False,
        released=True,
        abstained=False,
        spend_inr=1.0,
        potential_loss_inr=0.0,
        loss_averted_inr=0.0,
        text_latency_ms=1.0,
        effect_latency_ms=0.0,
        effect_count=0,
    )

    result = summarize([row], budget_inr=1.0)

    assert result["cost_per_1k_inr"] == 1000.0
    assert "cost_per_1k_usd" not in result
    assert "p99_text_latency_ms" not in result
    assert "p99_effect_latency_ms" not in result
    assert result["intervention_precision"] == 0.0
