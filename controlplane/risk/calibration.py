from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IsotonicCalibrator:
    """Map ranked scores to probabilities with pair-adjacent violators."""

    upper_bounds: tuple[float, ...]
    probabilities: tuple[float, ...]

    @classmethod
    def fit(
        cls,
        scores: list[float],
        labels: list[bool],
        weights: list[float] | None = None,
    ) -> IsotonicCalibrator:
        """Fit a monotone score-to-probability map, optionally on a weighted sample.

        `weights` exists because labels do not arrive as a random sample of traffic. A
        reviewer only ever sees rows the system raised, plus a fixed-rate audit of rows it
        released, so the labelled set is enriched for harm — measured on this corpus,
        36.3% against the 18.4% actually present. Fitting that unweighted produced a map
        with ECE 0.128 where the corpus fit reaches 0.008 to 0.043. A weight of `1/p`,
        where `p` is a row's known probability of being reviewed, recovers the population
        the map is meant to price.

        Weights only change what a block's mean is averaged over; the pooling rule and
        every guarantee below it are untouched. Omitting them leaves the offline path
        exactly as it was.
        """
        if len(scores) != len(labels) or not scores:
            raise ValueError("scores and labels must be non-empty and equally sized")
        if weights is None:
            weights = [1.0] * len(scores)
        elif len(weights) != len(scores):
            raise ValueError("weights must be the same length as scores")
        elif any(weight <= 0.0 for weight in weights):
            raise ValueError("weights must be positive")
        # Tied scores must enter as ONE block. Feeding them in one row at a time leaves
        # equal-x blocks that pool-adjacent-violators will not merge — a run of negatives
        # (mean 0) followed by positives (mean 1) is not a violation — and `predict` then
        # returns the first block whose upper bound covers the score, which is the
        # zero-probability one. Any detector emitting discrete or repeated scores had its
        # signal destroyed: a synthetic detector with raw AUC 0.9893 calibrated to 0.5000.
        totals: dict[float, list[float]] = {}
        for score, label, weight in zip(scores, labels, weights, strict=True):
            bucket = totals.setdefault(score, [0.0, 0.0])
            bucket[0] += float(label) * weight
            bucket[1] += weight

        blocks: list[list[float]] = []
        for score in sorted(totals):
            positives, count = totals[score]
            blocks.append([score, score, positives, count])
            while len(blocks) >= 2 and _mean(blocks[-2]) > _mean(blocks[-1]):
                right = blocks.pop()
                left = blocks.pop()
                blocks.append([left[0], right[1], left[2] + right[2], left[3] + right[3]])
        # Two knots per block -- its lower and upper bound, both carrying the block mean --
        # so that `predict` stays flat inside a block and ramps between blocks.
        knots: list[tuple[float, float]] = []
        for block in blocks:
            mean = _mean(block)
            knots.append((block[0], mean))
            if block[1] > block[0]:
                knots.append((block[1], mean))
        return cls(
            upper_bounds=tuple(point[0] for point in knots),
            probabilities=tuple(point[1] for point in knots),
        )

    def predict(self, score: float) -> float:
        """Piecewise-linear between block boundaries, not piecewise-constant.

        Returning the block mean for everything inside a block throws away the ordering the
        detector produced. It matters because most blocks are singletons whose mean is
        exactly 0.0 or 1.0 -- with 95 positives in a 331-row fitting fold, isotonic
        regression has nothing else to say -- so a piecewise-constant map collapsed 977
        OR-Bench rows onto **five** distinct scores. Ranking AUC fell 0.8053 to 0.7819, and,
        worse, the operating point stopped being tunable at all: the false-positive rate
        jumped from 0.195 straight to 1.000 with nothing in between, because there was no
        threshold that could sit inside the gap.

        Interpolating between knots keeps every guarantee that matters -- the map is still
        monotone, still bounded by the fitted extremes, and still exactly the block mean at
        each block boundary -- while preserving the order of scores the calibration data
        could not itself separate.
        """
        bounds = self.upper_bounds
        if score <= bounds[0]:
            return self.probabilities[0]
        if score >= bounds[-1]:
            return self.probabilities[-1]
        for index in range(1, len(bounds)):
            if score <= bounds[index]:
                left, right = bounds[index - 1], bounds[index]
                low, high = self.probabilities[index - 1], self.probabilities[index]
                if right <= left:
                    return high
                return low + (high - low) * (score - left) / (right - left)
        return self.probabilities[-1]


def _mean(block: list[float]) -> float:
    return block[2] / block[3]


def expected_calibration_error(
    probabilities: list[float],
    labels: list[bool],
    bins: int = 10,
    weights: list[float] | None = None,
) -> float:
    """Mean gap between predicted probability and observed frequency, by bin.

    `weights` matters for the same reason it matters in `fit`: measured on a sample that
    over-represents harm, a map that is correctly calibrated for traffic looks badly
    calibrated, because every bin's observed frequency is inflated. Weighting the fit but
    not the measurement was worth 0.13 of apparent error on this corpus against the 0.008
    to 0.043 the same map scores on the traffic it actually serves.
    """
    if len(probabilities) != len(labels) or not probabilities:
        raise ValueError("probabilities and labels must be non-empty and equally sized")
    if weights is None:
        weights = [1.0] * len(probabilities)
    elif len(weights) != len(probabilities):
        raise ValueError("weights must be the same length as probabilities")
    total = sum(weights)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        members = [
            (probability, label, weight)
            for probability, label, weight in zip(probabilities, labels, weights, strict=True)
            if lower <= probability < upper or (index == bins - 1 and probability == 1.0)
        ]
        mass = sum(item[2] for item in members)
        if mass:
            confidence = sum(item[0] * item[2] for item in members) / mass
            accuracy = sum(item[1] * item[2] for item in members) / mass
            error += mass / total * abs(confidence - accuracy)
    return error
