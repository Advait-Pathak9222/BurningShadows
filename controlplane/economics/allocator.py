from __future__ import annotations

from controlplane.models import (
    DecisionTrace,
    DetectionBundle,
    EvidenceRegime,
    RoutePolicy,
    TierDecision,
    TierEconomics,
    ToolCall,
    Verdict,
)


def expected_loss_inr(bundle: DetectionBundle, policy: RoutePolicy) -> float:
    """Sum expected consequences across overlapping harm axes."""
    return sum(
        probability * float(policy.consequence_inr[axis])
        for axis, probability in bundle.harm.values_by_name().items()
    )


def expected_loss_averted_inr(
    bundle: DetectionBundle, policy: RoutePolicy, tier: TierEconomics
) -> float:
    return sum(
        probability * float(policy.consequence_inr[axis]) * tier.catch_rate.values_by_name()[axis]
        for axis, probability in bundle.harm.values_by_name().items()
    )


def allocate_verification(
    *,
    interaction_id: str,
    bundle: DetectionBundle,
    policy: RoutePolicy,
    tiers: list[TierEconomics],
    shadow_price: float,
    conformal_threshold: float,
    tool_calls: list[ToolCall],
) -> DecisionTrace:
    """Spend assurance where expected avoided loss exceeds its priced cost."""
    if shadow_price < 0:
        raise ValueError("shadow_price must be non-negative")

    forced = bundle.harm.maximum() >= conformal_threshold
    choices = _tier_choices(bundle, policy, tiers, shadow_price)
    tier_number = _select_tier(choices, forced)
    verdict, reason = _verdict(bundle, tier_number, forced, bool(tool_calls))
    return DecisionTrace(
        interaction_id=interaction_id,
        route=policy.route,
        jurisdiction=policy.jurisdiction,
        verdict=verdict,
        reason=reason,
        harm=bundle.harm,
        evidence_regime=bundle.evidence_regime,
        selected_tier=tier_number,
        forced_by_conformal=forced,
        conformal_threshold=conformal_threshold,
        conformal_alpha=policy.alpha,
        shadow_price=shadow_price,
        expected_loss_inr=expected_loss_inr(bundle, policy),
        assurance_spend_inr=_assurance_spend(tiers, tier_number),
        tier_decisions=choices,
        effect_actions=[],
        policy_version=policy.policy_version,
        policy_hash=policy.policy_hash,
        detector_latency_ms=bundle.latency_ms,
    )


def decide_verdict(
    bundle: DetectionBundle,
    tier: int | None,
    *,
    forced: bool,
    has_effect: bool,
) -> tuple[Verdict, str]:
    """The shipped verdict rule, exposed so a baseline runs the same one we do.

    A comparison where only our policy may block or abstain is measuring the modelling
    difference, not the allocation. The rule itself is unchanged: this is a name for it,
    not a second copy of it.
    """
    return _verdict(bundle, tier, forced, has_effect)


def _tier_choices(
    bundle: DetectionBundle,
    policy: RoutePolicy,
    tiers: list[TierEconomics],
    shadow_price: float,
) -> list[TierDecision]:
    choices: list[TierDecision] = []
    for tier in tiers:
        benefit = expected_loss_averted_inr(bundle, policy, tier)
        direct_cost = tier.verification_cost_inr + tier.delay_cost_inr
        # At lambda=0 this is exactly the Round 1 rule: r*c*k > v+d.
        adjusted_cost = (1.0 + shadow_price) * direct_cost
        worth_it = benefit > adjusted_cost
        choices.append(
            TierDecision(
                tier=tier.tier,
                benefit_inr=benefit,
                adjusted_cost_inr=adjusted_cost,
                net_value_inr=benefit - adjusted_cost,
                selected=worth_it,
                reason="positive expected value" if worth_it else "priced out",
            )
        )
    return choices


def _select_tier(choices: list[TierDecision], forced: bool) -> int | None:
    affordable = [choice for choice in choices if choice.selected]
    selection = max(affordable, key=lambda choice: choice.net_value_inr, default=None)
    if forced and (selection is None or selection.tier == 0):
        selection = next((choice for choice in choices if choice.tier == 1), choices[0])
    return selection.tier if selection is not None else None


def _assurance_spend(tiers: list[TierEconomics], tier_number: int | None) -> float:
    if tier_number is not None:
        tier_cost = next(tier for tier in tiers if tier.tier == tier_number)
        return tier_cost.verification_cost_inr + tier_cost.delay_cost_inr
    return 0.0


def _verdict(
    bundle: DetectionBundle,
    tier: int | None,
    forced: bool,
    has_effect: bool,
) -> tuple[Verdict, str]:
    maximum = bundle.harm.maximum()
    if bundle.evidence_regime == EvidenceRegime.UNVERIFIABLE and maximum >= 0.35:
        return ("hold" if has_effect else "abstain"), "no evidence can support a confident release"
    if maximum >= 0.88:
        return "block", "calibrated harm exceeds the block boundary"
    if has_effect and (forced or tier is not None):
        return "hold", "text may stream, but the proposed effect waits"
    if tier is not None and maximum >= 0.45:
        return "annotate", "verification is worth its cost and found material uncertainty"
    if tier is not None:
        return "allow", "selected verification cleared the response"
    return "allow", "risk is below both the guarantee floor and priced cut line"
