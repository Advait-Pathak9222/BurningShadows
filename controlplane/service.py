from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from controlplane.detectors import Tier0Rules, Tier1SmallModels, Tier2Judge
from controlplane.economics import CostModel, allocate_verification
from controlplane.effects import gate_effects
from controlplane.guarantees import ConformalCalibration, learn_then_test
from controlplane.ledger import LedgerStore
from controlplane.models import (
    DecisionTrace,
    DetectionBundle,
    HarmVector,
    Interaction,
    PreflightDecision,
)
from controlplane.policy import PolicyStore
from controlplane.risk import IsotonicCalibrator, combine_signals, infer_evidence_regime


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @property
    def policy_dir(self) -> Path:
        return self.root / "config" / "policies"

    @property
    def economics(self) -> Path:
        return self.root / "config" / "economics.yaml"


class AssessmentEngine:
    """Run the input/output-only verification path from detectors to ledger."""

    def __init__(
        self,
        root: Path,
        *,
        ledger_path: Path | None = None,
        conformal_thresholds: dict[str, float] | None = None,
    ) -> None:
        paths = RuntimePaths(root)
        self.policy_store = PolicyStore(paths.policy_dir)
        self.cost_model = CostModel(paths.economics)
        self.tier0 = Tier0Rules()
        self.tier1 = Tier1SmallModels()
        self.tier2 = Tier2Judge()
        self.ledger = LedgerStore(ledger_path) if ledger_path is not None else None
        self.calibrators: dict[str, dict[str, IsotonicCalibrator]] = {}
        self.conformal_thresholds = conformal_thresholds or {
            "support-assistant": 0.55,
            "internal-kb": 0.58,
            "finops-agent": 0.48,
        }

    def detect(self, interaction: Interaction, include_tier2: bool = False) -> DetectionBundle:
        bundle = self._raw_detect(interaction, include_tier2)
        route_calibrators = self.calibrators.get(interaction.route)
        if route_calibrators is None:
            return bundle
        calibrated = {
            axis: route_calibrators[axis].predict(score)
            for axis, score in bundle.harm.values_by_name().items()
        }
        return bundle.model_copy(update={"harm": bundle.harm.model_validate(calibrated)})

    def preflight(self, route: str, jurisdiction: str, prompt: str) -> PreflightDecision:
        policy = self.policy_store.resolve(route, jurisdiction)
        interaction = Interaction(
            interaction_id="preflight",
            split="scenario",
            route=route,
            jurisdiction=jurisdiction,
            prompt=prompt,
            response="",
            truth=HarmVector.zeros(),
        )
        signal = self.tier0.run(interaction)
        return PreflightDecision(
            allowed=signal.scores.injection_or_exfil < 0.70,
            reasons=signal.evidence,
            prompt_risk=signal.scores,
            policy_version=policy.policy_version,
            policy_hash=policy.policy_hash,
            latency_ms=signal.latency_ms,
        )

    def _raw_detect(self, interaction: Interaction, include_tier2: bool = False) -> DetectionBundle:
        signals = [self.tier0.run(interaction), self.tier1.run(interaction)]
        if include_tier2:
            signals.append(self.tier2.run(interaction))
        return combine_signals(signals, infer_evidence_regime(interaction))

    def assess(self, interaction: Interaction, shadow_price: float = 0.0) -> DecisionTrace:
        policy = self.policy_store.resolve(interaction.route, interaction.jurisdiction)
        threshold = self.conformal_thresholds[interaction.route]
        bundle = self.detect(interaction)
        trace = allocate_verification(
            interaction_id=interaction.interaction_id,
            bundle=bundle,
            policy=policy,
            tiers=self.cost_model.tiers(policy, interaction.tool_calls),
            shadow_price=shadow_price,
            conformal_threshold=threshold,
            tool_calls=interaction.tool_calls,
        )
        if trace.selected_tier == 2:
            bundle = self.detect(interaction, include_tier2=True)
            trace = allocate_verification(
                interaction_id=interaction.interaction_id,
                bundle=bundle,
                policy=policy,
                tiers=self.cost_model.tiers(policy, interaction.tool_calls),
                shadow_price=shadow_price,
                conformal_threshold=threshold,
                tool_calls=interaction.tool_calls,
            )

        actions = gate_effects(interaction.tool_calls, trace.verdict, policy)
        trace = trace.model_copy(update={"effect_actions": actions})
        if self.ledger is not None:
            self.ledger.append(trace)
        return trace

    def calibrate(self, interactions: list[Interaction]) -> dict[str, ConformalCalibration]:
        self.calibrators = self._fit_calibrators(interactions)
        calibrations: dict[str, ConformalCalibration] = {}
        for route in self.conformal_thresholds:
            route_items = [item for item in interactions if item.route == route]
            scores = [self.detect(item).harm.maximum() for item in route_items]
            labels = [item.truth.has_harm() for item in route_items]
            policy = self.policy_store.resolve(route, route_items[0].jurisdiction)
            calibrations[route] = learn_then_test(
                route=route,
                scores=scores,
                harmed=labels,
                alpha=policy.alpha,
                delta=policy.delta,
            )
        self.conformal_thresholds = {
            route: calibration.threshold for route, calibration in calibrations.items()
        }
        return calibrations

    def _fit_calibrators(
        self, interactions: list[Interaction]
    ) -> dict[str, dict[str, IsotonicCalibrator]]:
        fitted: dict[str, dict[str, IsotonicCalibrator]] = {}
        for route in self.conformal_thresholds:
            route_items = [item for item in interactions if item.route == route]
            raw = [self._raw_detect(item).harm for item in route_items]
            fitted[route] = {
                axis: IsotonicCalibrator.fit(
                    [harm.values_by_name()[axis] for harm in raw],
                    [item.truth.values_by_name()[axis] >= 0.5 for item in route_items],
                )
                for axis in raw[0].values_by_name()
            }
        return fitted
