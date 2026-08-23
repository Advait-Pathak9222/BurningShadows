from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from controlplane.effects.classification import classify_effect
from controlplane.models import EffectClass, HarmVector, RoutePolicy, TierEconomics, ToolCall


class CostModel:
    """Estimate consequences, catch rates, verification cost, and delay cost."""

    def __init__(self, config_path: Path) -> None:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Economics config must be a mapping")
        self.config: dict[str, Any] = loaded

    @property
    def controller_learning_rate(self) -> float:
        return float(self.config["controller"]["learning_rate"])

    @property
    def gateway_budget_rate_inr(self) -> float:
        return float(self.config["controller"]["gateway_budget_rate_inr"])

    def tiers(self, policy: RoutePolicy, tool_calls: list[ToolCall]) -> list[TierEconomics]:
        effect_class = self._highest_effect_class(tool_calls)
        delay_rate = float(self.config["delay_cost_per_ms_inr"][effect_class.value])
        tiers: list[TierEconomics] = []
        for raw_tier, values in self.config["tiers"].items():
            tier = int(raw_tier)
            delay_ms = max(0.0, float(values["latency_ms"]) - policy.effect_latency_slo_ms)
            tiers.append(
                TierEconomics(
                    tier=tier,
                    catch_rate=HarmVector(**values["catch_rate"]),
                    verification_cost_inr=float(values["verification_cost_inr"]),
                    delay_cost_inr=delay_ms * delay_rate,
                )
            )
        return sorted(tiers, key=lambda tier: tier.tier)

    @staticmethod
    def _highest_effect_class(tool_calls: list[ToolCall]) -> EffectClass:
        order = {
            EffectClass.READ: 0,
            EffectClass.REVERSIBLE_WRITE: 1,
            EffectClass.EXTERNAL_FACING: 2,
            EffectClass.IRREVERSIBLE_WRITE: 3,
            EffectClass.FINANCIAL: 4,
        }
        classes = [classify_effect(call) for call in tool_calls]
        return max(classes, key=order.__getitem__) if classes else EffectClass.READ
