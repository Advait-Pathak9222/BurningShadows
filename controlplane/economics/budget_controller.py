from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BudgetController:
    """Update the non-negative shadow price from observed spend rate."""

    budget_rate_inr: float
    learning_rate: float = 0.02
    shadow_price: float = 0.0

    def update(self, spend_rate_inr: float) -> float:
        if self.budget_rate_inr <= 0:
            raise ValueError("budget_rate_inr must be positive")
        relative_error = (spend_rate_inr - self.budget_rate_inr) / self.budget_rate_inr
        self.shadow_price = max(
            0.0,
            self.shadow_price + self.learning_rate * relative_error,
        )
        return self.shadow_price
