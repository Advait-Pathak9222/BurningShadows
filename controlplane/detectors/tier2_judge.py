from __future__ import annotations

from time import perf_counter

from controlplane.detectors.base import Detector
from controlplane.detectors.pattern_pack import Tier2Pack, default_tier2_pack
from controlplane.models import DetectorSignal, HarmVector, Interaction

# The markers and scores live in `config/patterns/tier2.yaml`. This stub exists so `make demo`
# runs from a clean clone with no key, no network and no local model, and because every
# committed number was produced against it. The real judge is `ollama_judge.py`, selected with
# `tier2.provider: ollama` in `config/judge.yaml`.
_PACK: Tier2Pack = default_tier2_pack()


class Tier2Judge(Detector):
    """Provide a deterministic stand-in for an optional black-box LLM judge."""

    name = "tier2_llm_judge_stub"
    version = "2"
    tier = 2

    def __init__(self, pack: Tier2Pack | None = None) -> None:
        self.pack = pack or _PACK

    @property
    def pack_hash(self) -> str:
        """Which rules produced this detector's scores. Recorded on the trace."""
        return self.pack.content_hash[:16]

    def run(self, interaction: Interaction) -> DetectorSignal:
        started = perf_counter()
        text = interaction.response.lower()
        score = self.pack.scores.__getitem__

        def hit(group: str) -> bool:
            return any(marker in text for marker in self.pack.markers[group])

        # An unsupported claim is only unsupported when there was nothing to support it with.
        unsupported = hit("unsupported") and not interaction.context_documents
        elapsed = (perf_counter() - started) * 1000.0
        evidence = ["deterministic judge stub; replace through the Detector adapter"]
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(
                hallucination=score(
                    "hallucination_hit" if unsupported else "hallucination_clean"
                ),
                pii_leak=score("pii_hit" if hit("privacy") else "pii_clean"),
                bias=score("bias_hit" if hit("discriminatory") else "bias_clean"),
                unsafe_content=score("unsafe_hit" if hit("unsafe") else "unsafe_clean"),
                injection_or_exfil=score(
                    "injection_hit" if hit("injection") else "injection_clean"
                ),
            ),
            latency_ms=elapsed,
            evidence=evidence,
        )
