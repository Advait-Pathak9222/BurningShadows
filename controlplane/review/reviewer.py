from __future__ import annotations

import hashlib

from controlplane.models import (
    DecisionTrace,
    Interaction,
    ReviewRecord,
    ReviewVerdict,
)

# A reviewer is not an oracle. Real queues disagree with ground truth some of the time,
# and a recalibration loop that assumes perfect labels overstates what it has learned.
REVIEWER_ERROR_RATE = 0.06


def review_case(
    interaction: Interaction, trace: DecisionTrace, reviewer: str = "queue-reviewer-1"
) -> ReviewRecord:
    """Produce the label a human would return for one case.

    The label is the corpus ground truth with a deterministic error applied, so the
    recalibration loop is fed something imperfect rather than a perfect oracle.
    """
    truth = interaction.truth.has_harm()
    observed = truth if _draw(interaction.interaction_id) >= REVIEWER_ERROR_RATE else not truth
    withheld = trace.verdict in {"abstain", "hold", "block"}
    return ReviewRecord(
        interaction_id=interaction.interaction_id,
        route=interaction.route,
        reviewer=reviewer,
        verdict=_verdict(observed, withheld),
        reason_code=_reason(observed, withheld),
        observed_harm=observed,
        system_withheld=withheld,
        selected_tier=trace.selected_tier,
    )


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
