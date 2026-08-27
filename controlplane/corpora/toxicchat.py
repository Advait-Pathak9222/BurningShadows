"""Load ToxicChat as `Interaction` records.

Real user-assistant traffic from the Vicuna online demo, used to check the allocator
against traffic nobody on this team wrote. The mapping from ToxicChat's two labels onto
our five harm axes is fixed in `docs/PREREGISTRATION.md` (Pre-registration 5) and must not
be changed to improve a result.

This is the one evaluation path that touches the network, and only on the first run: the
CSVs are cached under `data/external/` and reused afterwards. `make demo` never calls it.
"""

from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from controlplane.models import HarmVector, Interaction

# Split 0124. The 1123 split is the earlier, smaller annotation round.
BASE_URL = "https://huggingface.co/datasets/lmsys/toxic-chat/resolve/main/data/0124"
FILES = {"train": "toxic-chat_annotation_train.csv", "test": "toxic-chat_annotation_test.csv"}

# Pre-registered: ToxicChat labels two of our five axes. The other three carry no ground
# truth here, which is not the same as their being absent.
ROUTE = "support-assistant"
JURISDICTION = "eu"
LABELLED_AXES = ("unsafe_content", "injection_or_exfil")


@dataclass(frozen=True)
class CorpusStats:
    """What the loaded split actually contains, for the results table."""

    rows: int
    harmful: int
    toxicity_rate: float
    jailbreak_rate: float
    human_annotated: int

    @property
    def human_annotated_share(self) -> float:
        return self.human_annotated / self.rows if self.rows else 0.0


def _cache_path(cache_dir: Path, split: str) -> Path:
    return cache_dir / "toxicchat" / FILES[split]


def ensure_downloaded(cache_dir: Path, split: str) -> Path:
    """Fetch one split unless it is already cached. Returns the local path."""
    if split not in FILES:
        raise ValueError(f"unknown split {split!r}; expected one of {sorted(FILES)}")
    path = _cache_path(cache_dir, split)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BASE_URL}/{FILES[split]}"
    # Written to a sibling first so an interrupted download cannot leave a truncated
    # CSV that later loads as a short corpus without anyone noticing.
    staging = path.with_suffix(".partial")
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - fixed HTTPS host
        staging.write_bytes(response.read())
    staging.replace(path)
    return path


def _interaction_id(conv_id: str, split: str) -> str:
    """Stable across machines: the fitting/selection fold split hashes this."""
    digest = hashlib.sha256(f"toxicchat:{split}:{conv_id}".encode()).hexdigest()[:12]
    return f"tc-{split}-{digest}"


def load(
    cache_dir: Path,
    split: Literal["train", "test"],
    *,
    human_annotated_only: bool = False,
) -> tuple[list[Interaction], CorpusStats]:
    """Load one ToxicChat split as interactions, plus what it contains.

    `human_annotated_only` selects the 5,654-row subset a person actually labelled. The
    remainder were auto-filtered as non-toxic by Perspective API, so their negatives come
    from a detector rather than a human. Both conditions are pre-registered for reporting.
    """
    frame = pd.read_csv(ensure_downloaded(cache_dir, split))
    if human_annotated_only:
        frame = frame[frame["human_annotation"]]

    # `calibration` is the split name the engine expects for anything it may fit on.
    engine_split: Literal["calibration", "test", "scenario"] = (
        "calibration" if split == "train" else "test"
    )
    interactions: list[Interaction] = []
    for row in frame.itertuples(index=False):
        toxic = float(row.toxicity)
        jailbreak = float(row.jailbreaking)
        interactions.append(
            Interaction(
                interaction_id=_interaction_id(str(row.conv_id), split),
                split=engine_split,
                route=ROUTE,
                jurisdiction=JURISDICTION,
                prompt=str(row.user_input),
                response=str(row.model_output),
                # ToxicChat carries no retrieved context, so the grounding mechanism is
                # not exercised by this corpus. Recorded in the pre-registration.
                context_documents=[],
                truth=HarmVector(
                    hallucination=0.0,
                    pii_leak=0.0,
                    bias=0.0,
                    unsafe_content=toxic,
                    injection_or_exfil=jailbreak,
                ),
            )
        )

    stats = CorpusStats(
        rows=len(frame),
        harmful=int((frame["toxicity"] > 0).sum()),
        toxicity_rate=float(frame["toxicity"].mean()),
        jailbreak_rate=float(frame["jailbreaking"].mean()),
        human_annotated=int(frame["human_annotation"].sum()),
    )
    return interactions, stats
