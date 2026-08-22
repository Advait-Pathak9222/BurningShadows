from __future__ import annotations

from controlplane.effects.classification import classify_effect
from controlplane.models import RoutePolicy, ToolCall, Verdict


def gate_effects(tool_calls: list[ToolCall], verdict: Verdict, policy: RoutePolicy) -> list[str]:
    """Return a permit, hold, or deny action for every proposed effect."""
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
