# The review loop: allocating attention, not just compute

> **This is the plan, written before the work.** It is kept as a record of what was intended
> rather than updated to match what exists, so the "we have almost nothing for this" framing
> below describes the state at the time of writing, not today. What shipped: R1 the review
> queue, R2 the stratified audit, and R4 session risk. R3 shipped by halves — `make relearn`
> refits the calibration maps from reviewer labels under a release gate, but its own "done
> when" is not met, because the measured catch rate is still reported rather than fed back
> into anything the allocator reads. `docs/LIMITATIONS.md` carries the outstanding half.

## Why

The problem statement names three things we have almost nothing for:

- **"Clear rules for when a human should be pulled in."** We have a policy field and an `abstain`
  verdict. There is no queue, no reviewer, no SLA, and nothing captured.
- **Feedback loops — how flagged or overridden cases improve detection over time.** `ReviewOverride`
  exists as a five-field dataclass with zero callers.
- **Multi-turn conversations and agents that compound risk.** `ConversationRiskAccumulator` exists
  with zero callers.

They are not three features. They are one workflow, and building it closes all three.

There is also a business reason, and it is the stronger one. From `docs/03-assumptions.md` and the
committed results:

| | Cost |
|---|---:|
| One Tier 2 automated check | INR 3.20 |
| One human review (INR 1,200/hr, 6 min) | **INR 120.00** |

A human review costs **38x** the most expensive automated check. At full budget the allocator spends
INR 3,800 per 1500 interactions on checking, which is INR 2.53 per interaction. Scaled to the
problem statement's 30,000 interactions per week:

| | Weekly | Reviewer-hours |
|---|---:|---:|
| All automated checking | INR 76,000 | — |
| Human review, abstentions only (2.6% measured) | INR 93,600 | 78 |
| Human review, everything not released (15.6% measured) | INR 561,600 | 468 |

**Human attention already costs more than every automated check combined, and the allocator does not
model it at all.** It optimises the smaller number and ignores the larger one.

This is not a pivot. It is the same rule on a scarcer resource: today `v` is a token price; the
generalisation is that reviewer capacity is a second budget with its own shadow price, and
`sum_j(r_j * c_j * k_tj) > (1 + lambda) * (v_t + d_t)` allocates attention exactly as it allocates
compute. Alert fatigue — a named complexity in the problem statement — stops being a metric we
report and becomes the constraint we optimise.

It also repairs our softest number. `c` has no derivation and we have said so repeatedly. Reviewer
cost is an invoice-backed figure. An ROI denominated in analyst hours is defensible in a way a
hypothesised hallucination cost is not.

## The shape

```
verdict in {abstain, hold, block}
    -> review queue          priority by expected loss per reviewer minute, with an SLA deadline
    -> reviewer decision     uphold or overturn, with a reason code
    -> ledger                override appended to the hash chain, provenance preserved
    -> recalibration         reviewer labels give measured k per tier and corrected r
    -> session state         a held or overturned turn raises the bar for later turns
```

Three budgets, one rule:

| Resource | Budget | Governed by |
|---|---|---|
| Compute | assurance spend per hour | shadow price `lambda_compute` |
| Attention | reviewer minutes per hour | shadow price `lambda_attention` |
| Neither | — | the conformal floor, which overrides both |

## Stages

Each stage leaves `make check` green, `make demo` offline, and the corpus byte-reproducible. Each
gets a row in `progress.csv` and a commit.

### R1 — Review queue as a second allocator

New `controlplane/review/`. A `ReviewCase` carries the interaction, the verdict that raised it, its
expected loss, an estimated review cost in minutes, and an SLA deadline from route policy. The queue
admits by expected loss per reviewer minute, subject to capacity, with deadline-aware promotion so a
low-value case cannot starve forever.

Config: `review:` block in `config/economics.yaml` (reviewer rate, minutes per case, capacity per
hour) and `review_sla_minutes` per route in the policy packs.

New metrics, reported alongside the existing ones: attention spend in rupees, queue depth, wait
time, SLA breach rate, and **total assurance cost = compute + attention**. That last one is the
headline the business case has been missing.

**Done when** the evaluation reports total cost of assurance with both components, and the review
queue is visible in a decision trace.

### R2 — Override capture

A `ReviewOutcome` — case, reviewer, decision, reason code, timestamp — appended to the existing
hash chain. Provenance for "who approved this transfer" becomes answerable forensically. Cheap,
because the chain already exists and already verifies.

**Done when** an override is in the ledger, the chain still verifies, and a test proves tampering
with an override breaks it.

### R3 — Recalibration from reviewer labels

Reviewer decisions are ground truth. They give measured `k` per tier through the beta-binomial
estimator that currently only appears in a staged demo, corrected `r`, and a drift signal. This is
the answer to the standing objection that `k` is a config constant rather than a measurement.

**Done when** `k` in the report comes from labels rather than YAML, and the change in the numbers is
reported honestly whichever way it goes.

### R4 — Session risk, wired in

`ConversationRiskAccumulator` gets a caller and session state, so a questionable turn raises the bar
for later turns in the same session. Closes the multi-turn complexity named in the problem statement.

**Done when** a two-turn scenario shows the second turn checked at a higher tier than it would have
been alone.

### R5 — Presidio behind the detector interface

`presidio-analyzer` is declared in `pyproject.toml` and imported nowhere, which makes "we compose
with real detectors rather than replacing them" a claim with nothing behind it. It is offline,
CPU-only and pip-installable, so it fits behind the existing `Detector` interface without touching
the demo path.

**Done when** a labelled PII comparison against the regex baseline is committed, reporting whichever
way it goes.

### R6 — Business case on measured attention economics

Rewrite the business case around total cost of assurance, with the reviewer figure derived rather
than assumed, plus a commercial model and a cost-of-doing-nothing baseline. These are the three
holes in a deliverable that is one third of the grade.

## Guardrails this must ship with

- **SLA breach is fail-safe.** A case that ages past its deadline escalates or blocks. It must never
  silently release.
- **Queue overflow sheds to the conformal floor**, never below it. The mechanism belongs to the
  runtime lane; the policy belongs here.
- **Two-person rule** for financial and irreversible effects.
- **Review thresholds are economically derived**, not the hardcoded 0.35 / 0.45 / 0.88 currently in
  `allocator.py`.
- **Overrides are in the hash chain**, so an override cannot be edited after the fact undetected.

## What this deliberately does not do

No authentication, multi-tenancy, rate limiting or telemetry backend. No reviewer UI beyond what the
console already renders. Those are undifferentiated and would consume the time the loop needs.
