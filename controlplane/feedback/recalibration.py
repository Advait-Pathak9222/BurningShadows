from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BetaBinomialCatchRate:
    """Update a tier catch-rate estimate from labelled shadow-mode outcomes."""

    caught: int = 0
    missed: int = 0
    prior_alpha: float = 2.0
    prior_beta: float = 2.0

    @property
    def mean(self) -> float:
        return (self.prior_alpha + self.caught) / (
            self.prior_alpha + self.prior_beta + self.caught + self.missed
        )

    def update(self, caught: bool) -> float:
        if caught:
            self.caught += 1
        else:
            self.missed += 1
        return self.mean
