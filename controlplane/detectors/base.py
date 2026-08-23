from __future__ import annotations

from abc import ABC, abstractmethod

from controlplane.models import DetectorSignal, Interaction


class Detector(ABC):
    """Define the third-party-style detector adapter contract."""

    name: str
    tier: int
    version: str

    @abstractmethod
    def run(self, interaction: Interaction) -> DetectorSignal:
        raise NotImplementedError
