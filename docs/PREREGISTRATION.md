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

---

# Pre-registration 3: does allocating attention beat a naive queue?

Written before the comparison was implemented and before any number from it existed. Locked at
commit `efed34e`, corpus `manifest_version: 3`, seed `20260824`.

## Why this is the experiment that matters

Pre-registration 2 came back partial, and the reason was more interesting than the result. Total
assurance cost is 30 to 70 times compute cost, every policy that raises more than a shift's worth of
cases saturates the same fixed reviewer capacity, and so every policy pays **the same attention
bill**. Allocating compute barely moves the total. We measured our own differentiator and found it
governs the smaller number.

What differs between policies at saturation is not what they spend. It is **what gets shed**. At 166
cases of capacity against 244 to 396 raised, between a third and three fifths of everything raised
is dropped, and which third is dropped is currently decided by a rule nobody has tested.

So the question that decides whether this product is differentiated is not *which rows get a Tier 2
check*. It is **which cases get the reviewer's hour**. That is what this tests.

## The rules under comparison

All at identical capacity, on identical raised cases, from the allocator run at each budget.

| Rule | Serving order | Why it is in the comparison |
|---|---|---|
| `deadline_density` | SLA deadline, then expected loss per reviewer minute | **Ours.** The shipped rule |
| `fifo` | Arrival order | What an unmanaged queue does, and what most review desks actually do |
| `random` | Deterministic shuffle | The honest null. If we cannot beat this, there is no allocation happening |
| `density` | Expected loss per reviewer minute only | Ours with the deadline term removed, to price what the deadline term costs |
| `deadline` | SLA deadline only | Ours with the value term removed, to price what the value term costs |

`density` and `deadline` are ablations, not rivals. They exist so that if we win, we can say which
half of our rule did the work — and if one of them beats the full rule, that is a finding about our
rule being worse than its own components.

## Primary endpoint

**Our rule must dominate `fifo` at every budget**: at least as much expected loss served, and no
more SLA breaches. Dominance rather than a single scalar, because a rule that serves more value by
letting tight-deadline cases breach has not improved anything — it has moved the failure.

Success: `deadline_density` weakly dominates `fifo` on both axes at all six budgets, and strictly
improves at least one axis at the 10% and 25% budgets.

Partial success: dominance at four or more of six budgets.

Failure: anything else, including a win on served value that is paid for in breaches.

## Secondary endpoints, reported either way

- Against `random`. Losing to a deterministic shuffle would mean the queue is not allocating at all,
  and it would be the most important negative result in the project.
- The two ablations. We expect `density` to serve more expected loss and breach more, and `deadline`
  the reverse. If the full rule does not sit between them on both axes, our combination is not doing
  what we claim.
- Shed cases above the 90th percentile of expected loss, per rule. Total value served can look
  healthy while the most expensive cases are the ones being dropped.
- Shed cases on `finops-agent` specifically, which carries the tightest SLA and the highest
  consequence.

## What is deliberately not claimed

Expected loss is `r * c` and both terms are ours: `r` is a calibrated detector score and `c` is a
policy assumption inside a 0.25x-4x band. This comparison therefore measures whether the queue
allocates well **against our own estimate of value**, not whether it allocates well against a real
review desk's outcomes. That is a genuine limitation and it goes next to the result, not in a
footnote.

Reviewer handling time is a constant 6 minutes per case. A real desk's handling time varies with
case difficulty, and a rule that knew the difference would allocate differently. Constant handling
time makes the comparison a ranking problem rather than a knapsack, which is a simplification in
every rule's favour equally.

## Methodology guards

1. **The queue, its capacity, and the case-raising rule are not touched.** Only the serving order
   varies. Everything else — `config/economics.yaml`, `case_from_trace`, the shed rule — stays as
   committed.
2. **The rules are compared on identical raised cases** from the same allocator run at each budget,
   so no rule is advantaged by seeing a different case mix.
3. **`random` is seeded and committed**, so the null is reproducible rather than resampled until it
   loses.
4. **The ablations are run whether or not they flatter us**, and if one beats the full rule that is
   reported as the headline.
5. **No metric substitution.** If the primary endpoint fails, it goes in `README.md` and
   `docs/LIMITATIONS.md` as a failure.

## What happens on failure

If our rule does not beat FIFO, the honest conclusion is that the reviewer queue is a cost centre we
have measured accurately and not yet improved — which is still a finding worth having, because the
measurement is what nobody else has. The shipped rule would stay, labelled as untested rather than
as a differentiator, and the business case would rest on the cost structure alone.


---

# Pre-registration 4: can PII detection reach AUC 0.9 without cheating?

Written before the detector was changed and before any number from the new detector existed.
Locked at commit `47e586e`, corpus `manifest_version: 3`, seed `20260824`.

## The problem, stated correctly

The PII axis scores **AUC 0.5897** on held-out traffic through the full calibrated pipeline.
Tier 1's PII signal alone is **0.4973**, which is chance. That is bad and it needs fixing.

But the reason is not that the detector guesses. Measured on the held-out set, the corpus
splits four ways:

| | Labelled a leak | Not a leak |
|---|---:|---:|
| Contains PII-shaped text | 37 | **309** |
| No pattern to match | **57** | 1097 |

A detector that scores every PII-shaped row above every plain row — a *perfect* shape
detector — reaches **AUC 0.5869** on this split. Our regexes score 0.5881. **They are
already at the ceiling of what text shape can tell you here**, and the remaining 0.41 of
AUC is not available to any amount of better pattern matching. Microsoft Presidio confirms
this from the other side: it finds strictly more (698 rows the regexes missed) and is wrong
about 94% of them.

So the target is reachable only by using a signal that is not the shape of the text.

## The claim under test

**Three mechanisms, each of which a production DLP system would implement independently of
this corpus, close most of the gap.**

1. **Obfuscation normalisation.** `arun dot personal at example dot com` is an email address
   written to evade a pattern match. Real filters normalise `dot`/`at`/spacing before
   matching, and attackers obfuscate precisely because filters do not.
2. **Grounded disclosure.** An identifier that appears in the response but not in the
   authorised source is an unauthorised disclosure; one that appears in both is the system
   repeating something it was given. This is the evidence-regime idea the whole product
   rests on, applied to the PII axis.
3. **Personal-context classification.** A disclosure framed as personal contact detail
   (`home address`, `personal`, `reach them directly`) is a different act from repeating a
   record the caller is entitled to (`work address on file`, `verified contact`).

## Primary endpoint

**AUC on the PII axis, over the 1500 held-out test rows, through the calibrated pipeline.**

- Success: **AUC >= 0.90**.
- Partial success: AUC >= 0.75, which would be past the shape ceiling by a wide margin.
- Failure: anything below 0.75, reported as a failure in `README.md` and
  `docs/LIMITATIONS.md`.

Precision, recall and F1 at the shipped decision threshold are reported alongside, because
an AUC that rises while precision collapses has moved the problem rather than solved it.

## The guard that matters: development happens on calibration only

The corpus has a 1500-row calibration split and a 1500-row held-out test split. **Every
phrase, threshold and rule in the new detector is derived from the calibration split.** The
test split is scored once, after the detector is frozen, and whatever it says is what gets
reported.

This is the guard against the failure this project has already caught in itself once: in
Phase A the corpus made harm perfectly predictable from row structure, calibrated AUC hit
1.000 on two routes, and the evaluation was measuring the fixture. A detector tuned against
the test set would reproduce exactly that, with a better-looking number.

## Reported either way: which mechanism earned the score

Each mechanism is measured separately and cumulatively, on test, in one table. This is not
decoration. Mechanisms 1 and 2 are corpus-independent and should transfer to real traffic.
**Mechanism 3 is a vocabulary, and vocabularies fitted to a generator we wrote do not
transfer.** If most of the gain comes from mechanism 3, the honest headline is that we fitted
our own corpus, and that is what will be written down.

The corpus is not regenerated, reweighted or relabelled. `tests/test_corpus_integrity.py`
must still pass, and `make data` must still reproduce the committed JSONL byte for byte.

## What happens on failure

The number is reported as measured, the shape ceiling above is published next to it so a
reader can see what was and was not achievable, and the honest conclusion is written down:
that offline lexical detectors cannot separate authorised from unauthorised disclosure, and
that this axis needs either a real judge or the policy context the gateway already has and
the detector does not see.

---

# Pre-registration 5: does the allocator hold up on real user traffic?

**Status: locked before the first run against this corpus.**

## The claim under test

Every number in this project comes from a corpus we generated. The mechanism could be sound and the
evidence still worthless if the generator quietly built a world the allocator was good at. This
tests the allocator on traffic nobody on this team wrote.

**Claim:** on held-out real user–assistant traffic, budget-aware allocation averts more expected
loss than a tuned fixed-rate policy at matched spend, and the per-route release floor still holds.

## The corpus, and why this one

`lmsys/toxic-chat`, split `0124` — 10,165 real user prompts from the Vicuna online demo with model
responses, human toxicity labels and a separate jailbreak label. CC-BY-NC-4.0.

It was chosen for one property above all others: **a 7.18% harm base rate**. Balanced adversarial
benchmarks (HarmBench, AdvBench and similar) sit near 50% harm, and on those almost every row clears
the expected-loss threshold, the allocator degenerates to `check_all`, and the experiment cannot
distinguish a working allocator from a broken one. A realistic base rate is the binding requirement,
not corpus size or name recognition.

Annotation provenance is mixed and this is recorded now rather than discovered later: 5,654 rows
were human-annotated, and 4,511 were auto-filtered as non-toxic by Perspective API below a score of
10^-1.43 without human review. Those labels come from a detector, not a person.

## Mapping decisions, locked in advance

These are modelling choices, not findings. They are fixed here so they cannot be tuned after seeing
a result.

| Decision | Locked value | Why |
|---|---|---|
| Route | `support-assistant`, jurisdiction `eu` | ToxicChat is single-domain general chat. Inventing three routes would fabricate structure the data does not carry. |
| `toxicity` maps to | `unsafe_content` (consequence ₹7,000) | Closest axis by definition |
| `jailbreaking` maps to | `injection_or_exfil` (consequence ₹15,000) | Matches the adversarial-intent axis |
| Unlabelled axes | `hallucination`, `pii_leak`, `bias` carry no ground truth | ToxicChat labels two of our five axes. Calibration will drive these toward zero because no row is positive; that is correct behaviour given the labels, and it is **not** evidence those harms are absent. |
| Calibration / test | ToxicChat's own `train` split calibrates, `test` split is held out | Their split, not ours |
| Fitting / selection folds | The existing hash-of-id split inside `calibrate()` | Same discipline as the synthetic corpus. Fitting and selecting on the same rows previously made the bound roughly 9x optimistic. |
| α, δ | 0.15 / 0.10, unchanged from `config/policies/eu.yaml` | Reusing shipped policy, not a corpus-specific tuning |

**`jailbreaking` is a strict subset of `toxicity` in this corpus** — zero rows are jailbreak-but-not-
toxic. The two axes are therefore nested, not independent, and no claim about axis independence may
be drawn from this run.

## Primary endpoint

**Allocation, not detection.** At matched assurance spend on the held-out test split, the allocator
averts more expected loss than the best tuned fixed-rate policy at **at least 5 of 6** budgets, and
the observed unchecked-harm rate stays at or below α = 0.15 on the released rows.

Partial success: more loss averted at 4 of 6 budgets with the floor holding.

Failure: anything else. A floor breach is a failure regardless of the allocation result.

## Secondary endpoints, reported either way

- **AUC of our calibrated score against `toxicity`**, reported beside the OpenAI moderation baseline
  already bundled in the corpus. **We expect to lose this comparison.** Our Tier 0 and Tier 1 are
  lexical stubs developed against our own corpus; OpenAI's endpoint is a trained moderation model.
  Losing it does not bear on the primary endpoint, because the primary endpoint is about how to
  spend a budget, not about who has the better detector.
- **The OpenAI moderation baseline at its own default threshold**, so the reader can see the
  operating point and not just the ranking.
- **Both annotation conditions**: all 10,165 rows at a 7.18% base rate, and the 5,654 human-annotated
  rows at 13.19%. Reporting only the more favourable one would be exactly the selection this
  document exists to prevent.
- **Coverage and abstention rates**, which on unfamiliar traffic are the honest signal of whether
  the evidence regime is doing anything.

## What is deliberately not claimed

- Nothing about `hallucination`, `pii_leak` or `bias` performance. ToxicChat does not label them.
- Nothing about the reviewer-queue result. ToxicChat carries no arrival times or SLAs.
- Nothing about effect gating. There are no tool calls in this corpus.
- No commercial claim. CC-BY-NC-4.0 forbids it.

## What happens on failure

The result is written into the README beside the synthetic-corpus numbers, with the failing endpoint
named. If the allocator does not beat a tuned fixed-rate policy on real traffic, that is the single
most important finding this project could produce, and burying it would make every other number here
worthless. The synthetic corpus stays as the reproducible offline default either way.

---

# Pre-registration 6: is the allocator broken, or is the detector?

**Status: locked after Pre-registration 5 returned a failed primary endpoint, before this ran.**

## Why this experiment exists

Pre-registration 5 failed. On real traffic the allocator averted less loss than a tuned fixed-rate
policy at every budget, and the diagnosis is visible in the secondary endpoint: our calibrated risk
score reached **AUC 0.4838**, which is chance. The allocator ranks candidates by
`risk x consequence`. Ranking on noise is not merely unhelpful — it is worse than a fixed rate,
because it spends the budget on a random subset while a fixed rate spends less for the same random
subset.

That failure is consistent with two different explanations, and they have opposite implications:

1. **The allocation mechanism does not work on real traffic.** Fatal to the project.
2. **The mechanism was starved of signal by a lexical detector that does not transfer.** A detector
   problem, which the architecture already claims is swappable.

These are distinguishable. The corpus ships OpenAI moderation scores, which reach **AUC 0.9390** on
the same held-out rows. Substituting them isolates the question.

## The claim under test

**Claim:** given a competent risk signal, budget-aware allocation beats a tuned fixed-rate policy at
matched spend on the same real traffic where it lost with our own detectors.

## What changes, and what must not

Exactly one thing changes: `AssessmentEngine.tier1` is replaced with an adapter returning the
corpus's bundled OpenAI moderation score on the `unsafe_content` axis. Everything else — isotonic
calibration, the fitting/selection fold split, Learn-Then-Test, the shadow-price controller, the
allocator, the cost model, alpha and delta — is untouched and re-fitted by the same code path.

The scores are precomputed in the CSV, so this run makes **no network call** and the offline promise
is intact. This is not a claim that we built a better detector. It is a claim about what the
allocator does when a competent one is plugged into the adapter the architecture already exposes.

## Primary endpoint

At matched assurance spend on the held-out test split, the allocator averts more expected loss than
the best tuned fixed-rate policy at **at least 5 of 6** budgets.

Failure: fewer than 5 of 6. If it fails here too, explanation (1) above is the surviving one, the
allocation mechanism is the problem rather than the detector, and that is what gets written down.

## Secondary endpoints, reported either way

- The per-route release floor: whether the certified bound still holds on held-out rows, and whether
  it binds at all. Under our own detectors at `alpha = 0.15` it did not bind, because the corpus base
  rate of 7.12% already sits below the tolerance.
- Coverage and mandatory-coverage rates, which say whether the floor or the budget is driving checks.
- The same run under both annotation conditions, as in Pre-registration 5.

## What this cannot claim

Nothing about ControlPlane's detection quality — the detection is OpenAI's. Nothing commercial;
the corpus is CC-BY-NC-4.0. And nothing about the four harm axes ToxicChat does not label.

---

# Pre-registration 7: does a varied harm mix restore the allocator's advantage?

**Status: locked before the first run against this corpus.**

## The claim under test

Pre-registrations 5 and 6 failed, and the diagnosis was that ToxicChat exercises a single harm axis:
with one active axis the consequence multiplier is constant, `risk x consequence` collapses to a
rescaling of `risk`, and the allocator sorts the same list as the baseline. `Spearman(risk, expected
loss) = 1.000000` exactly.

**Claim:** on real traffic labelled across several harm axes, so that equally risky rows carry
unequal consequences, budget-aware allocation beats a tuned fixed-rate policy at matched spend.

This is the condition the mechanism actually requires. If it fails here, the allocation idea does not
work on real data and that is the project's headline finding.

## The corpus

BeaverTails `round0/330k`, CC-BY-NC-4.0. 333,963 QA pairs labelled across 14 harm categories, 30.4%
of rows carrying more than one category.

**Two defects in the shipped corpus are recorded here before use.**

1. **The official train/test split leaks.** 99.91% of test prompts also appear in train (99.68% in
   the 30k release). Exact `(prompt, response)` pairs do not repeat, but prompts do, and the
   conformal bound claims validity on held-out data. We therefore **discard the official split** and
   construct our own by hashing the *prompt*, so every response to a given prompt lands in the same
   fold: 70% calibration, 30% test, verified prompt-disjoint.
2. **The natural harm rate is 55.69%**, which is the balanced-adversarial trap documented in
   `docs/EVIDENCE-PLAN.md`. At that prevalence nearly every row clears the expected-loss threshold,
   the allocator degenerates to `check_all`, and the comparison cannot distinguish a working
   allocator from a broken one. We therefore **correct prevalence to 7%** — matching ToxicChat and
   plausible production traffic — by keeping every safe row and deterministically subsampling unsafe
   rows on a hash of the row. Prevalence correction is applied identically to both folds.

## Mapping decisions, locked in advance

| Our axis | BeaverTails categories |
|---|---|
| `pii_leak` | `privacy_violation` |
| `bias` | `discrimination,stereotype,injustice`; `hate_speech,offensive_language`; `controversial_topics,politics` |
| `hallucination` | `misinformation_regarding_ethics,laws_and_safety` |
| `unsafe_content` | `violence,aiding_and_abetting,incitement`; `self_harm`; `drug_abuse,weapons,banned_substance`; `terrorism,organized_crime`; `child_abuse`; `animal_abuse`; `sexually_explicit,adult_content`; `non_violent_unethical_behavior`; `financial_crime,property_crime,theft` |
| `injection_or_exfil` | **unlabelled** — no category corresponds |

Route stays `support-assistant` / `eu`. Pre-registration 6 established that route count is not what
drives the collapse, so a single route is not a threat to this experiment. The four mapped axes carry
consequences of ₹18,000, ₹9,000, ₹5,000 and ₹7,000 respectively, which is the variation under test.

## The detector

Our hand-written lexical detectors scored AUC 0.4838 on real traffic. Allocation on a noise signal is
untestable, so Tier 1 is replaced by a **per-axis multinomial Naive Bayes bag-of-words scorer fitted
on the calibration fold only**, in numpy, with no new dependency and no network call.

This is deliberately a modest detector. The claim under test is about allocation, not detection, and
a weak-but-real per-axis signal is exactly what the allocator is supposed to arbitrate. Fitting
touches the calibration fold only; the test fold is never seen during fitting, and the existing
fitting/selection sub-split inside `calibrate()` is preserved.

## Primary endpoint

At matched assurance spend on the held-out test fold, the allocator averts more expected loss than
the best tuned fixed-rate policy at **at least 5 of 6** budgets.

## The diagnostic that decides whether the run means anything

**`Spearman(risk score, expected loss)` must be below 0.99 on the test fold.** If it is not, the harm
mix has again collapsed to one effective axis, the experiment is void by the same mechanism as
Pre-registration 6, and no conclusion about allocation may be drawn from it either way. This is
checked and reported before the primary endpoint.

## Secondary endpoints, reported either way

- Per-axis AUC of the fitted detector, so a reader can see whether the signal is real.
- The share of test rows firing on more than one axis, post-correction.
- Whether the conformal bound holds on the held-out fold, and whether it binds.
- The result at the natural 55.69% prevalence as well, to show what the trap looks like.

## What happens on failure

If the allocator loses here, with a varied harm mix and a working detector on real data, then the
central claim of the project does not survive contact with reality and the README says so in those
words. The synthetic-corpus result would then stand only as a statement about a corpus we generated.

---

# Pre-registration 8: can the hallucination axis be made to work on real grounded traffic?

**Status: locked after development on the calibration split, before the test split was read.**

## Why this exists

The `hallucination` axis scored **AUC 0.5215** on BeaverTails — no signal. The cause is structural,
not statistical: `tier0_rules.py` returns early when `context_documents` is empty, and
`tier1_models.py` is gated the same way. ToxicChat and BeaverTails both carry no retrieved context,
so **the grounding mechanism was disabled on every row of both corpora**. It was never tested.

RAGTruth is the corpus that tests it: 17,790 responses from six LLMs over retrieved passages, with
span-level annotations split into *evident conflict* (contradicts the context) and *baseless
information* (unsupported by it). The official split is prompt-disjoint — 0 overlap on
`(query, context)` — so unlike BeaverTails it can be used as shipped.

## The claim under test

**Claim:** given the source passages the mechanism was designed to use, ControlPlane's grounding
signal detects hallucination on real RAG traffic at a level comparable to published detectors.

## What is being added

A fitted grounding scorer replacing Tier 1 on the `hallucination` axis, using only features derived
from the response against its own retrieved context:

- unsupported content-token ratio, and its type-level variant
- IDF-weighted unsupported mass, IDF estimated from contexts alone
- unsupported-numeral ratio, and a capped unsupported-numeral count

Logistic regression, numpy, no new dependency, no network call. Fitted on the calibration split only.

**Response length is deliberately excluded.** On the calibration split it reaches 0.6548 by itself
and lifts the model from 0.7515 to 0.7714. It is a shortcut — a long grounded answer is not
hallucinated — and including it would buy 0.02 of AUC by learning a property of the corpus rather
than of grounding. Recorded here so the omission cannot later look like an oversight.

## Primary endpoint

Held-out response-level **AUC ≥ 0.70** on the RAGTruth test split, and **F1 within the published
band** for response-level detection on this benchmark, which spans 52.0% (RAGAS Faithfulness) to
79.22% (LettuceDetect large).

Success: AUC ≥ 0.70 and F1 ≥ 0.52, placing us inside the published band.
Partial: AUC ≥ 0.70 with F1 below 0.52.
Failure: AUC below 0.70.

## Secondary endpoints, reported either way

- The same detector with context withheld, which should collapse to chance. If it does not, the
  score is not measuring grounding.
- Per-task-type AUC across `QA`, `Summary` and `Data2txt`. A detector that works on only one is a
  narrower result than a single pooled number implies.
- Per-annotation-type performance on *evident conflict* against *baseless information*. Contradiction
  and unsupported-addition are different problems and we expect to be better at the first.
- Whether the release floor holds on this corpus.

## What is not claimed

Nothing about span-level localisation; we score whole responses. Nothing about the other four harm
axes, which RAGTruth does not label. And the comparison band is drawn from papers using fixed
operating points, whereas an unqualified best-F1 from us would be an oracle threshold — so the
reported F1 must state which it is.

---

# Pre-registration 9: does the allocation precondition hold on a multi-axis public corpus?

Written and committed before any detector was run against Aegis. The corpus loader existed and its
composition had been inspected — row counts, base rates, category distribution — because the mapping
below cannot be written without that. No score, no AUC and no allocation result had been computed.

## Why this experiment exists

`docs/results/allocation-regime.md` closed with a precondition rather than a win: budget-aware
allocation can only beat a well-ranked fixed-rate baseline when **the harm mix varies across
traffic**, measured as `Spearman(risk, expected loss) < 1`. On ToxicChat that statistic was exactly
1.000000 and the mechanism provably could not help. On BeaverTails it was 0.998494.

Both of those are effectively single-axis corpora, so the precondition has never actually been
tested — only its failure has. That is a weak position: a claim whose enabling condition has never
been observed in the wild is a claim about our own corpus.

NVIDIA's Aegis 1.0 is the corpus that tests it. Its 13-category taxonomy maps onto **three** of our
axes, including `pii_leak`, which no other public corpus here labels, and those three axes carry
genuinely different prices in our consequence table. It is human-annotated at 3-4 annotators per
row, and CC-BY-4.0 — the first corpus in this project a commercial deployment could use.

## The claim under test

**Claim:** on a public, human-annotated, multi-axis corpus, ControlPlane's detection sits inside the
published band for this benchmark, and the harm mix varies enough that expected-loss ranking is not
a monotone rescaling of risk ranking.

## Mapping decisions, locked in advance

- **Label convention.** Both of NVIDIA's own conventions are reported, not one: the Permissive model
  treats `Needs Caution` as safe, the Defensive model treats it as unsafe. Reporting whichever
  flatters us after seeing scores is exactly what this document exists to prevent.
- **Label definition.** Row-level majority vote across annotators, because that is the binary task
  the published Llama Guard and Aegis F1 numbers are measured on. The per-axis vector is the
  per-axis agreement rescaled to peak at the row-level agreement.
- **Category to axis**: `PII/Privacy` to `pii_leak`; `Hate/Identity Hate` to `bias`; the remaining
  eleven categories to `unsafe_content`. `hallucination` and `injection_or_exfil` receive no rows
  and are reported as **unlabelled**, not as zero.
- **The annotated string goes in `response`.** Tier 1 reads only that field, and scoring a field the
  annotation does not describe is the error that put ToxicChat at chance. This means we score the
  annotated text exactly as the published classifiers are given it.
- Official train/test split as shipped. Train calibrates, test scores, and the fitting/selection
  fold discipline inside calibration is unchanged.

## Primary endpoint

Held-out **AUPRC within the published band for the Aegis test set**, which spans 0.860 (Perspective
API) to 0.941 (Aegis-tuned Llama Guard), with Llama Guard Base at 0.930 and OpenAI Mod API at 0.895.

- **Success:** AUPRC at or above 0.860 under both conventions, placing us inside the published band.
- **Partial:** AUPRC at or above 0.860 under one convention only.
- **Failure:** below 0.860 under both.

F1 is reported beside it against the published range of 0.24 (Perspective) to 0.85 (Aegis
Defensive), at a threshold chosen on calibration and applied unchanged — never an oracle threshold.

## Secondary endpoints, reported either way

- **`Spearman(risk, expected loss)` and mean axes firing per harmful row.** This is the endpoint
  that matters most, and it is reported whatever it says. Below about 0.99 the allocator has
  something to work with; at 1.0 it provably does not.
- **The allocator against the tuned fixed-rate baseline at matched actual spend**, under the budget
  governor, across the same budget grid as every other corpus.
- **Per-axis AUC**, in particular `pii_leak`. Our headline PII result (0.9879) is measured entirely
  on a corpus we wrote; this is the first public data that labels the axis at all. We expect to do
  markedly worse here, because Aegis labels whether text *contains* private information, which
  `docs/results/pii.md` argues at length is the wrong question — and our detector is built for the
  other one.
- **Per `text_type` breakdown** across `user_message`, `llm_response`, `combined` and `multi_turn`.
- Whether the release floor holds, non-vacuously, on held-out rows.

## What is deliberately not claimed

Nothing about `hallucination` or `injection_or_exfil`, which Aegis does not label. Nothing about
annotator quality; we take the published annotations as given. And the base rate here is about 53%,
against 7% on our own corpus and ToxicChat — AUPRC at a 53% base rate is a far easier number than
AUPRC at 7%, so it must never be compared across corpora, only against the published numbers on
this one.

---

# Pre-registration 10: what does the system do to safe traffic that looks harmful?

Written and committed before any detector was run against OR-Bench.

## Why this experiment exists

Every corpus in this project so far has asked whether we catch harm. **None has asked what we do to
the safe traffic we should leave alone.** Our own corpus contains decoy clauses written by us to
resemble harmful ones, which makes them exactly as hard as we thought to make them — an
unfalsifiable test of over-blocking.

This is the most likely real objection to deploying this system, and it is currently unanswered.

OR-Bench supplies negatives that are hard on purpose: `or-bench-hard-1k` is prompts that
state-of-the-art models refuse *even though they are safe*, drawn from the same ten categories as
`or-bench-toxic`. A category-matched safe and toxic pair defeats the lexical shortcuts our Tier 0
rules rely on, which is the point.

The published result is a **trade-off, not a score**: across evaluated models the Spearman
correlation between safe-rejection rate and toxic-rejection rate is 0.878, so nearly every model
buys safety by refusing benign traffic. Published operating points include Claude-3-Opus at 91.0%
safe-rejection and 98.1% toxic-rejection, Llama-3-70b at 37.7% and 78.7%, GPT-4o at 6.7% and 84.9%,
and Mistral-large at 9.7% and 72.8%.

## The claim under test

**Claim:** ControlPlane's operating point is not simply on the published safety/over-refusal
trade-off line — it blocks less safe traffic than a model with comparable toxic-catch rate.

## Mapping decisions, locked in advance

- `or-bench-hard-1k` rows are **negatives**; `or-bench-toxic` rows are **positives**. No relabelling.
- Category to axis: `privacy` to `pii_leak`; `hate` to `bias`; the other eight to `unsafe_content`.
  The same mapping is applied to both files, so a safe row and a toxic row from one category differ
  only in their label.
- OR-Bench ships no split. A deterministic 50/50 fold is derived from a hash of the prompt text,
  fixed in `controlplane/corpora/orbench.py` before any run.
- The prompt string goes in `response`, for the same reason as Aegis.

## Primary endpoint

At a threshold chosen on the calibration fold and applied unchanged to the held-out fold:

- **Success:** false-refusal rate on the safe fold is **below 37.7%** — Llama-3-70b's published
  rate — at a toxic-catch rate of **at least 78.7%**, its published pairing. That is the specific
  published point we are claiming to beat, chosen before seeing our numbers because it sits in the
  middle of the published spread rather than at either extreme.
- **Partial:** we beat that point on one axis and not the other.
- **Failure:** we are worse on both, i.e. we refuse more safe traffic *and* catch less toxic traffic
  than a published model.

## Secondary endpoints, reported either way

- **AUC and AUPRC** on the pooled fold, as a threshold-free summary.
- **The block rate on safe traffic specifically**, which is the number an operator actually feels.
- **Per-category false-refusal rate.** A detector that is calm overall but refuses every `privacy`
  question has a problem the pooled number hides.
- Whether the release floor holds, and whether it is vacuous here. With a 33% base rate we expect
  high mandatory coverage, which would make the bound uninformative — and that must be said rather
  than counted as a fifth success.

## What is deliberately not claimed

We are a moderation and allocation layer, not a chat model, so this is **not** a like-for-like
comparison with the published models: they were measured by whether they *answered*, we are measured
by whether we *block*. A model can refuse for reasons a guardrail never sees. The comparison is
offered as a calibration of scale — is our over-refusal in the same league — and not as a claim to
have beaten those models at their own task. Any headline drawn from this must say so.
