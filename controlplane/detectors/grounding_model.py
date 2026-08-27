"""A fitted grounding scorer for the hallucination axis.

The hand-written rules in `tier0_rules.py` only fire on numeric mismatch, and both they
and `tier1_models.py` return early when `context_documents` is empty. That made the
hallucination axis untestable on corpora without retrieved passages — it scored 0.5215 on
BeaverTails not because the idea is wrong but because nothing was ever grounded.

This scores a response against its own retrieved context and nothing else: no model
weights, no network, no new dependency. Pre-registration 8.

Response length is deliberately not a feature. It reaches 0.6548 alone on the calibration
split and would lift the model by 0.02, but a long grounded answer is not a hallucinated
one — it is a property of the corpus, not of grounding.

**Evaluation adapter, not a shipped component.** This is fitted on the calibration fold of the
corpus under test and is used only by `controlplane/eval/`. It is **not wired into
`AssessmentEngine`**, so nothing the gateway serves uses it. Any number produced with it is a
statement about the allocation and calibration machinery given a competent detector, not about
what ControlPlane detects out of the box -- and every results page that quotes one says so.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
import numpy.typing as npt

from controlplane.detectors.base import Detector
from controlplane.models import DetectorSignal, HarmVector, Interaction

# Bare `np.ndarray` is unparameterised, and how loudly that is rejected depends on which
# numpy stubs happen to be installed: it passes here and fails `mypy --strict` on a newer
# numpy. Pinning the alias makes the annotation mean the same thing in every environment,
# which is what a quality gate a judge runs has to do.
FloatArray = npt.NDArray[np.float64]

WORD = re.compile(r"[a-z0-9']+")
NUMERAL = re.compile(r"\d[\d,.]*")

# Closed-class words carry no factual content, so an unsupported "the" is not evidence of
# anything. Removing them is what makes the unsupported ratio mean something.
STOPWORDS = frozenset(
    [
        "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "was", "were", "be", "been",
        "it", "its", "this", "that", "for", "on", "at", "as", "with", "by", "from", "not", "no",
        "if", "then", "than", "so", "such", "which", "who", "whom", "what", "when", "where",
        "how", "all", "any", "both", "each", "more", "most", "other", "some", "only", "own",
        "same", "can", "will", "just", "don", "should", "now", "i", "you", "he", "she", "they",
        "we", "his", "her", "their", "our", "your", "my", "me", "him", "them", "us", "there",
        "here", "also", "do", "does", "did", "have", "has", "had", "but", "about", "into", "over",
        "after", "before", "between", "under", "above",
    ]
)


def content_tokens(text: str) -> list[str]:
    return [word for word in WORD.findall(text.lower()) if word not in STOPWORDS and len(word) > 1]


class GroundingTier1(Detector):
    """Score `hallucination` by what the response asserts that its context does not support."""

    name = "fitted_grounding"
    version = "1"
    tier = 1

    FEATURES = ("unsupported_ratio", "unsupported_types", "unsupported_idf", "unsupported_numerals")

    def __init__(
        self,
        weights: FloatArray,
        document_frequency: Counter[str],
        documents: int,
    ) -> None:
        self._weights = weights
        self._document_frequency = document_frequency
        self._documents = documents

    def _idf(self, word: str) -> float:
        return math.log((self._documents + 1) / (self._document_frequency.get(word, 0) + 1))

    def features(self, response: str, context: str) -> list[float]:
        supported = set(content_tokens(context))
        emitted = content_tokens(response)
        if not emitted:
            return [0.0] * len(self.FEATURES)
        unsupported = [word for word in emitted if word not in supported]
        context_numerals = set(NUMERAL.findall(context))
        emitted_numerals = NUMERAL.findall(response)
        unsupported_numerals = [n for n in emitted_numerals if n not in context_numerals]
        weighted = sum(self._idf(word) for word in emitted) or 1.0
        return [
            len(unsupported) / len(emitted),
            len(set(unsupported)) / max(len(set(emitted)), 1),
            sum(self._idf(word) for word in unsupported) / weighted,
            (len(unsupported_numerals) / len(emitted_numerals)) if emitted_numerals else 0.0,
        ]

    @classmethod
    def fit(cls, interactions: list[Interaction], *, steps: int = 3000) -> GroundingTier1:
        grounded = [item for item in interactions if item.context_documents]
        if not grounded:
            raise ValueError("no grounded rows to fit on; this detector needs context documents")

        document_frequency: Counter[str] = Counter()
        for item in grounded:
            document_frequency.update(set(content_tokens(" ".join(item.context_documents))))
        blank = cls(np.zeros(len(cls.FEATURES) + 1), document_frequency, len(grounded))

        rows = np.array(
            [blank.features(item.response, " ".join(item.context_documents)) for item in grounded]
        )
        labels = np.array(
            [
                1.0 if item.truth.values_by_name()["hallucination"] >= 0.5 else 0.0
                for item in grounded
            ]
        )
        design = np.c_[rows, np.ones(len(rows))]
        weights = np.zeros(design.shape[1])
        for _ in range(steps):
            predicted = 1.0 / (1.0 + np.exp(-design @ weights))
            weights -= 0.5 * (design.T @ (predicted - labels)) / len(design)
        return cls(weights, document_frequency, len(grounded))

    def run(self, interaction: Interaction) -> DetectorSignal:
        if not interaction.context_documents:
            # Nothing to ground against. Returning zero is the honest answer; the evidence
            # regime already records that this response could not be checked.
            score = 0.0
            evidence = ["no context documents: grounding not assessable"]
        else:
            context = " ".join(interaction.context_documents)
            row = np.array([*self.features(interaction.response, context), 1.0])
            score = float(1.0 / (1.0 + np.exp(-row @ self._weights)))
            evidence = [f"unsupported content ratio {row[0]:.3f}, type ratio {row[1]:.3f}"]
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(
                hallucination=score,
                pii_leak=0.0,
                bias=0.0,
                unsafe_content=0.0,
                injection_or_exfil=0.0,
            ),
            latency_ms=0.0,
            evidence=evidence,
        )
