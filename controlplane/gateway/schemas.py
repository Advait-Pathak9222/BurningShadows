from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from controlplane.models import ToolCall


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = "controlplane-sim"
    messages: list[ChatMessage]
    stream: bool = False
    context_documents: list[str] = Field(default_factory=list)
    comparison_samples: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    jurisdiction: str = "eu"
