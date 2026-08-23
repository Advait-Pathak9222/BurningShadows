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
