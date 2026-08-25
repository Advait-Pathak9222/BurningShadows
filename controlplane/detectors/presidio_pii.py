"""Microsoft Presidio behind the `Detector` interface.

"We compose with existing safety products rather than replacing them" is our answer to the
"you are just a router" objection, and until now `presidio-analyzer` was declared in
`pyproject.toml` and imported nowhere. That made the claim positioning with nothing behind
it. This is the code.

**It is optional and it never runs on the demo path.** Two reasons, and the second is the
one that matters:

1. It is a 400 MB spaCy model and a heavy dependency tree. The competition prototype
   promises to run with no API key, no GPU and no network.
2. Presidio's default `AnalyzerEngine()` **silently downloads that model over the network
   on first use** if it is missing. A system that claims to be offline cannot have a code
   path that quietly fetches 400 MB. So this adapter checks for the model first and raises
   with instructions rather than letting the download happen.

Install with `pip install -e ".[models]"` and then
`python -m spacy download en_core_web_lg`.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from controlplane.detectors.base import Detector
from controlplane.models import DetectorSignal, HarmVector, Interaction

SPACY_MODEL = "en_core_web_lg"
# Entity types that mean a person is identifiable. Presidio also returns URL, DATE_TIME and
# NRP, which are not disclosures on their own and would flood the score with false positives.
PII_ENTITIES = (
    "CREDIT_CARD",
    "EMAIL_ADDRESS",
    "IBAN_CODE",
    "IP_ADDRESS",
    "PHONE_NUMBER",
    "US_BANK_NUMBER",
    "US_SSN",
    "PERSON",
)


class PresidioUnavailable(RuntimeError):
    """Raised instead of triggering a 400 MB download or returning a silent zero."""


def presidio_available() -> bool:
    """True when both the package and its model are present, without downloading either."""
    try:
        import spacy
        from presidio_analyzer import AnalyzerEngine  # noqa: F401
    except ImportError:
        return False
    return spacy.util.is_package(SPACY_MODEL)


class PresidioPii(Detector):
    """Score PII disclosure with Presidio rather than our own regexes.

    Tier 0, because it is a pattern-and-NER recogniser rather than a model that reasons.
    It replaces nothing: the comparison in `docs/results/pii.md` is what decides whether it
    earns a place, and it is reported whichever way it goes.
    """

    name = "presidio_pii"
    version = "2.2"
    tier = 0

    def __init__(self, *, score_floor: float = 0.4) -> None:
        if not presidio_available():
            raise PresidioUnavailable(
                "presidio-analyzer and its spaCy model are required. Install with "
                f'`pip install -e ".[models]"` then `python -m spacy download {SPACY_MODEL}`. '
                "This adapter refuses to download the model itself: it is 400 MB and the "
                "prototype promises to run offline."
            )
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
            }
        )
        self._engine: Any = AnalyzerEngine(nlp_engine=provider.create_engine())
        self._score_floor = score_floor
        # Every (entity, score) this adapter has seen, in call order. The PII probe
        # uses it to vary the entity list without paying for another full pass.
        self.detail: list[list[tuple[str, float]]] = []

    def run(self, interaction: Interaction) -> DetectorSignal:
        started = perf_counter()
        combined = f"{interaction.prompt}\n{interaction.response}"
        results = self._engine.analyze(
            text=combined, language="en", entities=list(PII_ENTITIES)
        )
        kept = [result for result in results if result.score >= self._score_floor]
        self.detail.append([(r.entity_type, float(r.score)) for r in kept])
        score = max((float(result.score) for result in kept), default=0.005)
        evidence = [
            f"{result.entity_type} at {result.start}:{result.end} ({result.score:.2f})"
            for result in sorted(kept, key=lambda item: -item.score)[:5]
        ]
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            # Only the PII axis. Presidio does not speak to grounding, bias, unsafe content
            # or injection, and inventing scores for those from a PII recogniser would be
            # exactly the sort of thing this project keeps catching in itself.
            scores=HarmVector(
                hallucination=0.0,
                pii_leak=score,
                bias=0.0,
                unsafe_content=0.0,
                injection_or_exfil=0.0,
            ),
            latency_ms=(perf_counter() - started) * 1000.0,
            evidence=evidence,
        )
