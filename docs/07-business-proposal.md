# Business proposal

## Decision to fund

Fund a limited shadow-mode pilot, not a production safety claim. The pilot should test whether
expected-loss allocation produces more labelled harm caught per assurance rupee than fixed-rate
checking while a route risk floor remains intact.

## Target users and their concerns

| Stakeholder | Decision they own | Concern answered by the prototype | Evidence they should demand |
| --- | --- | --- | --- |
| CFO / FinOps | Assurance budget and incident reserve | A visible cut line, spend variance, and loss sensitivity | Equal-spend curve using approved cost ranges |
| Head of Product | User latency and intervention burden | Text and effect latency separated; abstention and false positives reported | Route-level p99 and reviewer queue volume |
| Risk and Compliance | Minimum control and audit evidence | Per-route floor, jurisdiction policy version, held effects, hash links | Label protocol, calibration bound, audit export |
| Head of AI Platform | Integration and provider portability | OpenAI-shaped gateway and input/output-only adapters | Load test, provider adapter, failure-mode runbook |

## Proposed pilot

Run for six weeks on one support route and one held-effect FinOps route. Weeks 1-2 are shadow only:
sample outcomes, label detector catches, estimate consequence ranges, and measure latency. Weeks 3-4
compare fixed-rate and allocation policies offline at equal spend. Weeks 5-6 enable holds only for a
small set of reversible or financially capped effects, with human approval.

Production promotion requires all of the following:

- allocator ROI exceeds fixed-rate at equal spend across agreed budget bands and confidence intervals;
- the route release-risk upper bound remains under its approved alpha on fresh labels;
- every proposed effect has an audit decision and the external sink meets retention requirements;
- p99 added latency stays inside the route SLO;
- sensitivity analysis shows decisions remain stable across approved consequence ranges;
- incident and override owners approve the operational runbook.

## Business case model

The model is intentionally input-driven. For route `q` and harm axis `j`, avoided loss is estimated as
checked interactions times calibrated risk `r_qj`, consequence `c_qj`, and measured catch rate `k_tj`.
Assurance spend includes the chosen check and delay cost. Human review should be added as queue volume
times handling minutes times loaded reviewer rate.

No payback period is asserted from the synthetic report. Finance supplies low/base/high `c`; Platform
supplies measured `v` and `d`; Risk supplies alpha and label rules. The ledger exposes the terms used
for every decision so the resulting business case can be challenged.

## Delivery roadmap

| Phase | Scope | Exit evidence |
| --- | --- | --- |
| Competition prototype | Offline gateway, eight scenarios, fixtures, report, console | Reproducible commands and honest baseline comparison |
| Shadow pilot | Real detector adapters, provider adapter, random audit slice | Catch posteriors, route calibration, latency benchmark |
| Controlled effects | Reviewer queue, identity, capped held actions | No unaudited effects and approved override workflow |
| Scale decision | Shared controller, signed policy releases, audit sink | Multi-worker load, recovery test, policy deployment controls |

## Principal risks and mitigations

| Risk | Consequence | Mitigation and stop condition |
| --- | --- | --- |
| Cost values steer the wrong traffic | False confidence in the allocator | Range analysis; stop if over 20% of decisions flip |
| Selective labels inflate catch rate | `k` becomes biased | Retain a random shadow-audit slice |
| Drift invalidates the route bound | Mandatory misses increase | Window monitoring, label refresh, revert to broader coverage |
| Text harm streams before verdict | User exposure | Blocking output checks on high-consequence text routes |
| Floor exceeds budget | Budget target cannot be met | Report infeasible state; never relax alpha silently |
| Policy configuration is stale | Wrong jurisdiction behavior | Effective dates, signed release, dual approval, trace hash |

## Dataset workstream

The first external study should use LLM-AggreFact for grounded factuality and BBQ for bias. Prompt
injection and PII datasets need licence approval before redistribution. The dataset decision record,
access conditions, and non-inclusion reasons are in `06-datasets.md` and `data/dataset_manifest.yaml`.
