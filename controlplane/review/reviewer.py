from __future__ import annotations

import hashlib

from controlplane.models import (
    DecisionTrace,
    HarmVector,
    Interaction,
    ReviewRecord,
    ReviewVerdict,
)

# A reviewer is not an oracle. Real queues disagree with ground truth some of the time,
# and a recalibration loop that assumes perfect labels overstates what it has learned.
REVIEWER_ERROR_RATE = 0.06


def review_case(
    interaction: Interaction,
    trace: DecisionTrace,
    reviewer: str = "queue-reviewer-1",
    sampled_at_random: bool = False,
) -> ReviewRecord:
    """Produce the label a human would return for one case.

    The label is the corpus ground truth with a deterministic error applied, so the
    recalibration loop is fed something imperfect rather than a perfect oracle.
    """
    truth = interaction.truth.has_harm()
    correct = _draw(interaction.interaction_id) >= REVIEWER_ERROR_RATE
    observed = truth if correct else not truth
    withheld = trace.verdict in {"abstain", "hold", "block"}
    return ReviewRecord(
        interaction_id=interaction.interaction_id,
        route=interaction.route,
        reviewer=reviewer,
        verdict=_verdict(observed, withheld),
        reason_code=_reason(observed, withheld),
        observed_harm=observed,
        observed_axes=_observed_axes(interaction.truth, correct),
        sampled_at_random=sampled_at_random,
        system_withheld=withheld,
        selected_tier=trace.selected_tier,
    )


def _observed_axes(truth: HarmVector, correct: bool) -> HarmVector:
    """Which axes the reviewer marks, kept consistent with `observed_harm`.

    One draw decides whether the reviewer got the case right, the same draw that already
    sets `observed_harm`, so adding per-axis labels does not change the case-level error
    rate or any number derived from it. A reviewer who is wrong is wrong about the whole
    case: they either miss every axis that was there, or invent the single most plausible
    one, which is the axis the corpus scored highest without crossing the label line.
    """
    values = truth.values_by_name()
    if correct:
        return HarmVector(**{axis: 1.0 if value >= 0.5 else 0.0 for axis, value in values.items()})
    if truth.has_harm():
        return HarmVector.zeros()
    nearest = max(values, key=lambda axis: (values[axis], axis))
    return HarmVector(**{axis: 1.0 if axis == nearest else 0.0 for axis in values})


def _verdict(observed_harm: bool, withheld: bool) -> ReviewVerdict:
    if observed_harm == withheld:
        return ReviewVerdict.UPHELD
    return ReviewVerdict.OVERTURNED


def _reason(observed_harm: bool, withheld: bool) -> str:
    if observed_harm and withheld:
        return "harm confirmed, hold correct"
    if observed_harm and not withheld:
        return "harm present but released"
    if withheld:
        return "no harm found, over-flagged"
    return "no harm, release correct"


def _draw(interaction_id: str) -> float:
    digest = hashlib.sha256(f"review:{interaction_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64
