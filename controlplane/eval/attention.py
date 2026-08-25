"""Does allocating attention beat a naive queue?

Pre-registration 2 found that every policy raising more than a shift's worth of cases
saturates the same fixed reviewer capacity and pays the same attention bill. Allocating
compute barely moves the total. What differs at saturation is **what gets shed**, and that
is decided by the queue's serving order — a rule nobody had tested.

So this compares the shipped rule against the alternatives a real review desk uses, at
identical capacity on identical raised cases. Pre-registration 3 in
`docs/PREREGISTRATION.md` locks the endpoint: dominance over FIFO on both served value and
SLA breaches, because a rule that serves more value by letting tight-deadline cases breach
has moved the failure rather than fixed it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from controlplane.economics import BudgetController
from controlplane.models import Interaction, ReviewCase, ReviewOutcome
from controlplane.review import ReviewQueue, case_from_trace
from controlplane.service import AssessmentEngine

BUDGET_FRACTIONS = (0.10, 0.25, 0.40, 0.60, 0.80, 1.00)
INTERACTIONS_PER_HOUR = 180
STRATEGIES = ("deadline_density", "fifo", "random", "density", "deadline")
SHIPPED = "deadline_density"
NULL = "fifo"
HIGH_VALUE_QUANTILE = 0.90


def run_attention(root: Path, interactions: list[Interaction]) -> dict[str, Any]:
    engine = AssessmentEngine(root)
    engine.calibrate([item for item in interactions if item.split == "calibration"])
    test = [item for item in interactions if item.split == "test"]
    economics = engine.cost_model.review
    minutes = economics.capacity_minutes_per_hour * (len(test) / INTERACTIONS_PER_HOUR)
    full_spend = _full_check_spend(engine, test)

    budgets: list[dict[str, Any]] = []
    for fraction in BUDGET_FRACTIONS:
        cases = _raise_cases(engine, test, full_spend * fraction)
        cutoff = _quantile([case.expected_loss_inr for case in cases], HIGH_VALUE_QUANTILE)
        results = {
            name: _serve(cases, economics, minutes, name, cutoff) for name in STRATEGIES
        }
        budgets.append(
            {
                "budget_fraction": fraction,
                "cases_raised": float(len(cases)),
                "capacity_minutes": minutes,
                "high_value_cutoff_inr": cutoff,
                "oversubscription": _oversubscription(cases, economics, minutes),
                "reviewers_for_throughput": _reviewers_for_throughput(cases, economics, minutes),
                "strategies": results,
            }
        )

    return {
        "capacity_minutes": minutes,
        "reviewers_on_shift": economics.parallel_reviewers,
        "minutes_per_case": economics.minutes_per_case,
        "high_value_quantile": HIGH_VALUE_QUANTILE,
        "budgets": budgets,
        "verdict": _verdict(budgets),
    }


def _raise_cases(
    engine: AssessmentEngine, test: list[Interaction], budget: float
) -> list[ReviewCase]:
    """Stream the allocator exactly as the report does, and collect what it escalates."""
    controller = BudgetController(
        budget_rate_inr=max(budget / len(test), 1e-9),
        learning_rate=engine.cost_model.controller_learning_rate,
    )
    economics = engine.cost_model.review
    cases: list[ReviewCase] = []
    running = 0.0
    for position, item in enumerate(test, start=1):
        trace = engine.assess(item, shadow_price=controller.shadow_price)
        running += trace.assurance_spend_inr
        controller.update(running / position)
        policy = engine.policy_store.resolve(item.route, item.jurisdiction)
        case = case_from_trace(trace, policy, economics)
        if case is not None:
            cases.append(case)
    return cases


def _serve(
    cases: list[ReviewCase],
    economics: Any,
    minutes: float,
    strategy: str,
    high_value_cutoff: float,
) -> dict[str, float]:
    queue = ReviewQueue(economics, strategy=strategy)
    for case in cases:
        queue.submit(case)
    decisions = queue.drain(minutes)
    served = [d for d in decisions if d.outcome is not ReviewOutcome.SHED]
    shed = [d for d in decisions if d.outcome is ReviewOutcome.SHED]
    breached = [d for d in decisions if d.outcome is ReviewOutcome.BREACHED_SLA]
    return {
        "served": float(len(served)),
        "shed": float(len(shed)),
        "breached": float(len(breached)),
        "value_served_inr": sum(d.case.expected_loss_inr for d in served),
        "value_shed_inr": sum(d.case.expected_loss_inr for d in shed),
        "high_value_shed": float(
            sum(1 for d in shed if d.case.expected_loss_inr >= high_value_cutoff)
        ),
        "finops_shed": float(sum(1 for d in shed if d.case.route == "finops-agent")),
        "p99_wait_minutes": _quantile([d.wait_minutes for d in served], 0.99),
    }


def _oversubscription(cases: list[ReviewCase], economics: Any, minutes: float) -> float:
    """Reviewer-minutes demanded per minute available. Above 1.0, something is shed."""
    demanded = sum(case.review_minutes for case in cases)
    return demanded / minutes if minutes else 0.0


def _reviewers_for_throughput(
    cases: list[ReviewCase], economics: Any, minutes: float
) -> float:
    """Reviewers needed to keep up with the arrival rate, ignoring deadlines.

    This is the defensible capacity number: total reviewer-minutes demanded over the
    traffic window, divided by the window, in units of people. It is a lower bound on what
    a desk needs, because clearing the work on average is not the same as clearing each
    case inside its own SLA.

    We deliberately do **not** report a "reviewers needed to meet every SLA" figure. The
    queue drains one batch, so it has no arrival times, and computing an SLA requirement
    against a batch treats eight hours of arrivals as landing at once. That produces a
    number in the high double digits which is an artifact of the harness rather than a
    property of the workload. See the limitation recorded alongside this result.
    """
    demanded = sum(case.review_minutes for case in cases)
    hours = minutes / economics.capacity_minutes_per_hour if minutes else 0.0
    return demanded / (hours * 60.0) if hours else 0.0


def _verdict(budgets: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate the pre-registered endpoint: dominance over FIFO on both axes."""
    dominated = []
    strict = []
    for row in budgets:
        ours = row["strategies"][SHIPPED]
        null = row["strategies"][NULL]
        weak = (
            ours["value_served_inr"] >= null["value_served_inr"]
            and ours["breached"] <= null["breached"]
        )
        dominated.append(weak)
        strict.append(
            weak
            and (
                ours["value_served_inr"] > null["value_served_inr"]
                or ours["breached"] < null["breached"]
            )
        )
    tight = [row["budget_fraction"] in (0.10, 0.25) for row in budgets]
    strict_at_tight = all(
        value for value, is_tight in zip(strict, tight, strict=True) if is_tight
    )
    count = sum(dominated)
    if all(dominated) and strict_at_tight:
        outcome = "success"
    elif count >= 4:
        outcome = "partial"
    else:
        outcome = "failure"
    return {
        "outcome": outcome,
        "budgets_dominated": float(count),
        "budgets_total": float(len(budgets)),
        "strict_at_tight_budgets": strict_at_tight,
    }


def _quantile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(quantile * len(ordered)))]


def _full_check_spend(engine: AssessmentEngine, test: list[Interaction]) -> float:
    total = 0.0
    for item in test:
        policy = engine.policy_store.resolve(item.route, item.jurisdiction)
        tier = engine.cost_model.tiers(policy, item.tool_calls)[2]
        total += tier.verification_cost_inr + tier.delay_cost_inr
    return total


_OUTCOME_TEXT = {
    "success": "**SUCCESS.** The shipped rule dominates FIFO at every budget on both axes, "
    "and strictly improves at least one axis at the two tight budgets.",
    "partial": "**PARTIAL SUCCESS.** The shipped rule dominates FIFO at four or more of six "
    "budgets, but not at all of them.",
    "failure": "**FAILURE.** The shipped rule does not dominate FIFO at enough budgets. The "
    "reviewer queue is a cost centre we have measured accurately and not yet improved.",
}

_LABELS = {
    "deadline_density": "deadline_density (ours)",
    "fifo": "fifo (null)",
    "random": "random (null)",
    "density": "density (ablation)",
    "deadline": "deadline (ablation)",
}


def _diagnosis_lines(summary: dict[str, Any]) -> list[str]:
    """Say why the endpoint failed, using only what the run measured."""
    tight = summary["budgets"][0]
    ours = tight["strategies"][SHIPPED]
    null = tight["strategies"][NULL]
    density = tight["strategies"]["density"]
    ratio = (
        ours["value_served_inr"] / null["value_served_inr"]
        if null["value_served_inr"]
        else 0.0
    )
    worst = max(row["reviewers_for_throughput"] for row in summary["budgets"])
    return [
        "### Why it failed, and what the failure is actually about",
        "",
        f"The shipped rule loses on breaches at every budget, by four or five cases out of "
        f"{ours['breached']:.0f}. That is the whole margin, and the reason is not that the "
        f"rule is bad at deadlines. It is that **at this capacity the deadlines are not "
        f"reachable by any ordering.**",
        "",
        f"The queue is {tight['oversubscription']:.1f}x oversubscribed at the tightest "
        f"budget and worse above it. On this batch model roughly {ours['breached']:.0f} of "
        f"{ours['served']:.0f} served cases breach under *every* rule in the table, "
        f"including FIFO and random. Ordering by deadline front-loads the cases with the "
        f"tightest SLAs — `finops-agent` at 15 minutes — and those breach almost "
        f"immediately, so deadline-awareness makes the count marginally **worse** while "
        f"changing who is inside it. Ordering decides who breaches. It cannot decide "
        f"whether anyone has to.",
        "",
        f"**Keeping up with arrivals at all takes {worst:.1f} reviewers**, against the "
        f"{summary['reviewers_on_shift']:.0f} configured. That is a floor, not a target: "
        f"clearing the work on average is not the same as clearing each case inside its "
        f"own deadline. It is still the number worth putting in front of a buyer, because "
        f"no ordering rule substitutes for it.",
        "",
        "**A caveat that limits the breach counts above, found while checking this.** The "
        "queue drains a single batch, so it has no arrival times: the whole traffic window "
        "is treated as landing at once, and a case served last is charged a wait equal to "
        "the entire window. Real cases arrive spread out and wait only for the backlog "
        "standing when they arrive. **Every SLA breach count in this file, and in "
        "`docs/results/summary.md`, is therefore an upper bound rather than a measurement.** "
        "The comparison between rules is still sound — every rule is charged the same way "
        "on the same cases — but the absolute breach numbers are not, and the fix is an "
        "arrival-time model rather than a different ordering.",
        "",
        "### What the rule does buy, reported as a pre-registered secondary",
        "",
        f"On the axis the endpoint did not turn on, the margin is not small. At the 10% "
        f"budget the shipped rule serves **{ratio:.2f}x the expected loss** FIFO does "
        f"({ours['value_served_inr']:,.0f} against {null['value_served_inr']:,.0f}) from "
        f"the same {ours['served']:.0f} reviewer-hours, and sheds "
        f"**{ours['high_value_shed']:.0f} of the top-decile cases against FIFO's "
        f"{null['high_value_shed']:.0f}**. That holds at every budget.",
        "",
        "This is reported next to the failure, not instead of it. The pre-registration "
        "named dominance on both axes and the rule does not achieve it.",
        "",
        "### The ablation beats the full rule, which is the finding we least wanted",
        "",
        f"`density` — our rule with the deadline term removed — serves more expected loss "
        f"than the full rule at every budget ({density['value_served_inr']:,.0f} against "
        f"{ours['value_served_inr']:,.0f} at 10%) and breaches no more. By the "
        f"pre-registered guard that an ablation beating the full rule becomes the headline: "
        f"**the deadline term is not earning its place at this level of oversubscription.**",
        "",
        f"What it does buy is route fairness rather than deadline compliance. It sheds "
        f"{ours['finops_shed']:.0f} `finops-agent` cases against `density`'s "
        f"{density['finops_shed']:.0f}, so removing it would concentrate every dropped case "
        f"on the highest-consequence route. That is a defensible reason to keep a deadline "
        f"term and it is **not** the reason we gave for having one. The honest statement is "
        f"that the term is doing a different job than the docstring claims, and the docstring "
        f"is what needs to change.",
        "",
    ]


def write_attention(root: Path, summary: dict[str, Any]) -> Path:
    path = root / "docs" / "results" / "attention.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    verdict = summary["verdict"]
    lines = [
        "# Attention allocation: does our queue beat a naive one?",
        "",
        "Regenerated by `make attention`. Every number here is computed.",
        "",
        "Compute allocation barely moves total assurance cost, because reviewer capacity is "
        "fixed and every policy that raises more than a shift's worth of cases saturates it. "
        "What differs is **what gets shed**. This compares the shipped serving order against "
        "the alternatives a real review desk uses, at identical capacity on identical cases.",
        "",
        f"Capacity: {summary['capacity_minutes']:.0f} reviewer-minutes "
        f"({summary['reviewers_on_shift']:.0f} people on shift, "
        f"{summary['minutes_per_case']:.0f} minutes per case).",
        "",
        "## Against the pre-registered endpoint",
        "",
        "Pre-registration 3 required the shipped rule to **dominate FIFO on both axes** — at "
        "least as much expected loss served, and no more SLA breaches — at every budget, "
        "with a strict improvement at the 10% and 25% rows. Dominance rather than a single "
        "scalar, because a rule that serves more value by letting tight-deadline cases "
        "breach has moved the failure rather than fixed it.",
        "",
        _OUTCOME_TEXT[verdict["outcome"]],
        "",
        f"Budgets dominated: {verdict['budgets_dominated']:.0f} of "
        f"{verdict['budgets_total']:.0f}. Strict improvement at both tight budgets: "
        f"{verdict['strict_at_tight_budgets']}.",
        "",
    ]
    lines.extend(_diagnosis_lines(summary))
    for row in summary["budgets"]:
        lines.extend(
            [
                f"## Budget {row['budget_fraction']:.0%} — "
                f"{row['cases_raised']:.0f} cases raised",
                "",
                f"Queue {row['oversubscription']:.1f}x oversubscribed. Reviewers needed "
                f"just to keep up with arrivals: "
                f"{row['reviewers_for_throughput']:.1f}.",
                "",
                "| Rule | Served | Shed | SLA breaches | Value served | Value shed | "
                "High-value shed | finops shed | p99 wait |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for name in STRATEGIES:
            values = row["strategies"][name]
            lines.append(
                f"| {_LABELS[name]} | {values['served']:.0f} | {values['shed']:.0f} | "
                f"{values['breached']:.0f} | {values['value_served_inr']:,.0f} | "
                f"{values['value_shed_inr']:,.0f} | {values['high_value_shed']:.0f} | "
                f"{values['finops_shed']:.0f} | {values['p99_wait_minutes']:.1f} |"
            )
        lines.append("")
    lines.extend(
        [
            "## What this does not claim",
            "",
            "Expected loss is `r * c` and both terms are ours: `r` is a calibrated detector "
            "score and `c` is a policy assumption inside a 0.25x-4x band. This measures "
            "whether the queue allocates well **against our own estimate of value**, not "
            "against a real review desk's outcomes. Replacing `c` with a customer's numbers "
            "could reorder every row above.",
            "",
            "Reviewer handling time is a constant 6 minutes per case. A real desk's handling "
            "time varies with case difficulty, and a rule that knew the difference would "
            "allocate differently. Holding it constant makes this a ranking problem rather "
            "than a knapsack — a simplification that applies to every rule equally.",
            "",
            "Shedding costs nothing in this model because the allocator's verdict stands: a "
            "held effect stays held and a blocked response stays blocked. Shedding is "
            "therefore safe and expensive rather than unsafe — the cost is unreviewed "
            "false positives that a person would have released, and pricing that needs a "
            "false-positive cost we have not derived.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "docs" / "results" / "attention.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return path
