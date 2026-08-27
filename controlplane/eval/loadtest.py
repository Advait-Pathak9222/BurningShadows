from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from controlplane.economics import BudgetController
from controlplane.eval.runtime_report import render_runtime_report
from controlplane.models import DecisionTrace, HarmVector, Interaction, ToolCall
from controlplane.runtime import (
    AdmissionController,
    AdmissionLease,
    AdmissionRejected,
    RouteAdmissionLimits,
    RuntimeLimits,
)
from controlplane.service import AssessmentEngine
from controlplane.sim.provider import SeededModelProvider
from controlplane.sim.traffic import load_interactions

OFFERED_RATES = (20, 80, 400)
RUN_SECONDS = 1.5
WORK_HOLD_MS = 75.0
ROUTE = "support-assistant"
JURISDICTION = "eu"
PROMPT = "Transfer 5000 to Acme Corp."


@dataclass(frozen=True)
class RequestSample:
    status: Literal["served", "rejected"]
    admission_mode: Literal["unbounded", "normal", "degraded", "saturated"]
    text_ms: float | None
    effect_ms: float | None
    queue_wait_ms: float | None
    spend_inr: float
    selected_tier: int | None
    forced_by_conformal: bool
    floor_honoured: bool
    mandatory_completed: bool
    generated: bool


@dataclass(frozen=True)
class LoadRun:
    policy: Literal["unbounded", "bounded"]
    offered_rps: int
    request_count: int
    elapsed_s: float
    samples: list[RequestSample]
    admission_snapshot: dict[str, Any]
    lambda_samples: list[tuple[float, float]]

    @property
    def served(self) -> list[RequestSample]:
        return [sample for sample in self.samples if sample.status == "served"]

    @property
    def rejected(self) -> list[RequestSample]:
        return [sample for sample in self.samples if sample.status == "rejected"]

    @property
    def achieved_rps(self) -> float:
        return len(self.served) / self.elapsed_s


class _SpendTracker:
    def __init__(self, budget: BudgetController, started: float) -> None:
        self.budget = budget
        self.started = started
        self.total_inr = 0.0
        self.count = 0
        self.samples: list[tuple[float, float]] = [(0.0, budget.shadow_price)]

    def record(self, spend_inr: float) -> None:
        self.total_inr += spend_inr
        self.count += 1
        shadow_price = self.budget.update(self.total_inr / self.count)
        self.samples.append((time.perf_counter() - self.started, shadow_price))


def run_loadtest(root: Path) -> Path:
    started_at = datetime.now(UTC)
    limits = RuntimeLimits.load(root / "config" / "runtime.yaml")
    runs = asyncio.run(_run_suite(root, limits))
    failures = _acceptance_failures(runs, limits)
    report_path = root / "docs" / "results" / "runtime.md"
    report_path.write_text(
        render_runtime_report(
            started_at,
            runs,
            limits,
            failures,
            route=ROUTE,
            work_hold_ms=WORK_HOLD_MS,
        ),
        encoding="utf-8",
        newline="\n",
    )
    if failures:
        raise RuntimeError("Runtime acceptance failed: " + "; ".join(failures))
    return report_path


async def _run_suite(root: Path, limits: RuntimeLimits) -> list[LoadRun]:
    engine = AssessmentEngine(root)
    calibration = load_interactions(root / "data" / "calibration.jsonl")
    await asyncio.to_thread(engine.calibrate, calibration)
    provider = SeededModelProvider()
    runs: list[LoadRun] = []
    for offered_rps in OFFERED_RATES:
        runs.append(await _run_load(engine, provider, limits, offered_rps, bounded=False))
        runs.append(await _run_load(engine, provider, limits, offered_rps, bounded=True))
    return runs


async def _run_load(
    engine: AssessmentEngine,
    provider: SeededModelProvider,
    limits: RuntimeLimits,
    offered_rps: int,
    *,
    bounded: bool,
) -> LoadRun:
    admission = AdmissionController(limits) if bounded else None
    budget = BudgetController(
        budget_rate_inr=engine.cost_model.gateway_budget_rate_inr,
        learning_rate=engine.cost_model.controller_learning_rate,
    )
    started = time.perf_counter()
    spend = _SpendTracker(budget, started)
    request_count = int(offered_rps * RUN_SECONDS)
    tasks = [
        asyncio.create_task(
            _scheduled_request(
                started + index / offered_rps,
                index,
                engine,
                provider,
                admission,
                spend,
            )
        )
        for index in range(request_count)
    ]
    samples = list(await asyncio.gather(*tasks))
    snapshot = admission.snapshot() if admission is not None else {}
    policy: Literal["unbounded", "bounded"] = "bounded" if bounded else "unbounded"
    return LoadRun(
        policy=policy,
        offered_rps=offered_rps,
        request_count=request_count,
        elapsed_s=time.perf_counter() - started,
        samples=samples,
        admission_snapshot=snapshot,
        lambda_samples=spend.samples,
    )


async def _scheduled_request(
    scheduled_at: float,
    index: int,
    engine: AssessmentEngine,
    provider: SeededModelProvider,
    admission: AdmissionController | None,
    spend: _SpendTracker,
) -> RequestSample:
    await _wait_until(scheduled_at)
    lease = await _admit_or_none(admission)
    if admission is not None and lease is None:
        return _rejected_sample()
    try:
        preflight = await asyncio.to_thread(engine.preflight, ROUTE, JURISDICTION, PROMPT)
        if not preflight.allowed:
            raise RuntimeError("Load-test prompt was blocked by preflight")
        response, tool_calls = provider.generate(PROMPT)
        text_ms = _since_ms(scheduled_at)
        interaction = _interaction(index, response, tool_calls)
        trace = await asyncio.to_thread(_held_assessment, engine, interaction, lease, spend.budget)
    finally:
        if lease is not None:
            lease.release()
    spend.record(trace.assurance_spend_inr)
    return _served_sample(trace, lease, text_ms, _since_ms(scheduled_at))


async def _admit_or_none(admission: AdmissionController | None) -> AdmissionLease | None:
    if admission is None:
        return None
    try:
        return await admission.admit(ROUTE)
    except AdmissionRejected:
        return None


def _held_assessment(
    engine: AssessmentEngine,
    interaction: Interaction,
    lease: AdmissionLease | None,
    budget: BudgetController,
) -> DecisionTrace:
    time.sleep(WORK_HOLD_MS / 1000.0)
    return engine.assess(
        interaction,
        budget.shadow_price,
        mandatory_only=lease.degraded if lease is not None else False,
        admission_mode=lease.mode.value if lease is not None else "unbounded",
        queue_wait_ms=lease.queue_wait_ms if lease is not None else 0.0,
    )


def _interaction(index: int, response: str, tool_calls: list[ToolCall]) -> Interaction:
    return Interaction(
        interaction_id=f"load-{index}-{uuid.uuid4()}",
        split="scenario",
        route=ROUTE,
        jurisdiction=JURISDICTION,
        prompt=PROMPT,
        response=response,
        tool_calls=tool_calls,
        truth=HarmVector.zeros(),
    )


def _served_sample(
    trace: DecisionTrace,
    lease: AdmissionLease | None,
    text_ms: float,
    effect_ms: float,
) -> RequestSample:
    floor_honoured = not trace.forced_by_conformal or trace.selected_tier in {1, 2}
    return RequestSample(
        status="served",
        admission_mode=trace.admission_mode,
        text_ms=text_ms,
        effect_ms=effect_ms,
        queue_wait_ms=lease.queue_wait_ms if lease is not None else 0.0,
        spend_inr=trace.assurance_spend_inr,
        selected_tier=trace.selected_tier,
        forced_by_conformal=trace.forced_by_conformal,
        floor_honoured=floor_honoured,
        mandatory_completed=trace.mandatory_assessment_completed,
        generated=True,
    )


def _rejected_sample() -> RequestSample:
    return RequestSample(
        status="rejected",
        admission_mode="saturated",
        text_ms=None,
        effect_ms=None,
        queue_wait_ms=None,
        spend_inr=0.0,
        selected_tier=None,
        forced_by_conformal=False,
        floor_honoured=False,
        mandatory_completed=False,
        generated=False,
    )


def _acceptance_failures(runs: list[LoadRun], limits: RuntimeLimits) -> list[str]:
    saturated = next(
        run for run in runs if run.policy == "bounded" and run.offered_rps == max(OFFERED_RATES)
    )
    degraded = [sample for sample in saturated.served if sample.admission_mode == "degraded"]
    failures: list[str] = []
    if not degraded:
        failures.append("saturation produced no degraded responses")
    if not saturated.rejected:
        failures.append("saturation produced no explicit overload responses")
    if any(not sample.mandatory_completed for sample in degraded):
        failures.append("a degraded response skipped mandatory assessment")
    if any(not sample.floor_honoured for sample in degraded):
        failures.append("a degraded response violated the conformal floor")
    if any(sample.selected_tier == 2 for sample in degraded):
        failures.append("a degraded response paid for Tier 2")
    failures.extend(_queue_failures(saturated, limits.routes[ROUTE]))
    if any(sample.generated for sample in saturated.rejected):
        failures.append("an overloaded request generated response text")
    return failures


def _queue_failures(run: LoadRun, limits: RouteAdmissionLimits) -> list[str]:
    route = run.admission_snapshot["routes"][ROUTE]
    failures = []
    for lane_name in ("discretionary", "mandatory"):
        maximum = int(route[lane_name]["max_queued"])
        capacity = int(getattr(limits, lane_name).queue_capacity)
        if maximum > capacity:
            failures.append(f"{lane_name} queue reached {maximum} above capacity {capacity}")
        elif maximum < capacity:
            failures.append(f"{lane_name} queue did not fill: observed {maximum} of {capacity}")
    return failures


def _since_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


async def _wait_until(scheduled_at: float) -> None:
    remaining = scheduled_at - time.perf_counter()
    while remaining > 0.0:
        await asyncio.sleep(remaining)
        remaining = scheduled_at - time.perf_counter()
