from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from controlplane.economics.allocator import expected_loss_inr
from controlplane.eval.baselines import (
    Candidate,
    check_all,
    check_none,
    economic_allocator,
    fixed_rate,
)
from controlplane.eval.metrics import EvaluationRow, outcome, summarize
from controlplane.models import EvidenceRegime, Interaction
from controlplane.risk import expected_calibration_error
from controlplane.service import AssessmentEngine

BUDGET_FRACTIONS = (0.10, 0.25, 0.40, 0.60, 0.80, 1.00)


def build_report(
    root: Path, interactions: list[Interaction]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    report_dir = root / "reports"
    figure_dir = report_dir / "figures"
    report_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    calibration = [item for item in interactions if item.split == "calibration"]
    test = [item for item in interactions if item.split == "test"]
    engine = AssessmentEngine(root)
    conformal = engine.calibrate(calibration)
    reliability = _plot_reliability(engine, test, figure_dir / "reliability_by_route.png")
    candidates = _candidates(engine, test)
    maximum_spend = sum(candidate.verification_cost_inr for candidate in candidates)
    detail: dict[str, Any] = {"conformal": {}, "reliability": reliability}
    for route, calibration_result in conformal.items():
        detail["conformal"][route] = calibration_result.__dict__
    frame = pd.DataFrame(_evaluate_budgets(engine, test, candidates, maximum_spend))
    frame.to_csv(report_dir / "evaluation.csv", index=False)
    detail["metrics"] = frame.to_dict(orient="records")
    (report_dir / "evaluation.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True), encoding="utf-8"
    )
    _plot_curve(frame, figure_dir / "loss_averted_vs_spend.png")
    _write_markdown(frame, detail, report_dir / "evaluation.md")
    return frame, detail


def _evaluate_budgets(
    engine: AssessmentEngine,
    interactions: list[Interaction],
    candidates: list[Candidate],
    maximum_spend: float,
) -> list[dict[str, float | str]]:
    curve_rows: list[dict[str, float | str]] = []
    for fraction in BUDGET_FRACTIONS:
        target = maximum_spend * fraction
        selections = _selections(candidates, target, fraction)
        for policy_name, selected in selections.items():
            rows = _outcomes(engine, interactions, selected, policy_name)
            budget = maximum_spend if policy_name == "check_all" else target
            summary = summarize(rows, budget)
            summary["budget_fraction"] = fraction
            curve_rows.append(summary)
    return curve_rows


def _selections(candidates: list[Candidate], target: float, fraction: float) -> dict[str, set[int]]:
    allocator_selected = economic_allocator(candidates, target)
    allocator_spend = sum(
        candidate.verification_cost_inr
        for candidate in candidates
        if candidate.index in allocator_selected
    )
    selections = {
        "check_none": check_none(candidates),
        "fixed_rate": fixed_rate(candidates, allocator_spend),
        "allocator": allocator_selected,
    }
    if fraction == 1.0:
        selections["check_all"] = check_all(candidates)
    return selections


def _candidates(engine: AssessmentEngine, interactions: list[Interaction]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for index, interaction in enumerate(interactions):
        policy = engine.policy_store.resolve(interaction.route, interaction.jurisdiction)
        bundle = engine.detect(interaction)
        tier = engine.cost_model.tiers(policy, interaction.tool_calls)[2]
        candidates.append(
            Candidate(
                index=index,
                risk_score=bundle.harm.maximum(),
                expected_loss_inr=expected_loss_inr(bundle, policy),
                verification_cost_inr=tier.verification_cost_inr + tier.delay_cost_inr,
                mandatory=bundle.harm.maximum() >= engine.conformal_thresholds[interaction.route],
            )
        )
    return candidates


def _outcomes(
    engine: AssessmentEngine,
    interactions: list[Interaction],
    selected_indices: set[int],
    policy_name: str,
) -> list[EvaluationRow]:
    rows: list[EvaluationRow] = []
    for index, interaction in enumerate(interactions):
        policy = engine.policy_store.resolve(interaction.route, interaction.jurisdiction)
        tier = engine.cost_model.tiers(policy, interaction.tool_calls)[2]
        selected = index in selected_indices
        regime = engine.detect(interaction).evidence_regime
        rows.append(
            outcome(
                interaction=interaction,
                policy_name=policy_name,
                policy=policy,
                selected=selected,
                spend_inr=tier.verification_cost_inr + tier.delay_cost_inr,
                catch_rate=tier.catch_rate,
                abstained=regime == EvidenceRegime.UNVERIFIABLE and not selected,
                latency_ms=900.0 if selected else 4.0,
            )
        )
    return rows


def _plot_curve(frame: pd.DataFrame, path: Path) -> None:
    plt.figure(figsize=(8, 5))
    colors = {
        "allocator": "#A100FF",
        "fixed_rate": "#2E5BFF",
        "check_none": "#6B6574",
        "check_all": "#E83E8C",
    }
    for policy, group in frame.groupby("policy"):
        ordered = group.sort_values("assurance_spend_inr")
        plt.plot(
            ordered["assurance_spend_inr"],
            ordered["loss_averted_inr"],
            marker="o",
            label=policy,
            color=colors[str(policy)],
        )
    plt.xlabel("Assurance spend (INR)")
    plt.ylabel("Loss averted (INR, simulated)")
    plt.title("Loss averted vs assurance spend")
    plt.grid(alpha=0.2)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def _plot_reliability(
    engine: AssessmentEngine, interactions: list[Interaction], path: Path
) -> dict[str, dict[str, float]]:
    routes = ("support-assistant", "internal-kb", "finops-agent")
    figure, axes = plt.subplots(1, len(routes), figsize=(12, 3.6), sharex=True, sharey=True)
    diagnostics: dict[str, dict[str, float]] = {}
    for axis, route in zip(axes, routes, strict=True):
        route_items = [item for item in interactions if item.route == route]
        probabilities = [engine.detect(item).harm.maximum() for item in route_items]
        labels = [item.truth.has_harm() for item in route_items]
        diagnostics[route] = {
            "ece": expected_calibration_error(probabilities, labels),
            "samples": float(len(route_items)),
        }
        confidence, frequency = _reliability_points(probabilities, labels)
        axis.plot([0, 1], [0, 1], linestyle="--", color="#6B6574")
        axis.plot(confidence, frequency, marker="o", color="#A100FF")
        axis.set_title(route)
        axis.set_xlabel("Predicted risk")
    axes[0].set_ylabel("Observed harm rate")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return diagnostics


def _reliability_points(
    probabilities: list[float], labels: list[bool], bins: int = 8
) -> tuple[list[float], list[float]]:
    confidence: list[float] = []
    frequency: list[float] = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        members = [
            (probability, label)
            for probability, label in zip(probabilities, labels, strict=True)
            if lower <= probability < upper or (index == bins - 1 and probability == 1.0)
        ]
        if members:
            confidence.append(sum(item[0] for item in members) / len(members))
            frequency.append(sum(item[1] for item in members) / len(members))
    return confidence, frequency


def _write_markdown(frame: pd.DataFrame, detail: dict[str, Any], path: Path) -> None:
    allocator = frame[frame["policy"] == "allocator"].sort_values("budget_fraction")
    latest = allocator.iloc[-1]
    lines = [
        "# Reproducible evaluation",
        "",
        "All values below were generated from `data/test.jsonl` by `make report`.",
        "Monetary loss and catch rates are labelled simulation assumptions, "
        "not production findings.",
        "",
        f"- Allocator loss averted at full budget: INR {latest['loss_averted_inr']:.2f}",
        f"- Allocator assurance ROI at full budget: {latest['assurance_roi']:.2f}",
        f"- Allocator intervention precision: {latest['intervention_precision']:.3f}",
        "",
        "## Conformal calibration",
        "",
    ]
    for route, values in detail["conformal"].items():
        lines.append(
            f"- `{route}`: threshold {values['threshold']:.2f}, "
            f"upper escape-risk bound {values['upper_bound']:.3f} at alpha {values['alpha']:.2f}"
        )
    lines.extend(["", "## Held-out calibration", ""])
    for route, values in detail["reliability"].items():
        lines.append(f"- `{route}`: ECE {values['ece']:.3f} on {values['samples']:.0f} rows")
    lines.extend(["", "## Metrics by policy and budget", "", frame.to_markdown(index=False)])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
