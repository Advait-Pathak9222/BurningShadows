from __future__ import annotations

import re
from time import perf_counter

from controlplane.detectors.base import Detector
from controlplane.models import DetectorSignal, HarmVector, Interaction

PII_PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone": re.compile(r"(?<!\d)(?:\+?\d[\d -]{8,}\d)(?!\d)"),
    "account": re.compile(r"\b(?:account|acct|iban)[\s:#-]*[A-Z0-9-]{6,}\b", re.IGNORECASE),
    "aadhaar": re.compile(r"\b\d{4}[ -]\d{4}[ -]\d{4}\b"),
}
INJECTION_PHRASES = (
    "ignore previous instructions",
    "reveal the system prompt",
    "exfiltrate",
    "developer message",
    "bypass policy",
)
UNSAFE_PHRASES = ("make a bomb", "poison them", "steal credentials", "self-harm instructions")
BIAS_PHRASES = ("women are less", "men are better", "because of their race", "too old to")


class Tier0Rules(Detector):
    name = "tier0_rules"
    tier = 0

    def run(self, interaction: Interaction) -> DetectorSignal:
        started = perf_counter()
        combined = f"{interaction.prompt}\n{interaction.response}"
        lowered = combined.lower()
        evidence: list[str] = []

        pii_matches = [name for name, pattern in PII_PATTERNS.items() if pattern.search(combined)]
        if pii_matches:
            evidence.append(f"PII patterns: {', '.join(pii_matches)}")
        injection_hits = [phrase for phrase in INJECTION_PHRASES if phrase in lowered]
        if injection_hits:
            evidence.append(f"injection phrase: {injection_hits[0]}")
        unsafe_hits = [phrase for phrase in UNSAFE_PHRASES if phrase in lowered]
        bias_hits = [phrase for phrase in BIAS_PHRASES if phrase in lowered]

        numeric_mismatch = _numeric_mismatch(interaction.response, interaction.context_documents)
        if numeric_mismatch:
            evidence.append("response number is absent from supplied context")
        elapsed = (perf_counter() - started) * 1000.0
        return DetectorSignal(
            name=self.name,
            tier=self.tier,
            scores=HarmVector(
                hallucination=0.72 if numeric_mismatch else 0.08,
                pii_leak=(min(0.98, 0.55 + 0.25 * len(pii_matches)) if pii_matches else 0.005),
                bias=0.88 if bias_hits else 0.005,
                unsafe_content=0.92 if unsafe_hits else 0.005,
                injection_or_exfil=(
                    min(0.99, 0.45 + 0.35 * len(injection_hits)) if injection_hits else 0.01
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
