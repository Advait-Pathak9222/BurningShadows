"""Load BeaverTails as `Interaction` records, with two corrections applied.

Pre-registration 7 records both, because each is a defect in the shipped corpus rather
than a preference of ours:

1. The official train/test split shares 99.91% of its prompts across folds. The conformal
   bound claims validity on held-out data, so we discard that split and build our own by
   hashing the prompt — every response to a prompt lands in the same fold.
2. The natural harm rate is 55.69%. At that prevalence nearly every row clears the
   expected-loss threshold and the allocator degenerates into checking everything, which
   is the balanced-adversarial trap in `docs/EVIDENCE-PLAN.md`. Prevalence is corrected to
   7% by keeping every safe row and subsampling unsafe rows on a hash of the row.
"""

from __future__ import annotations

import hashlib
import json
import lzma
from dataclasses import dataclass
from pathlib import Path

from controlplane.corpora.download import ensure_cached_file
from controlplane.models import HarmVector, Interaction

# Pinned to an immutable commit, not `main`. See controlplane/corpora/download.py.
REVISION = "8401fe609d288129cc684a9b3be6a93e41cfe678"
BASE_URL = (
    "https://huggingface.co/datasets/PKU-Alignment/BeaverTails/resolve/"
    f"{REVISION}/round0/330k"
)
FILES = ("train.jsonl.xz", "test.jsonl.xz")
DIGESTS = {
    "train.jsonl.xz": "12f04c9200000929ebbc616c29cb53331f6df36e7341d73e4a12cffac0eb1c08",
    "test.jsonl.xz": "1c726c662b85bf4761913041fe9e098f80e5206344864597dbde86bc9a1bfc96",
}

ROUTE = "support-assistant"
JURISDICTION = "eu"

# Locked in Pre-registration 7. `injection_or_exfil` has no corresponding category.
AXIS_CATEGORIES: dict[str, tuple[str, ...]] = {
    "pii_leak": ("privacy_violation",),
    "bias": (
        "discrimination,stereotype,injustice",
        "hate_speech,offensive_language",
        "controversial_topics,politics",
    ),
    "hallucination": ("misinformation_regarding_ethics,laws_and_safety",),
    "unsafe_content": (
        "violence,aiding_and_abetting,incitement",
        "self_harm",
        "drug_abuse,weapons,banned_substance",
        "terrorism,organized_crime",
        "child_abuse",
        "animal_abuse",
        "sexually_explicit,adult_content",
        "non_violent_unethical_behavior",
        "financial_crime,property_crime,theft",
    ),
}


@dataclass(frozen=True)
class CorpusStats:
    calibration_rows: int
    test_rows: int
    test_harm_rate: float
    test_multi_axis_rate: float
    prompt_overlap: int
    natural_harm_rate: float


def _download(cache_dir: Path) -> list[Path]:
    return [
        ensure_cached_file(
            url=f"{BASE_URL}/{name}",
            path=cache_dir / "beavertails" / name,
            sha256=DIGESTS[name],
            timeout_seconds=300,
        )
        for name in FILES
    ]


def _digest(text: str, salt: str) -> int:
    return int(hashlib.sha256(f"{salt}:{text}".encode()).hexdigest()[:8], 16)


def _harm_vector(category: dict[str, bool]) -> HarmVector:
    values = {
        axis: 1.0 if any(category.get(name, False) for name in names) else 0.0
        for axis, names in AXIS_CATEGORIES.items()
    }
    return HarmVector(injection_or_exfil=0.0, **values)


def load(
    cache_dir: Path,
    *,
    target_prevalence: float = 0.07,
    calibration_cap: int = 10_000,
    test_cap: int = 10_000,
) -> tuple[list[Interaction], list[Interaction], CorpusStats]:
    """Return prompt-disjoint calibration and test folds at the requested prevalence.

    `target_prevalence` of 0 or below keeps the corpus's natural rate, which
    Pre-registration 7 requires reporting alongside the corrected run.
    """
    rows: list[dict[str, object]] = []
    for path in _download(cache_dir):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle)

    natural_harm = sum(1 for row in rows if not row["is_safe"]) / len(rows)

    folds: dict[str, list[dict[str, object]]] = {"calibration": [], "test": []}
    for row in rows:
        name = "calibration" if _digest(str(row["prompt"]), "bt") % 100 < 70 else "test"
        folds[name].append(row)

    prepared: dict[str, list[Interaction]] = {}
    for name, fold in folds.items():
        selected = _correct_prevalence(fold, target_prevalence)
        cap = calibration_cap if name == "calibration" else test_cap
        # Deterministic thinning, applied after correction so it preserves the prevalence.
        if len(selected) > cap:
            keep = sorted(selected, key=lambda row: _digest(str(row["response"]), "cap"))[:cap]
            selected = keep
        prepared[name] = [_to_interaction(row, name) for row in selected]

    test = prepared["test"]
    multi = sum(1 for item in test if sum(1 for v in item.truth.values_by_name().values() if v) > 1)
    stats = CorpusStats(
        calibration_rows=len(prepared["calibration"]),
        test_rows=len(test),
        test_harm_rate=sum(1 for item in test if item.truth.has_harm()) / max(len(test), 1),
        test_multi_axis_rate=multi / max(len(test), 1),
        prompt_overlap=len(
            {item.prompt for item in prepared["calibration"]} & {item.prompt for item in test}
        ),
        natural_harm_rate=natural_harm,
    )
    return prepared["calibration"], test, stats


def _correct_prevalence(
    fold: list[dict[str, object]], target: float
) -> list[dict[str, object]]:
    if target <= 0.0:
        return fold
    safe = [row for row in fold if row["is_safe"]]
    unsafe = [row for row in fold if not row["is_safe"]]
    wanted = int(round(len(safe) * target / (1.0 - target)))
    unsafe = sorted(unsafe, key=lambda row: _digest(str(row["response"]), "prev"))[:wanted]
    # Interleave deterministically so the budget controller does not meet all the harm
    # in one block; it adapts online and a sorted stream would flatter or punish it.
    merged = safe + unsafe
    return sorted(merged, key=lambda row: _digest(str(row["response"]), "order"))


def _to_interaction(row: dict[str, object], fold: str) -> Interaction:
    response = str(row["response"])
    digest = hashlib.sha256(f"bt:{row['prompt']}:{response}".encode()).hexdigest()[:12]
    category = row["category"]
    assert isinstance(category, dict)
    return Interaction(
        interaction_id=f"bt-{digest}",
        split="calibration" if fold == "calibration" else "test",
        route=ROUTE,
        jurisdiction=JURISDICTION,
        prompt=str(row["prompt"]),
        response=response,
        context_documents=[],
        truth=_harm_vector(category),
    )
