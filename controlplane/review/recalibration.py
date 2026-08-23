from __future__ import annotations

import hashlib
from dataclasses import dataclass

from controlplane.feedback import BetaBinomialCatchRate
from controlplane.models import ReviewRecord

# Below this the posterior is mostly the Beta(2,2) prior, and reporting it as a measured
# catch rate would be reporting 0.5 dressed up as evidence.
MIN_OBSERVATIONS = 10


@dataclass(frozen=True)
class TierCatchEstimate:
    tier: int
    catches: int
    misses: int
    posterior_mean: float
    configured: float

    @property
    def observations(self) -> int:
        return self.catches + self.misses

    @property
    def has_evidence(self) -> bool:
        return self.observations >= MIN_OBSERVATIONS

    @property
    def reportable(self) -> float | None:
        """The measured rate, or nothing when the tier was never exercised."""
        return self.posterior_mean if self.has_evidence else None


def audit_sample(interaction_ids: list[str], rate: float) -> set[str]:
    """Pick a deterministic random slice of released traffic to review anyway.

    Reviewing only what the system flagged measures precision and nothing else: every
    row in that set was withheld by construction, so it carries no information about
    what was missed. Catch rate needs rows the system chose to release.
    """
    if not 0.0 < rate <= 1.0:
        raise ValueError("audit rate must lie in (0, 1]")
    return {
        interaction_id
        for interaction_id in interaction_ids
        if _draw(interaction_id) < rate
    }


def catch_rates(
    records: list[ReviewRecord], configured: dict[int, float]
) -> dict[int, TierCatchEstimate]:
    """Estimate catch rate per tier from reviewer labels on checked interactions.

    Conditioned on the tier having run: a row nobody checked is evidence about the
    allocator's choice, not about any detector's ability to catch.
    """
    estimates: dict[int, TierCatchEstimate] = {}
    for tier, expected in sorted(configured.items()):
        checked = [
            record
            for record in records
            if record.selected_tier == tier and record.observed_harm
        ]
        catches = sum(record.system_withheld for record in checked)
        misses = len(checked) - catches
        posterior = BetaBinomialCatchRate(caught=catches, missed=misses)
        estimates[tier] = TierCatchEstimate(
            tier=tier,
            catches=catches,
            misses=misses,
            posterior_mean=posterior.mean,
            configured=expected,
        )
    return estimates


def unchecked_escape_rate(records: list[ReviewRecord]) -> dict[str, float]:
    """What declining to check actually costs, measured on the rows we declined.

    A catch rate cannot be computed here: a row the allocator chose not to escalate was
    by construction not withheld, so catches are structurally zero and the ratio would be
    a tautology. The answerable question is what share of that traffic carried harm.
    """
    unchecked = [record for record in records if record.selected_tier is None]
    harmful = sum(record.observed_harm for record in unchecked)
    return {
        "reviewed": float(len(unchecked)),
        "carried_harm": float(harmful),
        "escape_rate": harmful / len(unchecked) if unchecked else 0.0,
    }


def intervention_precision(records: list[ReviewRecord]) -> dict[str, float]:
    """What share of what we withheld a reviewer agreed was harmful."""
    withheld = [record for record in records if record.system_withheld]
    upheld = sum(record.observed_harm for record in withheld)
    released = [record for record in records if not record.system_withheld]
    escaped = sum(record.observed_harm for record in released)
    return {
        "reviewed": float(len(records)),
        "withheld": float(len(withheld)),
        "precision": upheld / len(withheld) if withheld else 0.0,
        "released_reviewed": float(len(released)),
        "escaped_found": float(escaped),
        "escape_rate_in_audit": escaped / len(released) if released else 0.0,
    }


def _draw(interaction_id: str) -> float:
    digest = hashlib.sha256(f"audit:{interaction_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64
