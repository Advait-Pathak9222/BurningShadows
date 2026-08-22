from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from controlplane.models import ToolCall


class SeededModelProvider:
    """Return repeatable responses so the demo needs no API key or network."""

    def generate(self, prompt: str) -> tuple[str, list[ToolCall]]:
        lowered = prompt.lower()
        if "5,000" in prompt or "5000" in prompt or "transfer" in lowered:
            return (
                "I prepared a $5,000 transfer to Acme Corp using account number ACME-778899.",
                [ToolCall(name="transfer_funds", arguments={"amount": 5000, "payee": "Acme Corp"})],
            )
        if "retention" in lowered:
            return (
                "The resolved policy pack controls retention and stamps its "
                "version in the audit record.",
                [],
            )
        if "vendor" in lowered:
            return "The vendor definitely passed every security review in 2026.", []
        return (
            "The supplied source says the renewal fee is ₹499 and can be refunded within 14 days.",
            [],
        )

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        response, _ = self.generate(prompt)
        for token in response.split():
            yield f"{token} "
            await asyncio.sleep(0)
