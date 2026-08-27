"""Load NVIDIA's Aegis AI Content Safety Dataset 1.0 as `Interaction` records.

The fourth public corpus, and the first that is **multi-axis by construction**: its 13-category
taxonomy maps onto three of our five harm axes, including `pii_leak`, which no other corpus
here labels. `docs/results/allocation-regime.md` shows that budget-aware allocation can only
beat a well-ranked baseline when the harm mix varies, and it names the statistic that decides
it. This corpus is the test of that precondition on data nobody on this team wrote.

It is also the first corpus in this project under a **permissive licence** (CC-BY-4.0), where
ToxicChat and BeaverTails are both CC-BY-NC-4.0.

Mapping and conventions are fixed in `docs/PREREGISTRATION.md` (Pre-registration 9) and must
not be changed to improve a result.
"""

from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from controlplane.models import HarmVector, Interaction

BASE_URL = (
    "https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-1.0/resolve/main"
)
FILES = {
    "train": "Content Moderation Extracted Annotations 02.08.24_train_release_0418_v1.parquet",
    "test": "Content Moderation Extracted Annotations 02.08.24_test_release_0418_v1.parquet",
}
ANNOTATION_COLUMNS = tuple(f"labels_{index}" for index in range(5))

ROUTE = "support-assistant"
JURISDICTION = "eu"

# Pre-registered. Every Aegis category maps to exactly one of our axes. `hallucination` and
# `injection_or_exfil` get no rows: Aegis 1.0 labels neither groundedness nor jailbreaks, and
# an axis with no ground truth is reported as unlabelled rather than as zero.
AXIS_BY_CATEGORY = {
    "PII/Privacy": "pii_leak",
    "Hate/Identity Hate": "bias",
    "Harassment": "unsafe_content",
    "Violence": "unsafe_content",
    "Threat": "unsafe_content",
    "Sexual": "unsafe_content",
    "Sexual (minor)": "unsafe_content",
    "Suicide and Self Harm": "unsafe_content",
    "Criminal Planning/Confessions": "unsafe_content",
    "Guns and Illegal Weapons": "unsafe_content",
    "Controlled/Regulated Substances": "unsafe_content",
    "Profanity": "unsafe_content",
    "Other": "unsafe_content",
}
SAFE = "Safe"
CAUTION = "Needs Caution"
LABELLED_AXES = ("pii_leak", "bias", "unsafe_content")


@dataclass(frozen=True)
class CorpusStats:
    """What the loaded split actually contains, for the results table."""

    rows: int
    harmful: int
    harm_rate: float
    convention: str
    axis_rates: dict[str, float]
    text_type_counts: dict[str, int]
    mean_axes_per_harmful_row: float


def _cache_path(cache_dir: Path, split: str) -> Path:
    return cache_dir / "aegis" / FILES[split]


def ensure_downloaded(cache_dir: Path, split: str) -> Path:
    """Fetch one split unless it is already cached. Returns the local path."""
    if split not in FILES:
        raise ValueError(f"unknown split {split!r}; expected one of {sorted(FILES)}")
    path = _cache_path(cache_dir, split)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BASE_URL}/{urllib.parse.quote(FILES[split])}"
    with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310 - fixed HTTPS host
        path.write_bytes(response.read())
    return path


def _interaction_id(raw_id: str, split: str) -> str:
    """Stable across machines: the fitting/selection fold split hashes this."""
    digest = hashlib.sha256(f"aegis:{split}:{raw_id}".encode()).hexdigest()[:12]
    return f"ae-{split}-{digest}"


def _annotations(row: pd.Series) -> list[set[str]]:
    """One set of categories per annotator who saw this row."""
    out: list[set[str]] = []
    for column in ANNOTATION_COLUMNS:
        value = row.get(column)
        if not isinstance(value, str) or value in {"", "None"}:
            continue
        labels = {part.strip() for part in value.split(",") if part.strip()}
        if labels:
            out.append(labels)
    return out


def _axes_hit(labels: set[str], *, caution_is_harm: bool) -> set[str]:
    """Which of our axes one annotator's category set fires."""
    hit: set[str] = set()
    for label in labels:
        if label == SAFE:
            continue
        if label == CAUTION:
            if caution_is_harm:
                hit.add("unsafe_content")
            continue
        axis = AXIS_BY_CATEGORY.get(label)
        if axis is not None:
            hit.add(axis)
    return hit


def _axis_scores(annotations: list[set[str]], *, caution_is_harm: bool) -> dict[str, float]:
    """Row-level majority decides harm; the per-axis split carries the disagreement.

    The label has to be the **row-level** majority vote, because that is the binary task the
    published Llama Guard and Aegis F1 scores are measured on. Gating each axis separately
    would silently drop rows where annotators agree the text is unsafe but disagree about
    which category it belongs to -- 2 of 631 positives on the test split, and a different
    task from the one we are claiming to be in band on.

    So: a row is harmful when most annotators called it unsafe, and the axis vector is the
    per-axis agreement rescaled to peak at that row-level agreement. Ratios between axes are
    preserved, which is what the allocator prices; the peak is what `has_harm` reads.
    """
    scores = dict.fromkeys(LABELLED_AXES, 0.0)
    if not annotations:
        return scores
    unsafe_votes = 0
    for labels in annotations:
        hit = _axes_hit(labels, caution_is_harm=caution_is_harm)
        unsafe_votes += bool(hit)
        for axis in hit:
            scores[axis] += 1.0

    agreement = unsafe_votes / len(annotations)
    if agreement <= 0.5:
        return dict.fromkeys(LABELLED_AXES, 0.0)
    peak = max(scores.values())
    if peak <= 0.0:  # pragma: no cover - an unsafe vote always fires a mapped axis
        return dict.fromkeys(LABELLED_AXES, 0.0)
    return {axis: value / peak * agreement for axis, value in scores.items()}


def load(
    cache_dir: Path,
    split: Literal["train", "test"],
    *,
    caution_is_harm: bool = False,
) -> tuple[list[Interaction], CorpusStats]:
    """Load one Aegis split as interactions, plus what it contains.

    `caution_is_harm` selects between the two conventions NVIDIA themselves published: the
    Permissive model treats `Needs Caution` as safe, the Defensive model treats it as unsafe.
    Both are reported, because picking whichever flatters us after seeing the scores is the
    thing pre-registration exists to prevent.
    """
    frame = pd.read_parquet(ensure_downloaded(cache_dir, split))
    engine_split: Literal["calibration", "test", "scenario"] = (
        "calibration" if split == "train" else "test"
    )

    interactions: list[Interaction] = []
    axis_totals = dict.fromkeys(LABELLED_AXES, 0.0)
    harmful = 0
    axes_on_harmful = 0
    for _, row in frame.iterrows():
        harm = _axis_scores(_annotations(row), caution_is_harm=caution_is_harm)
        firing = [axis for axis, value in harm.items() if value > 0]
        if firing:
            harmful += 1
            axes_on_harmful += len(firing)
        for axis in firing:
            axis_totals[axis] += 1.0
        interactions.append(
            Interaction(
                interaction_id=_interaction_id(str(row["id"]), split),
                split=engine_split,
                route=ROUTE,
                jurisdiction=JURISDICTION,
                # The annotated string goes in `response`, the field every tier reads --
                # Tier 1 reads only this one. Scoring a field the annotation does not
                # describe is the error that put ToxicChat at chance; see its results page.
                prompt="",
                response=str(row["text"]),
                context_documents=[],
                truth=HarmVector(
                    hallucination=0.0,
                    pii_leak=harm["pii_leak"],
                    bias=harm["bias"],
                    unsafe_content=harm["unsafe_content"],
                    injection_or_exfil=0.0,
                ),
            )
        )

    stats = CorpusStats(
        rows=len(frame),
        harmful=harmful,
        harm_rate=harmful / len(frame) if len(frame) else 0.0,
        convention="defensive" if caution_is_harm else "permissive",
        axis_rates={
            axis: total / len(frame) if len(frame) else 0.0
            for axis, total in axis_totals.items()
        },
        text_type_counts={
            str(key): int(value) for key, value in frame["text_type"].value_counts().items()
        },
        mean_axes_per_harmful_row=axes_on_harmful / harmful if harmful else 0.0,
    )
    return interactions, stats
