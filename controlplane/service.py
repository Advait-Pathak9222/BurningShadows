from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from controlplane.detectors import Tier0Rules, Tier1SmallModels, Tier2Judge
from controlplane.economics import CostModel, allocate_verification
from controlplane.economics.allocator import expected_loss_averted_inr
from controlplane.effects import gate_effects
from controlplane.feedback import SessionRiskStore, tightened_threshold
from controlplane.guarantees import ConformalCalibration, learn_then_test
from controlplane.ledger import LedgerStore
from controlplane.models import (
    DecisionTrace,
    DetectionBundle,
    DetectorSignal,
    HarmVector,
    Interaction,
    PreflightDecision,
    RoutePolicy,
    TierEconomics,
)
from controlplane.policy import PolicyStore
from controlplane.risk import IsotonicCalibrator, combine_signals, infer_evidence_regime

# Large enough to price out every discretionary tier, finite so the arithmetic stays real.
_PRICE_OUT_EVERYTHING = 1e12


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
        # No invented defaults. Serving a route before calibrate() has fitted it would
        # price traffic against a made-up threshold, which is what the gateway did.
        self.conformal_thresholds: dict[str, float] = dict(conformal_thresholds or {})
        # Multi-turn risk. Only ever tightens the floor; see feedback/session.py.
        self.sessions = SessionRiskStore()

    def detect(self, interaction: Interaction, include_tier2: bool = False) -> DetectionBundle:
        return self._bundle(interaction, self._signals(interaction, include_tier2))

    def _signals(
        self, interaction: Interaction, include_tier2: bool = False
    ) -> list[DetectorSignal]:
        signals = [self.tier0.run(interaction), self.tier1.run(interaction)]
        if include_tier2:
            signals.append(self.tier2.run(interaction))
        return signals

    def _combine(
        self, interaction: Interaction, signals: list[DetectorSignal]
    ) -> DetectionBundle:
        """Merge detector signals without calibrating them.

        Kept separate from `_calibrate` because the uncalibrated vector is what a future
        refit has to be fitted against: a calibration map is a function of the raw score,
        so storing only the calibrated value leaves nothing to re-derive the map from.
        """
        return combine_signals(signals, infer_evidence_regime(interaction))

    def _calibrate(self, route: str, bundle: DetectionBundle) -> DetectionBundle:
        route_calibrators = self.calibrators.get(route)
        if route_calibrators is None:
            return bundle
        calibrated = {
            axis: route_calibrators[axis].predict(score)
            for axis, score in bundle.harm.values_by_name().items()
        }
        return bundle.model_copy(update={"harm": bundle.harm.model_validate(calibrated)})

    def _bundle(
        self, interaction: Interaction, signals: list[DetectorSignal]
    ) -> DetectionBundle:
        return self._calibrate(interaction.route, self._combine(interaction, signals))

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
        return self._combine(interaction, self._signals(interaction, include_tier2))

    def assess(
        self,
        interaction: Interaction,
        shadow_price: float = 0.0,
        *,
        mandatory_only: bool = False,
        admission_mode: Literal["unbounded", "normal", "degraded"] = "unbounded",
        queue_wait_ms: float = 0.0,
        session_id: str | None = None,
    ) -> DecisionTrace:
        policy = self.policy_store.resolve(interaction.route, interaction.jurisdiction)
        fitted = self._threshold(interaction.route)
        # Risk carried in from earlier turns of this session lowers the bar at which a
        # check becomes mandatory. It never raises it, so the certified per-route bound is
        # never relaxed by conversation history.
        session_risk = self.sessions.risk(session_id)
        threshold = tightened_threshold(fitted, session_risk)
        signals = self._signals(interaction)
        raw = self._combine(interaction, signals)
        bundle = self._calibrate(interaction.route, raw)
        tiers = self.cost_model.tiers(policy, interaction.tool_calls)
        effective_price = shadow_price
        if mandatory_only:
            effective_price = _mandatory_only_price(bundle, policy, tiers, shadow_price)
        trace = allocate_verification(
            interaction_id=interaction.interaction_id,
            bundle=bundle,
            policy=policy,
            tiers=tiers,
            shadow_price=effective_price,
            conformal_threshold=threshold,
            tool_calls=interaction.tool_calls,
            raw_harm=raw.harm,
        )
        if trace.selected_tier == 2:
            # Tier 0 and Tier 1 already ran; escalation adds the judge to their signals
            # instead of recomputing the whole cascade.
            signals = [*signals, self.tier2.run(interaction)]
            raw = self._combine(interaction, signals)
            bundle = self._calibrate(interaction.route, raw)
            reviewed = allocate_verification(
                interaction_id=interaction.interaction_id,
                bundle=bundle,
                policy=policy,
                tiers=tiers,
                shadow_price=effective_price,
                conformal_threshold=threshold,
                tool_calls=interaction.tool_calls,
                raw_harm=raw.harm,
            )
            # Tier 2 has already run and been paid for. The second pass may revise the
            # verdict on better evidence, but it must not report the check as skipped.
            trace = reviewed.model_copy(
                update={
                    "selected_tier": 2,
                    "assurance_spend_inr": trace.assurance_spend_inr,
                    "forced_by_conformal": trace.forced_by_conformal,
                }
            )

        actions = gate_effects(interaction.tool_calls, trace.verdict, policy)
        trace = trace.model_copy(
            update={
                "effect_actions": actions,
                "session_id": session_id,
                "session_risk": session_risk,
                "fitted_conformal_threshold": fitted,
                "degraded": mandatory_only,
                "admission_mode": admission_mode,
                "queue_wait_ms": queue_wait_ms,
                "mandatory_assessment_completed": True,
            }
        )
        # Fold this turn in only after it has been decided, so a turn never raises its own
        # bar and the accumulator reflects what was actually observed.
        self.sessions.observe(session_id, bundle.harm.maximum())
        if self.ledger is not None:
            self.ledger.append(trace)
        return trace

    def floor_spend_inr(self, interactions: list[Interaction]) -> float:
        """What the conformal floor alone obliges over these rows, at any budget.

        This is the assurance bill the guarantee sends whether or not the budget can pay
        it, so it is the *minimum feasible budget*: below it the floor and the budget are
        in direct conflict and the floor wins. Reported rather than enforced, because
        which of the two gives is an operator's decision, not ours.

        Priced at an effectively infinite shadow price so every economic check is priced
        out and only the conformal override survives.
        """
        # Costing the floor is a question, not a decision, so it must not enter the audit
        # chain. Detach the ledger for the duration rather than letting an estimate write
        # records that no served request corresponds to.
        ledger, self.ledger = self.ledger, None
        try:
            return sum(
                self.assess(item, shadow_price=_PRICE_OUT_EVERYTHING, mandatory_only=True)
                .assurance_spend_inr
                for item in interactions
            )
        finally:
            self.ledger = ledger

    def floor_rate_inr(self, interactions: list[Interaction]) -> float:
        """Per-row floor cost, for sizing a `BudgetGovernor` reservation.

        Estimate this on calibration rows, never on the rows being served: a reservation
        informed by the traffic it is rationing is not a prediction.
        """
        if not interactions:
            raise ValueError("floor_rate_inr needs at least one interaction")
        return self.floor_spend_inr(interactions) / len(interactions)

    def _threshold(self, route: str) -> float:
        if route not in self.conformal_thresholds:
            raise RuntimeError(
                f"Route {route!r} has no fitted conformal threshold; call calibrate() first"
            )
        return self.conformal_thresholds[route]

    def calibrate(self, interactions: list[Interaction]) -> dict[str, ConformalCalibration]:
        """Fit the score map and select thresholds on disjoint folds of the calibration split."""
        fitting, selection = _split_folds(interactions)
        self.calibrators = self._fit_calibrators(fitting)
        calibrations: dict[str, ConformalCalibration] = {}
        for route in sorted({item.route for item in interactions}):
            route_items = [item for item in selection if item.route == route]
            if not route_items:
                raise ValueError(f"No selection-fold rows for route {route!r}")
            policy = self.policy_store.resolve(route, route_items[0].jurisdiction)
            calibrations[route] = learn_then_test(
                route=route,
                scores=[self.detect(item).harm.maximum() for item in route_items],
                harmed=[item.truth.has_harm() for item in route_items],
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
        for route in sorted({item.route for item in interactions}):
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


def _split_folds(
    interactions: list[Interaction],
) -> tuple[list[Interaction], list[Interaction]]:
    """Learn-Then-Test is only valid when the score map is fixed before the labels are read.

    Fitting the isotonic maps and selecting thresholds on the same rows made the bound
    optimistic by roughly a factor of nine on finops-agent. The split is keyed off the
    interaction id so both folds are stable across runs and machines.
    """
    fitting: list[Interaction] = []
    selection: list[Interaction] = []
    for item in interactions:
        digest = hashlib.sha256(f"fold:{item.interaction_id}".encode()).digest()
        # The isotonic map converges on less data than the finite-sample test needs,
        # so the selection fold gets the larger share.
        (fitting if digest[0] < 90 else selection).append(item)
    return fitting, selection


def _mandatory_only_price(
    bundle: DetectionBundle,
    policy: RoutePolicy,
    tiers: list[TierEconomics],
    current_price: float,
) -> float:
    """Price out economic choices while leaving the allocator's conformal override intact."""
    cut_lines = []
    for tier in tiers:
        direct_cost = tier.verification_cost_inr + tier.delay_cost_inr
        if direct_cost <= 0.0:
            raise ValueError("Mandatory-only admission requires positive tier costs")
        benefit = expected_loss_averted_inr(bundle, policy, tier)
        cut_lines.append(max(0.0, benefit / direct_cost - 1.0))
    cut_line = max(cut_lines, default=0.0)
    return max(current_price, math.nextafter(cut_line, math.inf))
