from __future__ import annotations

import hashlib
import re
from time import perf_counter

from controlplane.detectors.base import Detector
from controlplane.models import DetectorSignal, HarmVector, Interaction

TOXIC_WORDS = {"idiot", "worthless", "hate", "inferior", "violent"}
BIAS_WORDS = {"race", "gender", "women", "men", "caste", "religion", "elderly"}
EXFIL_WORDS = {"secret", "system prompt", "api key", "credential", "private database"}


class Tier1SmallModels(Detector):
    """Mimic replaceable NLI, safety, and anomaly adapters without model downloads."""

    name = "tier1_small_models_stub"
    version = "1"
    tier = 1

    def run(self, interaction: Interaction) -> DetectorSignal:
        started = perf_counter()
        response_tokens = _tokens(interaction.response)
        evidence: list[str] = []
        hallucination = _hallucination_score(interaction, response_tokens, evidence)
        lowered = interaction.response.lower()
        toxic_hits = sum(word in lowered for word in TOXIC_WORDS)
        bias_hits = sum(word in lowered for word in BIAS_WORDS)
        exfil_hits = sum(word in lowered for word in EXFIL_WORDS)
        anomaly = min(1.0, max(0.0, (len(interaction.response) - 500) / 1000))
        elapsed = (perf_counter() - started) * 1000.0
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(
                hallucination=hallucination,
                pii_leak=min(0.85, 0.005 + exfil_hits * 0.30),
                bias=min(0.93, 0.01 + bias_hits * 0.24),
                unsafe_content=min(0.95, 0.005 + toxic_hits * 0.32),
                injection_or_exfil=min(0.92, 0.01 + exfil_hits * 0.30 + anomaly * 0.2),
            ),
            latency_ms=elapsed,
            evidence=evidence,
        )


def _hallucination_score(
    interaction: Interaction, response_tokens: set[str], evidence: list[str]
) -> float:
    jitter = _score_jitter(interaction.response)
    if interaction.context_documents:
        context_tokens = _tokens(" ".join(interaction.context_documents))
        grounding = len(response_tokens & context_tokens) / max(1, len(response_tokens))
        if grounding < 0.45:
            evidence.append(f"low lexical grounding ({grounding:.2f})")
        return min(0.96, max(0.04, 1.0 - grounding + jitter))
    if interaction.comparison_samples:
        agreements = [
            len(response_tokens & _tokens(sample)) / max(1, len(response_tokens | _tokens(sample)))
            for sample in interaction.comparison_samples
        ]
        agreement = sum(agreements) / len(agreements)
        evidence.append(f"sample agreement ({agreement:.2f})")
        return min(0.90, max(0.12, 1.0 - agreement + jitter))
    evidence.append("no grounding document or comparison samples")
    return min(0.85, max(0.25, 0.52 + jitter))


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _score_jitter(interaction_id: str) -> float:
    digest = hashlib.sha256(interaction_id.encode()).digest()
    return (digest[0] / 255.0 - 0.5) * 0.24
