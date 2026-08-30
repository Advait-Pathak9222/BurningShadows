from __future__ import annotations

import hashlib
from collections.abc import Callable
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
    trace: DecisionTrace,
    policy: RoutePolicy,
    economics: ReviewEconomics,
    arrived_at_minutes: float = 0.0,
) -> ReviewCase | None:
    """Raise a case only for verdicts where the system declined to decide on its own.

    `arrived_at_minutes` is when the interaction happened, measured from the start of the
    traffic window. The queue needs it because a reviewer cannot work a case that does not
    exist yet; leaving it at zero reproduces the batch model and its inflated waits.
    """
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
        arrived_at_minutes=arrived_at_minutes,
    )


def _sort_key(strategy: str) -> Callable[[ReviewCase], tuple[float, ...]]:
    """Serving orders under comparison. `deadline_density` is what ships.

    The alternatives exist so the shipped rule can be falsified rather than asserted:
    `fifo` is what an unmanaged desk does, `random` is the null that would mean the queue
    is not allocating at all, and the two single-term rules are ablations that say which
    half of ours did the work. See pre-registration 3 in `docs/PREREGISTRATION.md`.
    """
    orders: dict[str, Callable[[ReviewCase], tuple[float, ...]]] = {
        # Deadline first, then value density. Ordering by density alone lets a tight-SLA
        # finops case sit behind a queue of higher-value internal-kb ones and breach.
        "deadline_density": lambda case: (case.sla_minutes, -case.value_density),
        "deadline": lambda case: (case.sla_minutes,),
        "density": lambda case: (-case.value_density,),
        "fifo": lambda case: (),
        "random": lambda case: (_stable_uniform(case.interaction_id),),
    }
    if strategy not in orders:
        raise ValueError(f"unknown serving strategy: {strategy}")
    return orders[strategy]


def _stable_uniform(interaction_id: str) -> float:
    """Seeded so the null is reproducible rather than resampled until it loses."""
    digest = hashlib.sha256(f"queue-null:{interaction_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


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
    strategy: str = "deadline_density"
    # Share of serving slots filled uniformly at random rather than by the rule.
    #
    # This costs queue performance and buys the only thing that can recalibrate the
    # system. Serving by expected loss per minute means harmful rows are likelier to be
    # reviewed *within* the raised population, so the labels it produces are a biased
    # sample of it — and biased in a way no stratum-level weight can undo, because the
    # selection happens inside the stratum. Measured on this corpus: a value-ordered
    # sample runs 37% harmful against 18.4% in the traffic it has to price, and inverse
    # probability weighting moved that to 38.2%, which is to say nowhere.
    #
    # A randomly filled slot has a known, uniform inclusion probability. Those rows, and
    # the fixed-rate audit of released rows, are the only ones a refit may fit on.
    random_share: float = 0.0

    def submit(self, case: ReviewCase) -> None:
        self.pending.append(case)

    def drain(self, minutes_available: float) -> list[ReviewDecision]:
        """Work the queue across the traffic window; shed whatever is still waiting at the end.

        A discrete-event simulation over `reviewers` servers, not one pass down a sorted
        list. The difference is the whole point: **a reviewer cannot start a case before it
        arrives.** Charging the last case served a wait equal to the entire window is what
        a batch model does, and it inflated every SLA figure this project has reported.
        Wait is now measured from a case's own arrival to the moment its review finishes,
        which is what an SLA is actually stated over.

        `minutes_available` is reviewer-minutes for the window, so the window in wall-clock
        minutes is that divided by the people on shift.
        """
        reviewers = max(1, int(round(self.economics.parallel_reviewers)))
        window = minutes_available / reviewers
        key = _sort_key(self.strategy)
        arrivals = sorted(
            self.pending, key=lambda case: (case.arrived_at_minutes, case.interaction_id)
        )
        self.pending.clear()

        free_at = [0.0] * reviewers
        waiting: list[ReviewCase] = []
        next_arrival = 0
        decisions: list[ReviewDecision] = []

        while True:
            reviewer = min(range(reviewers), key=lambda index: free_at[index])
            now = free_at[reviewer]
            # Everything that has landed by the time this reviewer frees up is a candidate.
            # This is what makes the serving rule matter: it chooses from the backlog that
            # actually exists at that moment, not from the whole day at once.
            while (
                next_arrival < len(arrivals)
                and arrivals[next_arrival].arrived_at_minutes <= now
            ):
                waiting.append(arrivals[next_arrival])
                next_arrival += 1
            if not waiting:
                if next_arrival >= len(arrivals):
                    break
                # Idle until the next case exists, rather than inventing work to do.
                free_at[reviewer] = arrivals[next_arrival].arrived_at_minutes
                continue
            at_random = self._is_random_slot(len(decisions))
            if at_random:
                # Uniform over what is waiting, so every raised case in the window has the
                # same chance of landing here. That is the whole point: a known inclusion
                # probability, which the serving rule cannot give.
                case = min(waiting, key=lambda item: _stable_uniform(item.interaction_id))
            else:
                case = min(waiting, key=lambda item: (*key(item), item.interaction_id))
            waiting.remove(case)
            finished = max(now, case.arrived_at_minutes) + case.review_minutes
            if finished > window:
                break
            free_at[reviewer] = finished
            waited = finished - case.arrived_at_minutes
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
                    sampled_at_random=at_random,
                )
            )

        served = {decision.case.interaction_id for decision in decisions}
        for case in arrivals:
            if case.interaction_id not in served:
                decisions.append(
                    self._shed(case, max(0.0, window - case.arrived_at_minutes))
                )
        return decisions

    def _is_random_slot(self, served_so_far: int) -> bool:
        """Spread the random slots evenly rather than drawing per slot.

        A per-slot coin flip would make the number of random reviews itself random, so a
        run could produce far fewer labels than the share implies. Spacing them keeps the
        count exact and the run reproducible.
        """
        if self.random_share <= 0.0:
            return False
        if self.random_share >= 1.0:
            return True
        spacing = round(1.0 / self.random_share)
        return served_so_far % spacing == 0

    @staticmethod
    def _shed(case: ReviewCase, elapsed: float) -> ReviewDecision:
        # Shedding costs nothing and reviews nothing. The verdict already taken by the
        # allocator stands, which is why blocking rather than releasing is the safe default
        # for the verdicts that raise a case at all.
        return ReviewDecision(
            case=case, outcome=ReviewOutcome.SHED, wait_minutes=elapsed, spend_inr=0.0
        )
