from __future__ import annotations

from controlplane.models import EvidenceRegime, Interaction


def infer_evidence_regime(interaction: Interaction) -> EvidenceRegime:
    if interaction.context_documents:
        return EvidenceRegime.GROUNDED
    if interaction.comparison_samples:
        return EvidenceRegime.ESTIMABLE
    return EvidenceRegime.UNVERIFIABLE
