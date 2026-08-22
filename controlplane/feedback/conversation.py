from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConversationRiskAccumulator:
    """Carry decayed risk forward so questionable turns raise later scrutiny."""

    risk: float = 0.0
    decay: float = 0.75

    def observe(self, turn_risk: float) -> float:
        self.risk = min(1.0, self.decay * self.risk + (1.0 - self.decay) * turn_risk)
        return self.risk
