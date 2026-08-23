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
