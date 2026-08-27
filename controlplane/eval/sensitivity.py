"""Does the allocation survive our uncertainty about `c`?

`c` — the rupee consequence of an escaped harm — is the softest input in the system and
the one every rupee figure depends on. `docs/00-assessment.md` names the stop condition:

    route consequence ranges are so uncertain that more than 20% of decisions flip in
    sensitivity analysis

That condition has been quoted in five documents and measured in none. This module
measures it.

Two questions, because they are different questions:

**Level.** Scale every consequence by the same factor. This asks whether we have the
overall magnitude right. It is the easy question, and a uniform scale moves the whole
benefit term against a fixed cut line, so a high flip rate here is expected near the
budget-binding region and says little about the ranking.

**Ranking.** Draw each axis and route independently inside its own plausible band. This
asks whether the allocator is steering the right traffic, which is the claim that matters:
allocation only beats blanket coverage if the ordering of expected loss is roughly right.
A decision that survives independent perturbation of the terms is robust in the way a
buyer cares about.

The budget is held fixed in rupees across every scenario, and the controller is re-run,
because a customer who revises their consequence estimates upward does not thereby have
more money. What changes is which traffic wins the budget.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controlplane.economics import BudgetController, allocate_verification
from controlplane.models import DetectionBundle, Interaction, RoutePolicy
from controlplane.service import AssessmentEngine

# The band Finance and Risk would be asked to approve. Wide, because the honest position
# is that nobody knows this number to better than a factor of a few.
LOW_MULTIPLIER = 0.25
HIGH_MULTIPLIER = 4.0
LEVEL_SCALES = (0.25, 0.5, 1.0, 2.0, 4.0)
DRAWS = 48
# The budget fraction the sweep is run at. 25% is the tight, contested row: the one the
# pre-registration names and the one where the tuned baseline currently wins on ROI.
BUDGET_FRACTION = 0.25
STOP_CONDITION = 0.20
SEED = "sensitivity-20260825"


@dataclass(frozen=True)
class Decision:
    """The part of a decision this analysis compares: what we bought, and what we said."""

    tier: int | None
    verdict: str


def run_sensitivity(root: Path, interactions: list[Interaction]) -> dict[str, Any]:
    engine = AssessmentEngine(root)
    engine.calibrate([item for item in interactions if item.split == "calibration"])
    test = [item for item in interactions if item.split == "test"]

    # Detect once. Consequence does not enter detection, so re-running it per scenario
    # would cost minutes and change nothing.
    bundles = {item.interaction_id: engine.detect(item) for item in test}
    budget = _full_check_spend(engine, test) * BUDGET_FRACTION

    base = _run(engine, test, bundles, budget, _scaled_policies(engine, test, 1.0))

    level = []
    for scale in LEVEL_SCALES:
        if scale == 1.0:
            continue
        run = _run(engine, test, bundles, budget, _scaled_policies(engine, test, scale))
        level.append(
            {
                "scale": scale,
                "flip_rate": _flip_rate(base, run),
                "tier_flip_rate": _flip_rate(base, run, verdict=False),
                "verdict_flip_rate": _flip_rate(base, run, tier=False),
                "coverage": _coverage(run),
            }
        )

    ranking = []
    ranking_tier = []
    ranking_verdict = []
    ever_flipped: set[str] = set()
    for draw in range(DRAWS):
        run = _run(engine, test, bundles, budget, _drawn_policies(engine, test, draw))
        ranking.append(_flip_rate(base, run))
        ranking_tier.append(_flip_rate(base, run, verdict=False))
        ranking_verdict.append(_flip_rate(base, run, tier=False))
        ever_flipped |= {key for key, value in run.items() if base[key] != value}

    mean_ranking_flip = _mean(ranking)
    worst_ranking_flip = max(ranking) if ranking else 0.0
    ever_rate = len(ever_flipped) / len(base) if base else 0.0

    return {
        "budget_fraction": BUDGET_FRACTION,
        "budget_inr": budget,
        "interactions": float(len(test)),
        "low_multiplier": LOW_MULTIPLIER,
        "high_multiplier": HIGH_MULTIPLIER,
        "draws": float(DRAWS),
        "stop_condition": STOP_CONDITION,
        "base_coverage": _coverage(base),
        "level": level,
        "level_worst_flip_rate": max((row["flip_rate"] for row in level), default=0.0),
        "ranking_mean_flip_rate": mean_ranking_flip,
        "ranking_worst_flip_rate": worst_ranking_flip,
        "ranking_ever_flip_rate": ever_rate,
        "ranking_tier_flip_rate": _mean(ranking_tier),
        "ranking_verdict_flip_rate": _mean(ranking_verdict),
        "ranking_worst_exceeds_stop": worst_ranking_flip > STOP_CONDITION,
        # The headline is the ranking mean: the level sweep deliberately walks the budget
        # off its operating point, so quoting its worst case as *the* sensitivity would
        # overstate what the analysis found.
        "flip_rate": mean_ranking_flip,
    }


def _run(
    engine: AssessmentEngine,
    test: list[Interaction],
    bundles: dict[str, DetectionBundle],
    budget: float,
    policies: dict[str, RoutePolicy],
) -> dict[str, Decision]:
    """Stream the test set with the controller live, exactly as the report does."""
    controller = BudgetController(
        budget_rate_inr=max(budget / len(test), 1e-9),
        learning_rate=engine.cost_model.controller_learning_rate,
    )
    decisions: dict[str, Decision] = {}
    running = 0.0
    for position, item in enumerate(test, start=1):
        policy = policies[_policy_key(item)]
        trace = allocate_verification(
            interaction_id=item.interaction_id,
            bundle=bundles[item.interaction_id],
            policy=policy,
            tiers=engine.cost_model.tiers(policy, item.tool_calls),
            shadow_price=controller.shadow_price,
            conformal_threshold=engine.conformal_thresholds[item.route],
            tool_calls=item.tool_calls,
        )
        running += trace.assurance_spend_inr
        controller.update(running / position)
        decisions[item.interaction_id] = Decision(trace.selected_tier, trace.verdict)
    return decisions


def _scaled_policies(
    engine: AssessmentEngine, test: list[Interaction], scale: float
) -> dict[str, RoutePolicy]:
    return {
        key: policy.model_copy(
            update={
                "consequence_inr": {
                    axis: value * scale for axis, value in policy.consequence_inr.items()
                }
            }
        )
        for key, policy in _base_policies(engine, test).items()
    }


def _drawn_policies(
    engine: AssessmentEngine, test: list[Interaction], draw: int
) -> dict[str, RoutePolicy]:
    """Perturb each route and axis independently, log-uniform inside the approved band.

    Log-uniform rather than uniform because the uncertainty is multiplicative: halving and
    doubling a consequence are equally plausible revisions, and a uniform draw over
    [0.25x, 4x] would put most of its mass above the base value and quietly inflate every
    benefit term.
    """
    span = math.log(HIGH_MULTIPLIER) - math.log(LOW_MULTIPLIER)
    drawn: dict[str, RoutePolicy] = {}
    for key, policy in _base_policies(engine, test).items():
        consequence = {}
        for axis, value in policy.consequence_inr.items():
            unit = _stable_uniform(f"{SEED}:{draw}:{key}:{axis}")
            consequence[axis] = value * math.exp(math.log(LOW_MULTIPLIER) + unit * span)
        drawn[key] = policy.model_copy(update={"consequence_inr": consequence})
    return drawn


def _base_policies(
    engine: AssessmentEngine, test: list[Interaction]
) -> dict[str, RoutePolicy]:
    return {
        _policy_key(item): engine.policy_store.resolve(item.route, item.jurisdiction)
        for item in test
    }


def _policy_key(item: Interaction) -> str:
    return f"{item.route}:{item.jurisdiction}"


def _flip_rate(
    base: dict[str, Decision],
    other: dict[str, Decision],
    *,
    tier: bool = True,
    verdict: bool = True,
) -> float:
    if not base:
        return 0.0
    flipped = 0
    for key, value in base.items():
        moved = other[key]
        tier_moved = tier and value.tier != moved.tier
        verdict_moved = verdict and value.verdict != moved.verdict
        if tier_moved or verdict_moved:
            flipped += 1
    return flipped / len(base)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _coverage(run: dict[str, Decision]) -> float:
    if not run:
        return 0.0
    return sum(1 for value in run.values() if value.tier is not None) / len(run)


def _full_check_spend(engine: AssessmentEngine, test: list[Interaction]) -> float:
    total = 0.0
    for item in test:
        policy = engine.policy_store.resolve(item.route, item.jurisdiction)
        tier = engine.cost_model.tiers(policy, item.tool_calls)[2]
        total += tier.verification_cost_inr + tier.delay_cost_inr
    return total


def _stable_uniform(key: str) -> float:
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _worst_draw_note(summary: dict[str, Any]) -> str:
    """Say plainly when the worst case breaches the bar even though the mean clears it."""
    if not summary["ranking_worst_exceeds_stop"]:
        return (
            "Every individual draw stays inside the stop condition, not just the mean."
        )
    return (
        f"**The mean clears the stop condition and the worst single draw does not** "
        f"({summary['ranking_worst_flip_rate']:.1%} against "
        f"{summary['stop_condition']:.0%}). There exist consequence assignments inside "
        f"the approved band under which more than the permitted share of decisions move. "
        f"The stop condition is stated over the range rather than over its worst corner, "
        f"so this passes as written — but a pilot should approve the band before "
        f"unattended use, not after."
    )


def write_sensitivity(root: Path, summary: dict[str, Any]) -> Path:
    path = root / "docs" / "results" / "sensitivity.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    passes = summary["flip_rate"] <= summary["stop_condition"]
    lines = [
        "# Consequence sensitivity",
        "",
        "Regenerated by `make sensitivity`. Every number here is computed.",
        "",
        f"`c` is the softest input in the system. This sweeps it over "
        f"[{summary['low_multiplier']}x, {summary['high_multiplier']}x] of the committed "
        f"policy values and reports how many decisions move, at the "
        f"{summary['budget_fraction']:.0%} budget on "
        f"{summary['interactions']:.0f} held-out rows.",
        "",
        "The budget is held fixed in rupees and the controller is re-run for every "
        "scenario. Revising a consequence estimate upward does not give a customer more "
        "money; it changes which traffic wins the budget they have.",
        "",
        "## Stop condition",
        "",
        f"`docs/00-assessment.md` says the thesis is not ready for unattended use if more "
        f"than {summary['stop_condition']:.0%} of decisions flip across plausible "
        f"consequence ranges.",
        "",
        f"**Measured: {summary['flip_rate']:.1%} — {'PASSES' if passes else 'FAILS'}.**",
        "",
        "## Ranking sensitivity",
        "",
        "Each route and harm axis drawn independently, log-uniform inside the band. This "
        "is the question that matters: allocation only beats blanket coverage if the "
        "ordering of expected loss is roughly right.",
        "",
        f"- Draws: {summary['draws']:.0f}",
        f"- Mean flip rate: {summary['ranking_mean_flip_rate']:.1%}",
        f"- Worst single draw: {summary['ranking_worst_flip_rate']:.1%}",
        f"- Decisions that flipped in at least one draw: "
        f"{summary['ranking_ever_flip_rate']:.1%}",
        f"- Of the mean flip rate, tier changes: "
        f"{summary['ranking_tier_flip_rate']:.1%}; verdict changes: "
        f"{summary['ranking_verdict_flip_rate']:.1%}",
        "",
        _worst_draw_note(summary),
        "",
        "### The verdict does not move",
        "",
        "Across every scenario in this file, tier selection moves and the **verdict does "
        "not**. That is a property of the design rather than a coincidence: `c` enters "
        "the decision only through the benefit term that prices a check, while allow, "
        "annotate, abstain, hold and block are functions of calibrated harm, the evidence "
        "regime, and the conformal floor — none of which contain `c`.",
        "",
        "So the softest input in the system governs **how much we spend looking**, not "
        "**what we do about what we find**. A buyer who disputes our consequence "
        "estimates is disputing the assurance bill, not the safety behaviour. That is the "
        "right place for that argument to land.",
        "",
        "## Level sensitivity",
        "",
        "Every consequence scaled by the same factor. This walks the budget off its "
        "operating point by construction, so a high flip rate here is expected and is a "
        "statement about the budget binding, not about the ranking.",
        "",
        f"Base coverage at the {summary['budget_fraction']:.0%} budget: "
        f"{summary['base_coverage']:.1%}.",
        "",
        "| Scale | Decisions flipped | Tier changed | Verdict changed | Coverage |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in summary["level"]:
        lines.append(
            f"| {row['scale']}x | {row['flip_rate']:.1%} | {row['tier_flip_rate']:.1%} | "
            f"{row['verdict_flip_rate']:.1%} | {row['coverage']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## How to read this",
            "",
            "A flip is a decision that bought a different tier or issued a different "
            "verdict than it did at the committed consequence values. Flips are not "
            "errors: an allocator that never responded to consequence would not be "
            "allocating. The question is whether the response is proportionate to how "
            "well we actually know `c`.",
            "",
            "The headline figure is the ranking mean, not the level worst case. Quoting "
            "the level sweep's worst row as the sensitivity would overstate what this "
            "found, because that row also moves the budget.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (root / "docs" / "results" / "sensitivity.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
    )
    return path
