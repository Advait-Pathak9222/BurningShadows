"""A per-axis bag-of-words scorer fitted on the calibration fold.

Our hand-written lexical detectors scored AUC 0.4838 on real traffic — chance — and
allocation on a noise signal is untestable. Pre-registration 7 replaces Tier 1 with this:
a multinomial Naive Bayes log-likelihood ratio per harm axis, fitted only on calibration
rows, in numpy, with no new dependency and no network call.

It is deliberately modest. The claim under test is about how a budget is spent, not about
detection quality, and a weak-but-real per-axis signal is exactly what the allocator is
supposed to arbitrate between.

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

from controlplane.detectors.base import Detector
from controlplane.models import HARM_AXES, DetectorSignal, HarmVector, Interaction

TOKEN = re.compile(r"[a-z']+")
VOCABULARY_SIZE = 20_000
SMOOTHING = 0.4


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class FittedBayesTier1(Detector):
    """Score each harm axis by a smoothed log-likelihood ratio over response tokens."""

    name = "fitted_bayes_bow"
    version = "1"
    tier = 1

    def __init__(self, weights: dict[str, dict[str, float]], scale: dict[str, float]) -> None:
        self._weights = weights
        self._scale = scale

    @classmethod
    def fit(cls, interactions: list[Interaction]) -> FittedBayesTier1:
        documents = [
            (tokenize(item.response), item.truth.values_by_name()) for item in interactions
        ]
        # One shared vocabulary keeps the axes comparable and the model small.
        overall: Counter[str] = Counter()
        for tokens, _ in documents:
            overall.update(tokens)
        vocabulary = {word for word, _ in overall.most_common(VOCABULARY_SIZE)}

        weights: dict[str, dict[str, float]] = {}
        scale: dict[str, float] = {}
        for axis in HARM_AXES:
            positive: Counter[str] = Counter()
            negative: Counter[str] = Counter()
            positives = negatives = 0
            for tokens, truth in documents:
                target = positive if truth[axis] >= 0.5 else negative
                if truth[axis] >= 0.5:
                    positives += 1
                else:
                    negatives += 1
                target.update(word for word in tokens if word in vocabulary)
            if positives == 0 or negatives == 0:
                # No signal to learn: an axis with no positive examples must score zero
                # rather than inherit whatever the smoothing prior implies.
                weights[axis] = {}
                scale[axis] = 0.0
                continue
            positive_total = sum(positive.values()) + SMOOTHING * len(vocabulary)
            negative_total = sum(negative.values()) + SMOOTHING * len(vocabulary)
            weights[axis] = {
                word: math.log((positive[word] + SMOOTHING) / positive_total)
                - math.log((negative[word] + SMOOTHING) / negative_total)
                for word in vocabulary
            }
            scale[axis] = 1.0
        return cls(weights, scale)

    def _score(self, axis: str, tokens: list[str]) -> float:
        if not self._scale.get(axis) or not tokens:
            return 0.0
        table = self._weights[axis]
        total = sum(table.get(word, 0.0) for word in tokens)
        # Length-normalised, then squashed. Isotonic calibration downstream only needs a
        # monotone relationship to probability, so the exact squashing constant is free.
        mean = total / len(tokens)
        return 1.0 / (1.0 + math.exp(-mean * 2.0))

    def run(self, interaction: Interaction) -> DetectorSignal:
        tokens = tokenize(interaction.response)
        scores = {axis: self._score(axis, tokens) for axis in HARM_AXES}
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(**scores),
            latency_ms=0.0,
            evidence=[f"bag-of-words log-likelihood ratio over {len(tokens)} tokens"],
        )
