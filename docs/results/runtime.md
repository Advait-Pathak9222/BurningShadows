# Runtime admission-control results

Acceptance: **PASS**. Measured 2026-08-25T13:18:18.382280+00:00 on Windows-11-10.0.26200-SP0, Python 3.13.4, 12 logical CPUs.
No attempt was made to isolate other host workloads.

The seeded provider and lexical detector stubs run offline. These numbers describe the scheduler harness, not production model or detector capacity. Each assessment includes a declared 75 ms blocking hold so the test reaches saturation.

## Runtime limits

| Version | Route | Lane | Concurrency | Queue | Rate / s | Burst | Timeout ms |
|---|---|---|---:|---:|---:|---:|---:|
| runtime-2026.08 | support-assistant | discretionary | 8 | 8 | 40.0 | 32 | 25.0 |
| runtime-2026.08 | support-assistant | mandatory | 2 | 6 | 20.0 | 16 | 50.0 |
| runtime-2026.08 | internal-kb | discretionary | 6 | 12 | 30.0 | 12 | 25.0 |
| runtime-2026.08 | internal-kb | mandatory | 2 | 8 | 15.0 | 6 | 50.0 |
| runtime-2026.08 | finops-agent | discretionary | 4 | 8 | 20.0 | 8 | 25.0 |
| runtime-2026.08 | finops-agent | mandatory | 3 | 12 | 20.0 | 8 | 75.0 |

## Offered load and tail latency

| Policy | Offered RPS | Achieved RPS | Served | Rejected | Text p50/p95/p99/p99.9 ms | Effect p50/p95/p99/p99.9 ms | Cost / 1k INR |
|---|---:|---:|---:|---:|---:|---:|---:|
| unbounded | 20 | 19.5 | 30 | 0 | 9.06/16.05/16.72/16.72 | 85.65/92.36/92.80/92.80 | 3200.0 |
| bounded | 20 | 19.6 | 30 | 0 | 4.66/13.99/15.83/15.83 | 81.03/90.41/92.31/92.31 | 3200.0 |
| unbounded | 80 | 76.6 | 120 | 0 | 2.91/7.30/9.04/10.55 | 79.16/83.65/85.32/86.84 | 3200.0 |
| bounded | 80 | 70.2 | 111 | 9 | 6.51/36.05/39.77/43.96 | 82.59/112.23/116.60/119.78 | 2655.9 |
| unbounded | 400 | 200.3 | 600 | 0 | 264.97/844.95/896.51/908.23 | 816.95/1432.13/1499.27/1511.48 | 1272.2 |
| bounded | 400 | 63.9 | 101 | 499 | 9.85/16.73/28.37/30.82 | 87.01/99.07/106.81/109.05 | 2303.0 |

Observed degradation boundary (first point with >1% rejection or effect p99 above twice the lowest-load p99): unbounded: 400 offered RPS; bounded: 80 offered RPS.

Latency uses nearest-rank percentiles from the scheduled arrival time. Rejected requests have no text or effect latency sample; their count is reported separately.

## Saturation behaviour

| Offered RPS | Normal | Degraded | Rejected | Floor held | Mandatory completed | Tier 2 while degraded | Queue p99 ms | Max queues discretionary/mandatory |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 30 | 0 | 0 | n/a | n/a | 0 | 0.05 | 0/0 (caps 8/6) |
| 80 | 91 | 20 | 9 | 20/20 | 20/20 | 0 | 37.49 | 0/3 (caps 8/6) |
| 400 | 71 | 30 | 499 | 30/30 | 30/30 | 0 | 22.00 | 8/6 (caps 8/6) |

At the highest load, degradation and rejection both occurred; every served degraded request completed mandatory assessment, none selected Tier 2, and 0 rejected requests generated text.

## Same-run before and after

| Path | Achieved RPS | Effect p99 ms | Effect p99.9 ms | Rejected |
|---|---:|---:|---:|---:|
| unbounded | 200.3 | 1499.27 | 1511.48 | 0 |
| bounded | 63.9 | 106.81 | 109.05 | 499 |

The bounded path trades throughput for bounded work and explicit overload responses. Its tail values apply only to served requests, so they are not a detector speedup.

## Budget signal

| Policy | Offered RPS | Lambda start | Lambda end | Lambda maximum |
|---|---:|---:|---:|---:|
| unbounded | 20 | 0.000 | 34.300 | 34.300 |
| bounded | 20 | 0.000 | 34.300 | 34.300 |
| unbounded | 80 | 0.000 | 137.200 | 137.200 |
| bounded | 80 | 0.000 | 119.561 | 119.561 |
| unbounded | 400 | 0.000 | 456.810 | 456.810 |
| bounded | 400 | 0.000 | 83.419 | 83.419 |

This work item did not change the proportional budget controller. A target equilibrium, overshoot and settling-time criterion will be registered before the controller-dynamics work; none is inferred from this short saturation run.
