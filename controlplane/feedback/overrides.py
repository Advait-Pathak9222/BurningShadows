from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewOverride:
    interaction_id: str
    reviewer: str
    original_verdict: str
    corrected_verdict: str
    reason: str
