from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from controlplane.economics import BudgetController
from controlplane.eval.baselines import Candidate, check_all, fixed_rate
from controlplane.eval.metrics import (
    EvaluationRow,
    escaped_harm_by_route,
    outcome,
    summarize,
)
from controlplane.eval.tracking import log_evaluation
from controlplane.guarantees.conformal import binomial_upper_bound
from controlplane.ledger import LedgerStore
from controlplane.models import DecisionTrace, Interaction
from controlplane.risk import expected_calibration_error
from controlplane.service import AssessmentEngine

BUDGET_FRACTIONS = (0.10, 0.25, 0.40, 0.60, 0.80, 1.00)
BASELINE_TIERS = (1, 2)


@dataclass(frozen=True)
class AllocatorRun:
    rows: list[EvaluationRow]
    traces: list[DecisionTrace]
    spend_inr: float
    final_shadow_price: float


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

    detail: dict[str, Any] = {
        "conformal": {route: dict(vars(value)) for route, value in conformal.items()},
        "conformal_validation": _validate_conformal(engine, test, conformal),
        "reliability": _plot_reliability(engine, test, figure_dir / "reliability_by_route.png"),
    }
    frame = pd.DataFrame(_evaluate_budgets(root, engine, test, detail))
    frame.to_csv(report_dir / "evaluation.csv", index=False)
    detail["metrics"] = frame.to_dict(orient="records")
    (report_dir / "evaluation.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    _plot_curve(frame, figure_dir / "loss_averted_vs_spend.png")
    _write_markdown(frame, detail, report_dir / "evaluation.md")
    _write_results(root, frame, detail)
    log_evaluation(root, frame, detail)
    return frame, detail


def _evaluate_budgets(
    root: Path,
    engine: AssessmentEngine,
    test: list[Interaction],
    detail: dict[str, Any],
) -> list[dict[str, float | str]]:
    bundles = {item.interaction_id: engine.detect(item) for item in test}
    scores = {key: bundle.harm.maximum() for key, bundle in bundles.items()}
    latency = {key: bundle.latency_ms for key, bundle in bundles.items()}
    full_spend = _full_check_spend(engine, test)
    by_tier = {tier: _candidates(engine, test, scores, tier) for tier in BASELINE_TIERS}
    unchecked = _baseline_rows(engine, test, set(), 0, latency, "check_none")
    everything = _baseline_rows(engine, test, check_all(by_tier[2]), 2, latency, "check_all")

    curve: list[dict[str, float | str]] = []
    audit: dict[str, Any] = {}
    for fraction in BUDGET_FRACTIONS:
        budget = full_spend * fraction
        record = fraction == BUDGET_FRACTIONS[-1]
        run = _run_allocator(root, engine, test, budget, fraction, record)
        if record:
            audit[f"{fraction:.2f}"] = _audit_coverage(root, test, run, fraction)
        tuned = _best_fixed_rate(engine, test, by_tier, latency, run.spend_inr)
        for rows, reference in (
            (run.rows, budget),
            (unchecked, budget),
            (everything, full_spend),
            (tuned, budget),
        ):
            summary = summarize(rows, reference)
            summary["budget_fraction"] = fraction
            curve.append(summary)
        detail.setdefault("shadow_price", {})[f"{fraction:.2f}"] = run.final_shadow_price
        detail.setdefault("escaped_by_route", {})[f"{fraction:.2f}"] = escaped_harm_by_route(
            run.rows
        )
    detail["audit"] = audit
    detail["full_check_spend_inr"] = full_spend
    return curve


def _best_fixed_rate(
    engine: AssessmentEngine,
    test: list[Interaction],
    candidates_by_tier: dict[int, list[Candidate]],
    latency: dict[str, float],
    spend_limit: float,
) -> list[EvaluationRow]:
    """Tune the baseline over its tier choice and report its strongest configuration."""
    best: list[EvaluationRow] | None = None
    for tier, candidates in candidates_by_tier.items():
        rows = _baseline_rows(
            engine, test, fixed_rate(candidates, spend_limit), tier, latency, "fixed_rate"
        )
        averted = sum(row.loss_averted_inr for row in rows)
        if best is None or averted > sum(row.loss_averted_inr for row in best):
            best = rows
    assert best is not None
    return best


def _candidates(
    engine: AssessmentEngine,
    test: list[Interaction],
    scores: dict[str, float],
    tier_number: int,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for index, interaction in enumerate(test):
        policy = engine.policy_store.resolve(interaction.route, interaction.jurisdiction)
        tier = engine.cost_model.tiers(policy, interaction.tool_calls)[tier_number]
        candidates.append(
            Candidate(
                index=index,
                risk_score=scores[interaction.interaction_id],
                verification_cost_inr=tier.verification_cost_inr + tier.delay_cost_inr,
            )
        )
    return candidates


def _baseline_rows(
    engine: AssessmentEngine,
    test: list[Interaction],
    selected: set[int],
    tier_number: int,
    latency: dict[str, float],
    policy_name: str,
) -> list[EvaluationRow]:
    rows: list[EvaluationRow] = []
    for index, interaction in enumerate(test):
        policy = engine.policy_store.resolve(interaction.route, interaction.jurisdiction)
        tier = engine.cost_model.tiers(policy, interaction.tool_calls)[tier_number]
        checked = index in selected
        measured = latency[interaction.interaction_id]
        rows.append(
            outcome(
                interaction=interaction,
                policy_name=policy_name,
                policy=policy,
                checked=checked,
                spend_inr=(tier.verification_cost_inr + tier.delay_cost_inr) if checked else 0.0,
                catch_rate=tier.catch_rate,
                released=True,
                abstained=False,
                text_latency_ms=measured,
                effect_latency_ms=measured if interaction.tool_calls else 0.0,
            )
        )
    return rows


def _run_allocator(
    root: Path,
    engine: AssessmentEngine,
    test: list[Interaction],
    budget: float,
    fraction: float,
    record: bool,
) -> AllocatorRun:
    """Stream the test set through the shipped allocator with the budget controller live."""
    controller = BudgetController(
        budget_rate_inr=max(budget / len(test), 1e-9),
        learning_rate=engine.cost_model.controller_learning_rate,
    )
    ledger = LedgerStore(_ledger_path(root, fraction)) if record else None
    rows: list[EvaluationRow] = []
    traces: list[DecisionTrace] = []
    running = 0.0
    for position, interaction in enumerate(test, start=1):
        trace = engine.assess(interaction, shadow_price=controller.shadow_price)
        if ledger is not None:
            ledger.append(trace)
        running += trace.assurance_spend_inr
        controller.update(running / position)
        traces.append(trace)
        rows.append(_allocator_row(engine, interaction, trace))
    return AllocatorRun(rows, traces, running, controller.shadow_price)


def _allocator_row(
    engine: AssessmentEngine, interaction: Interaction, trace: DecisionTrace
) -> EvaluationRow:
    policy = engine.policy_store.resolve(interaction.route, interaction.jurisdiction)
    tiers = engine.cost_model.tiers(policy, interaction.tool_calls)
    checked = trace.selected_tier is not None
    tier = tiers[trace.selected_tier] if trace.selected_tier is not None else tiers[0]
    return outcome(
        interaction=interaction,
        policy_name="allocator",
        policy=policy,
        checked=checked,
        spend_inr=trace.assurance_spend_inr,
        catch_rate=tier.catch_rate,
        released=trace.verdict not in {"block", "abstain"},
        abstained=trace.verdict == "abstain",
        text_latency_ms=trace.detector_latency_ms,
        effect_latency_ms=trace.detector_latency_ms if interaction.tool_calls else 0.0,
    )


def _full_check_spend(engine: AssessmentEngine, test: list[Interaction]) -> float:
    total = 0.0
    for interaction in test:
        policy = engine.policy_store.resolve(interaction.route, interaction.jurisdiction)
        tier = engine.cost_model.tiers(policy, interaction.tool_calls)[2]
        total += tier.verification_cost_inr + tier.delay_cost_inr
    return total


def _ledger_path(root: Path, fraction: float) -> Path:
    path = root / "reports" / f"audit-{int(fraction * 100):03d}.db"
    path.unlink(missing_ok=True)
    return path


def _audit_coverage(
    root: Path, test: list[Interaction], run: AllocatorRun, fraction: float
) -> dict[str, float | bool]:
    """Count effects that survived into a verified ledger record, not effects proposed."""
    ledger = LedgerStore(_ledger_path_existing(root, fraction))
    chain_ok, record_count = ledger.verify()
    logged = 0
    for record in ledger.records(limit=len(test) + 1):
        payload = json.loads(str(record["record_json"]))
        logged += len(payload.get("effect_actions", []))
    proposed = sum(len(item.tool_calls) for item in test)
    return {
        "chain_valid": chain_ok,
        "records": float(record_count),
        "decisions": float(len(run.traces)),
        "effects_proposed": float(proposed),
        "effects_logged": float(logged),
        "coverage": logged / proposed if proposed else 1.0,
    }


def _ledger_path_existing(root: Path, fraction: float) -> Path:
    return root / "reports" / f"audit-{int(fraction * 100):03d}.db"


def _validate_conformal(
    engine: AssessmentEngine, test: list[Interaction], conformal: dict[str, Any]
) -> dict[str, dict[str, float | bool]]:
    """Check the declared bound against held-out traffic the thresholds never saw."""
    validation: dict[str, dict[str, float | bool]] = {}
    for route, calibration in conformal.items():
        items = [item for item in test if item.route == route]
        released = [
            item for item in items if engine.detect(item).harm.maximum() < calibration.threshold
        ]
        escaped = sum(item.truth.has_harm() for item in released)
        rate = escaped / len(released) if released else 0.0
        validation[route] = {
            "threshold": calibration.threshold,
            "alpha": calibration.alpha,
            "released": float(len(released)),
            "escaped": float(escaped),
            "observed_rate": rate,
            "observed_upper_bound": binomial_upper_bound(
                escaped, len(released), calibration.delta
            ),
            "holds": rate <= calibration.alpha,
        }
    return validation


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
            "base_rate": sum(labels) / len(labels),
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
    lines = [
        "# Reproducible evaluation",
        "",
        "Generated from `data/test.jsonl` by `make report`. Monetary loss and catch rates are",
        "labelled simulation assumptions, not production findings.",
        "",
        "## Conformal bound on held-out data",
        "",
        "| Route | threshold | alpha | released | escaped | observed rate | holds |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for route, values in detail["conformal_validation"].items():
        lines.append(
            f"| `{route}` | {values['threshold']:.2f} | {values['alpha']:.2f} | "
            f"{values['released']:.0f} | {values['escaped']:.0f} | "
            f"{values['observed_rate']:.4f} | {'yes' if values['holds'] else 'NO'} |"
        )
    lines.extend(["", "## Calibration quality (held-out)", ""])
    for route, values in detail["reliability"].items():
        lines.append(
            f"- `{route}`: ECE {values['ece']:.3f} at base rate "
            f"{values['base_rate']:.3f} on {values['samples']:.0f} rows"
        )
    lines.extend(["", "## Metrics by policy and budget", "", frame.to_markdown(index=False)])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_results(root: Path, frame: pd.DataFrame, detail: dict[str, Any]) -> None:
    """Commit a reviewable summary so numbers are diffable without running the code."""
    results_dir = root / "docs" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "conformal_validation": detail["conformal_validation"],
        "reliability": detail["reliability"],
        "audit": detail["audit"],
        "shadow_price": detail["shadow_price"],
        "full_check_spend_inr": detail["full_check_spend_inr"],
        "metrics": detail["metrics"],
    }
    (results_dir / "results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    _write_summary(results_dir / "summary.md", frame, detail)


def _write_summary(path: Path, frame: pd.DataFrame, detail: dict[str, Any]) -> None:
    allocator = frame[frame["policy"] == "allocator"].sort_values("budget_fraction")
    baseline = frame[frame["policy"] == "fixed_rate"].sort_values("budget_fraction")
    lines = [
        "# Results summary",
        "",
        "Regenerated by `make report`. Every number here is computed; none are typed by hand.",
        "",
        "## Allocator against a tuned fixed-rate baseline",
        "",
        "The baseline is tuned over its tier choice at each budget and ranks the whole test",
        "set at once, so it sees scores the online allocator has not reached yet. It spends",
        "less than its limit whenever blanket Tier 1 coverage beats partial Tier 2 coverage,",
        "so the two policies are compared at matched budget, not at matched spend.",
        "",
        "| Budget | Allocator spend | Baseline spend | Allocator averted | Baseline averted "
        "| Averted delta | Allocator ROI | Baseline ROI |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for (_, left), (_, right) in zip(allocator.iterrows(), baseline.iterrows(), strict=True):
        delta = left["loss_averted_inr"] - right["loss_averted_inr"]
        share = delta / right["loss_averted_inr"] if right["loss_averted_inr"] else 0.0
        lines.append(
            f"| {left['budget_fraction']:.0%} | {left['assurance_spend_inr']:,.2f} | "
            f"{right['assurance_spend_inr']:,.2f} | {left['loss_averted_inr']:,.0f} | "
            f"{right['loss_averted_inr']:,.0f} | {share:+.1%} | "
            f"{left['assurance_roi']:,.0f} | {right['assurance_roi']:,.0f} |"
        )
    lines.extend(_verdict_lines(allocator, baseline))
    lines.extend(["", "## Shadow price at the end of each run", ""])
    for fraction, value in detail["shadow_price"].items():
        lines.append(f"- budget {float(fraction):.0%}: lambda {float(value):.3f}")
    lines.extend(["", "## Conformal bound on held-out traffic", ""])
    for route, values in detail["conformal_validation"].items():
        lines.append(
            f"- `{route}`: observed {values['observed_rate']:.4f} against alpha "
            f"{values['alpha']:.2f} on {values['released']:.0f} released rows "
            f"({'holds' if values['holds'] else 'VIOLATED'})"
        )
    audit = next(iter(detail["audit"].values()))
    lines.extend(
        [
            "",
            "## Audit",
            "",
            f"- hash chain valid: {audit['chain_valid']}",
            f"- decisions recorded: {audit['records']:.0f} of {audit['decisions']:.0f}",
            f"- effects logged: {audit['effects_logged']:.0f} of "
            f"{audit['effects_proposed']:.0f} proposed "
            f"(coverage {audit['coverage']:.4f})",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verdict_lines(allocator: pd.DataFrame, baseline: pd.DataFrame) -> list[str]:
    """State the comparison outcome in the artifact, so nobody has to read it off a chart."""
    averted = allocator["loss_averted_inr"].values > baseline["loss_averted_inr"].values
    roi = allocator["assurance_roi"].values > baseline["assurance_roi"].values
    averted_wins, roi_wins = int(averted.sum()), int(roi.sum())
    budgets = len(allocator)
    return [
        "",
        f"Allocator averts more loss at {averted_wins} of {budgets} budgets and achieves better "
        f"assurance ROI at {roi_wins} of {budgets}.",
    ]

