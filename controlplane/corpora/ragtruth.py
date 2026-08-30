"""Load RAGTruth as `Interaction` records.

17,790 responses from six LLMs over retrieved passages, annotated span by span into
*evident conflict* (contradicts the context) and *baseless information* (unsupported by
it). MIT licensed — the only corpus here without a non-commercial clause.

This is the corpus that supplies `context_documents`, which is what the grounding
mechanism was built for and what ToxicChat and BeaverTails both lacked. Its official
split is prompt-disjoint (0 overlap on query and context), so unlike BeaverTails it is
used as shipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from controlplane.corpora.download import ensure_cached_file
from controlplane.models import HarmVector, Interaction

# Pinned to an immutable commit, not `main`. See controlplane/corpora/download.py.
REVISION = "eb4f4b9d1b68eb7092d3e1a61c0cd82d9808737b"
BASE_URL = (
    f"https://huggingface.co/datasets/wandb/RAGTruth-processed/resolve/{REVISION}/data"
)
DIGESTS = {
    "train": "c14ae31ff459c829edc860bda034ee2dbc0a11107b7511195a32bb4ab1ee8000",
    "test": "2fc4fb703ea47ee0d4ab6110b86312f94fdf0bda157bc6ee67c7e61fb90d3bbd",
}
FILES = {"train": "train-00000-of-00001.parquet", "test": "test-00000-of-00001.parquet"}

ROUTE = "support-assistant"
JURISDICTION = "eu"


@dataclass(frozen=True)
class CorpusStats:
    rows: int
    hallucination_rate: float
    evident_conflict: int
    baseless_info: int
    task_types: dict[str, int]


def ensure_downloaded(cache_dir: Path, split: str) -> Path:
    """Fetch one split unless it is already cached, verifying its pinned digest."""
    if split not in FILES:
        raise ValueError(f"unknown split {split!r}; expected one of {sorted(FILES)}")
    filename = FILES[split]
    path = cache_dir / "ragtruth" / filename
    return ensure_cached_file(
        url=f"{BASE_URL}/{filename}",
        path=path,
        sha256=DIGESTS[split],
        timeout_seconds=300,
    )


def load(
    cache_dir: Path,
    split: Literal["train", "test"],
    *,
    with_context: bool = True,
) -> tuple[list[Interaction], CorpusStats]:
    """Load one split. `with_context=False` withholds the passages, which is the
    pre-registered control: a grounding score must collapse to chance without them."""
    frame = pd.read_parquet(ensure_downloaded(cache_dir, split))
    engine_split: Literal["calibration", "test", "scenario"] = (
        "calibration" if split == "train" else "test"
    )

    interactions: list[Interaction] = []
    conflicts = baseless = 0
    for row in frame.itertuples(index=False):
        counts = row.hallucination_labels_processed
        conflict = int(counts["evident_conflict"])
        unsupported = int(counts["baseless_info"])
        conflicts += conflict
        baseless += unsupported
        context = str(row.context)
        interactions.append(
            Interaction(
                interaction_id=f"rt-{split}-{row.id}-{row.model}",
                split=engine_split,
                route=ROUTE,
                jurisdiction=JURISDICTION,
                prompt=str(row.query),
                response=str(row.output),
                context_documents=[context] if with_context else [],
                truth=HarmVector(
                    hallucination=1.0 if (conflict + unsupported) > 0 else 0.0,
                    pii_leak=0.0,
                    bias=0.0,
                    unsafe_content=0.0,
                    injection_or_exfil=0.0,
                ),
            )
        )

    rate = sum(1 for item in interactions if item.truth.has_harm()) / max(len(interactions), 1)
    stats = CorpusStats(
        rows=len(interactions),
        hallucination_rate=rate,
        evident_conflict=conflicts,
        baseless_info=baseless,
        task_types={str(k): int(v) for k, v in frame.task_type.value_counts().items()},
    )
    return interactions, stats


def task_types(cache_dir: Path, split: Literal["train", "test"]) -> dict[str, str]:
    """Interaction id to RAGTruth `task_type`, for the per-task breakdown.

    The pooled AUC is carried by `QA`; on `Data2txt` the detector is barely above chance,
    and that only shows up broken out. See `docs/results/ragtruth.md`.
    """
    frame = pd.read_parquet(ensure_downloaded(cache_dir, split))
    return {
        f"rt-{split}-{row.id}-{row.model}": str(row.task_type)
        for row in frame.itertuples(index=False)
    }
