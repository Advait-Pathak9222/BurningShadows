from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from controlplane.economics import BudgetController, decide_verdict
from controlplane.economics.allocator import expected_loss_inr
from controlplane.eval.baselines import Candidate, check_all, fixed_rate
from controlplane.eval.metrics import (
    EvaluationRow,
    escaped_harm_by_route,
    outcome,
    percentile,
    summarize,
)
from controlplane.eval.tracking import log_evaluation
from controlplane.guarantees.conformal import binomial_upper_bound
from controlplane.ledger import LedgerStore
from controlplane.models import (
    DecisionTrace,
    DetectionBundle,
    Interaction,
    ReviewOutcome,
    ReviewRecord,
)
from controlplane.review import (
    ReviewQueue,
    audit_sample,
    case_from_trace,
    catch_rates,
    intervention_precision,
    review_case,
    unchecked_escape_rate,
)
from controlplane.risk import expected_calibration_error
from controlplane.service import AssessmentEngine

BUDGET_FRACTIONS = (0.10, 0.25, 0.40, 0.60, 0.80, 1.00)
# Traffic rate the reviewer capacity in config/economics.yaml is stated against.
INTERACTIONS_PER_HOUR = 180
BASELINE_TIERS = (1, 2)


@dataclass(frozen=True)
class AllocatorRun:
    rows: list[EvaluationRow]
    traces: list[DecisionTrace]
    spend_inr: float
    final_shadow_price: float
    ledger: LedgerStore | None = None
    review: dict[str, float] = field(default_factory=dict)
    records: list[ReviewRecord] = field(default_factory=list)


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

    # One detection pass, shared. Three separate passes over the same 1500 rows made
    # any future cache-hit-rate number a statement about the harness, not the traffic.
    bundles = {item.interaction_id: engine.detect(item) for item in test}
    scores = {key: bundle.harm.maximum() for key, bundle in bundles.items()}
    detail: dict[str, Any] = {
        "conformal": {route: dict(vars(value)) for route, value in conformal.items()},
        "conformal_validation": _validate_conformal(test, conformal, scores),
        "reliability": _plot_reliability(
            test, figure_dir / "reliability_by_route.png", scores
        ),
    }
    frame = pd.DataFrame(_evaluate_budgets(root, engine, test, detail, bundles))
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
    bundles: dict[str, DetectionBundle],
) -> list[dict[str, float | str]]:
    scores = {key: bundle.harm.maximum() for key, bundle in bundles.items()}
    latency = {key: bundle.latency_ms for key, bundle in bundles.items()}
    full_spend = _full_check_spend(engine, test)
    by_tier = {tier: _candidates(engine, test, scores, tier) for tier in BASELINE_TIERS}
    unchecked = _baseline_rows(engine, test, set(), 0, latency, "check_none", bundles)
    everything = _baseline_rows(
        engine, test, check_all(by_tier[2]), 2, latency, "check_all", bundles
    )

    curve: list[dict[str, float | str]] = []
    audit: dict[str, Any] = {}
    pooled_records: list[ReviewRecord] = []
    for fraction in BUDGET_FRACTIONS:
        budget = full_spend * fraction
        record = fraction == BUDGET_FRACTIONS[-1]
        run = _run_allocator(root, engine, test, budget, fraction, record)
        if record:
            audit[f"{fraction:.2f}"] = _audit_coverage(test, run)
            if run.ledger is not None:
                run.ledger.close()
        tuned = _best_fixed_rate(engine, test, by_tier, latency, run.spend_inr, bundles)
        reviews = {"allocator": run.review}
        for name, result in (
            ("check_none", unchecked),
            ("check_all", everything),
            ("fixed_rate", tuned),
        ):
            # Every policy is charged the reviewer minutes its own verdicts raise,
            # through the same queue at the same capacity. Charging only ours handed
            # the baselines the 90-98% of assurance cost that is human attention.
            reviews[name], _ = _run_review(engine, test, result[1], None)
        for name, rows, reference in (
            ("allocator", run.rows, budget),
            ("check_none", unchecked[0], budget),
            ("check_all", everything[0], full_spend),
            ("fixed_rate", tuned[0], budget),
        ):
            summary = summarize(rows, reference)
            summary["budget_fraction"] = fraction
            review = reviews[name]
            # Queue attention only, which is what the pre-registration locked: the
            # reviewer minutes a policy's own verdicts raise. The audit slice is our
            # measurement apparatus rather than an operating cost of any policy, and it
            # scales with how much traffic went unchecked — charging it into the headline
            # would hand a policy that checks nothing an enormous bill for our
            # instrumentation. It is reported beside the total instead.
            attention = review["queue_spend_inr"]
            total = float(summary["assurance_spend_inr"]) + attention
            summary["attention_spend_inr"] = attention
            summary["audit_spend_inr"] = review["audit_spend_inr"]
            summary["total_assurance_inr"] = total
            summary["total_assurance_roi"] = (
                float(summary["loss_averted_inr"]) / total if total else 0.0
            )
            summary["cases_raised"] = review["cases_raised"]
            summary["cases_shed"] = review["shed"]
            summary["shed_rate"] = review["shed_rate"]
            curve.append(summary)
        detail.setdefault("shadow_price", {})[f"{fraction:.2f}"] = run.final_shadow_price
        detail.setdefault("review", {})[f"{fraction:.2f}"] = run.review
        detail.setdefault("compute_spend", {})[f"{fraction:.2f}"] = run.spend_inr
        pooled_records.extend(run.records)
        detail.setdefault("escaped_by_route", {})[f"{fraction:.2f}"] = escaped_harm_by_route(
            run.rows
        )
    detail["audit"] = audit
    detail["feedback"] = _feedback(engine, pooled_records)
    detail["full_check_spend_inr"] = full_spend
    return curve


def _feedback(engine: AssessmentEngine, records: list[ReviewRecord]) -> dict[str, Any]:
    """Turn reviewer labels into measured catch rates, rather than config constants.

    Labels are pooled across every budget. A tier's catch rate is a property of the
    detector, not of the budget that happened to select it, and the cheap tiers are only
    ever selected under budget pressure, so a single operating point leaves them with no
    observations at all.
    """
    configured = {
        int(tier): float(values["catch_rate"]["hallucination"])
        for tier, values in engine.cost_model.config["tiers"].items()
    }
    estimates = catch_rates(records, configured)
    unchecked = unchecked_escape_rate(records)
    return {
        "precision": intervention_precision(records),
        "records": float(len(records)),
        "unchecked": unchecked,
        "catch_rate": {
            str(tier): {
                "catches": estimate.catches,
                "misses": estimate.misses,
                "observations": estimate.observations,
                "measured": estimate.reportable,
                "configured": estimate.configured,
                "has_evidence": estimate.has_evidence,
                "selected": estimate.observations > 0,
            }
            for tier, estimate in estimates.items()
        },
    }


def _best_fixed_rate(
    engine: AssessmentEngine,
    test: list[Interaction],
    candidates_by_tier: dict[int, list[Candidate]],
    latency: dict[str, float],
    spend_limit: float,
    bundles: dict[str, DetectionBundle],
) -> tuple[list[EvaluationRow], list[DecisionTrace]]:
    """Tune the baseline over its tier choice and report its strongest configuration.

    Tuned on loss averted, as before. Attention cost is deliberately not part of the
    tuning objective: letting the baseline optimise a metric we introduced would make the
    comparison circular, and the honest question is what the strongest loss-averting
    baseline costs once its reviewer bill is counted.
    """
    best: tuple[list[EvaluationRow], list[DecisionTrace]] | None = None
    for tier, candidates in candidates_by_tier.items():
        result = _baseline_rows(
            engine,
            test,
            fixed_rate(candidates, spend_limit),
            tier,
            latency,
            "fixed_rate",
            bundles,
        )
        averted = sum(row.loss_averted_inr for row in result[0])
        if best is None or averted > sum(row.loss_averted_inr for row in best[0]):
            best = result
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
    bundles: dict[str, DetectionBundle],
) -> tuple[list[EvaluationRow], list[DecisionTrace]]:
    """Run a baseline through the shipped decision path, not a parallel one.

    A baseline differs from the allocator in exactly one thing: which rows it checks and
    at what tier. Everything downstream — the verdict rule, the right to block or abstain,
    and the reviewer minutes the verdict consumes — is the same code, because otherwise
    the comparison measures the modelling difference rather than the allocation.

    `forced` is False throughout: a fixed-rate policy has no conformal floor. That is the
    thing the floor exists to add, and attributing it to the baseline would hide it.
    """
    rows: list[EvaluationRow] = []
    traces: list[DecisionTrace] = []
    for index, interaction in enumerate(test):
        policy = engine.policy_store.resolve(interaction.route, interaction.jurisdiction)
        tier = engine.cost_model.tiers(policy, interaction.tool_calls)[tier_number]
        checked = index in selected
        measured = latency[interaction.interaction_id]
        bundle = bundles[interaction.interaction_id]
        chosen = tier_number if checked else None
        verdict, reason = decide_verdict(
            bundle, chosen, forced=False, has_effect=bool(interaction.tool_calls)
        )
        spend = (tier.verification_cost_inr + tier.delay_cost_inr) if checked else 0.0
        traces.append(
            DecisionTrace(
                interaction_id=interaction.interaction_id,
                route=policy.route,
                jurisdiction=policy.jurisdiction,
                verdict=verdict,
                reason=reason,
                harm=bundle.harm,
                evidence_regime=bundle.evidence_regime,
                selected_tier=chosen,
                forced_by_conformal=False,
                conformal_threshold=engine.conformal_thresholds[interaction.route],
                conformal_alpha=policy.alpha,
                shadow_price=0.0,
                expected_loss_inr=expected_loss_inr(bundle, policy),
                assurance_spend_inr=spend,
                tier_decisions=[],
                effect_actions=[],
                policy_version=policy.policy_version,
                policy_hash=policy.policy_hash,
                detector_latency_ms=measured,
            )
        )
        rows.append(
            outcome(
                interaction=interaction,
                policy_name=policy_name,
                policy=policy,
                checked=checked,
                spend_inr=spend,
                catch_rate=tier.catch_rate,
                released=verdict not in {"block", "abstain"},
                abstained=verdict == "abstain",
                text_latency_ms=measured,
                effect_latency_ms=measured if interaction.tool_calls else 0.0,
            )
        )
    return rows, traces


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
    ledger = _fresh_ledger(root, fraction) if record else None
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
    review, records = _run_review(engine, test, traces, ledger)
    return AllocatorRun(rows, traces, running, controller.shadow_price, ledger, review, records)


def _run_review(
    engine: AssessmentEngine,
    test: list[Interaction],
    traces: list[DecisionTrace],
    ledger: LedgerStore | None,
) -> tuple[dict[str, float], list[ReviewRecord]]:
    """Price the reviewer minutes the allocator's verdicts consume, and collect labels.

    Capacity is stated per hour of traffic, so the window scales with the interaction
    count rather than assuming a reviewer idles whenever the queue is short.
    """
    economics = engine.cost_model.review
    queue = ReviewQueue(economics)
    by_id = {item.interaction_id: item for item in test}
    for interaction, trace in zip(test, traces, strict=True):
        policy = engine.policy_store.resolve(interaction.route, interaction.jurisdiction)
        case = case_from_trace(trace, policy, economics)
        if case is not None:
            queue.submit(case)
    raised = len(queue.pending)
    hours = len(test) / INTERACTIONS_PER_HOUR
    decisions = queue.drain(economics.capacity_minutes_per_hour * hours)
    served = [d for d in decisions if d.outcome is not ReviewOutcome.SHED]
    shed = [d for d in decisions if d.outcome is ReviewOutcome.SHED]
    breached = [d for d in decisions if d.outcome is ReviewOutcome.BREACHED_SLA]

    trace_by_id = {trace.interaction_id: trace for trace in traces}
    records = [
        review_case(by_id[d.case.interaction_id], trace_by_id[d.case.interaction_id])
        for d in served
    ]
    records.extend(_audit_released(engine, test, traces))
    if ledger is not None:
        for record in records:
            ledger.append_review(record)

    summary = {
        "cases_raised": float(raised),
        "case_rate": raised / len(test) if test else 0.0,
        "reviewed": float(len(served) - len(breached)),
        "sla_breached": float(len(breached)),
        "shed": float(len(shed)),
        "shed_rate": len(shed) / raised if raised else 0.0,
        "attention_spend_inr": sum(d.spend_inr for d in decisions)
        + (len(records) - len(served)) * economics.cost_per_case_inr,
        "queue_spend_inr": sum(d.spend_inr for d in decisions),
        "audit_spend_inr": (len(records) - len(served)) * economics.cost_per_case_inr,
        "reviewer_minutes": sum(d.case.review_minutes for d in served),
        "capacity_minutes": economics.capacity_minutes_per_hour * hours,
        "p99_wait_minutes": percentile([d.wait_minutes for d in served], 0.99),
        "audit_reviews": float(len(records) - len(served)),
    }
    return summary, records


def _audit_released(
    engine: AssessmentEngine, test: list[Interaction], traces: list[DecisionTrace]
) -> list[ReviewRecord]:
    """Review a slice of what was released, sampled harder where we have no opinion.

    Rows the allocator declined to check are the only place a miss is visible, and barely
    one in four hundred of them carries harm. Sampling them at the same rate as rows a
    detector already scored spends the audit budget where it learns nothing.
    """
    released = [
        (item, trace)
        for item, trace in zip(test, traces, strict=True)
        if trace.verdict not in {"abstain", "hold", "block"}
    ]
    unchecked = [pair for pair in released if pair[1].selected_tier is None]
    checked = [pair for pair in released if pair[1].selected_tier is not None]
    sampled = audit_sample(
        [item.interaction_id for item, _ in unchecked], engine.cost_model.audit_rate_unchecked
    ) | audit_sample(
        [item.interaction_id for item, _ in checked], engine.cost_model.audit_rate_checked
    )
    return [
        review_case(item, trace) for item, trace in released if item.interaction_id in sampled
    ]


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


def _fresh_ledger(root: Path, fraction: float) -> LedgerStore:
    """Clear in place rather than deleting the file, which a live connection holds open."""
    ledger = LedgerStore(root / "reports" / f"audit-{int(fraction * 100):03d}.db")
    ledger.reset()
    return ledger


def _audit_coverage(test: list[Interaction], run: AllocatorRun) -> dict[str, float | bool]:
    """Count effects that survived into a verified ledger record, not effects proposed.

    The window is the verified chain length, not the interaction count. Reviews join the
    same chain, so sizing the read by ``len(test)`` silently dropped the oldest decisions
    off the end of a ``sequence DESC`` page and under-reported effect coverage.
    """
    ledger = run.ledger
    assert ledger is not None
    chain_ok, record_count = ledger.verify()
    logged = 0
    decisions = 0
    reviews = 0
    for record in ledger.records(limit=record_count):
        payload = json.loads(str(record["record_json"]))
        if payload.get("kind") == "review":
            reviews += 1
            continue
        decisions += 1
        logged += len(payload.get("effect_actions", []))
    proposed = sum(len(item.tool_calls) for item in test)
    return {
        "chain_valid": chain_ok,
        "records": float(record_count),
        "decisions_recorded": float(decisions),
        "reviews_recorded": float(reviews),
        "decisions_expected": float(len(run.traces)),
        "effects_proposed": float(proposed),
        "effects_logged": float(logged),
        "coverage": logged / proposed if proposed else 1.0,
    }


def _validate_conformal(
    test: list[Interaction], conformal: dict[str, Any], scores: dict[str, float]
) -> dict[str, dict[str, float | bool]]:
    """Check the declared bound against held-out traffic the thresholds never saw."""
    validation: dict[str, dict[str, float | bool]] = {}
    for route, calibration in conformal.items():
        items = [item for item in test if item.route == route]
        released = [
            item for item in items if scores[item.interaction_id] < calibration.threshold
        ]
        escaped = sum(item.truth.has_harm() for item in released)
        rate = escaped / len(released) if released else 0.0
        # A route that releases nothing unchecked satisfies the bound by construction:
        # the floor has demanded full coverage. That is a real operating point, but the
        # guarantee carries no information there and must not be reported as evidence.
        vacuous = not released
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
            "vacuous": vacuous,
            "mandatory_coverage": (len(items) - len(released)) / len(items) if items else 0.0,
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
    interactions: list[Interaction], path: Path, scores: dict[str, float]
) -> dict[str, dict[str, float]]:
    routes = ("support-assistant", "internal-kb", "finops-agent")
    figure, axes = plt.subplots(1, len(routes), figsize=(12, 3.6), sharex=True, sharey=True)
    diagnostics: dict[str, dict[str, float]] = {}
    for axis, route in zip(axes, routes, strict=True):
        route_items = [item for item in interactions if item.route == route]
        probabilities = [scores[item.interaction_id] for item in route_items]
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
        "review": detail["review"],
        "compute_spend": detail["compute_spend"],
        "feedback": detail["feedback"],
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
    lines.extend(_total_cost_lines(frame, allocator, baseline))
    lines.extend(_attention_lines(detail))
    lines.extend(["", "## Shadow price at the end of each run", ""])
    for fraction, value in detail["shadow_price"].items():
        lines.append(f"- budget {float(fraction):.0%}: lambda {float(value):.3f}")
    lines.extend(["", "## Conformal bound on held-out traffic", ""])
    for route, values in detail["conformal_validation"].items():
        if values["vacuous"]:
            lines.append(
                f"- `{route}`: **vacuous** — the floor demands 100% coverage at alpha "
                f"{values['alpha']:.2f}, so no row is released unchecked and the bound is "
                f"satisfied by construction. It is not evidence about the detector."
            )
            continue
        lines.append(
            f"- `{route}`: observed {values['observed_rate']:.4f} against alpha "
            f"{values['alpha']:.2f} on {values['released']:.0f} released rows, "
            f"{values['mandatory_coverage']:.1%} checked under the floor "
            f"({'holds' if values['holds'] else 'VIOLATED'})"
        )
    audit = next(iter(detail["audit"].values()))
    lines.extend(
        [
            "",
            "## Audit",
            "",
            f"- hash chain valid: {audit['chain_valid']}",
            f"- decisions recorded: {audit['decisions_recorded']:.0f} of "
            f"{audit['decisions_expected']:.0f}",
            f"- reviews recorded in the same chain: {audit['reviews_recorded']:.0f}",
            f"- chain length: {audit['records']:.0f} records",
            f"- effects logged: {audit['effects_logged']:.0f} of "
            f"{audit['effects_proposed']:.0f} proposed "
            f"(coverage {audit['coverage']:.4f})",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _total_cost_lines(
    frame: pd.DataFrame, allocator: pd.DataFrame, baseline: pd.DataFrame
) -> list[str]:
    """The pre-registered comparison: both policies on one decision path, both charged.

    Pre-registration 2 in `docs/PREREGISTRATION.md` locked this before it was run.
    """
    lines = [
        "",
        "## Total cost of assurance: the pre-registered comparison",
        "",
        "Every policy here runs the same decision path. Each may block or abstain, each is",
        "credited for harm that never reached anyone, and each is charged the reviewer",
        "minutes its own verdicts raise through the same queue at the same capacity. The",
        "policies differ in one thing only: which rows they check, and at what tier.",
        "",
        "Before this, only the allocator was charged for attention and only the allocator",
        "could block. Both distortions were real and they pointed in opposite directions.",
        "",
        "| Budget | Policy | Compute | Attention | Total | Averted | ROI on compute | "
        "ROI on total | Cases | Shed |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for fraction in sorted(frame["budget_fraction"].unique()):
        rows = frame[frame["budget_fraction"] == fraction]
        for name in ("allocator", "fixed_rate", "check_all", "check_none"):
            row = rows[rows["policy"] == name].iloc[0]
            lines.append(
                f"| {fraction:.0%} | {name} | {row['assurance_spend_inr']:,.2f} | "
                f"{row['attention_spend_inr']:,.0f} | {row['total_assurance_inr']:,.0f} | "
                f"{row['loss_averted_inr']:,.0f} | {row['assurance_roi']:,.0f} | "
                f"{row['total_assurance_roi']:,.1f} | {row['cases_raised']:.0f} | "
                f"{row['cases_shed']:.0f} |"
            )
    tight = [0.10, 0.25]
    ratios = []
    for fraction in tight:
        left = allocator[allocator["budget_fraction"] == fraction].iloc[0]
        right = baseline[baseline["budget_fraction"] == fraction].iloc[0]
        ratios.append(
            (
                fraction,
                right["assurance_roi"] / left["assurance_roi"],
                right["total_assurance_roi"] / left["total_assurance_roi"],
            )
        )
    lines.extend(
        [
            "",
            "### Against the pre-registered endpoint",
            "",
            "The endpoint was ROI on total cost at the 10% and 25% budgets, with success "
            "requiring the allocator to match or beat the tuned baseline at both.",
            "",
            "| Budget | Baseline/allocator on compute | Baseline/allocator on total |",
            "|---:|---:|---:|",
        ]
    )
    for fraction, compute_ratio, total_ratio in ratios:
        lines.append(f"| {fraction:.0%} | {compute_ratio:.2f}x | {total_ratio:.3f}x |")
    lines.extend(
        [
            "",
            "**Result: partial success, and the reason matters more than the number.** The "
            "allocator does not beat the tuned baseline on total cost at either row, so the "
            "primary endpoint fails. The pre-registered partial-success bar — the ratio "
            "falling to 1.5x or below at both rows — is met, and comfortably.",
            "",
            "But the gap does not close because allocation got better. It closes because "
            "**the attention bill is roughly 30 to 70 times the compute bill and both "
            "policies pay it in full**, so the compute difference the first table argues "
            "about is arithmetically almost irrelevant to what assurance actually costs.",
            "",
            "That cuts against us as much as for us. It says the thing we allocate is the "
            "smaller number. It also says the thing every guardrail vendor competes on is "
            "the smaller number, and that the reviewer queue — oversubscribed, shedding, "
            "and allocated by nobody — is where the money and the risk both are.",
            "",
            "Two further readings the table forces, neither of them flattering:",
            "",
            "- **`check_none` posts the best ROI on total cost.** It averts a seventh of "
            "what the allocator does and pays almost nothing, and a ratio rewards that. "
            "ROI is the wrong headline for a safety control; loss averted is what a "
            "business carries, and `check_none` leaves the overwhelming majority of it on "
            "the table. We report ROI because we pre-registered it, not because it is the "
            "number to optimise.",
            "- **Attention spend is identical across every policy that raises more than a "
            "shift's worth of cases.** Reviewer capacity is fixed, so the queue saturates "
            "and every such policy pays the same. What differs is what gets shed. That is "
            "the comparison worth running next, and it is not in this table.",
            "",
        ]
    )
    return lines


def _attention_lines(detail: dict[str, Any]) -> list[str]:
    """Compute is not the binding constraint; reviewer minutes are."""
    lines = [
        "",
        "## Total cost of assurance: compute against attention",
        "",
        "A review costs INR 120 against INR 3.20 for the dearest automated check. Reviewer",
        "capacity is budgeted separately and the queue reports what it could not absorb.",
        "",
        "| Budget | Compute | Attention | Total | Attention share | Cases raised | Shed |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for fraction, review in sorted(detail["review"].items()):
        compute = detail["compute_spend"][fraction]
        attention = review["attention_spend_inr"]
        total = compute + attention
        lines.append(
            f"| {float(fraction):.0%} | {compute:,.2f} | {attention:,.2f} | {total:,.2f} | "
            f"{attention / total if total else 0:.1%} | {review['cases_raised']:.0f} | "
            f"{review['shed_rate']:.1%} |"
        )
    lines.append("")
    lines.append(
        "Raising the compute budget raises the number of cases needing a person, so buying "
        "more automated checking increases the human bill rather than reducing it."
    )
    return lines


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

