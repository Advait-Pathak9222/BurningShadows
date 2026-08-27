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

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from controlplane.models import HarmVector, Interaction

BASE_URL = "https://huggingface.co/datasets/wandb/RAGTruth-processed/resolve/main/data"
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
    path = cache_dir / "ragtruth" / FILES[split]
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".partial")
    with urllib.request.urlopen(f"{BASE_URL}/{FILES[split]}", timeout=300) as response:  # noqa: S310
        staging.write_bytes(response.read())
    staging.replace(path)
    return path


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
