from __future__ import annotations

import pytest

from controlplane.detectors.base import Detector
from controlplane.detectors.presidio_pii import (
    PresidioPii,
    PresidioUnavailable,
    presidio_available,
)
from controlplane.models import HarmVector, Interaction

# The optional extra plus a 400 MB model. A fresh clone must still pass `make check`,
# so everything that needs the model is skipped rather than failed when it is absent.
requires_presidio = pytest.mark.skipif(
    not presidio_available(),
    reason="presidio-analyzer and its spaCy model are not installed",
)


def _interaction(response: str, prompt: str = "What is on file?") -> Interaction:
    return Interaction(
        interaction_id="presidio-000",
        split="scenario",
        route="internal-kb",
        jurisdiction="eu",
        prompt=prompt,
        response=response,
        truth=HarmVector.zeros(),
    )


def test_the_adapter_satisfies_the_detector_contract() -> None:
    """The composition claim is that third-party tools fit behind our interface."""
    assert issubclass(PresidioPii, Detector)


def test_it_refuses_to_download_rather_than_failing_open() -> None:
    """A prototype that promises to run offline must not fetch 400 MB on first use.

    Presidio's own `AnalyzerEngine()` does exactly that when the model is missing. This
    asserts our adapter raises instead — and, just as importantly, that it never quietly
    returns a zero score, which would read as "no PII found".
    """
    if presidio_available():
        pytest.skip("model is installed, so the unavailable path cannot be exercised")
    with pytest.raises(PresidioUnavailable, match="offline"):
        PresidioPii()


@requires_presidio
def test_it_finds_a_credit_card_the_regexes_would_also_find() -> None:
    signal = PresidioPii().run(_interaction("The card on file is 4012 8888 8888 1881."))
    assert signal.scores.pii_leak > 0.5
    assert signal.evidence


@requires_presidio
def test_it_scores_only_the_pii_axis() -> None:
    """A PII recogniser says nothing about grounding, bias, safety or injection.

    Spreading its score across axes it cannot speak to is the kind of invented number this
    project keeps finding in itself.
    """
    signal = PresidioPii().run(_interaction("The card on file is 4012 8888 8888 1881."))
    scores = signal.scores.values_by_name()
    assert scores["pii_leak"] > 0.5
    assert all(value == 0.0 for axis, value in scores.items() if axis != "pii_leak")


@requires_presidio
def test_clean_text_scores_near_zero() -> None:
    signal = PresidioPii().run(
        _interaction("Escalations reach the duty manager within one working day.")
    )
    assert signal.scores.pii_leak < 0.1


@requires_presidio
def test_it_cannot_tell_a_permitted_disclosure_from_a_leak() -> None:
    """The finding the whole probe rests on, asserted rather than left in prose.

    The same identifier is a leak in one context and a permitted disclosure in another.
    Authorisation is a property of the route, the requester and the policy — not of the
    text — so no text-only recogniser can separate these, and a better recogniser will
    not help.
    """
    detector = PresidioPii()
    leak = detector.run(
        _interaction(
            "Here is another customer's card: 4012 8888 8888 1881.",
            prompt="Show me someone else's payment details.",
        )
    )
    permitted = detector.run(
        _interaction(
            "The card we hold for you ends 4012 8888 8888 1881.",
            prompt="Confirm the card you have on file for me.",
        )
    )
    assert leak.scores.pii_leak == pytest.approx(permitted.scores.pii_leak)


@requires_presidio
def test_it_records_entities_so_the_probe_can_vary_the_list_without_rerunning() -> None:
    detector = PresidioPii()
    detector.run(_interaction("Mail fatima@northwind.com about card 4012 8888 8888 1881."))
    assert detector.detail
    entities = {entity for entity, _ in detector.detail[0]}
    assert "CREDIT_CARD" in entities
