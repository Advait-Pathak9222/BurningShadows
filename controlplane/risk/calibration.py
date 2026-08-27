from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IsotonicCalibrator:
    """Map ranked scores to probabilities with pair-adjacent violators."""

    upper_bounds: tuple[float, ...]
    probabilities: tuple[float, ...]

    @classmethod
    def fit(cls, scores: list[float], labels: list[bool]) -> IsotonicCalibrator:
        if len(scores) != len(labels) or not scores:
            raise ValueError("scores and labels must be non-empty and equally sized")
        # Tied scores must enter as ONE block. Feeding them in one row at a time leaves
        # equal-x blocks that pool-adjacent-violators will not merge — a run of negatives
        # (mean 0) followed by positives (mean 1) is not a violation — and `predict` then
        # returns the first block whose upper bound covers the score, which is the
        # zero-probability one. Any detector emitting discrete or repeated scores had its
        # signal destroyed: a synthetic detector with raw AUC 0.9893 calibrated to 0.5000.
        totals: dict[float, list[float]] = {}
        for score, label in zip(scores, labels, strict=True):
            bucket = totals.setdefault(score, [0.0, 0.0])
            bucket[0] += float(label)
            bucket[1] += 1.0

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
    probabilities: list[float], labels: list[bool], bins: int = 10
) -> float:
    if len(probabilities) != len(labels) or not probabilities:
        raise ValueError("probabilities and labels must be non-empty and equally sized")
    total = len(probabilities)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        members = [
            (probability, label)
            for probability, label in zip(probabilities, labels, strict=True)
            if lower <= probability < upper or (index == bins - 1 and probability == 1.0)
        ]
        if members:
            confidence = sum(item[0] for item in members) / len(members)
            accuracy = sum(item[1] for item in members) / len(members)
            error += len(members) / total * abs(confidence - accuracy)
    return error
