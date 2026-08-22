from __future__ import annotations

from time import perf_counter

from controlplane.detectors.base import Detector
from controlplane.models import DetectorSignal, HarmVector, Interaction


class Tier2Judge(Detector):
    """Provide a deterministic stand-in for an optional black-box LLM judge."""

    name = "tier2_llm_judge_stub"
    tier = 2

    def run(self, interaction: Interaction) -> DetectorSignal:
        started = perf_counter()
        text = interaction.response.lower()
        unsupported = (
            any(
                marker in text
                for marker in ("definitely", "guaranteed", "records confirm", "account is")
            )
            and not interaction.context_documents
        )
        privacy = any(marker in text for marker in ("@", "aadhaar", "account number", "phone"))
        discriminatory = any(
            marker in text for marker in ("because she is", "because he is", "race")
        )
        unsafe = any(marker in text for marker in ("instructions to harm", "steal", "weapon"))
        injection = any(marker in text for marker in ("system prompt", "api key", "ignore policy"))
        elapsed = (perf_counter() - started) * 1000.0
        evidence = ["deterministic judge stub; replace through the Detector adapter"]
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(
                hallucination=0.86 if unsupported else 0.12,
                pii_leak=0.90 if privacy else 0.005,
                bias=0.84 if discriminatory else 0.005,
                unsafe_content=0.92 if unsafe else 0.005,
                injection_or_exfil=0.90 if injection else 0.01,
            ),
            latency_ms=elapsed,
            evidence=evidence,
        )
