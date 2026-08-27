from __future__ import annotations

import pytest

from controlplane.detectors.grounding_model import GroundingTier1, content_tokens
from controlplane.models import HarmVector, Interaction


def _row(name: str, response: str, context: str | None, hallucinated: bool) -> Interaction:
    return Interaction(
        interaction_id=name,
        split="calibration",
        route="support-assistant",
        jurisdiction="eu",
        prompt="q",
        response=response,
        context_documents=[context] if context else [],
        truth=HarmVector(
            hallucination=1.0 if hallucinated else 0.0,
            pii_leak=0.0,
            bias=0.0,
            unsafe_content=0.0,
            injection_or_exfil=0.0,
        ),
    )


@pytest.fixture
def fitted() -> GroundingTier1:
    rows = []
    for index in range(40):
        rows.append(
            _row(f"ok-{index}", "the renewal fee is 499 rupees", "renewal fee 499 rupees", False)
        )
        rows.append(
            _row(
                f"bad-{index}",
                "the renewal fee is 9999 zorbulon credits",
                "renewal fee 499 rupees",
                True,
            )
        )
    return GroundingTier1.fit(rows, steps=400)


def test_score_is_zero_without_context() -> None:
    """The grounding claim only means something if the score collapses without a source.

    Measured on RAGTruth: withholding the context takes the detector to exactly 0.5000 AUC.
    A detector that still scored without a source would be reading style, not support.
    """
    detector = GroundingTier1.fit(
        [
            _row("a", "supported text here", "supported text here", False),
            _row("b", "unsupported novel wording", "supported text here", True),
        ],
        steps=50,
    )
    signal = detector.run(_row("probe", "anything at all", None, False))
    assert signal.scores.values_by_name()["hallucination"] == 0.0
    assert "not assessable" in signal.evidence[0]


def test_unsupported_content_scores_above_supported_content(fitted: GroundingTier1) -> None:
    supported = fitted.run(
        _row("s", "the renewal fee is 499 rupees", "renewal fee 499 rupees", False)
    )
    invented = fitted.run(
        _row("u", "the renewal fee is 9999 zorbulon credits", "renewal fee 499 rupees", False)
    )
    assert (
        invented.scores.values_by_name()["hallucination"]
        > supported.scores.values_by_name()["hallucination"]
    )


def test_only_the_hallucination_axis_is_written(fitted: GroundingTier1) -> None:
    """This detector grounds text. It must not invent scores on axes it cannot observe."""
    scores = fitted.run(_row("x", "some words", "other words", False)).scores.values_by_name()
    assert scores["pii_leak"] == 0.0
    assert scores["bias"] == 0.0
    assert scores["unsafe_content"] == 0.0
    assert scores["injection_or_exfil"] == 0.0


def test_stopwords_are_dropped_so_unsupported_ratio_means_something() -> None:
    assert content_tokens("the a of and to in is") == []
    assert content_tokens("renewal fee 499") == ["renewal", "fee", "499"]


def test_fitting_without_any_grounded_row_is_refused() -> None:
    with pytest.raises(ValueError, match="context documents"):
        GroundingTier1.fit([_row("n", "text", None, False)])
