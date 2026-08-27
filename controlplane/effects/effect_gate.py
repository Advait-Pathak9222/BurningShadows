from __future__ import annotations

from controlplane.effects.classification import classify_effect
from controlplane.models import RoutePolicy, ToolCall, Verdict


def gate_effects(tool_calls: list[ToolCall], verdict: Verdict, policy: RoutePolicy) -> list[str]:
    """Return a permit, hold, or deny action for every proposed effect.

    **This is a decision, not an execution guarantee.** The function returns strings, and the
    decision is written to the hash chain, but nothing here holds a durable lease over the
    effect. A gateway that crashes between deciding `hold` and the caller acting on it leaves
    no lock behind, and a restart does not replay or recover the held effect -- the caller is
    trusted to honour the action it was given.

    That is enough for the property this project actually evaluates: whether the *decision* is
    correct, priced and auditable. It is not enough to run irreversible effects against, which
    would need a durable lease with a fencing token and restart recovery. Recorded here rather
    than only in `docs/LIMITATIONS.md`, because this is the function someone would reach for
    when wiring it to a real payment API.
    """
    actions: list[str] = []
    for tool_call in tool_calls:
        effect_class = classify_effect(tool_call)
        if verdict == "block":
            action = "deny"
        elif verdict in {"hold", "abstain"} or effect_class in policy.human_review_required_for:
            action = "hold"
        else:
            action = "permit"
        actions.append(f"{tool_call.name}:{effect_class.value}:{action}")
    return actions
