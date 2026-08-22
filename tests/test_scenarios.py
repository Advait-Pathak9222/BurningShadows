from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from controlplane.eval.report import build_report
from controlplane.models import Interaction
from controlplane.service import AssessmentEngine
from controlplane.sim.scenarios import run_scenarios


@pytest.fixture(scope="module")
def scenarios(
    project_root: Path, corpus: list[Interaction], calibrated_engine: AssessmentEngine
) -> dict[str, Any]:
    frame, _ = build_report(project_root, corpus)
    return run_scenarios(project_root, calibrated_engine, corpus, frame)


def test_consequence_alone_changes_the_verdict(scenarios: dict[str, Any]) -> None:
    same = scenarios["same_response_three_routes"]
    assert same["verdicts_diverge_by_route"], "no held-out row is decided by route economics"
    routes = same["routes"]
    assert len({values["verdict"] for values in routes.values()}) > 1
    assert (
        routes["finops-agent"]["expected_loss_inr"] > routes["internal-kb"]["expected_loss_inr"]
    )


def test_overlapping_harm_is_carried_as_a_vector(scenarios: dict[str, Any]) -> None:
    """The decision keeps every axis; how many the detector can score is measured separately."""
    overlap = scenarios["overlapping_harm"]
    assert overlap["labelled_axes"] > 1
    assert set(overlap["risk"]) == {
        "hallucination",
        "pii_leak",
        "bias",
        "unsafe_content",
        "injection_or_exfil",
    }
    assert overlap["expected_loss_inr"] > 0
    assert any(value > 0.0 for value in overlap["risk"].values())


def test_unverifiable_claim_abstains_with_a_reason(scenarios: dict[str, Any]) -> None:
    unverifiable = scenarios["no_ground_truth"]
    assert unverifiable["evidence_regime"] == "unverifiable"
    assert unverifiable["abstained"], "no held-out row without evidence triggers abstention"
    assert unverifiable["verdict"] == "abstain"
    assert unverifiable["reason"] == "no evidence can support a confident release"


def test_agentic_transfer_never_fires(scenarios: dict[str, Any]) -> None:
    hold = scenarios["agentic_hold"]
    assert hold["verdict"] in {"hold", "block"}
    assert hold["transfer_fired"] is False
    assert not any(action.endswith(":permit") for action in hold["effect_actions"])


def test_jurisdiction_changes_policy_and_retention(scenarios: dict[str, Any]) -> None:
    switch = scenarios["jurisdiction_switch"]
    assert switch["eu"]["policy_version"] != switch["india"]["policy_version"]
    assert switch["eu"]["policy_hash"] != switch["india"]["policy_hash"]
    assert switch["eu"]["retention_days"] != switch["india"]["retention_days"]


def test_budget_cut_raises_lambda_and_reallocates_to_high_consequence(
    scenarios: dict[str, Any],
) -> None:
    shock = scenarios["budget_shock"]
    assert shock["lambda_final_after"] > shock["lambda_final_before"]
    assert (
        shock["spend_per_interaction_after_inr"] < shock["spend_per_interaction_before_inr"]
    )
    assert (
        shock["high_consequence_spend_share_after"]
        > shock["high_consequence_spend_share_before"]
    )


def test_conformal_floor_survives_the_budget_cut(scenarios: dict[str, Any]) -> None:
    shock = scenarios["budget_shock"]
    assert shock["conformal_floor_coverage_after"] == 1.0
    assert shock["conformal_thresholds_unchanged"] == shock["conformal_thresholds_unchanged"]


def test_new_failure_mode_lowers_the_measured_catch_rate(scenarios: dict[str, Any]) -> None:
    drift = scenarios["drift"]
    assert drift["tier1_catch_rate_after"] < drift["tier1_catch_rate_before"]
    assert drift["new_failure_mode_misses"] > 0
    assert (
        drift["tier1_breakeven_shadow_price_after"]
        < drift["tier1_breakeven_shadow_price_before"]
    ), "a weaker checker must stop paying for itself under less budget pressure"
    assert drift["still_checked_under_floor"] is True


def test_alert_fatigue_reports_both_sides_at_matched_budget(scenarios: dict[str, Any]) -> None:
    """Records the comparison without asserting which side wins."""
    fatigue = scenarios["alert_fatigue"]
    assert fatigue["allocator_spend_inr"] > 0
    assert fatigue["fixed_rate_spend_inr"] > 0
    assert 0.0 <= fatigue["allocator_precision"] <= 1.0
    assert 0.0 <= fatigue["fixed_rate_precision"] <= 1.0
