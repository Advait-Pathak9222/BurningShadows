from __future__ import annotations

import re
from time import perf_counter

from controlplane.detectors.base import Detector
from controlplane.detectors.disclosure import score_disclosure
from controlplane.detectors.pattern_pack import Tier0Pack, default_tier0_pack
from controlplane.models import DetectorSignal, HarmVector, Interaction

# Tier 0's vocabulary and its axis scores live in `config/patterns/tier0.yaml`, not here, so
# adding an attack phrase is a data edit rather than a source edit and a redeploy. The names
# stay bound at module level because `eval/pii_probe.py` imports `PII_PATTERNS` directly.
_PACK: Tier0Pack = default_tier0_pack()

PII_PATTERNS = _PACK.pii_patterns
INJECTION_PHRASES = _PACK.injection_phrases
UNSAFE_PHRASES = _PACK.unsafe_phrases
BIAS_PHRASES = _PACK.bias_phrases


class Tier0Rules(Detector):
    name = "tier0_rules"
    version = "2"
    tier = 0

    def __init__(self, pack: Tier0Pack | None = None) -> None:
        self.pack = pack or _PACK

    @property
    def pack_hash(self) -> str:
        """Which rules produced this detector's scores. Recorded on the trace."""
        return self.pack.content_hash[:16]

    def run(self, interaction: Interaction) -> DetectorSignal:
        started = perf_counter()
        combined = f"{interaction.prompt}\n{interaction.response}"
        lowered = combined.lower()
        evidence: list[str] = []

        # Shape alone cannot separate a leak from a permitted disclosure here: a perfect
        # shape detector tops out at AUC 0.587 on this corpus. The score comes from whether
        # the disclosure is grounded in the supplied source. See detectors/disclosure.py.
        pii_score, pii_evidence = score_disclosure(
            interaction.response, interaction.context_documents
        )
        evidence.extend(pii_evidence)
        injection_hits = [phrase for phrase in self.pack.injection_phrases if phrase in lowered]
        if injection_hits:
            evidence.append(f"injection phrase: {injection_hits[0]}")
        unsafe_hits = [phrase for phrase in self.pack.unsafe_phrases if phrase in lowered]
        bias_hits = [phrase for phrase in self.pack.bias_phrases if phrase in lowered]

        numeric_mismatch = _numeric_mismatch(interaction.response, interaction.context_documents)
        if numeric_mismatch:
            evidence.append("response number is absent from supplied context")
        score = self.pack.scores.__getitem__
        elapsed = (perf_counter() - started) * 1000.0
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(
                hallucination=score(
                    "hallucination_numeric_mismatch" if numeric_mismatch
                    else "hallucination_clean"
                ),
                pii_leak=pii_score,
                bias=score("bias_hit" if bias_hits else "bias_clean"),
                unsafe_content=score("unsafe_hit" if unsafe_hits else "unsafe_clean"),
                injection_or_exfil=(
                    min(
                        score("injection_cap"),
                        score("injection_base") + score("injection_per_hit")
                        * len(injection_hits),
                    )
                    if injection_hits
                    else score("injection_clean")
                ),
            ),
            latency_ms=elapsed,
            evidence=evidence,
        )


def _numeric_mismatch(response: str, context_documents: list[str]) -> bool:
    if not context_documents:
        return False
    response_numbers = set(re.findall(r"(?<!\w)(?:[$₹]\s*)?\d[\d,.]*(?!\w)", response))
    if not response_numbers:
        return False
    context = " ".join(context_documents)
    return any(number not in context for number in response_numbers)
