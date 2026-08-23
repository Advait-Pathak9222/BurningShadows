from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from controlplane.economics import BudgetController
from controlplane.gateway.schemas import ChatCompletionRequest
from controlplane.models import HarmVector, Interaction, PreflightDecision, ToolCall
from controlplane.service import AssessmentEngine
from controlplane.sim.provider import SeededModelProvider
from controlplane.sim.traffic import load_interactions


class _SpendWindow:
    """Feed realised spend per interaction back into the shadow price."""

    def __init__(self) -> None:
        self.total_inr = 0.0
        self.count = 0

    def record(self, spend_inr: float, budget: BudgetController) -> float:
        self.total_inr += spend_inr
        self.count += 1
        return budget.update(self.total_inr / self.count)


ROOT = Path(__file__).resolve().parents[2]
engine = AssessmentEngine(ROOT, ledger_path=ROOT / "data" / "audit.db")
provider = SeededModelProvider()
controller = BudgetController(
    budget_rate_inr=engine.cost_model.gateway_budget_rate_inr,
    learning_rate=engine.cost_model.controller_learning_rate,
)
_spend = _SpendWindow()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Fit before serving: an uncalibrated engine prices traffic against nothing."""
    calibration = ROOT / "data" / "calibration.jsonl"
    if not calibration.exists():
        raise RuntimeError(f"No calibration split at {calibration}; run `make data` first")
    await asyncio.to_thread(engine.calibrate, load_interactions(calibration))
    yield


app = FastAPI(title="ControlPlane.ai", version="0.2.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str | float | bool]:
    return {
        "status": "ok",
        "provider": "seeded-simulator",
        "calibrated": bool(engine.conformal_thresholds),
        "shadow_price": controller.shadow_price,
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    x_controlplane_route: str = Header(default="support-assistant"),
) -> Response:
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")
    prompt = request.messages[-1].content
    preflight = await _run_preflight(x_controlplane_route, request.jurisdiction, prompt)
    if not preflight.allowed:
        return _blocked_response(preflight)
    response_text, generated_calls = provider.generate(prompt)
    interaction = _build_interaction(request, x_controlplane_route, response_text, generated_calls)
    if request.stream:
        return StreamingResponse(
            _stream_with_decision(request.model, interaction),
            media_type="text/event-stream",
            headers={"x-controlplane-decision": "pending"},
        )
    return await _completion_response(request.model, response_text, interaction)


async def _run_preflight(route: str, jurisdiction: str, prompt: str) -> PreflightDecision:
    try:
        return await asyncio.to_thread(engine.preflight, route, jurisdiction, prompt)
    except KeyError as error:
        raise HTTPException(status_code=400, detail=error.args[0]) from error


def _blocked_response(preflight: PreflightDecision) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "request blocked by preflight", "controlplane": preflight.model_dump()},
        headers={"x-controlplane-decision": "block"},
    )


def _build_interaction(
    request: ChatCompletionRequest,
    route: str,
    response_text: str,
    generated_calls: list[ToolCall],
) -> Interaction:
    return Interaction(
        interaction_id=f"api-{uuid.uuid4()}",
        split="scenario",
        route=route,
        jurisdiction=request.jurisdiction,
        prompt=request.messages[-1].content,
        response=response_text,
        context_documents=request.context_documents,
        comparison_samples=request.comparison_samples,
        tool_calls=request.tool_calls or generated_calls,
        truth=HarmVector.zeros(),
    )


async def _completion_response(
    model: str, response_text: str, interaction: Interaction
) -> JSONResponse:
    trace = await asyncio.to_thread(engine.assess, interaction, controller.shadow_price)
    _spend.record(trace.assurance_spend_inr, controller)
    payload: dict[str, Any] = {
        "id": interaction.interaction_id,
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": response_text}}],
        "controlplane": trace.model_dump(mode="json"),
    }
    return JSONResponse(payload, headers={"x-controlplane-decision": trace.verdict})


async def _stream_with_decision(model: str, interaction: Interaction) -> AsyncIterator[str]:
    assessment = asyncio.create_task(
        asyncio.to_thread(engine.assess, interaction, controller.shadow_price)
    )
    async for token in provider.stream(interaction.prompt):
        chunk = {
            "id": interaction.interaction_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {"content": token}}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
    trace = await assessment
    _spend.record(trace.assurance_spend_inr, controller)
    final = {"controlplane": trace.model_dump(mode="json")}
    yield f"event: controlplane.decision\ndata: {json.dumps(final)}\n\n"
    yield "data: [DONE]\n\n"
