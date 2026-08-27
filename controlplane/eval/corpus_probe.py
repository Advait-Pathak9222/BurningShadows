"""Run the shipped pipeline against an external corpus and report it comparably.

`toxicchat_probe.py` grew corpus-specific; this is the general version, used by Aegis
(Pre-registration 9) and OR-Bench (Pre-registration 10). Every helper it borrows from
`report.py` is deliberate: recomputing loss averted here would make these numbers
incomparable with the synthetic-corpus results they are printed beside.

Two things it does that earlier probes did not:

- The allocator runs under `BudgetGovernor`, so its budget is a budget. Without it the
  allocator spent up to 3.75x its budget while the baseline it was compared against was
  held to budget exactly, and the "matched spend" endpoint was not matched.
- The baseline is matched to the allocator's **actual** spend, not to its nominal budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controlplane.detectors.fitted_bayes import FittedBayesTier1
from controlplane.economics import BudgetController, BudgetGovernor
from controlplane.economics.allocator import expected_loss_inr
from controlplane.eval.benchmark_metrics import (
    average_precision,
    best_f1_threshold,
    flag_everything_f1,
    operating_point,
    rank_auc,
    spearman,
)
from controlplane.eval.metrics import EvaluationRow, summarize
from controlplane.eval.report import (
    _allocator_row,
    _best_fixed_rate,
    _candidates,
    _full_check_spend,
    _validate_conformal,
)
from controlplane.models import DetectionBundle, Interaction
from controlplane.service import AssessmentEngine, _split_folds

# Wider at the bottom than the report's grid, because `allocation-regime.md` showed the
# whole earlier grid sat above the boundary where blanket cheap coverage stops being
# affordable, and every budget tested was therefore in the regime allocation cannot win.
BUDGET_FRACTIONS = (0.01, 0.03, 0.056, 0.10, 0.25, 0.50, 1.00)
HARM_AXES = ("hallucination", "pii_leak", "bias", "unsafe_content", "injection_or_exfil")


@dataclass(frozen=True)
class CorpusSpec:
    """What a corpus is, and which of its structure is worth breaking results out by."""

    name: str
    licence: str
    source_url: str
    labelled_axes: tuple[str, ...]
    groups: dict[str, str]  # interaction_id -> group name, for the breakdown table


def _labels(test: list[Interaction]) -> list[bool]:
    return [item.truth.has_harm() for item in test]


def _run_allocator(
    engine: AssessmentEngine,
    test: list[Interaction],
    budget: float,
    floor_rate: float,
) -> tuple[list[EvaluationRow], float, int]:
    """Stream the corpus through the allocator under a governed budget."""
    controller = BudgetController(
        budget_rate_inr=max(budget / len(test), 1e-9),
        learning_rate=engine.cost_model.controller_learning_rate,
    )
    governor = BudgetGovernor(
        budget_inr=budget, rows_expected=len(test), floor_rate_inr=floor_rate
    )
    rows: list[EvaluationRow] = []
    running = 0.0
    shed = 0
    for position, interaction in enumerate(test, start=1):
        exhausted = governor.mandatory_only()
        shed += exhausted
        trace = engine.assess(
            interaction, shadow_price=controller.shadow_price, mandatory_only=exhausted
        )
        running += trace.assurance_spend_inr
        governor.commit(trace.assurance_spend_inr)
        controller.update(running / position)
        rows.append(_allocator_row(engine, interaction, trace))
    return rows, running, shed


def _detection(
    engine: AssessmentEngine,
    calibration: list[Interaction],
    test: list[Interaction],
    scores: dict[str, float],
    spec: CorpusSpec,
) -> dict[str, Any]:
    """Threshold-free ranking metrics, plus one honestly-chosen operating point."""
    labels = _labels(test)
    ordered = [scores[item.interaction_id] for item in test]

    # The threshold comes from calibration and is applied unchanged. An F1 maximised on the
    # split it is reported on is an oracle number and is not what published fixed-operating-
    # point F1 means; both are shown so the difference is visible.
    calibration_scores = [engine.detect(item).harm.maximum() for item in calibration]
    threshold = best_f1_threshold(_labels(calibration), calibration_scores)
    fixed = operating_point(labels, ordered, threshold)
    oracle = operating_point(labels, ordered, best_f1_threshold(labels, ordered))

    per_axis: dict[str, Any] = {}
    for axis in spec.labelled_axes:
        axis_labels = [
            float(item.truth.values_by_name()[axis]) >= 0.5 for item in test
        ]
        axis_scores = [
            float(engine.detect(item).harm.values_by_name()[axis]) for item in test
        ]
        per_axis[axis] = {
            "auc": rank_auc(axis_labels, axis_scores),
            "auprc": average_precision(axis_labels, axis_scores),
            "positives": sum(axis_labels),
        }

    groups: dict[str, Any] = {}
    for name in sorted(set(spec.groups.values())):
        member = [
            index
            for index, item in enumerate(test)
            if spec.groups.get(item.interaction_id) == name
        ]
        if not member:
            continue
        group_labels = [labels[index] for index in member]
        group_scores = [ordered[index] for index in member]
        point = operating_point(group_labels, group_scores, threshold)
        groups[name] = {
            "rows": len(member),
            "base_rate": sum(group_labels) / len(member),
            "auc": rank_auc(group_labels, group_scores),
            "flag_rate": point.flagged / len(member),
            "false_positive_rate": point.false_positive_rate,
            "recall": point.recall,
        }

    return {
        "auc": rank_auc(labels, ordered),
        "auprc": average_precision(labels, ordered),
        "base_rate": sum(labels) / len(labels) if labels else 0.0,
        "threshold_from_calibration": threshold,
        "fixed_threshold": {
            "precision": fixed.precision,
            "recall": fixed.recall,
            "f1": fixed.f1,
            "false_positive_rate": fixed.false_positive_rate,
            "flag_rate": fixed.flagged / len(test) if test else 0.0,
            "degenerate": fixed.is_degenerate,
        },
        "oracle_threshold_f1": oracle.f1,
        # The null every F1 above must be read against. See `flag_everything_f1`.
        "flag_everything_f1": flag_everything_f1(labels),
        "per_axis": per_axis,
        "per_group": groups,
    }


def _harm_mix(
    engine: AssessmentEngine, test: list[Interaction], bundles: dict[str, DetectionBundle]
) -> dict[str, Any]:
    """The precondition from `allocation-regime.md`, measured before allocation is run.

    At Spearman 1.0 expected-loss ranking is a monotone rescaling of risk ranking and the
    allocator is provably sorting the same list the baseline already sorts.
    """
    risk: list[float] = []
    loss: list[float] = []
    axes_firing = 0
    harmful = 0
    for item in test:
        policy = engine.policy_store.resolve(item.route, item.jurisdiction)
        bundle = bundles[item.interaction_id]
        risk.append(bundle.harm.maximum())
        loss.append(expected_loss_inr(bundle, policy))
        firing = sum(
            1 for axis in HARM_AXES if float(item.truth.values_by_name()[axis]) >= 0.5
        )
        if firing:
            harmful += 1
            axes_firing += firing
    return {
        "spearman_risk_expected_loss": spearman(risk, loss),
        "mean_axes_per_harmful_row": axes_firing / harmful if harmful else 0.0,
        "harmful_rows": harmful,
    }


def probe(
    root: Path,
    calibration: list[Interaction],
    test: list[Interaction],
    spec: CorpusSpec,
    *,
    fitted_tier1: bool = False,
) -> dict[str, Any]:
    """Calibrate on one split, score the other, and report detection and allocation.

    `fitted_tier1` swaps the hand-written Tier 1 for a bag-of-words model fitted on this
    corpus, the same substitution Pre-registration 6 made for ToxicChat. It separates two
    questions that a single number confuses: whether the allocation machinery works, and
    whether our lexical stubs happen to cover a given corpus's vocabulary.

    It is fitted on the **fitting fold only**. Fitting it on the whole calibration split
    lets it memorise the selection fold that certifies the conformal bound, which is how a
    certified 0.1407 came to sit against a measured 0.2800 on held-out ToxicChat rows.
    """
    engine = AssessmentEngine(root)
    if fitted_tier1:
        fitting, _ = _split_folds(calibration)
        engine.tier1 = FittedBayesTier1.fit(fitting)  # type: ignore[assignment]
    conformal = engine.calibrate(calibration)
    floor_rate = engine.floor_rate_inr(calibration)

    bundles = {item.interaction_id: engine.detect(item) for item in test}
    scores = {key: bundle.harm.maximum() for key, bundle in bundles.items()}
    latency = {key: bundle.latency_ms for key, bundle in bundles.items()}

    full_check = _full_check_spend(engine, test)
    blanket_tier1 = sum(
        engine.cost_model.tiers(
            engine.policy_store.resolve(item.route, item.jurisdiction), item.tool_calls
        )[1].verification_cost_inr
        for item in test
    )
    candidates_by_tier = {tier: _candidates(engine, test, scores, tier) for tier in (1, 2)}

    budgets: list[dict[str, Any]] = []
    for fraction in BUDGET_FRACTIONS:
        budget = full_check * fraction
        rows, spend, shed = _run_allocator(engine, test, budget, floor_rate)
        allocator = summarize(rows, budget)
        # Matched to what the allocator actually spent, which is the whole point.
        fixed_rows, _ = _best_fixed_rate(
            engine, test, candidates_by_tier, latency, spend, bundles
        )
        fixed = summarize(fixed_rows, spend)
        averted = float(allocator["loss_averted_inr"])
        reference = float(fixed["loss_averted_inr"])
        budgets.append(
            {
                "budget_fraction": fraction,
                "budget_inr": budget,
                "allocator_spend_inr": spend,
                "spend_over_budget": spend / budget if budget else float("inf"),
                "rows_mandatory_only": shed,
                "blanket_tier1_affordable": budget >= blanket_tier1,
                "allocator_loss_averted_inr": averted,
                "fixed_rate_loss_averted_inr": reference,
                "gain": (averted - reference) / reference if reference else 0.0,
                "allocator_escaped_unchecked": allocator["escaped_harm_rate_unchecked"],
                "fixed_rate_escaped_unchecked": fixed["escaped_harm_rate_unchecked"],
            }
        )

    wins = sum(1 for row in budgets if float(row["gain"]) > 0)
    return {
        "tier1": "fitted_bayes_bow" if fitted_tier1 else "lexical_stub",
        # Consumed by callers that need a threshold sweep, then deleted before writing.
        "_scores": [scores[item.interaction_id] for item in test],
        "corpus": {
            "name": spec.name,
            "licence": spec.licence,
            "source": spec.source_url,
            "calibration_rows": len(calibration),
            "test_rows": len(test),
            "labelled_axes": list(spec.labelled_axes),
        },
        "detection": _detection(engine, calibration, test, scores, spec),
        "harm_mix": _harm_mix(engine, test, bundles),
        "conformal": {route: dict(vars(value)) for route, value in conformal.items()},
        "conformal_validation": _validate_conformal(test, conformal, scores),
        "economics": {
            "full_tier2_spend_inr": full_check,
            "blanket_tier1_spend_inr": blanket_tier1,
            "blanket_tier1_boundary_fraction": blanket_tier1 / full_check
            if full_check
            else 0.0,
            "floor_rate_inr_per_row": floor_rate,
            "floor_spend_inr": floor_rate * len(test),
        },
        "budgets": budgets,
        "allocator_wins": wins,
        "budgets_tested": len(budgets),
    }
