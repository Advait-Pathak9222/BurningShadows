"""Hold assurance spend to a budget without ever cancelling a mandatory check.

The shadow price alone does not bound spend. It is a Lagrange multiplier on a soft
constraint, and two things defeat it:

1. The conformal floor is not discretionary. Rows above the per-route threshold are checked
   whatever lambda says, by design -- that is the guarantee. A controller that only raises
   lambda therefore cannot price them out.
2. Raising lambda prices out cheap checks first, but a row whose expected loss averted is
   several thousand rupees stays worth checking at any lambda the controller reaches.

Measured on the shipped corpus, the consequence was an allocator spending **3.75x its
budget** at the tightest setting while the fixed-rate baseline it was compared against was
held to the budget exactly. The comparison was not at matched spend, and the budget was not
a budget.

The governor closes this by *reserving* the floor's own cost. Discretionary spending stops
once committed spend plus the expected remaining floor cost reaches the budget; from there
the allocator runs in mandatory-only mode, which prices out economic checks while leaving
the conformal override untouched. Spend then lands at 1.00x-1.03x of budget across the
whole grid, and no conformally-forced row goes unchecked.

The floor rate is estimated on calibration rows and never on the rows being served, for the
same reason the conformal thresholds are: a reservation informed by the traffic it is
rationing is not a prediction.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BudgetGovernor:
    """Decide, per row, whether discretionary assurance spending is still affordable."""

    budget_inr: float
    rows_expected: int
    floor_rate_inr: float
    committed_inr: float = 0.0
    rows_served: int = 0

    def __post_init__(self) -> None:
        if self.budget_inr < 0:
            raise ValueError("budget_inr must be non-negative")
        if self.rows_expected <= 0:
            raise ValueError("rows_expected must be positive")
        if self.floor_rate_inr < 0:
            raise ValueError("floor_rate_inr must be non-negative")

    @property
    def rows_remaining(self) -> int:
        """Includes the row about to be served, which is what the reservation must cover."""
        return max(0, self.rows_expected - self.rows_served)

    @property
    def reserved_inr(self) -> float:
        """What the guarantee is expected to cost over the rows still to come."""
        return self.floor_rate_inr * self.rows_remaining

    @property
    def feasible(self) -> bool:
        """False when the budget cannot even cover the floor, which is an operator decision.

        An infeasible budget is not an error and is never resolved by skipping mandatory
        checks. The run proceeds, the floor is honoured, and the overspend is reported so
        the operator can raise the budget or relax alpha -- knowingly, either way.
        """
        return self.budget_inr >= self.floor_rate_inr * self.rows_expected

    def mandatory_only(self) -> bool:
        """True once discretionary spending would eat into the reserved floor."""
        return self.committed_inr + self.reserved_inr >= self.budget_inr

    def commit(self, spend_inr: float) -> None:
        if spend_inr < 0:
            raise ValueError("spend_inr must be non-negative")
        self.committed_inr += spend_inr
        self.rows_served += 1
