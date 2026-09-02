"""Every detector score on every corpus row, fixed by digest.

Moving the tier vocabularies out of Python and into `config/patterns/` was supposed to change
where the knowledge lives and nothing else. This test is what makes that claim checkable: it
scores all 3000 rows with all three lexical tiers and hashes the result. The digests below
were taken from the implementation as it stood before the pattern packs existed, verified
row by row and axis by axis at the time.

A failure here does not necessarily mean a bug. It means a detector now scores differently
than the run that produced every committed figure, so `docs/results/`, the README and the
submitted documents no longer describe the code. If the change is deliberate, regenerate the
numbers with `make report` first, then update the digest in the same commit, so the two can
never drift apart silently.

This is the guard that the pattern packs need most. Serving a new pack against a calibration
map fitted on the old one corrupts every probability while leaving spend almost unchanged.
Measured earlier in this project, a cruder calibration map changed 22.4% of tier decisions and
removed all 80 blocks while total spend moved 0.3%. Cost metrics cannot see that. A digest can.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from controlplane.detectors.base import Detector
from controlplane.detectors.tier0_rules import Tier0Rules
from controlplane.detectors.tier1_models import Tier1SmallModels
from controlplane.detectors.tier2_judge import Tier2Judge
from controlplane.models import Interaction
from controlplane.sim.traffic import ensure_corpus

REPO = Path(__file__).resolve().parents[1]
AXES = ("hallucination", "pii_leak", "bias", "unsafe_content", "injection_or_exfil")

# Taken from the pre-pattern-pack implementation. See the module docstring before changing.
EXPECTED = {
    "tier0": "32be21f148ab9330565e96866223758f56ad5c45cf5d3f638f52774afd2498ee",
    "tier1": "4b2d612479aad8769fa1a414eb2d4e18da66d07d0879c2184a1b6f35d0f17637",
    "tier2": "fb72e5e3d1904ac02c962cb731ee3757412749f379f17897f05b72286031e6cf",
}


@pytest.fixture(scope="module")
def corpus() -> list[Interaction]:
    """Sorted, so the digest depends on the scores and not on generation order."""
    return sorted(ensure_corpus(REPO / "data"), key=lambda row: row.interaction_id)


def _digest(detector: Detector, corpus: list[Interaction]) -> str:
    running = hashlib.sha256()
    for row in corpus:
        scores = detector.run(row).scores
        running.update(row.interaction_id.encode())
        for axis in AXES:
            running.update(f"{getattr(scores, axis):.12f}".encode())
    return running.hexdigest()


@pytest.mark.parametrize(
    ("label", "detector"),
    [
        ("tier0", Tier0Rules()),
        ("tier1", Tier1SmallModels()),
        ("tier2", Tier2Judge()),
    ],
)
def test_scores_match_the_run_that_produced_the_published_figures(
    label: str, detector: Detector, corpus: list[Interaction]
) -> None:
    assert len(corpus) == 3000, "the corpus changed size, so the digests do not apply"
    assert _digest(detector, corpus) == EXPECTED[label], (
        f"{label} now scores the corpus differently than when the committed numbers were "
        f"produced. Regenerate with `make report` before updating this digest."
    )
