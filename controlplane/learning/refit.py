"""Refit the calibration maps from what reviewers actually found.

The map that turns a raw detector score into a probability was fitted once, at startup,
off a seeded corpus, and never again. Every conformal threshold sits on top of it, so the
guarantee was certified against data the system would never see. This closes that loop:
reviewer labels and the raw scores now carried in the ledger are joined into
`(score, label)` pairs, the maps are refitted, and the thresholds are re-selected.

Two disciplines carry over from the offline path and are not negotiable here.

**The folds stay disjoint.** `in_fitting_fold` is the same predicate the offline split
uses, so a row that fitted a map can never certify the threshold built on it. Doing both
on the same rows once made the bound nine times optimistic on `finops-agent`.

**A refit is offered, not applied.** `learn_then_test` cannot fail — with no passing
threshold it returns 0.0, which releases nothing and trivially satisfies the bound by
checking everything. So the release gate below tests the things that can actually go
wrong: too little data, a threshold that collapsed to full coverage, and a map that
calibrates worse than the one already serving.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controlplane.economics import CostModel
from controlplane.guarantees import in_fitting_fold, learn_then_test
from controlplane.learning.artifacts import (
    AxisCalibration,
    CalibrationArtifact,
    RouteCalibration,
)
from controlplane.ledger import LedgerStore
from controlplane.models import HARM_AXES, HarmVector
from controlplane.policy import PolicyStore
from controlplane.risk.calibration import IsotonicCalibrator, expected_calibration_error

# A map fitted on a handful of rows is noise wearing a probability's clothes. These are
# floors, not targets: the reported row counts are what a reader should judge it on.
#
# The selection floor is derived rather than chosen. With alpha = 0.15 and delta
# Bonferroni-corrected to 0.10/21 = 0.004762, a threshold releasing rows with zero escapes
# still needs log(delta)/log(1-alpha) = 33 released rows before the exact binomial bound
# can clear alpha at all. Released rows are the subset of the selection fold below the
# threshold, so the fold itself has to be comfortably larger than that.
MIN_FITTING_ROWS = 40
MIN_SELECTION_ROWS = 60
# How much worse than the incumbent a candidate may calibrate before it is refused.
ECE_TOLERANCE = 0.01
# An absolute ceiling, checked even with no incumbent to compare against. The bound is
# certified at alpha = 0.15, so a map whose probabilities are off by a third of that is
# not fit to price anything, however good its bound looks. The corpus fit reaches 0.008
# to 0.043 by route, so this is a ceiling on failure, not a target.
MAX_ECE = 0.05
# Reading the whole chain, not a page of it. The chain is one row per decision plus one
# per review, so this is generous for any corpus this project evaluates on.
CHAIN_READ_LIMIT = 1_000_000
# The verdicts that send a case to a person, and so the ones the queue samples from.
WITHHELD_VERDICTS = frozenset({"hold", "abstain", "block"})


@dataclass(frozen=True)
class LabelledScore:
    """One raw score vector with the axes a reviewer actually found wrong.

    `weight` is `1/p`, where `p` is this row's probability of being reviewed at all.
    Without it the fit sees the reviewed population rather than the served one.
    """

    interaction_id: str
    route: str
    jurisdiction: str
    raw: HarmVector
    observed_axes: HarmVector
    observed_harm: bool
    weight: float = 1.0


@dataclass(frozen=True)
class RefitOutcome:
    """What the refit produced, and for every route it refused, why."""

    artifact: CalibrationArtifact | None
    accepted: dict[str, str]
    refused: dict[str, str]
    pairs_found: int

    @property
    def released(self) -> bool:
        return self.artifact is not None


def collect_labelled_scores(ledger: LedgerStore, cost_model: CostModel) -> list[LabelledScore]:
    """Join decisions to reviews on interaction id, and weight for how they were sampled.

    Rows written before `raw_harm` and `observed_axes` existed are skipped rather than
    defaulted: a missing score is not a score of zero, and inventing one would poison the
    map with rows nobody measured.

    Reviews reach the chain through two very different doors, and pretending otherwise is
    what makes a naive refit worse than no refit at all. Measured on this corpus at full
    coverage: 166 queue reviews at a 36.8% harm rate against 39 audit reviews at 12.8%,
    with the traffic itself at 18.4%. Each row is therefore weighted by the inverse of its
    own probability of being looked at.
    """
    decisions: dict[str, dict[str, Any]] = {}
    reviews: dict[str, dict[str, Any]] = {}
    for row in ledger.records(limit=CHAIN_READ_LIMIT):
        payload = json.loads(str(row["record_json"]))
        target = decisions if payload.get("kind") == "decision" else reviews
        # The chain comes back newest first; keep the newest record per interaction.
        target.setdefault(str(payload.get("interaction_id", "")), payload)

    served = _inclusion_rates(decisions, reviews)
    collected: list[LabelledScore] = []
    for interaction_id, decision in decisions.items():
        review = reviews.get(interaction_id)
        if review is None:
            continue
        raw = decision.get("raw_harm")
        axes = review.get("observed_axes")
        if raw is None or axes is None:
            continue
        route = str(decision["route"])
        probability = _inclusion_probability(review, route, served, cost_model)
        if probability <= 0.0:
            continue
        collected.append(
            LabelledScore(
                interaction_id=interaction_id,
                route=route,
                jurisdiction=str(decision["jurisdiction"]),
                raw=HarmVector.model_validate(raw),
                observed_axes=HarmVector.model_validate(axes),
                observed_harm=bool(review["observed_harm"]),
                weight=1.0 / probability,
            )
        )
    return collected


def _inclusion_rates(
    decisions: dict[str, dict[str, Any]], reviews: dict[str, dict[str, Any]]
) -> dict[str, float]:
    """What share of each route's raised cases landed in a randomly filled slot.

    Only those slots have a computable inclusion probability, so this is the rate the
    weights are built from. Cases the serving rule chose are counted in the denominator,
    because they were eligible for a random slot, but never in the numerator.
    """
    raised: dict[str, int] = {}
    sampled: dict[str, int] = {}
    for interaction_id, decision in decisions.items():
        if decision.get("verdict") not in WITHHELD_VERDICTS:
            continue
        route = str(decision["route"])
        raised[route] = raised.get(route, 0) + 1
        review = reviews.get(interaction_id)
        if review is not None and bool(review.get("sampled_at_random", False)):
            sampled[route] = sampled.get(route, 0) + 1
    return {
        route: sampled.get(route, 0) / count for route, count in raised.items() if count
    }


def _inclusion_probability(
    review: dict[str, Any],
    route: str,
    served: dict[str, float],
    cost_model: CostModel,
) -> float:
    """This row's probability of being reviewed, or zero when nobody can compute it.

    Returning zero excludes a row from the fit, and most reviewed rows are excluded. A
    case served by the queue was chosen because its expected loss per minute was high, so
    within the raised population harmful rows are far likelier to be looked at. That is
    selection inside a stratum, and a stratum-level weight cannot undo it: measured here,
    weighting moved the sample's harm rate from 37.2% to 38.2% against traffic at 18.4%.

    Two designs survive. A slot reserved for uniform sampling picks from everything
    waiting with equal probability, and the fixed-rate audit samples released rows at a
    rate somebody configured. Both are computable; the serving rule is not.
    """
    if bool(review.get("sampled_at_random", False)):
        return served.get(route, 0.0)
    if bool(review["system_withheld"]):
        return 0.0
    if review.get("selected_tier") is None:
        return cost_model.audit_rate_unchecked
    return cost_model.audit_rate_checked


def refit_calibration(
    rows: list[LabelledScore],
    policy_store: PolicyStore,
    detector_version: str,
    incumbent: CalibrationArtifact | None = None,
) -> RefitOutcome:
    """Fit maps on one fold, certify thresholds on the other, and gate the release."""
    accepted: dict[str, str] = {}
    refused: dict[str, str] = {}
    routes: dict[str, RouteCalibration] = {}

    for route in sorted({row.route for row in rows}):
        members = [row for row in rows if row.route == route]
        fitting = [row for row in members if in_fitting_fold(row.interaction_id)]
        selection = [row for row in members if not in_fitting_fold(row.interaction_id)]
        if len(fitting) < MIN_FITTING_ROWS or len(selection) < MIN_SELECTION_ROWS:
            refused[route] = (
                f"too few rows: {len(fitting)} fitting (need {MIN_FITTING_ROWS}), "
                f"{len(selection)} selection (need {MIN_SELECTION_ROWS})"
            )
            continue

        calibrators = _fit_axes(fitting)
        policy = policy_store.resolve(route, members[0].jurisdiction)
        # The threshold must be certified against the map that will actually serve it,
        # so the selection fold is scored through the new calibrators, not the old ones.
        scores = [_calibrated_max(calibrators, row.raw) for row in selection]
        harmed = [row.observed_harm for row in selection]
        weights = [row.weight for row in selection]
        certified = learn_then_test(
            route=route,
            scores=scores,
            harmed=harmed,
            alpha=policy.alpha,
            delta=policy.delta,
        )

        if certified.threshold <= 0.0:
            refused[route] = (
                "no threshold passed the bound, so the release would be full coverage"
            )
            continue

        candidate_ece = expected_calibration_error(scores, harmed, weights=weights)
        if candidate_ece > MAX_ECE:
            refused[route] = (
                f"calibration error {candidate_ece:.4f} exceeds the {MAX_ECE} ceiling; "
                f"the bound can look fine while the probabilities under it are wrong"
            )
            continue
        if incumbent is not None and route in incumbent.routes:
            previous = incumbent.calibrators()[route]
            incumbent_ece = expected_calibration_error(
                [_calibrated_max(previous, row.raw) for row in selection],
                harmed,
                weights=weights,
            )
            if candidate_ece > incumbent_ece + ECE_TOLERANCE:
                refused[route] = (
                    f"calibration got worse: ECE {candidate_ece:.4f} against the "
                    f"incumbent's {incumbent_ece:.4f}"
                )
                continue

        routes[route] = RouteCalibration(
            axes={
                axis: AxisCalibration.of(calibrator)
                for axis, calibrator in calibrators.items()
            },
            threshold=certified.threshold,
            alpha=certified.alpha,
            delta=certified.delta,
            released=certified.released,
            escaped_harms=certified.escaped_harms,
            empirical_risk=certified.empirical_risk,
            upper_bound=certified.upper_bound,
            fitting_rows=len(fitting),
            selection_rows=len(selection),
        )
        accepted[route] = (
            f"threshold {certified.threshold:.2f}, bound {certified.upper_bound:.4f} "
            f"<= alpha {certified.alpha}, ECE {candidate_ece:.4f}, "
            f"fitted on {len(fitting)} rows"
        )

    artifact = (
        CalibrationArtifact(detector_version=detector_version, routes=routes)
        if routes
        else None
    )
    return RefitOutcome(
        artifact=artifact, accepted=accepted, refused=refused, pairs_found=len(rows)
    )


def _fit_axes(rows: list[LabelledScore]) -> dict[str, IsotonicCalibrator]:
    weights = [row.weight for row in rows]
    return {
        axis: IsotonicCalibrator.fit(
            [row.raw.values_by_name()[axis] for row in rows],
            [row.observed_axes.values_by_name()[axis] >= 0.5 for row in rows],
            weights,
        )
        for axis in HARM_AXES
    }


def _calibrated_max(calibrators: dict[str, IsotonicCalibrator], raw: HarmVector) -> float:
    """The quantity a conformal threshold is actually applied to."""
    return max(
        calibrators[axis].predict(score) for axis, score in raw.values_by_name().items()
    )


def write_refit_report(root: Path, outcome: RefitOutcome, fingerprint: str) -> list[Path]:
    """Write what the refit found, including every refusal and the reason for it.

    A refusal is the outcome this feature produces most often, and it is the one worth
    reading: it names which route lacked what. Leaving it in terminal output would make
    the only durable record of a learning loop the runs that happened to succeed.
    """
    directory = root / "docs" / "results"
    directory.mkdir(parents=True, exist_ok=True)
    routes = (
        {route: value.model_dump(mode="json") for route, value in outcome.artifact.routes.items()}
        if outcome.artifact is not None
        else {}
    )
    payload = {
        "detector_version": fingerprint,
        "pairs_found": outcome.pairs_found,
        "released": outcome.released,
        "accepted": outcome.accepted,
        "refused": outcome.refused,
        "floors": {
            "min_fitting_rows": MIN_FITTING_ROWS,
            "min_selection_rows": MIN_SELECTION_ROWS,
            "max_ece": MAX_ECE,
            "ece_tolerance": ECE_TOLERANCE,
        },
        "routes": routes,
    }
    json_path = directory / "relearn.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    lines = [
        "# Refitting the calibrator from reviewer labels",
        "",
        "**Generated by `make relearn`. Do not edit by hand.**",
        "",
        f"Detector fingerprint `{fingerprint}`. Usable labelled pairs joined from the audit "
        f"chain: **{outcome.pairs_found}**.",
        "",
        "Only rows whose probability of being reviewed can be computed are counted: the queue's "
        "random reserve, and the fixed-rate audit of released rows. Cases the serving rule chose "
        "are excluded, because a queue ordered by expected loss selects harmful rows from inside "
        "the raised population and no stratum-level weight undoes that.",
        "",
        "## Outcome by route",
        "",
        "| Route | Released | Why |",
        "|---|:--:|---|",
    ]
    for route in sorted(set(outcome.accepted) | set(outcome.refused)):
        if route in outcome.accepted:
            lines.append(f"| {route} | yes | {outcome.accepted[route]} |")
        else:
            lines.append(f"| {route} | **no** | {outcome.refused[route]} |")
    if not outcome.accepted and not outcome.refused:
        lines.append("| *(no route had any usable pairs)* | -- | -- |")

    lines += [
        "",
        "## The gate",
        "",
        "A refit is offered, not applied. `learn_then_test` cannot fail -- with no passing "
        "threshold it returns 0.0, which releases nothing and satisfies the bound by checking "
        "everything -- so the gate tests what can actually go wrong: at least "
        f"{MIN_FITTING_ROWS} fitting and {MIN_SELECTION_ROWS} selection rows, a threshold that "
        f"still releases something, calibration error at or below {MAX_ECE}, and no regression "
        f"beyond {ECE_TOLERANCE} against the map already serving.",
        "",
        "The selection floor is derived rather than chosen: with alpha 0.15 and delta "
        "Bonferroni-corrected to 0.10/21, a threshold releasing rows with zero escapes still "
        "needs 33 released rows before the exact binomial bound can clear alpha at all.",
        "",
    ]
    md_path = directory / "relearn.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return [json_path, md_path]
