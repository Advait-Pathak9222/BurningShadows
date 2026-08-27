# When budget-aware allocation is worth deploying

Budget-aware allocation is the mechanism this project is named after. It is **not** universally
better than a well-ranked fixed-rate policy. This page says exactly when it helps, how that was
established, and which of our own earlier claims did not survive the check.

---

## Two errors in how this was measured, both ours

### 1. The comparison was never at matched spend

The pre-registered endpoint said "at matched assurance spend". It was not. The allocator's budget is
not a constraint on it — the conformal floor forces mandatory checks regardless of the shadow price —
while the fixed-rate baseline was held to the budget exactly. At tight budgets the allocator was
spending **28x its budget** and being credited with the extra loss it averted.

Every "win" reported at a tight budget was that artifact. The comparison below gives the baseline
exactly what the allocator actually spent.

### 2. Every budget ever tested was in the regime where allocation cannot help

The budget grid was defined as a fraction of full **Tier 2** coverage. Blanket **Tier 1** coverage
costs `n x 0.18` against `n x 3.20`, so cheap blanket coverage stays affordable until the budget
fraction falls below **5.625%**. The tested grid was 10% to 100% — entirely above it. At every point
we ever measured, the baseline could simply check every row at Tier 1, and no selective policy can
beat blanket coverage when blanket coverage is affordable.

`fixed_rate` on the shipped corpus at a 10% budget spent exactly ₹270.00 = 0.18 x 1500. It had been
blanket Tier 1 the whole time.

---

## The result, at matched actual spend

Allocator against the best tuned fixed-rate policy, both spending the same rupees.

| Budget fraction | Synthetic | BeaverTails 7% | BeaverTails natural |
|---:|---:|---:|---:|
| 1.0% | −0.83% | **+10.28%** | 0.00% |
| 3.0% | −0.21% | −13.16% | 0.00% |
| 5.6% | **+0.79%** | −20.49% | +0.01% |
| 10% | **+1.93%** | −13.96% | 0.00% |
| 25% | **+3.62%** | **+5.55%** | +0.10% |
| 50% | **+2.44%** | **+10.65%** | +0.08% |
| 100% | +0.14% | **+11.24%** | −0.49% |
| **wins** | **5 of 7** | **4 of 7** | **3 of 7** |

Gains span −20% to +11%. There is no budget at which allocation is reliably better across all three,
and no corpus on which it wins everywhere.

---

## What the gain actually depends on

**The harm mix has to vary.** Expected loss is `risk x consequence`. If every flagged row is the same
kind of harm, the consequence multiplier is a constant and expected-loss ranking is a monotone
rescaling of risk ranking — which is exactly what the baseline already does. On ToxicChat, which
labels one effective axis, `Spearman(risk, expected loss) = 1.000000` and the allocator is sorting
the identical list.

This is not about route count, which was our first and wrong explanation. Restricted to a single
route, the shipped corpus still gives 0.83–0.96, because *which* axis fires changes the price:
`hallucination` is ₹5,000 and `pii_leak` ₹18,000, so two rows with identical risk carry different
expected loss.

| Corpus | Axes firing per row | Rows on >1 axis | Spearman |
|---|---:|---:|---:|
| ToxicChat | 1.00 | 0% | **1.000000** |
| BeaverTails 7% | 1.06 | 16.8% | 0.998494 |
| Synthetic | 1.51 | 43.9% | 0.941539 |

**Below about 0.99 the mechanism has something to work with; at 1.0 it provably cannot.** That number
is computable on any corpus before running an allocation experiment, and it should be, because two
of our pre-registrations were spent discovering it the slow way.

---

## One fix that looked obvious and was wrong

Tier 1 costs ₹0.18 and catches 0.65–0.90; Tier 2 costs ₹3.20 and catches 0.83–0.94. Per rupee, Tier 1
is roughly 16x more efficient, and `_select_tier` maximises **net value**, so it escalates to Tier 2
whenever expected loss is large — spending budget that would have bought seventeen times the
coverage. The project had already found the analogous result for the reviewer queue, where the
`density` rule beat the shipped one.

Ranking tiers by benefit per rupee instead was measured, and it is **worse by 26% to 58%**. Per-row
density always selects Tier 0, the cheapest, and never escalates at all. The knapsack is over
`(row, tier)` pairs across the whole stream, not within one row; given a shadow price, per-row
maximisation of net value is already the correct Lagrangian rule. The change was not made.

---

## The honest statement

> Budget-aware allocation earns its place when the harm mix varies across traffic and blanket
> coverage at the cheapest effective tier is unaffordable. Where either condition fails it is at
> best neutral and can be materially worse. Both conditions are computable in advance from the cost
> model and the label structure, so an operator can tell before deploying whether this mechanism is
> worth anything to them.

That is narrower than the claim this project started with, and it is the one that survives three
public corpora and a matched-spend comparison.
