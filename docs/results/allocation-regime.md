# When budget-aware allocation is worth deploying

Budget-aware allocation is the mechanism this project is named after. It is **not** universally
better than a well-ranked fixed-rate policy. This page says exactly when it helps, how that was
established, and which of our own earlier claims did not survive the check.

*Written interpretation. Every number on this page comes from a file written by `make report`
(synthetic corpus) or `make benchmarks` (BeaverTails, Aegis, OR-Bench) — see the `budgets` and
`harm_mix` blocks in `docs/results/*.json`.*

---

## Two errors in how this was measured, both ours

### 1. The comparison was never at matched spend

The pre-registered endpoint said "at matched assurance spend". It was not. The allocator's budget is
not a constraint on it — the conformal floor forces mandatory checks regardless of the shadow price —
while the fixed-rate baseline was held to the budget exactly. At tight budgets the allocator was
spending **28x its budget** and being credited with the extra loss it averted.

Every "win" reported at a tight budget was that artifact. The comparison below gives the baseline
exactly what the allocator actually spent.

**This has since been fixed at the source rather than only in the comparison.** `BudgetGovernor`
reserves the conformal floor's own expected cost, so discretionary spending stops before it eats
the reservation and the allocator degrades to mandatory-only instead of overspending. Spend now
lands at **1.00x-1.03x of budget** across the whole grid, against up to 3.75x before, and no
conformally-forced row goes unchecked at any budget tested. The remaining case is a budget set
*below* the floor cost, which is reported as infeasible rather than silently breached.

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
and no corpus on which it wins everywhere. Aegis (1 of 7) and OR-Bench (3 of 7) were added later
under the budget governor and are reported in [aegis.md](aegis.md) and [orbench.md](orbench.md).

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
| **Aegis, permissive** | 1.09 | — | 0.909260 |
| **Aegis, defensive** | 1.09 | — | **0.815965** |

**Below about 0.99 the mechanism has something to work with; at 1.0 it provably cannot.** That number
is computable on any corpus before running an allocation experiment, and it should be, because two
of our pre-registrations were spent discovering it the slow way.

### The precondition is necessary, and it is not sufficient

Aegis is the first **public** corpus on which condition 1 actually holds — Spearman 0.816, well
clear of the degenerate end. If the harm mix were the only thing standing between the allocator and
a win, this is where the win would appear.

It does not. On Aegis the allocator wins **1 of 7** budgets, with gains between -1.14% and +0.10%.

The reason is the second condition, and it is arithmetic. Blanket Tier 1 on Aegis costs 216 INR
against 3,837 INR for full Tier 2 — the boundary at **5.6250%**, identical to every other corpus
because it is `0.18 / 3.20` and nothing else. Below that boundary the conformal floor already obliges
215.82 INR, so **the floor is blanket coverage** and there is nothing left to allocate. Above it,
blanket Tier 1 is affordable and no selective policy beats blanket coverage.

OR-Bench says the same thing at a different scale: boundary 5.6250%, floor 175.86 INR against a
blanket Tier 1 cost of 176 INR, allocator wins 3 of 7 with gains of at most +1.16%.

So the honest statement of the mechanism's value needs **both** conditions, and on every public
corpus tested so far at least one of them fails.

---

## One fix that looked obvious and was wrong

Tier 1 costs ₹0.18 and catches 0.65–0.90; Tier 2 costs ₹3.20 and catches 0.83–0.94. Per rupee, Tier 1
is roughly 16x more efficient, and `_select_tier` maximises **net value**, so it escalates to Tier 2
whenever expected loss is large — spending budget that would have bought seventeen times the
coverage. The project had already found the analogous result for the reviewer queue, where the
`density` rule beat the shipped one.

Ranking tiers by benefit per rupee instead was measured during development and was substantially
worse. **That measurement is not a committed artifact and no number from it is quoted here**, because
this repository should not carry figures that `make` cannot reproduce.

The reason it fails is structural and can be checked by reading the code rather than trusting a
number. Per-row benefit-per-rupee is maximised by the cheapest tier whenever the catch rates are
within a small factor of one another, so `_select_tier` would return Tier 0 for every row and never
escalate. The knapsack here is over `(row, tier)` pairs across the whole stream, not within a single
row; given a shadow price, per-row maximisation of **net value** — which is what
`controlplane/economics/allocator.py` does — is already the correct Lagrangian rule. The change was
not made.

---

## The honest statement

> Budget-aware allocation earns its place when the harm mix varies across traffic and blanket
> coverage at the cheapest effective tier is unaffordable. Where either condition fails it is at
> best neutral and can be materially worse. Both conditions are computable in advance from the cost
> model and the label structure, so an operator can tell before deploying whether this mechanism is
> worth anything to them.

That is narrower than the claim this project started with, and it is the one that survives three
public corpora and a matched-spend comparison.
