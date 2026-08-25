# Pre-registration: does paged verification earn its place?

Written before the paged-verification work was built, so the bar cannot move once results
arrive. Locked at commit `e5ae957`, corpus `manifest_version: 2`, seed `20260823`.

## The claim under test

ControlPlane currently allocates assurance one fixed-size slot per request: a 20-token answer
and a 1000-token answer both consume one Tier 2 check at a flat 3.20 INR. The claim is that
making verification divisible — allocating Tier 2 over spans of a response rather than over
whole responses — lets the allocator buy the expensive check only where consequence
concentrates, and therefore closes the gap to a tuned blanket-Tier-1 baseline.

If that is true it should show up in one place: the tight-budget rows, where we currently lose.

## The locked baseline

From `docs/results/summary.md` at `e5ae957`, on 1500 held-out rows:

| Budget | Policy | Spend (INR) | Loss averted (INR) | Assurance ROI | Coverage |
|---:|---|---:|---:|---:|---:|
| 10% | allocator | 677.66 | 5,660,800 | 8,353 | 0.482 |
| 10% | fixed_rate (tuned) | 270.00 | 5,594,700 | **20,721** | 1.000 |
| 25% | allocator | 1,169.92 | 5,913,800 | 5,055 | 0.485 |
| 25% | fixed_rate (tuned) | 270.00 | 5,594,700 | **20,721** | 1.000 |

Reference points: `check_all` averts 6,259,500 for 4,800.00 (ROI 1,304); `check_none` averts 0.

The baseline wins ROI by **2.48x at the 10% budget and 4.10x at the 25% budget**. That gap is
the thing being attacked. It exists because blanket Tier 1 over all 1500 rows costs only 270 INR
and lands within 1.2% of the allocator's loss averted.

## Primary endpoint

**Assurance ROI at the 10% and 25% budget rows**, with loss averted not regressing.

Success is declared only if, at **both** rows:

1. `allocator.assurance_roi >= fixed_rate.assurance_roi`, and
2. `allocator.loss_averted_inr` is at least the locked value above.

Partial success: the ROI ratio `fixed_rate / allocator` falls to **1.5x or below** at both rows
(from 2.48x and 4.10x), with loss averted not regressing.

Failure: anything else. Including — explicitly — a result where loss averted rises but ROI does
not improve, because that is just buying more checks.

## Secondary endpoints, reported either way

- Loss averted at matched absolute rupees, not matched budget fraction. The tuned baseline
  under-spends its limit whenever blanket Tier 1 beats partial Tier 2, so `summary.md` prints
  both spends and the comparison must be read at the spend actually incurred.
- `escaped_harm_rate_effective` must not rise. Buying fewer, better-targeted checks must not
  quietly release more harm.
- The conformal bound must still hold on held-out data on all three routes at alpha 0.10.
- Detector invocations avoided and INR saved, both counter-based.

## Methodology guards

These exist because the same change that rewrites the corpus also changes the cost model, and
both push in the direction that flatters us.

1. **The corpus is held fixed across the comparison.** The before/after must both be measured on
   the multi-claim corpus. Comparing new-corpus-paged against old-corpus-flat measures nothing.
   The locked table above will therefore be **re-derived** on the new corpus with the unpaged,
   flat-cost allocator, and that re-derived row is what paging is judged against. The table above
   is the record of where we started, not the comparator.
2. **Price calibration is asserted by a test.** Token-proportional cost must satisfy
   `cost_fixed + cost_per_unit * mean_units == 3.20` at the corpus mean length. Without it, paging
   looks cheap because the price changed rather than because allocation improved.
3. **Coverage-weighted catch lands before segmentation is switched on.** `_caught_loss` currently
   draws catch once per interaction, so a run that reads 20% of the text would still claim a full
   catch — reading less, paying less, reporting the same. The fix must be committed and the
   results regenerated *before* `segmenter: sentence_v1` is enabled, never after.
4. **The decision thresholds in `allocator.py` (0.35 / 0.45 / 0.88) are not tuned during this
   change.** Moving them while the score distribution changes would make the result
   unfalsifiable.
5. **No metric substitution.** If the primary endpoint fails, it is reported as a failure in
   `README.md` and `docs/LIMITATIONS.md`. A different metric is not promoted in its place.

## What happens on failure

Paging is reported as not having earned its place, the mechanism stays behind
`segmenter: whole_response`, and the honest conclusion is written down: on this workload a cheap
blanket check is hard to beat, and the allocator's value is confined to buying the expensive tier
where consequence is high. That is the same discipline applied when the Round 1 dominance claim
failed.

---

# Pre-registration 2: is the baseline's ROI advantage an accounting artifact?

Written before the change was implemented and before any new number was produced. Locked at
commit `c5cc876`, corpus `manifest_version: 3`, seed `20260824`.

## The claim under test

The committed comparison charges the allocator for the reviewer minutes its verdicts consume
and charges the baselines nothing. It also lets the allocator block or abstain — a response
that never reaches anyone counts as fully averted — while forcing every baseline row to be
released. `docs/LIMITATIONS.md` already names the second of these as flattering us.

So the two policies are not being compared on the same terms in either direction. The claim is
that the honest comparison is a **single decision path** where allocator and baseline differ
only in *which rows are checked and at what tier*, with both:

1. running the shipped verdict rule, so both can block, abstain, hold or annotate, and both are
   credited for harm that never reached anyone; and
2. charged the reviewer minutes their own verdicts raise, through the same queue, with the same
   capacity and the same shedding.

## Why this is not a result we are steering toward

The two corrections push in opposite directions and we do not know which dominates.

- **Against us:** giving the baselines block-and-abstain credit removes a modelling advantage we
  have documented as ours. Baseline loss averted should rise.
- **For us:** blanket Tier 1 checks every row, and a checked row is far likelier to produce a
  verdict that raises a review case. At INR 120 a case against INR 0.18 a check, the baseline's
  270 INR of compute may be attached to a much larger attention bill.

There is also a real possibility of **no effect**: reviewer capacity is fixed, so if both policies
saturate the queue they pay the same attention bill and the ROI ranking is unchanged. That outcome
is reported as no effect, not as a win.

## Primary endpoint

**Total assurance ROI at the 10% and 25% budget rows**, where

```
total assurance ROI = loss_averted_inr / (compute_spend_inr + attention_spend_inr)
```

Success is declared only if, at **both** rows:

1. `allocator.total_assurance_roi >= fixed_rate.total_assurance_roi`, and
2. `allocator.loss_averted_inr` does not fall below its value at commit `c5cc876`.

Partial success: the ratio `fixed_rate / allocator` on total ROI falls to **1.5x or below** at
both rows, from the 2.26x and 3.72x it stands at now on compute-only ROI.

Failure: anything else — including a result where the allocator wins because it raised fewer
cases while shedding more of them. See the shedding guard below.

## Secondary endpoints, reported either way

- Cases raised, cases served, cases shed, and shed rate, **per policy**. A policy that appears
  cheaper because it overloads the queue and sheds the overflow has not saved anything; it has
  moved unreviewed risk off the books. If the winning policy also sheds more, the result is
  reported as inconclusive.
- `escaped_harm_rate_effective` per policy. Blocking more is not free if it is indiscriminate.
- Release rate and abstention rate per policy, so the block-and-abstain credit is visible rather
  than buried in the averted figure.
- Compute-only ROI stays in the table. The new number is reported next to it, not instead of it.

## Methodology guards

1. **The verdict rule is not touched.** `_verdict` in `economics/allocator.py` and its thresholds
   0.35 / 0.45 / 0.88 are used exactly as shipped for both policies. Tuning them during this
   change would make the result unfalsifiable.
2. **The queue, its capacity, and the shedding rule are not touched.** `config/economics.yaml`
   `review:` block stays as committed.
3. **The corpus is not regenerated.** Same manifest, same seed, byte-identical JSONL.
4. **Both corrections land in one commit.** Landing the attention charge first and the
   block-and-abstain credit second would let us read the intermediate number and stop early.
5. **No metric substitution.** If the primary endpoint fails, it is written into `README.md` and
   `docs/LIMITATIONS.md` as a failure, and the compute-only ROI table stands as the headline.

## What happens on failure

The finding is written down plainly: the baseline's ROI advantage survives fair accounting, the
allocator's value on this workload is confined to buying the expensive tier where consequence is
high, and the attention economics is a statement about the cost structure of assurance rather than
about our allocator specifically. That is still a defensible business claim, and it is the one we
would then make.
