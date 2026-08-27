"""Evaluate the allocator against real user traffic.

Endpoints are fixed in `docs/PREREGISTRATION.md` (Pre-registration 5) before this ran. The
primary endpoint is allocation at matched spend, not detection quality: our Tier 0 and
Tier 1 are lexical stubs developed against our own corpus, and the pre-registration records
that we expect to lose the detector comparison to OpenAI's moderation endpoint.

Every helper reused from `report.py` is deliberate. Recomputing loss averted here would
make these numbers incomparable with the synthetic-corpus results they sit beside.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from controlplane.corpora import toxicchat
from controlplane.economics import BudgetController
from controlplane.eval.metrics import EvaluationRow, summarize
from controlplane.eval.report import (
    _allocator_row,
    _best_fixed_rate,
    _candidates,
    _full_check_spend,
    _validate_conformal,
)
from controlplane.models import Interaction
from controlplane.service import AssessmentEngine

BUDGET_FRACTIONS = (0.10, 0.25, 0.40, 0.60, 0.80, 1.00)


def _rank_auc(labels: list[float], scores: list[float]) -> float:
    """Mann-Whitney AUC. Ties get mid-ranks, which matters: the lexical detectors
    return long runs of identical scores and optimistic tie handling would flatter them."""
    positives = sum(1 for value in labels if value > 0)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks: list[float] = [float(value) for value in pd.Series(scores).rank(method="average")]
    positive_rank_sum = sum(rank for rank, label in zip(ranks, labels, strict=True) if label > 0)
    return (positive_rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _moderation_scores(cache_dir: Path, split: str, ids: list[str]) -> dict[str, float]:
    """OpenAI moderation is bundled with the corpus, so the baseline costs no API call."""
    frame = pd.read_csv(toxicchat.ensure_downloaded(cache_dir, split))
    by_position = {
        toxicchat._interaction_id(str(row.conv_id), split): max(
            value for _, value in json.loads(str(row.openai_moderation))
        )
        for row in frame.itertuples(index=False)
    }
    return {key: by_position[key] for key in ids if key in by_position}


def _run_allocator_rows(
    engine: AssessmentEngine, test: list[Interaction], budget: float
) -> tuple[list[EvaluationRow], float]:
    """Mirror the shipped allocator loop without touching the ledger."""
    controller = BudgetController(
        budget_rate_inr=max(budget / len(test), 1e-9),
        learning_rate=engine.cost_model.controller_learning_rate,
    )
    rows: list[EvaluationRow] = []
    running = 0.0
    for position, interaction in enumerate(test, start=1):
        trace = engine.assess(interaction, shadow_price=controller.shadow_price)
        running += trace.assurance_spend_inr
        controller.update(running / position)
        rows.append(_allocator_row(engine, interaction, trace))
    return rows, running


def run_probe(
    root: Path, cache_dir: Path, *, human_annotated_only: bool = False
) -> dict[str, Any]:
    calibration, train_stats = toxicchat.load(
        cache_dir, "train", human_annotated_only=human_annotated_only
    )
    test, test_stats = toxicchat.load(
        cache_dir, "test", human_annotated_only=human_annotated_only
    )

    engine = AssessmentEngine(root)
    conformal = engine.calibrate(calibration)

    bundles = {item.interaction_id: engine.detect(item) for item in test}
    scores = {key: bundle.harm.maximum() for key, bundle in bundles.items()}
    latency = {
        item.interaction_id: bundles[item.interaction_id].latency_ms for item in test
    }

    ids = [item.interaction_id for item in test]
    labels = [item.truth.values_by_name()["unsafe_content"] for item in test]
    moderation = _moderation_scores(cache_dir, "test", ids)
    shared = [key for key in ids if key in moderation]
    shared_labels = [
        item.truth.values_by_name()["unsafe_content"] for item in test
        if item.interaction_id in moderation
    ]

    detection = {
        "controlplane_auc": _rank_auc(labels, [scores[key] for key in ids]),
        "openai_moderation_auc": _rank_auc(
            shared_labels, [moderation[key] for key in shared]
        ),
        "rows_scored": len(ids),
        "rows_with_moderation": len(shared),
    }

    full_check = _full_check_spend(engine, test)
    candidates_by_tier = {tier: _candidates(engine, test, scores, tier) for tier in (0, 1, 2)}

    budgets: list[dict[str, float | str]] = []
    for fraction in BUDGET_FRACTIONS:
        budget = full_check * fraction
        allocator_rows, spend = _run_allocator_rows(engine, test, budget)
        allocator = summarize(allocator_rows, budget)
        allocator["budget_fraction"] = fraction

        fixed_rows, _ = _best_fixed_rate(
            engine, test, candidates_by_tier, latency, budget, bundles
        )
        fixed = summarize(fixed_rows, budget)
        fixed["budget_fraction"] = fraction
        budgets.extend([allocator, fixed])

    return {
        "condition": "human_annotated_only" if human_annotated_only else "all_rows",
        "corpus": {
            "name": "lmsys/toxic-chat split 0124",
            "licence": "CC-BY-NC-4.0",
            "calibration_rows": train_stats.rows,
            "test_rows": test_stats.rows,
            "test_toxicity_rate": test_stats.toxicity_rate,
            "test_jailbreak_rate": test_stats.jailbreak_rate,
            "human_annotated_share": test_stats.human_annotated_share,
        },
        "conformal": {route: dict(vars(value)) for route, value in conformal.items()},
        "conformal_validation": _validate_conformal(test, conformal, scores),
        "detection": detection,
        "budgets": budgets,
        "full_check_spend_inr": full_check,
    }
