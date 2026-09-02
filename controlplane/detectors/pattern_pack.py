"""Load the cheap tier's knowledge base from `config/patterns/`, and hash it.

Tier 0's vocabulary used to be module constants. That made every rule change a source edit
and a redeploy, and it meant nothing recorded *which* rules produced a given decision. Both
are fixed by loading the vocabulary as data and stamping its content hash onto the trace.

The hash matters more than it looks. A detector and its calibrator can drift apart silently:
serving a new pattern pack against a probability map fitted on the old one corrupts every
probability, and therefore every expected-loss figure and every threshold, while leaving the
cost metrics almost unchanged. Measured earlier in this project, swapping calibration for a
cruder map changed 22.4% of tier decisions and removed all 80 blocks while total spend moved
by 0.3%. A drift that invisible cannot be monitored for. It has to be checked at load, which
is what the hash is for.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PACK_DIR = Path(__file__).resolve().parents[2] / "config" / "patterns"


def _canonical(payload: Any) -> str:
    """A stable serialisation, so the hash depends on content and not on key order."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a mapping, found {type(loaded).__name__}")
    return loaded


def _require(payload: dict[str, Any], key: str, kind: type) -> Any:
    if key not in payload:
        raise ValueError(f"pattern pack is missing {key!r}")
    value = payload[key]
    if not isinstance(value, kind):
        raise ValueError(f"pattern pack key {key!r} must be {kind.__name__}")
    return value


def _phrases(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    raw = _require(payload, key, list)
    if not raw:
        raise ValueError(f"pattern pack key {key!r} is empty")
    for phrase in raw:
        if not isinstance(phrase, str) or not phrase.strip():
            raise ValueError(f"pattern pack key {key!r} holds a non-string or blank entry")
        if phrase != phrase.lower():
            # Matching is done against lowercased text, so an uppercase phrase can never fire.
            raise ValueError(f"pattern pack phrase {phrase!r} must be lowercase")
    return tuple(raw)


def _compiled(payload: dict[str, Any], key: str) -> dict[str, re.Pattern[str]]:
    raw = _require(payload, key, dict)
    compiled: dict[str, re.Pattern[str]] = {}
    for name, expression in raw.items():
        if not isinstance(expression, str):
            raise ValueError(f"pattern {name!r} must be a string")
        try:
            compiled[str(name)] = re.compile(expression)
        except re.error as error:
            raise ValueError(f"pattern {name!r} does not compile: {error}") from error
    if not compiled:
        raise ValueError(f"pattern pack key {key!r} is empty")
    return compiled


def _scores(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, float]:
    raw = _require(payload, "scores", dict)
    missing = [key for key in keys if key not in raw]
    if missing:
        raise ValueError(f"pattern pack is missing scores {missing}")
    out: dict[str, float] = {}
    for key in keys:
        value = raw[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"score {key!r} must be a number")
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"score {key!r} must sit in [0, 1], found {value}")
        out[key] = float(value)
    return out


TIER0_SCORE_KEYS = (
    "hallucination_numeric_mismatch",
    "hallucination_clean",
    "bias_hit",
    "bias_clean",
    "unsafe_hit",
    "unsafe_clean",
    "injection_base",
    "injection_per_hit",
    "injection_cap",
    "injection_clean",
)
DISCLOSURE_SCORE_KEYS = (
    "secret_value_ungrounded",
    "identifier_in_personal_frame",
    "personal_frame_unauthorised",
    "identifier_ungrounded",
    "secret_named_only",
    "identifier_grounded",
    "nothing_disclosed",
)
DISCLOSURE_REGEX_KEYS = ("dot", "at", "email", "phone", "secret_value")
TIER1_SCORE_KEYS = (
    "pii_base", "pii_per_hit", "pii_cap",
    "bias_base", "bias_per_hit", "bias_cap",
    "unsafe_base", "unsafe_per_hit", "unsafe_cap",
    "injection_base", "injection_per_hit", "injection_anomaly_weight", "injection_cap",
    "grounded_cap", "grounded_floor", "grounding_bar",
    "samples_cap", "samples_floor",
    "blind_cap", "blind_floor", "blind_centre",
)
TIER1_SHAPE_KEYS = (
    "anomaly_length_offset", "anomaly_length_scale", "jitter_span", "token_min_length",
)
TIER2_SCORE_KEYS = (
    "hallucination_hit", "hallucination_clean",
    "pii_hit", "pii_clean",
    "bias_hit", "bias_clean",
    "unsafe_hit", "unsafe_clean",
    "injection_hit", "injection_clean",
)
TIER2_MARKER_KEYS = ("unsupported", "privacy", "discriminatory", "unsafe", "injection")


def _shape(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, float]:
    """Lengths and spans rather than probabilities, so the bound is positive, not [0, 1]."""
    raw = _require(payload, "shape", dict)
    missing = [key for key in keys if key not in raw]
    if missing:
        raise ValueError(f"pattern pack is missing shape values {missing}")
    out: dict[str, float] = {}
    for key in keys:
        value = raw[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"shape value {key!r} must be a number")
        if float(value) <= 0:
            raise ValueError(f"shape value {key!r} must be positive, found {value}")
        out[key] = float(value)
    return out


@dataclass(frozen=True)
class Tier0Pack:
    """Everything the Tier 0 rule detector knows."""

    version: int
    pii_patterns: dict[str, re.Pattern[str]]
    injection_phrases: tuple[str, ...]
    unsafe_phrases: tuple[str, ...]
    bias_phrases: tuple[str, ...]
    scores: dict[str, float]
    content_hash: str


@dataclass(frozen=True)
class DisclosurePack:
    """Everything the sensitive-disclosure ladder knows."""

    version: int
    regexes: dict[str, re.Pattern[str]]
    personal_framing: tuple[str, ...]
    authorised_framing: tuple[str, ...]
    secret_terms: tuple[str, ...]
    scores: dict[str, float]
    content_hash: str


@dataclass(frozen=True)
class Tier1Pack:
    """Everything the Tier 1 lexical stub knows."""

    version: int
    toxic_words: tuple[str, ...]
    bias_words: tuple[str, ...]
    exfil_words: tuple[str, ...]
    scores: dict[str, float]
    shape: dict[str, float]
    content_hash: str


@dataclass(frozen=True)
class Tier2Pack:
    """Everything the deterministic judge stub knows."""

    version: int
    markers: dict[str, tuple[str, ...]]
    scores: dict[str, float]
    content_hash: str


def load_tier0_pack(path: Path | None = None) -> Tier0Pack:
    source = path or (PACK_DIR / "tier0.yaml")
    payload = _load_yaml(source)
    return Tier0Pack(
        version=int(_require(payload, "version", int)),
        pii_patterns=_compiled(payload, "pii_patterns"),
        injection_phrases=_phrases(payload, "injection_phrases"),
        unsafe_phrases=_phrases(payload, "unsafe_phrases"),
        bias_phrases=_phrases(payload, "bias_phrases"),
        scores=_scores(payload, TIER0_SCORE_KEYS),
        content_hash=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
    )


def load_disclosure_pack(path: Path | None = None) -> DisclosurePack:
    source = path or (PACK_DIR / "disclosure.yaml")
    payload = _load_yaml(source)
    regexes = _compiled(payload, "regexes")
    missing = [key for key in DISCLOSURE_REGEX_KEYS if key not in regexes]
    if missing:
        raise ValueError(f"disclosure pack is missing regexes {missing}")
    return DisclosurePack(
        version=int(_require(payload, "version", int)),
        regexes=regexes,
        personal_framing=_phrases(payload, "personal_framing"),
        authorised_framing=_phrases(payload, "authorised_framing"),
        secret_terms=_phrases(payload, "secret_terms"),
        scores=_scores(payload, DISCLOSURE_SCORE_KEYS),
        content_hash=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
    )


def load_tier1_pack(path: Path | None = None) -> Tier1Pack:
    source = path or (PACK_DIR / "tier1.yaml")
    payload = _load_yaml(source)
    return Tier1Pack(
        version=int(_require(payload, "version", int)),
        toxic_words=_phrases(payload, "toxic_words"),
        bias_words=_phrases(payload, "bias_words"),
        exfil_words=_phrases(payload, "exfil_words"),
        scores=_scores(payload, TIER1_SCORE_KEYS),
        shape=_shape(payload, TIER1_SHAPE_KEYS),
        content_hash=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
    )


def load_tier2_pack(path: Path | None = None) -> Tier2Pack:
    source = path or (PACK_DIR / "tier2.yaml")
    payload = _load_yaml(source)
    raw = _require(payload, "markers", dict)
    missing = [key for key in TIER2_MARKER_KEYS if key not in raw]
    if missing:
        raise ValueError(f"tier 2 pack is missing markers {missing}")
    return Tier2Pack(
        version=int(_require(payload, "version", int)),
        markers={key: _phrases(raw, key) for key in TIER2_MARKER_KEYS},
        scores=_scores(payload, TIER2_SCORE_KEYS),
        content_hash=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
    )


@lru_cache(maxsize=1)
def default_tier0_pack() -> Tier0Pack:
    """The shipped pack, loaded once. Detectors take a pack, so tests can pass their own."""
    return load_tier0_pack()


@lru_cache(maxsize=1)
def default_disclosure_pack() -> DisclosurePack:
    return load_disclosure_pack()


@lru_cache(maxsize=1)
def default_tier1_pack() -> Tier1Pack:
    return load_tier1_pack()


@lru_cache(maxsize=1)
def default_tier2_pack() -> Tier2Pack:
    return load_tier2_pack()


@lru_cache(maxsize=1)
def pattern_pack_hash() -> str:
    """One hash over both packs, for stamping on a decision or a learned artifact.

    Truncated to sixteen hex characters. That is 64 bits against a handful of packs, so a
    collision is not a practical concern, and it stays readable in a trace and a filename.
    """
    combined = "".join(
        pack.content_hash
        for pack in (
            default_tier0_pack(),
            default_disclosure_pack(),
            default_tier1_pack(),
            default_tier2_pack(),
        )
    )
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
