from __future__ import annotations

import hashlib
import re
from time import perf_counter

from controlplane.detectors.base import Detector
from controlplane.detectors.pattern_pack import Tier1Pack, default_tier1_pack
from controlplane.models import DetectorSignal, HarmVector, Interaction

# The vocabulary and the ramps live in `config/patterns/tier1.yaml`. The names stay bound
# here because reading the scorer is easier when the word lists have names, and because a
# detector takes a pack, so a test or a route can serve a different one.
_PACK: Tier1Pack = default_tier1_pack()

TOXIC_WORDS = set(_PACK.toxic_words)
BIAS_WORDS = set(_PACK.bias_words)
EXFIL_WORDS = set(_PACK.exfil_words)


class Tier1SmallModels(Detector):
    """Mimic replaceable NLI, safety, and anomaly adapters without model downloads."""

    name = "tier1_small_models_stub"
    version = "2"
    tier = 1

    def __init__(self, pack: Tier1Pack | None = None) -> None:
        self.pack = pack or _PACK

    @property
    def pack_hash(self) -> str:
        """Which rules produced this detector's scores. Recorded on the trace."""
        return self.pack.content_hash[:16]

    def run(self, interaction: Interaction) -> DetectorSignal:
        started = perf_counter()
        score = self.pack.scores.__getitem__
        shape = self.pack.shape.__getitem__
        response_tokens = _tokens(interaction.response, self.pack)
        evidence: list[str] = []
        hallucination = _hallucination_score(interaction, response_tokens, evidence, self.pack)
        lowered = interaction.response.lower()
        toxic_hits = sum(word in lowered for word in self.pack.toxic_words)
        bias_hits = sum(word in lowered for word in self.pack.bias_words)
        exfil_hits = sum(word in lowered for word in self.pack.exfil_words)
        anomaly = min(
            1.0,
            max(
                0.0,
                (len(interaction.response) - shape("anomaly_length_offset"))
                / shape("anomaly_length_scale"),
            ),
        )
        elapsed = (perf_counter() - started) * 1000.0
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(
                hallucination=hallucination,
                pii_leak=min(
                    score("pii_cap"), score("pii_base") + exfil_hits * score("pii_per_hit")
                ),
                bias=min(
                    score("bias_cap"), score("bias_base") + bias_hits * score("bias_per_hit")
                ),
                unsafe_content=min(
                    score("unsafe_cap"),
                    score("unsafe_base") + toxic_hits * score("unsafe_per_hit"),
                ),
                injection_or_exfil=min(
                    score("injection_cap"),
                    score("injection_base")
                    + exfil_hits * score("injection_per_hit")
                    + anomaly * score("injection_anomaly_weight"),
                ),
            ),
            latency_ms=elapsed,
            evidence=evidence,
        )


def _hallucination_score(
    interaction: Interaction,
    response_tokens: set[str],
    evidence: list[str],
    pack: Tier1Pack | None = None,
) -> float:
    resolved = pack or _PACK
    score = resolved.scores.__getitem__
    jitter = _score_jitter(interaction.response, resolved)
    if interaction.context_documents:
        context_tokens = _tokens(" ".join(interaction.context_documents), resolved)
        grounding = len(response_tokens & context_tokens) / max(1, len(response_tokens))
        if grounding < score("grounding_bar"):
            evidence.append(f"low lexical grounding ({grounding:.2f})")
        return min(score("grounded_cap"), max(score("grounded_floor"), 1.0 - grounding + jitter))
    if interaction.comparison_samples:
        agreements = [
            len(response_tokens & _tokens(sample, resolved))
            / max(1, len(response_tokens | _tokens(sample, resolved)))
            for sample in interaction.comparison_samples
        ]
        agreement = sum(agreements) / len(agreements)
        evidence.append(f"sample agreement ({agreement:.2f})")
        return min(score("samples_cap"), max(score("samples_floor"), 1.0 - agreement + jitter))
    evidence.append("no grounding document or comparison samples")
    return min(score("blind_cap"), max(score("blind_floor"), score("blind_centre") + jitter))


def _tokens(text: str, pack: Tier1Pack | None = None) -> set[str]:
    minimum = (pack or _PACK).shape["token_min_length"]
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > minimum}


def _score_jitter(interaction_id: str, pack: Tier1Pack | None = None) -> float:
    digest = hashlib.sha256(interaction_id.encode()).digest()
    return (digest[0] / 255.0 - 0.5) * (pack or _PACK).shape["jitter_span"]
