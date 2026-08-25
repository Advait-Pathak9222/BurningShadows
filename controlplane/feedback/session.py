"""Session risk: a questionable turn raises the bar for the turns that follow it.

Multi-turn conversations and agents that compound risk are named in the problem statement.
A single turn can look benign while a sequence walks somewhere it should not go, and a
system that scores every turn independently cannot see that.

**The one design constraint that matters.** Session risk is allowed to make the conformal
floor *stricter* for a session and never looser. That direction is safe: checking more
than the certified threshold requires can only reduce escaped harm relative to the bound,
so the per-route guarantee in `docs/results/summary.md` still holds. Loosening it for a
session that looked clean would invalidate the bound silently, because the threshold was
selected by a risk test over the whole route population and nothing certifies a per-session
one.

So session state never touches the calibrated harm score. It only lowers the threshold at
which a check becomes mandatory.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from controlplane.feedback.conversation import ConversationRiskAccumulator


@dataclass
class SessionRiskStore:
    """Per-session accumulators, keyed by whatever the caller uses as a session id.

    Process-local and unbounded, which is fine for a prototype and is not fine for a
    deployment: a real one needs eviction and shared state across workers. Recorded in
    `docs/LIMITATIONS.md` rather than pretended away.
    """

    decay: float = 0.75
    sessions: dict[str, ConversationRiskAccumulator] = field(default_factory=dict)

    def risk(self, session_id: str | None) -> float:
        """Risk carried into this turn from earlier ones. Zero for a new session."""
        if session_id is None:
            return 0.0
        accumulator = self.sessions.get(session_id)
        return accumulator.risk if accumulator is not None else 0.0

    def observe(self, session_id: str | None, turn_risk: float) -> float:
        """Fold this turn's calibrated harm into the session and return the new level."""
        if session_id is None:
            return 0.0
        accumulator = self.sessions.setdefault(
            session_id, ConversationRiskAccumulator(decay=self.decay)
        )
        return accumulator.observe(turn_risk)

    def reset(self, session_id: str | None = None) -> None:
        if session_id is None:
            self.sessions.clear()
        else:
            self.sessions.pop(session_id, None)


def tightened_threshold(threshold: float, session_risk: float) -> float:
    """Deduct a session's accumulated risk from the bar a turn must clear.

    Subtractive rather than multiplicative, and the difference is not cosmetic. Scaling by
    `(1 - risk)` moves a 0.40 threshold to 0.38 after a probing turn, which is too small to
    change any decision — a mechanism that cannot alter an outcome is not a mechanism.
    Deducting puts session risk and turn risk in the same units: a session carrying 0.12 of
    risk lowers the bar by 0.12, and a session whose accumulated risk reaches the fitted
    threshold puts every subsequent turn under mandatory check.

    Monotone and one-directional. At zero session risk the fitted threshold is used
    unchanged, and rising session risk can only lower it, which can only force more
    checking. It never rises above the fitted value, so the certified per-route bound is
    never relaxed by conversation history.
    """
    if not 0.0 <= session_risk <= 1.0:
        raise ValueError("session_risk must be a probability")
    return max(0.0, threshold - session_risk)
