# Runtime admission-control preregistration

Locked before the admission controller and load harness were implemented on
`runtime/admission-backpressure`. This document defines the first runtime work item's acceptance
tests. It does not change the allocator experiment registered in `docs/PREREGISTRATION.md`.

## Claim under test

When offered load exceeds the discretionary verification lane's capacity, the gateway should
continue only through a reserved mandatory lane. That lane may skip checks selected solely by
economic value, but it must retain the Tier 0 and Tier 1 signals used to enforce the fitted
conformal floor. If the mandatory lane is also unavailable, the gateway must reject the request
before returning model output.

## Fixed test conditions

- The offline seeded provider and stub detectors are the default workload. Throughput therefore
  measures the runtime harness, not a production detector cascade.
- Runtime limits come from `config/runtime.yaml`; the load test records those limits with its
  output.
- The saturation scenario must hold verification workers long enough to fill both bounded queues.
  It must not infer overload from machine load alone.
- Text and gated-effect latency are measured separately from monotonic timestamps.

## Acceptance criteria

The implementation passes only if one command in the repository demonstrates all of these:

1. Queue depth never exceeds the configured capacity for either lane.
2. At least one request is admitted in degraded mode after discretionary capacity is exhausted.
3. Every served degraded request completes the mandatory assessment path. The numerator is the
   count of degraded responses with a completed mandatory assessment; the denominator is every
   degraded response served.
4. At least one request receives an explicit overload response when the mandatory lane and queue
   are full. No response text may be generated for such a request.
5. Normal-load requests remain eligible for all tiers, while degraded requests are not charged
   for discretionary Tier 2 work.
6. The report includes offered and achieved requests per second, p50/p95/p99/p99.9 for first text
   and effect decision latency, queue wait and depth, admission counts, and cost per 1,000 served
   interactions. Empty latency samples must be reported as unavailable, not as zero.

The run fails if any denominator needed by criteria 2-4 is zero. No speedup or production-capacity
claim is preregistered for this work item.

## J1 admission SLO tuning objective

**Status: locked, not executed.** This objective was registered before the sweep was written, and
the sweep was never implemented — the work stopped before that item. The `slo-sweep` command it
refers to has been removed rather than shipped as a stub that exits non-zero. Nothing in this
repository claims a result against these criteria, and the committed admission limits remain
what `docs/results/runtime.md` reports them to be: a bounded tail bought at a throughput cost,
and a regression at 80 offered RPS. This section is retained because a registered objective that
went unrun is part of the record, not something to delete once it became inconvenient.

Locked on 2026-08-25 at base commit `bce1217`, before implementing or running the admission sweep.
This objective governs tuning for `support-assistant` under the existing offline scheduler harness.
It does not turn stub-detector throughput into a production capacity claim.

### Declared capacity and service objective

The declared capacity is **80 offered interactions per second**. A candidate passes only if every
condition below holds in the same sweep command:

1. At 20 and 80 offered RPS, effect-decision p99 is at most 150 ms and first-text p99 is at most
   50 ms.
2. At 20 and 80 offered RPS, the rejection rate is at most 1%. A zero-request denominator is a
   failed run, not a zero rejection rate.
3. At 20 and 80 offered RPS, achieved served throughput is at least 95% of the higher achieved
   throughput from same-command unbounded measurements taken before and after the sweep. The 5%
   margin is the declared timer and scheduler tolerance; a larger loss is a regression.
4. At 400 offered RPS, effect-decision p99 for served requests is at most 150 ms and achieved
   served throughput is at least 76 RPS, which is 95% of declared capacity. Beyond capacity,
   explicit rejection is preferred to unbounded queue growth.
5. At every offered load, every degraded response completes mandatory assessment, every required
   conformal floor is honoured, no degraded request selects Tier 2, no rejected request generates
   text, and observed queue depth stays within its configured bound.

Empty latency samples fail the candidate. Percentiles use the existing nearest-rank definition.
The 75 ms blocking hold, seeded provider, lexical detectors, offered rates and run duration remain
fixed so this sweep measures admission scheduling rather than a changed workload.

### Candidate grid

The sweep applies each multiplier to both discretionary and mandatory lanes of the currently
committed `support-assistant` limits. Integer fields round upward after multiplication; queue
timeouts do not change.

| Dimension | Multipliers |
|---|---|
| concurrency | 1.0, 1.5, 2.0 |
| queue capacity | 0.5, 1.0, 2.0 |
| token rate | 1.0, 1.5, 2.0 |
| burst | 0.5, 1.0, 2.0 |

All 81 combinations must appear in the committed result, including failures. Unbounded baselines
run at the beginning and end of the same command; the less favourable comparison is used when
testing candidate throughput. This prevents a transiently slow baseline from making a candidate
pass.

If several candidates pass, choose lexicographically by the lowest total concurrency, token rate,
queue capacity and burst, in that order. Rerun the chosen candidate three times; all three must pass
before `config/runtime.yaml` changes. If no candidate passes, keep the current limits and record the
failed objective in `docs/RUNTIME_LIMITATIONS.md` rather than moving a threshold after seeing data.
