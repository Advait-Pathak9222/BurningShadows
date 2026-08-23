from __future__ import annotations

import math
import os
import platform
import sys
from datetime import datetime
from typing import TYPE_CHECKING

from controlplane.runtime import RuntimeLimits

if TYPE_CHECKING:
    from controlplane.eval.loadtest import LoadRun


def render_runtime_report(
    started_at: datetime,
    runs: list[LoadRun],
    limits: RuntimeLimits,
    failures: list[str],
    *,
    route: str,
    work_hold_ms: float,
) -> str:
    outcome = "PASS" if not failures else "FAIL"
    lines = [
        "# Runtime admission-control results",
        "",
        f"Acceptance: **{outcome}**. Measured {started_at.isoformat()} on "
        f"{platform.platform()}, Python {sys.version.split()[0]}, {os.cpu_count()} logical CPUs.",
        "No attempt was made to isolate other host workloads.",
        "",
        "The seeded provider and lexical detector stubs run offline. These numbers describe the "
        "scheduler harness, not production model or detector capacity. Each assessment includes "
        f"a declared {work_hold_ms:.0f} ms blocking hold so the test reaches saturation.",
        "",
        "## Runtime limits",
        "",
        _limits_table(limits),
        "",
        "## Offered load and tail latency",
        "",
        _latency_table(runs),
        "",
        _degradation_text(runs),
        "",
        "Latency uses nearest-rank percentiles from the scheduled arrival time. Rejected requests "
        "have no text or effect latency sample; their count is reported separately.",
        "",
        "## Saturation behaviour",
        "",
        _saturation_table(runs, limits, route),
        "",
        _acceptance_text(runs, failures),
        "",
        "## Same-run before and after",
        "",
        _comparison_table(runs),
        "",
        "The bounded path trades throughput for bounded work and explicit overload responses. "
        "Its tail values apply only to served requests, so they are not a detector speedup.",
        "",
        "## Budget signal",
        "",
        _lambda_table(runs),
        "",
        "This work item did not change the proportional budget controller. A target equilibrium, "
        "overshoot and settling-time criterion will be registered before the controller-dynamics "
        "work; none is inferred from this short saturation run.",
        "",
    ]
    return "\n".join(lines)


def _limits_table(limits: RuntimeLimits) -> str:
    header = (
        "| Version | Route | Lane | Concurrency | Queue | Rate / s | Burst | Timeout ms |"
    )
    rows = [header, "|---|---|---|---:|---:|---:|---:|---:|"]
    for route, route_limits in limits.routes.items():
        for lane_name in ("discretionary", "mandatory"):
            lane = getattr(route_limits, lane_name)
            rows.append(
                f"| {limits.version} | {route} | {lane_name} | {lane.concurrency} | "
                f"{lane.queue_capacity} | {lane.rate_per_second:.1f} | {lane.burst} | "
                f"{lane.queue_timeout_ms:.1f} |"
            )
    return "\n".join(rows)


def _latency_table(runs: list[LoadRun]) -> str:
    header = (
        "| Policy | Offered RPS | Achieved RPS | Served | Rejected | "
        "Text p50/p95/p99/p99.9 ms | Effect p50/p95/p99/p99.9 ms | Cost / 1k INR |"
    )
    rows = [header, "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for run in runs:
        text_values = [sample.text_ms for sample in run.served if sample.text_ms is not None]
        effect_values = [sample.effect_ms for sample in run.served if sample.effect_ms is not None]
        spend = sum(sample.spend_inr for sample in run.served)
        cost_per_thousand = 1000.0 * spend / len(run.served) if run.served else None
        rows.append(
            f"| {run.policy} | {run.offered_rps} | {run.achieved_rps:.1f} | "
            f"{len(run.served)} | {len(run.rejected)} | {_percentiles(text_values)} | "
            f"{_percentiles(effect_values)} | {_number(cost_per_thousand, 1)} |"
        )
    return "\n".join(rows)


def _saturation_table(runs: list[LoadRun], limits: RuntimeLimits, route: str) -> str:
    header = (
        "| Offered RPS | Normal | Degraded | Rejected | Floor held | Mandatory completed | "
        "Tier 2 while degraded | Queue p99 ms | Max queues discretionary/mandatory |"
    )
    rows = [header, "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for run in (item for item in runs if item.policy == "bounded"):
        degraded = [sample for sample in run.served if sample.admission_mode == "degraded"]
        normal = [sample for sample in run.served if sample.admission_mode == "normal"]
        floor = sum(sample.floor_honoured for sample in degraded)
        mandatory = sum(sample.mandatory_completed for sample in degraded)
        tier_two = sum(sample.selected_tier == 2 for sample in degraded)
        waits = [sample.queue_wait_ms for sample in run.served if sample.queue_wait_ms is not None]
        rows.append(
            f"| {run.offered_rps} | {len(normal)} | {len(degraded)} | {len(run.rejected)} | "
            f"{_ratio(floor, len(degraded))} | {_ratio(mandatory, len(degraded))} | {tier_two} | "
            f"{_number(_percentile(waits, 99), 2)} | {_max_queues(run, limits, route)} |"
        )
    return "\n".join(rows)


def _degradation_text(runs: list[LoadRun]) -> str:
    statements = []
    for policy in ("unbounded", "bounded"):
        selected = sorted(
            (run for run in runs if run.policy == policy),
            key=lambda run: run.offered_rps,
        )
        baseline = _effect_p99(selected[0])
        boundary = next(
            (
                run.offered_rps
                for run in selected[1:]
                if _tail_degraded(run, baseline)
            ),
            None,
        )
        value = "not observed" if boundary is None else f"{boundary} offered RPS"
        statements.append(f"{policy}: {value}")
    return (
        "Observed degradation boundary (first point with >1% rejection or effect p99 above twice "
        "the lowest-load p99): " + "; ".join(statements) + "."
    )


def _tail_degraded(run: LoadRun, baseline: float | None) -> bool:
    rejection_rate = len(run.rejected) / run.request_count
    current = _effect_p99(run)
    return rejection_rate > 0.01 or (
        baseline is not None and current is not None and current > 2.0 * baseline
    )


def _effect_p99(run: LoadRun) -> float | None:
    effects = [sample.effect_ms for sample in run.served if sample.effect_ms is not None]
    return _percentile(effects, 99)


def _comparison_table(runs: list[LoadRun]) -> str:
    offered = max(run.offered_rps for run in runs)
    selected = [run for run in runs if run.offered_rps == offered]
    header = "| Path | Achieved RPS | Effect p99 ms | Effect p99.9 ms | Rejected |"
    rows = [header, "|---|---:|---:|---:|---:|"]
    for run in selected:
        effects = [sample.effect_ms for sample in run.served if sample.effect_ms is not None]
        rows.append(
            f"| {run.policy} | {run.achieved_rps:.1f} | "
            f"{_number(_percentile(effects, 99), 2)} | "
            f"{_number(_percentile(effects, 99.9), 2)} | {len(run.rejected)} |"
        )
    return "\n".join(rows)


def _lambda_table(runs: list[LoadRun]) -> str:
    header = "| Policy | Offered RPS | Lambda start | Lambda end | Lambda maximum |"
    rows = [header, "|---|---:|---:|---:|---:|"]
    for run in runs:
        values = [value for _, value in run.lambda_samples]
        rows.append(
            f"| {run.policy} | {run.offered_rps} | {values[0]:.3f} | "
            f"{values[-1]:.3f} | {max(values):.3f} |"
        )
    return "\n".join(rows)


def _acceptance_text(runs: list[LoadRun], failures: list[str]) -> str:
    offered = max(run.offered_rps for run in runs)
    saturated = next(
        run for run in runs if run.policy == "bounded" and run.offered_rps == offered
    )
    generated_after_rejection = sum(sample.generated for sample in saturated.rejected)
    if failures:
        return "Acceptance failures: " + "; ".join(failures) + "."
    return (
        "At the highest load, degradation and rejection both occurred; every served degraded "
        "request completed mandatory assessment, none selected Tier 2, and "
        f"{generated_after_rejection} rejected requests generated text."
    )


def _max_queues(run: LoadRun, limits: RuntimeLimits, route: str) -> str:
    snapshot = run.admission_snapshot["routes"][route]
    observed = [int(snapshot[name]["max_queued"]) for name in ("discretionary", "mandatory")]
    configured = limits.routes[route]
    capacities = [configured.discretionary.queue_capacity, configured.mandatory.queue_capacity]
    return f"{observed[0]}/{observed[1]} (caps {capacities[0]}/{capacities[1]})"


def _percentiles(values: list[float]) -> str:
    percentiles = (50, 95, 99, 99.9)
    return "/".join(_number(_percentile(values, item), 2) for item in percentiles)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100.0 * len(ordered)))
    return ordered[rank - 1]


def _number(value: float | None, places: int) -> str:
    return "n/a" if value is None else f"{value:.{places}f}"


def _ratio(numerator: int, denominator: int) -> str:
    return "n/a" if denominator == 0 else f"{numerator}/{denominator}"
