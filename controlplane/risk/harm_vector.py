from __future__ import annotations

from controlplane.models import DetectionBundle, DetectorSignal, EvidenceRegime, HarmVector


def combine_signals(
    signals: list[DetectorSignal], evidence_regime: EvidenceRegime
) -> DetectionBundle:
    """Combine detector outputs while preserving every harm axis."""
    if not signals:
        raise ValueError("At least one detector signal is required")
    axes = HarmVector.zeros().values_by_name()
    combined: dict[str, float] = {}
    for axis in axes:
        values = [signal.scores.values_by_name()[axis] for signal in signals]
        strongest = max(values)
        mean = sum(values) / len(values)
        combined[axis] = min(1.0, 0.72 * strongest + 0.28 * mean)

    if evidence_regime == EvidenceRegime.UNVERIFIABLE:
        combined["hallucination"] = max(0.38, combined["hallucination"])
    return DetectionBundle(
        harm=HarmVector(**combined),
        evidence_regime=evidence_regime,
        signals=signals,
        latency_ms=max(signal.latency_ms for signal in signals),
    )
