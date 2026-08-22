from __future__ import annotations

from controlplane.models import EffectClass, ToolCall

FINANCIAL_WORDS = {"transfer", "pay", "refund", "purchase", "wire"}
IRREVERSIBLE_WORDS = {"delete", "terminate", "close", "revoke"}
EXTERNAL_WORDS = {"email", "publish", "post", "message", "notify"}
WRITE_WORDS = {"update", "create", "write", "change", "schedule"}


def classify_effect(tool_call: ToolCall) -> EffectClass:
    """Classify a tool call by reversibility and blast radius."""
    if tool_call.effect_class is not None:
        return tool_call.effect_class
    name = tool_call.name.lower()
    if any(word in name for word in FINANCIAL_WORDS):
        return EffectClass.FINANCIAL
    if any(word in name for word in IRREVERSIBLE_WORDS):
        return EffectClass.IRREVERSIBLE_WRITE
    if any(word in name for word in EXTERNAL_WORDS):
        return EffectClass.EXTERNAL_FACING
    if any(word in name for word in WRITE_WORDS):
        return EffectClass.REVERSIBLE_WRITE
    return EffectClass.READ
