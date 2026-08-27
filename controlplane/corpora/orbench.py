"""Load OR-Bench as `Interaction` records: the over-refusal test this project never ran.

Every corpus here so far asked whether we catch harm. None asked what we do to the safe
traffic that *looks* harmful -- the customer asking how to spot a phishing email, the analyst
asking which drug interactions are dangerous. A guardrail that blocks those is not safe, it is
broken, and on our own corpus the negatives were written by us and are therefore easy.

OR-Bench supplies hard negatives on purpose. `or-bench-hard-1k` is prompts that state-of-the-art
models refuse *even though they are safe*; `or-bench-toxic` is genuinely toxic prompts drawn
from the same ten categories. Held together they are a discrimination task whose negatives were
adversarially selected to defeat exactly the lexical shortcuts our Tier 0 rules rely on.

The published result this is measured against is a trade-off, not a score: across models the
Spearman correlation between safe-rejection rate and toxic-rejection rate is **0.878**, so
almost everything buys safety by refusing benign traffic. The interesting question is not our
AUC, it is whether our operating point sits off that line.

Endpoints are fixed in `docs/PREREGISTRATION.md` (Pre-registration 10). CC-BY-4.0.
"""

from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pandas as pd

from controlplane.models import HarmVector, Interaction

BASE_URL = "https://huggingface.co/datasets/bench-llms/or-bench/resolve/main"
FILES = {"safe": "or-bench-hard-1k.csv", "toxic": "or-bench-toxic.csv"}

ROUTE = "support-assistant"
JURISDICTION = "eu"

# Pre-registered. OR-Bench's ten categories map onto three of our axes; the same mapping is
# applied to both files, so a safe row and a toxic row from one category differ only in label.
AXIS_BY_CATEGORY = {
    "privacy": "pii_leak",
    "hate": "bias",
    "harassment": "unsafe_content",
    "violence": "unsafe_content",
    "sexual": "unsafe_content",
    "self-harm": "unsafe_content",
    "illegal": "unsafe_content",
    "unethical": "unsafe_content",
    "deception": "unsafe_content",
    "harmful": "unsafe_content",
}
LABELLED_AXES = ("pii_leak", "bias", "unsafe_content")

# Fold assignment. OR-Bench ships no split, so one is derived from a hash of the prompt text
# and fixed here rather than chosen after seeing a result. Roughly half calibrates, half tests.
CALIBRATION_SHARE = 0.5


@dataclass(frozen=True)
class CorpusStats:
    """What the loaded fold actually contains, for the results table."""

    rows: int
    toxic: int
    safe: int
    toxic_rate: float
    category_counts: dict[str, int]

    @property
    def is_balanced_enough(self) -> bool:
        """Both classes present, which every metric below assumes."""
        return self.toxic > 0 and self.safe > 0


def _cache_path(cache_dir: Path, part: str) -> Path:
    return cache_dir / "orbench" / FILES[part]


def ensure_downloaded(cache_dir: Path, part: str) -> Path:
    """Fetch one file unless it is already cached. Returns the local path."""
    if part not in FILES:
        raise ValueError(f"unknown part {part!r}; expected one of {sorted(FILES)}")
    path = _cache_path(cache_dir, part)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{BASE_URL}/{FILES[part]}"
    with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310 - fixed HTTPS host
        path.write_bytes(response.read())
    return path


def _digest(text: str) -> int:
    return int(hashlib.sha256(f"orbench:{text}".encode()).hexdigest()[:12], 16)


def _interaction_id(text: str, part: str) -> str:
    return f"ob-{part}-{hashlib.sha256(text.encode()).hexdigest()[:12]}"


def _fold(text: str) -> str:
    """Deterministic and machine-independent, like every other fold split here."""
    return "calibration" if (_digest(text) % 1000) / 1000.0 < CALIBRATION_SHARE else "test"


def load(cache_dir: Path, split: str) -> tuple[list[Interaction], CorpusStats]:
    """Load one derived fold, pooling the safe and toxic files.

    Both files carry prompts only. As with Aegis, the annotated string goes in `response`,
    the field every tier reads.
    """
    if split not in {"calibration", "test"}:
        raise ValueError(f"unknown split {split!r}")

    interactions: list[Interaction] = []
    categories: dict[str, int] = {}
    toxic_rows = 0
    for part, toxic in (("safe", False), ("toxic", True)):
        frame = pd.read_csv(BytesIO(ensure_downloaded(cache_dir, part).read_bytes()))
        for row in frame.itertuples(index=False):
            text = str(row.prompt)
            if _fold(text) != split:
                continue
            category = str(row.category)
            axis = AXIS_BY_CATEGORY.get(category)
            if axis is None:
                raise ValueError(f"unmapped OR-Bench category {category!r}")
            categories[category] = categories.get(category, 0) + 1
            toxic_rows += toxic
            values = dict.fromkeys(LABELLED_AXES, 0.0)
            if toxic:
                values[axis] = 1.0
            interactions.append(
                Interaction(
                    interaction_id=_interaction_id(text, part),
                    split="calibration" if split == "calibration" else "test",
                    route=ROUTE,
                    jurisdiction=JURISDICTION,
                    prompt="",
                    response=text,
                    context_documents=[],
                    truth=HarmVector(
                        hallucination=0.0,
                        pii_leak=values["pii_leak"],
                        bias=values["bias"],
                        unsafe_content=values["unsafe_content"],
                        injection_or_exfil=0.0,
                    ),
                )
            )

    total = len(interactions)
    stats = CorpusStats(
        rows=total,
        toxic=toxic_rows,
        safe=total - toxic_rows,
        toxic_rate=toxic_rows / total if total else 0.0,
        category_counts=dict(sorted(categories.items())),
    )
    return interactions, stats


def categories(cache_dir: Path, split: str) -> dict[str, str]:
    """Interaction id to OR-Bench category, for the per-category false-refusal table.

    A detector that is calm overall but refuses every `privacy` question has a problem the
    pooled number hides. Pre-registration 10 asks for this breakdown either way.
    """
    out: dict[str, str] = {}
    for part in ("safe", "toxic"):
        frame = pd.read_csv(BytesIO(ensure_downloaded(cache_dir, part).read_bytes()))
        for row in frame.itertuples(index=False):
            text = str(row.prompt)
            if _fold(text) == split:
                out[_interaction_id(text, part)] = str(row.category)
    return out
