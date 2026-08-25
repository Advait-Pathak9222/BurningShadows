from __future__ import annotations

from pathlib import Path

from controlplane.economics import allocate_verification
from controlplane.eval.sensitivity import (
    HIGH_MULTIPLIER,
    LOW_MULTIPLIER,
    Decision,
    _drawn_policies,
    _flip_rate,
    _scaled_policies,
)
from controlplane.models import HarmVector, Interaction
from controlplane.service import AssessmentEngine


def _interaction(index: int = 0) -> Interaction:
    return Interaction(
        interaction_id=f"sens-{index:04d}",
        split="test",
        route="finops-agent",
        jurisdiction="eu",
        prompt="What is the outstanding balance?",
        response="The balance is INR 4,20,000 and the account number is 4012 8888 8888 1881.",
        context_documents=["The balance is INR 12,000."],
        truth=HarmVector.zeros(),
    )


def test_the_draw_is_deterministic(project_root: Path) -> None:
    """A sensitivity result nobody can reproduce is not evidence."""
    engine = AssessmentEngine(project_root)
    test = [_interaction()]
    assert _drawn_policies(engine, test, 7) == _drawn_policies(engine, test, 7)


def test_different_draws_move_the_consequence(project_root: Path) -> None:
    engine = AssessmentEngine(project_root)
    test = [_interaction()]
    first = _drawn_policies(engine, test, 1)["finops-agent:eu"].consequence_inr
    second = _drawn_policies(engine, test, 2)["finops-agent:eu"].consequence_inr
    assert first != second


def test_every_draw_stays_inside_the_approved_band(project_root: Path) -> None:
    """The band is what Finance and Risk would sign off. Nothing may leave it."""
    engine = AssessmentEngine(project_root)
    test = [_interaction()]
    base = _scaled_policies(engine, test, 1.0)["finops-agent:eu"].consequence_inr
    for draw in range(24):
        drawn = _drawn_policies(engine, test, draw)["finops-agent:eu"].consequence_inr
        for axis, value in drawn.items():
            ratio = value / base[axis]
            assert LOW_MULTIPLIER <= ratio <= HIGH_MULTIPLIER


def test_the_axes_move_independently(project_root: Path) -> None:
    """A single shared multiplier would test the level, not the ranking."""
    engine = AssessmentEngine(project_root)
    test = [_interaction()]
    base = _scaled_policies(engine, test, 1.0)["finops-agent:eu"].consequence_inr
    drawn = _drawn_policies(engine, test, 3)["finops-agent:eu"].consequence_inr
    ratios = {round(drawn[axis] / base[axis], 6) for axis in base}
    assert len(ratios) > 1


def test_an_unchanged_scenario_flips_nothing() -> None:
    base = {"a": Decision(2, "allow"), "b": Decision(None, "allow")}
    assert _flip_rate(base, dict(base)) == 0.0


def test_tier_and_verdict_flips_are_counted_separately() -> None:
    base = {"a": Decision(2, "allow"), "b": Decision(1, "allow")}
    moved = {"a": Decision(1, "allow"), "b": Decision(1, "annotate")}
    assert _flip_rate(base, moved, verdict=False) == 0.5
    assert _flip_rate(base, moved, tier=False) == 0.5
    assert _flip_rate(base, moved) == 1.0


def test_consequence_does_not_reach_the_verdict(project_root: Path) -> None:
    """The claim the sensitivity report makes, asserted rather than observed.

    `c` prices a check. It is not an input to allow/annotate/abstain/hold/block, which
    read calibrated harm, the evidence regime and the conformal floor. So a buyer who
    disputes our consequence estimates is disputing the assurance bill, not the safety
    behaviour — and that has to stay true as the allocator changes.
    """
    engine = AssessmentEngine(project_root)
    item = _interaction()
    bundle = engine.detect(item)
    verdicts = set()
    for key, policy in _scaled_policies(engine, [item], 1.0).items():
        for scale in (0.05, 0.25, 1.0, 4.0, 50.0):
            scaled = policy.model_copy(
                update={
                    "consequence_inr": {
                        axis: value * scale
                        for axis, value in policy.consequence_inr.items()
                    }
                }
            )
            trace = allocate_verification(
                interaction_id=item.interaction_id,
                bundle=bundle,
                policy=scaled,
                tiers=engine.cost_model.tiers(scaled, item.tool_calls),
                # Shadow price held at zero so this isolates `c`: a live controller would
                # move lambda in response to the spend the new consequence induces.
                shadow_price=0.0,
                conformal_threshold=0.5,
                tool_calls=item.tool_calls,
            )
            verdicts.add(trace.verdict)
        assert key == "finops-agent:eu"
    assert len(verdicts) == 1


def test_a_baseline_runs_the_same_verdict_rule_we_do(project_root: Path) -> None:
    """The fairness correction, asserted so it cannot quietly regress.

    A comparison where only our policy may block or abstain measures the modelling
    difference, not the allocation. `decide_verdict` is the shipped rule, and a baseline
    with the same bundle and the same tier must reach the same verdict our allocator
    would.
    """
    from controlplane.economics import decide_verdict

    engine = AssessmentEngine(project_root)
    item = _interaction()
    bundle = engine.detect(item)
    policy = engine.policy_store.resolve(item.route, item.jurisdiction)
    trace = allocate_verification(
        interaction_id=item.interaction_id,
        bundle=bundle,
        policy=policy,
        tiers=engine.cost_model.tiers(policy, item.tool_calls),
        shadow_price=0.0,
        conformal_threshold=1.01,  # above any score, so nothing is forced
        tool_calls=item.tool_calls,
    )
    verdict, _ = decide_verdict(
        bundle,
        trace.selected_tier,
        forced=False,
        has_effect=bool(item.tool_calls),
    )
    assert verdict == trace.verdict
