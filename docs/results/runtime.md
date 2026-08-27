# Runtime admission-control results

Acceptance: **PASS**. Measured 2026-08-27T20:54:54.191177+00:00 on Windows-11-10.0.26200-SP0, Python 3.13.4, 12 logical CPUs.
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
| unbounded | 20 | 19.5 | 30 | 0 | 5.67/16.08/16.16/16.16 | 81.95/92.65/92.81/92.81 | 3200.0 |
| bounded | 20 | 19.5 | 30 | 0 | 10.12/16.09/17.08/17.08 | 86.43/92.49/93.54/93.54 | 3200.0 |
| unbounded | 80 | 76.4 | 120 | 0 | 5.56/11.86/14.17/14.51 | 81.90/88.23/91.29/91.79 | 3200.0 |
| bounded | 80 | 70.0 | 111 | 9 | 6.14/39.65/45.41/47.69 | 82.56/116.26/122.21/124.10 | 2655.9 |
| unbounded | 400 | 198.4 | 600 | 0 | 299.34/518.89/540.56/553.69 | 831.08/1455.12/1508.12/1526.42 | 1327.6 |
| bounded | 400 | 63.7 | 101 | 499 | 7.64/21.35/26.22/35.81 | 84.06/99.13/104.07/112.81 | 2303.0 |

Observed degradation boundary (first point with >1% rejection or effect p99 above twice the lowest-load p99): unbounded: 400 offered RPS; bounded: 80 offered RPS.

Latency uses nearest-rank percentiles from the scheduled arrival time. Rejected requests have no text or effect latency sample; their count is reported separately.

## Saturation behaviour

| Offered RPS | Normal | Degraded | Rejected | Floor held | Mandatory completed | Tier 2 while degraded | Queue p99 ms | Max queues discretionary/mandatory |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 30 | 0 | 0 | n/a | n/a | 0 | 0.05 | 0/0 (caps 8/6) |
| 80 | 91 | 20 | 9 | 20/20 | 20/20 | 0 | 39.75 | 0/3 (caps 8/6) |
| 400 | 71 | 30 | 499 | 30/30 | 30/30 | 0 | 20.91 | 8/6 (caps 8/6) |

At the highest load, degradation and rejection both occurred; every served degraded request completed mandatory assessment, none selected Tier 2, and 0 rejected requests generated text.

## Same-run before and after

| Path | Achieved RPS | Effect p99 ms | Effect p99.9 ms | Rejected |
|---|---:|---:|---:|---:|
| unbounded | 198.4 | 1508.12 | 1526.42 | 0 |
| bounded | 63.7 | 104.07 | 112.81 | 499 |

The bounded path trades throughput for bounded work and explicit overload responses. Its tail values apply only to served requests, so they are not a detector speedup.

## Budget signal

| Policy | Offered RPS | Lambda start | Lambda end | Lambda maximum |
|---|---:|---:|---:|---:|
| unbounded | 20 | 0.000 | 34.300 | 34.300 |
| bounded | 20 | 0.000 | 34.300 | 34.300 |
| unbounded | 80 | 0.000 | 137.200 | 137.200 |
| bounded | 80 | 0.000 | 119.548 | 119.548 |
| unbounded | 400 | 0.000 | 472.203 | 472.203 |
| bounded | 400 | 0.000 | 83.308 | 83.308 |

This work item did not change the proportional budget controller. A target equilibrium, overshoot and settling-time criterion will be registered before the controller-dynamics work; none is inferred from this short saturation run.
