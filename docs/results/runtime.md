# Runtime admission-control results

Acceptance: **PASS**. Measured 2026-08-23T10:59:48.798241+00:00 on Windows-11-10.0.26200-SP0, Python 3.13.4, 12 logical CPUs.
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
| unbounded | 20 | 19.6 | 30 | 0 | 4.24/12.70/13.96/13.96 | 80.57/89.27/90.60/90.60 | 2394.7 |
| bounded | 20 | 19.6 | 30 | 0 | 6.68/9.96/14.02/14.02 | 83.02/86.12/90.20/90.20 | 2394.7 |
| unbounded | 80 | 76.6 | 120 | 0 | 3.37/7.85/8.75/9.20 | 79.50/83.89/85.05/85.25 | 733.7 |
| bounded | 80 | 70.2 | 111 | 9 | 6.58/38.95/42.98/45.35 | 82.71/115.52/119.52/121.83 | 778.6 |
| unbounded | 400 | 203.2 | 600 | 0 | 234.27/939.76/986.97/997.61 | 772.79/1384.55/1426.73/1458.83 | 839.4 |
| bounded | 400 | 60.1 | 94 | 506 | 8.96/48.98/58.58/58.58 | 85.36/127.98/136.59/136.59 | 854.7 |

Observed degradation boundary (first point with >1% rejection or effect p99 above twice the lowest-load p99): unbounded: 400 offered RPS; bounded: 80 offered RPS.

Latency uses nearest-rank percentiles from the scheduled arrival time. Rejected requests have no text or effect latency sample; their count is reported separately.

## Saturation behaviour

| Offered RPS | Normal | Degraded | Rejected | Floor held | Mandatory completed | Tier 2 while degraded | Queue p99 ms | Max queues discretionary/mandatory |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 30 | 0 | 0 | n/a | n/a | 0 | 0.05 | 0/0 (caps 8/6) |
| 80 | 91 | 20 | 9 | 20/20 | 20/20 | 0 | 40.62 | 0/3 (caps 8/6) |
| 400 | 64 | 30 | 506 | 30/30 | 30/30 | 0 | 25.12 | 8/6 (caps 8/6) |

At the highest load, degradation and rejection both occurred; every served degraded request completed mandatory assessment, none selected Tier 2, and 0 rejected requests generated text.

## Same-run before and after

| Path | Achieved RPS | Effect p99 ms | Effect p99.9 ms | Rejected |
|---|---:|---:|---:|---:|
| unbounded | 203.2 | 1426.73 | 1458.83 | 0 |
| bounded | 60.1 | 136.59 | 136.59 | 506 |

The bounded path trades throughput for bounded work and explicit overload responses. Its tail values apply only to served requests, so they are not a detector speedup.

## Budget signal

| Policy | Offered RPS | Lambda start | Lambda end | Lambda maximum |
|---|---:|---:|---:|---:|
| unbounded | 20 | 0.000 | 32.456 | 32.456 |
| bounded | 20 | 0.000 | 32.456 | 32.456 |
| unbounded | 80 | 0.000 | 51.114 | 51.131 |
| bounded | 80 | 0.000 | 51.101 | 51.101 |
| unbounded | 400 | 0.000 | 38.265 | 51.131 |
| bounded | 400 | 0.000 | 41.975 | 41.975 |

This work item did not change the proportional budget controller. A target equilibrium, overshoot and settling-time criterion will be registered before the controller-dynamics work; none is inferred from this short saturation run.
