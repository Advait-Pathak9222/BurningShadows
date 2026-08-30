# Business proposal

## What we are selling

Enterprises running generative AI at scale face a checking problem with no ceiling. Verifying an
answer properly means a second model re-reading it, which roughly doubles cost and latency, so the
practical choices are to check everything (unaffordable), check nothing (liability), or check on a
fixed rule that ignores what is actually at stake.

ControlPlane reframes verification as capital allocation. The business sets an assurance budget and
the system spends it where mistakes cost the most, under a per-route floor that cannot be traded
away. The differentiator is not detection quality. It is that **how much traffic gets checked is an
output of the economics, not a configuration value** — and that the floor is a finite-sample
guarantee rather than a promise.

## The finding that shapes the case

Building the reviewer queue changed what this product is about. Measured on 1500 held-out
interactions and scaled to the problem statement's 30,000 interactions per week:

| Budget | Compute | Attention (queue) | Total | Attention share | Audit slice |
|---:|---:|---:|---:|---:|---:|
| 10% | 13,218 | 398,400 | 411,618 | **96.8%** | 470,400 |
| 100% | 69,412 | 398,400 | 467,812 | 85.2% | 319,200 |

All figures INR per week.

**Between 85% and 97% of the cost of assurance is human attention, not compute.** A review costs
INR 120 against INR 3.20 for the dearest automated check — 38x. Every guardrail vendor competes on
the 2-10%. The reviewer queue is where the money is, and it is the resource the allocator now
budgets.

Attention here is **queue cost only** — the reviewer minutes the system's own verdicts consume. The
audit slice is shown separately because it is measurement apparatus rather than an operating cost:
it is what we spend to learn our catch rate, and it is largest at a tight budget precisely because
that is when most traffic goes unchecked and a random sample is the only place a miss becomes
visible. **Counting it into the headline would be charging the customer for our instrumentation.**
A buyer who does not want measured catch rates does not pay it.

Two consequences worth stating plainly to a buyer:

- **Buying more automated checking increases the human bill.** Raising the compute budget takes
  cases raised from 295 to 453 per 1500 interactions, because more checking produces more holds,
  abstentions and blocks. Assurance spend is not a substitute for reviewer headcount; without
  allocation it is a multiplier on it.
- **The queue is already 2.7x oversubscribed** at two reviewers on shift: 9,060 cases raised per
  week demanding 906 reviewer-hours against 333 available, and 63% of cases shed. Intervention
  precision is 0.396, so three fifths of what is escalated a reviewer disagrees with. That is alert
  fatigue, measured rather than asserted. **Keeping up with arrivals at all needs 4.1 reviewers
  against the two configured**, and no queue rule substitutes for that. Allocation decides which
  cases a short-staffed desk loses; it cannot decide that the desk is short-staffed.

## Where the money comes from

The unit economics are input-driven and every term is exposed in the audit record so Finance and
Risk can challenge it.

| Term | Source | Status |
|---|---|---|
| Reviewer rate and handling time | Invoice and queue study | **Defensible.** This is a real number a CFO already owns |
| Check price `v` | Provider token prices | Defensible once a real provider adapter is in place |
| Catch rate `k` | **Measured from reviewer labels plus a stratified audit slice** | Tier 2 measures 0.950 against a configured 0.880 over 398 observations; Tier 1 measures 0.593 against 0.680 over 23 |
| Consequence `c` | Finance and Risk, low/base/high | **Assumption, now bounded.** Still our softest input, but `make sensitivity` shows 10.9% of decisions move across a 0.25x-4x band and the *verdict* never does |

The value side is deliberately not headlined. The synthetic corpus produces a loss-averted figure in
the millions per week, and that number is a property of our assumed `c`, not evidence. What can be
defended today is the cost side, the catch rates, and the guarantee.

## Commercial model

| Element | Proposal |
|---|---|
| Deployment | Self-hosted alongside the customer's existing gateway. It is an OpenAI-shaped endpoint, so integration is a base-URL change |
| Pricing | Per 1,000 interactions assessed, with the assurance budget set by the customer. Cost per 1k is already a reported metric |
| Land | One customer-facing route in shadow mode. No enforcement, no latency risk |
| Expand | Add the effect-bearing route, then enforcement on capped effects |
| Value narrative | Reviewer hours redirected, not GPU spend saved. The buyer is whoever owns the review function |

The buyer is the Head of AI Platform or Chief Risk Officer, and the budget usually already exists as
manual review headcount rather than as a tooling line.

## Cost of doing nothing

Two baselines the customer already pays, both derivable from their own data in a two-week study:

1. **Unchecked release.** With no verification, our measured residual loss is 10.4x the allocator's
   on the same traffic. The customer's equivalent is their incident rate times their own consequence
   range.
2. **Blanket manual review.** Reviewing every flagged case at current flag rates is what the 2.7x
   oversubscription describes. Most organisations are already silently shedding; they simply do not
   measure it.

Note honestly: **a tuned blanket-Tier-1 baseline gets within 1.1% of our loss averted** at a
fraction of the compute spend. Our advantage on compute alone is small, and once both policies are
charged the reviewer minutes they generate it is smaller still — the baseline's ROI advantage falls
from 2.28x to 1.002x at the tight budget, but because the attention bill dwarfs compute for both, not
because allocation improved.

Where we do beat the obvious alternative is on the resource that costs the money. Our reviewer
queue serves **1.59x the expected loss FIFO does from the same reviewer-hours**, breaching 65 SLAs
against 139 and dropping 2 top-decile cases against 15. At two thirds of a desk's output being shed,
that is the difference between losing your cheapest cases and losing your most expensive ones.

State it with its caveats, because they are the reason to trust it: the first run of that
pre-registered comparison **failed**, under a queue model of ours that had no arrival times; we
found and committed the defect before fixing it, then re-ran. And an ablation without our deadline
term still beats the full rule at every budget, so the rule as shipped is not the best version of
itself. `docs/results/attention.md` has all of it.

## Target users

| Stakeholder | Decision they own | What the prototype answers | Evidence to demand |
|---|---|---|---|
| CFO / FinOps | Assurance budget and reviewer headcount | Total cost of assurance split into compute and attention | Equal-spend curve on approved cost ranges |
| Head of Product | Latency and intervention burden | Text and effect latency separated; precision and shed rate reported | Route p99 and queue volume |
| Risk and Compliance | Minimum control and audit evidence | Per-route floor, jurisdiction policy version, overrides in the hash chain | Label protocol, calibration bound, audit export |
| Head of AI Platform | Integration and portability | OpenAI-shaped gateway, input/output-only adapters, admission control | Load test, provider adapter, failure runbook |

## Pilot

Six weeks, one support route and one effect-bearing FinOps route.

- **Weeks 1-2, shadow only.** Sample outcomes, label detector catches, estimate consequence ranges,
  measure latency. No enforcement.
- **Weeks 3-4.** Compare fixed-rate against allocation offline at equal spend, and against equal
  reviewer minutes.
- **Weeks 5-6.** Enable holds for reversible or financially capped effects, with human approval.

Promotion to production requires all of:

- allocator ROI exceeds fixed-rate at equal spend across agreed budget bands, with intervals;
- the route release-risk upper bound stays under approved alpha on fresh labels;
- every proposed effect has an audit record and the sink meets retention requirements;
- p99 added latency stays inside route SLO;
- decisions remain stable across approved consequence ranges;
- incident and override owners approve the runbook.

## Roadmap

| Phase | Scope | Exit evidence |
|---|---|---|
| Competition prototype | Offline gateway, scenarios, review loop, admission control, report | Reproducible commands, honest baseline comparison |
| Shadow pilot | Real detector adapters, provider adapter, stratified audit slice | Catch posteriors, route calibration, latency benchmark |
| Controlled effects | Reviewer identity, capped held actions, durable effect leases | No unaudited effects, approved override workflow |
| Scale | Shared calibration artifact, signed policy releases, external audit sink | Multi-worker load, recovery test, policy deployment controls |

## Principal risks

| Risk | Consequence | Mitigation and stop condition |
|---|---|---|
| `c` steers the wrong traffic | False confidence in the allocator | **Measured**: 10.9% of decisions flip across a 0.25x-4x band against a 20% stop condition, and the verdict never moves. Worst single draw is 27.7% and does breach |
| Selective labels inflate `k` | Catch rate is biased upward | Stratified audit slice, already implemented and costed |
| Reviewer capacity is the real constraint | The allocator optimises the wrong budget | **Confirmed, and it is.** Attention is 85-97% of total cost, the queue needs 4.1 reviewers to keep up against two configured, and our serving rule only beat FIFO after we corrected our own queue model |
| Drift invalidates the route bound | Mandatory misses rise | Window monitoring, label refresh, widen coverage |
| Text streams before a verdict | User exposure | Blocking output checks on high-consequence text routes |
| Floor exceeds budget | Budget target unmeetable | Report infeasibility; never relax alpha silently |
| Policy configuration stale | Wrong jurisdiction behaviour | Effective dates, signed release, dual approval, trace hash |

## What we are not claiming

The corpus is synthetic and generated by us. The loss figures are arithmetic on an assumed
consequence range, not evidence of production loss reduction. Detector stubs are lexical, so latency
and throughput numbers describe our harness.

Three things we set out to prove and did not:

1. **Round 1 dominance over a fixed-rate baseline.** The margin is 1.0% to 5.4% on loss averted, and
   a blanket cheap check gets within 1.1% for a fraction of the spend.
2. **That allocating compute meaningfully lowers total assurance cost.** It does not, because
   compute is 3% to 16% of the bill.
3. **That our reviewer queue allocates attention better than a naive one, first time.**
   Pre-registered, tested, **failed** — then we found that our own queue model had no arrival times,
   fixed it, and the re-run passed. Discount it accordingly; we do.

**And an ablation beats the rule we ship.** Removing the deadline term from the queue serves more
expected loss and breaches fewer SLAs at every budget. We are reporting a result that says our own
design is not its best version, because pre-registration 3 said an ablation beating the full rule
becomes the headline.

What we do stand behind, because it is measured rather than asserted: **the cost structure.**
Attention is 81% to 98% of assurance cost. The queue is 2.7x oversubscribed and needs 4.1 reviewers
where two are staffed. Intervention precision is 0.396, so three fifths of what reaches a person is
something they disagree with. Catch rates come from labels, not config: Tier 2 at 0.950 against a
configured 0.880 over 398 observations. And 10.9% of decisions move across a 4x swing in the softest
input we have, while the verdict does not move at all.

That is the honest pitch: **we cannot yet prove we allocate better than the obvious alternatives,
and we can prove that nobody — including us — was measuring the resource that actually costs the
money.** The second is the more valuable finding, and it is the one a buyer can act on this quarter.
