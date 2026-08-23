from __future__ import annotations

from dataclasses import dataclass, field

from controlplane.models import (
    DecisionTrace,
    ReviewCase,
    ReviewDecision,
    ReviewOutcome,
    ReviewReason,
    RoutePolicy,
)

# A verdict only reaches a person when the system has declined to decide alone.
REVIEW_REASONS: dict[str, ReviewReason] = {
    "abstain": ReviewReason.UNVERIFIABLE,
    "hold": ReviewReason.EFFECT_HELD,
    "block": ReviewReason.BLOCKED,
}


@dataclass(frozen=True)
class ReviewEconomics:
    reviewer_cost_per_hour_inr: float
    minutes_per_case: float
    capacity_minutes_per_hour: float

    @property
    def cost_per_case_inr(self) -> float:
        return self.reviewer_cost_per_hour_inr / 60.0 * self.minutes_per_case

    @property
    def parallel_reviewers(self) -> float:
        """Capacity is stated in reviewer-minutes per hour, so 120 means two people."""
        return max(1.0, self.capacity_minutes_per_hour / 60.0)


def case_from_trace(
    trace: DecisionTrace, policy: RoutePolicy, economics: ReviewEconomics
) -> ReviewCase | None:
    """Raise a case only for verdicts where the system declined to decide on its own."""
    reason = REVIEW_REASONS.get(trace.verdict)
    if reason is None:
        return None
    return ReviewCase(
        interaction_id=trace.interaction_id,
        route=trace.route,
        reason=reason,
        expected_loss_inr=trace.expected_loss_inr,
        review_minutes=economics.minutes_per_case,
        review_cost_inr=economics.cost_per_case_inr,
        sla_minutes=policy.review_sla_minutes,
    )


@dataclass
class ReviewQueue:
    """Allocate reviewer minutes the way the allocator allocates rupees.

    Reviewer capacity is the second budget. A review costs roughly 38x the most expensive
    automated check, so attention, not compute, is the binding constraint at any realistic
    volume. Cases are served by expected loss per reviewer minute, with deadline promotion
    so a cheap case cannot starve behind an endless supply of expensive ones.
    """

    economics: ReviewEconomics
    pending: list[ReviewCase] = field(default_factory=list)

    def submit(self, case: ReviewCase) -> None:
        self.pending.append(case)

    def drain(self, minutes_available: float) -> list[ReviewDecision]:
        """Serve what capacity allows; shed the rest rather than letting it wait unbounded."""
        decisions: list[ReviewDecision] = []
        consumed = 0.0
        reviewers = self.economics.parallel_reviewers
        for case in self._serving_order():
            if consumed + case.review_minutes > minutes_available:
                decisions.append(self._shed(case, consumed / reviewers))
                continue
            consumed += case.review_minutes
            # Reviewer-minutes are consumed in parallel, so wall-clock wait is the work
            # divided across the people on shift.
            waited = consumed / reviewers
            decisions.append(
                ReviewDecision(
                    case=case,
                    outcome=(
                        ReviewOutcome.BREACHED_SLA
                        if waited > case.sla_minutes
                        else ReviewOutcome.REVIEWED
                    ),
                    wait_minutes=waited,
                    spend_inr=case.review_cost_inr,
                )
            )
        self.pending.clear()
        return decisions

    def _serving_order(self) -> list[ReviewCase]:
        # Deadline first, then value density. Ordering by density alone lets a tight-SLA
        # finops case sit behind a queue of higher-value internal-kb ones and breach.
        return sorted(
            self.pending,
            key=lambda case: (case.sla_minutes, -case.value_density, case.interaction_id),
        )

    @staticmethod
    def _shed(case: ReviewCase, elapsed: float) -> ReviewDecision:
        # Shedding costs nothing and reviews nothing. The verdict already taken by the
        # allocator stands, which is why blocking rather than releasing is the safe default
        # for the verdicts that raise a case at all.
        return ReviewDecision(
            case=case, outcome=ReviewOutcome.SHED, wait_minutes=elapsed, spend_inr=0.0
        )
