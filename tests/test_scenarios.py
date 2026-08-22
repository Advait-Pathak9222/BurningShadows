from __future__ import annotations

from pathlib import Path

from controlplane.eval.report import build_report
from controlplane.models import Interaction
from controlplane.service import AssessmentEngine
from controlplane.sim.scenarios import run_scenarios


def test_eight_golden_scenarios(
    project_root: Path,
    corpus: list[Interaction],
    calibrated_engine: AssessmentEngine,
    tmp_path: Path,
) -> None:
    frame, _ = build_report(project_root, corpus)
    engine = AssessmentEngine(
        project_root,
        ledger_path=tmp_path / "scenario.db",
        conformal_thresholds=dict(calibrated_engine.conformal_thresholds),
    )
    engine.calibrate([item for item in corpus if item.split == "calibration"])
    scenarios = run_scenarios(project_root, engine, corpus, frame)
    _assert_route_and_harm_scenarios(scenarios)
    _assert_operating_scenarios(scenarios)
    _assert_adaptation_scenarios(scenarios)


def _assert_route_and_harm_scenarios(scenarios: dict[str, object]) -> None:
    routes = scenarios["same_response_three_routes"]["routes"]
    assert routes["internal-kb"]["verdict"] == "allow"
    assert routes["support-assistant"]["verdict"] == "annotate"
    assert routes["finops-agent"]["verdict"] == "hold"

    overlap = scenarios["overlapping_harm"]
    assert overlap["risk"]["hallucination"] > 0.5
    assert overlap["risk"]["pii_leak"] > 0.5
    assert scenarios["no_ground_truth"]["verdict"] == "abstain"


def _assert_operating_scenarios(scenarios: dict[str, object]) -> None:
    fatigue = scenarios["alert_fatigue"]
    assert fatigue["allocator_spend_inr"] == fatigue["fixed_rate_spend_inr"]
    assert fatigue["allocator_loss_averted_inr"] > fatigue["fixed_rate_loss_averted_inr"]

    hold = scenarios["agentic_hold"]
    assert hold["verdict"] == "hold"
    assert hold["transfer_fired"] is False

    switch = scenarios["jurisdiction_switch"]
    assert switch["eu"]["policy_version"] != switch["india"]["policy_version"]
    assert switch["eu"]["retention_days"] != switch["india"]["retention_days"]


def _assert_adaptation_scenarios(scenarios: dict[str, object]) -> None:
    shock = scenarios["budget_shock"]
    assert shock["coverage_after"] < shock["coverage_before"]
    assert shock["conformal_floor_coverage_after"] == 1.0

    drift = scenarios["drift"]
    assert drift["tier1_catch_rate_after"] < drift["tier1_catch_rate_before"]
    assert drift["recommended_tier"] == 2
