# Runtime admission-control results

Acceptance: **PASS**. Measured 2026-08-23T10:21:53.288325+00:00 on Windows-11-10.0.26200-SP0, Python 3.12.7, 8 logical CPUs.
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
| unbounded | 20 | 19.5 | 30 | 0 | 8.49/17.06/17.82/17.82 | 85.65/94.13/94.88/94.88 | 2394.7 |
| bounded | 20 | 19.6 | 30 | 0 | 6.94/10.07/16.85/16.85 | 84.32/91.24/94.09/94.09 | 2394.7 |
| unbounded | 80 | 76.2 | 120 | 0 | 6.34/13.12/16.30/18.93 | 84.08/91.94/97.28/98.78 | 733.7 |
| bounded | 80 | 69.5 | 110 | 10 | 8.09/32.00/39.20/39.54 | 85.60/113.76/116.50/128.34 | 784.0 |
| unbounded | 400 | 149.0 | 600 | 0 | 397.04/999.55/1043.78/1054.78 | 1328.28/2427.41/2521.26/2532.57 | 839.4 |
| bounded | 400 | 61.5 | 97 | 503 | 8.93/14.66/17.30/17.30 | 87.27/93.94/101.26/101.26 | 802.7 |

Observed degradation boundary (first point with >1% rejection or effect p99 above twice the lowest-load p99): unbounded: 400 offered RPS; bounded: 80 offered RPS.

Latency uses nearest-rank percentiles from the scheduled arrival time. Rejected requests have no text or effect latency sample; their count is reported separately.

## Saturation behaviour

| Offered RPS | Normal | Degraded | Rejected | Floor held | Mandatory completed | Tier 2 while degraded | Queue p99 ms | Max queues discretionary/mandatory |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 30 | 0 | 0 | n/a | n/a | 0 | 0.08 | 0/0 (caps 8/6) |
| 80 | 90 | 20 | 10 | 20/20 | 20/20 | 0 | 36.10 | 2/3 (caps 8/6) |
| 400 | 67 | 30 | 503 | 30/30 | 30/30 | 0 | 9.67 | 8/6 (caps 8/6) |

At the highest load, degradation and rejection both occurred; every served degraded request completed mandatory assessment, none selected Tier 2, and 0 rejected requests generated text.

## Same-run before and after

| Path | Achieved RPS | Effect p99 ms | Effect p99.9 ms | Rejected |
|---|---:|---:|---:|---:|
| unbounded | 149.0 | 2521.26 | 2532.57 | 0 |
| bounded | 61.5 | 101.26 | 101.26 | 503 |

The bounded path trades throughput for bounded work and explicit overload responses. Its tail values apply only to served requests, so they are not a detector speedup.

## Budget signal

| Policy | Offered RPS | Lambda start | Lambda end | Lambda maximum |
|---|---:|---:|---:|---:|
| unbounded | 20 | 0.000 | 32.456 | 32.456 |
| bounded | 20 | 0.000 | 32.456 | 32.456 |
| unbounded | 80 | 0.000 | 51.114 | 51.131 |
| bounded | 80 | 0.000 | 51.088 | 51.088 |
| unbounded | 400 | 0.000 | 38.265 | 51.131 |
| bounded | 400 | 0.000 | 42.484 | 42.484 |

This work item did not change the proportional budget controller. A target equilibrium, overshoot and settling-time criterion will be registered before the controller-dynamics work; none is inferred from this short saturation run.
