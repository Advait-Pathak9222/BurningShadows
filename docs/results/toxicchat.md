# Real traffic: what happened when the allocator met ToxicChat

Endpoints were fixed in [Pre-registrations 5 and 6](../PREREGISTRATION.md) before either run. **Both
primary endpoints failed.** This records what was measured, what caused it, and what the project is
entitled to claim afterwards.

*Written interpretation. Regenerate the underlying numbers with `make toxicchat`, which writes
`docs/results/toxicchat.json`.*

Corpus: `lmsys/toxic-chat`, split `0124`. 5,082 calibration rows and 5,083 held-out test rows of real
user–assistant traffic from the Vicuna demo. Test-split toxicity 7.12%, jailbreak 1.79%.
CC-BY-NC-4.0, so nothing here supports a commercial claim.

---

## Result 1: our detectors transfer poorly — and the first number here was wrong

| Detector | ROC-AUC | AUPRC |
|---|---:|---:|
| ControlPlane lexical, **scoring the response** | 0.4838 | 0.1881 |
| ControlPlane lexical, **scoring the prompt** | **0.6290** | 0.3204 |
| OpenAI moderation (bundled with the corpus) | 0.9390 | 0.6321 |

**Correction.** The first version of this page reported 0.4838 and called it chance. That number
came from a mapping error of ours, not from the detector: **ToxicChat's `toxicity` label annotates
the user prompt**, and we mapped our detectors onto the model response. Scoring the field the corpus
actually labels gives 0.6290.

The conclusion survives in weaker form — 0.6290 is well short of the 0.9390 a trained moderation
model reaches, so our hand-written lexical rules do transfer poorly. But "chance" was wrong, and it
conflated a real weakness with an error we introduced. `docs/LIMITATIONS.md` predicted the weakness;
it did not predict the mistake.

## Result 2: the calibration pipeline is not the problem

Pre-registration 6 swapped `AssessmentEngine.tier1` for an adapter serving the corpus's bundled
OpenAI moderation scores. Nothing else changed — same isotonic calibration, same fitting/selection
folds, same Learn-Then-Test, same allocator, same α and δ.

| Signal | AUC after our calibration |
|---|---:|
| Bundled moderation score, raw | 0.9390 |
| The same score through our pipeline | **0.9377** |

Our calibration preserves essentially all of a competent detector's signal. The adapter contract
works: swapping a detector is a one-line substitution, exactly as
[Industry fit](../INDUSTRY-FIT.md) claims.

## Result 3: with a good detector, the allocator still did not win

| Budget | Allocator spend | Allocator averted | Fixed-rate spend | Fixed-rate averted | Winner |
|---:|---:|---:|---:|---:|---|
| 10% | ₹2,062.52 | ₹3,663,000 | ₹914.94 | ₹3,685,000 | fixed |
| 25% | ₹4,281.30 | ₹3,684,000 | ₹4,064.00 | ₹3,692,000 | fixed |
| 40% | ₹6,585.22 | ₹3,705,000 | ₹6,505.60 | ₹3,756,000 | fixed |
| 60% | ₹9,125.04 | ₹3,835,000 | ₹9,756.80 | ₹3,821,000 | **allocator** |
| 80% | ₹9,967.62 | ₹3,835,000 | ₹13,011.20 | ₹3,871,000 | fixed |
| 100% | ₹10,176.00 | ₹3,835,000 | ₹16,265.60 | ₹3,878,000 | fixed |

**1 of 6, against a pre-registered bar of 5 of 6.** The human-annotated-only condition gave 2 of 6.
Both fail.

## Why: the allocator had nothing to arbitrate

`Spearman(risk score, expected loss) = 1.000000` on ToxicChat. Ranking by expected loss is
**identical** to ranking by raw risk, and the fixed-rate baseline already ranks by risk. The two
policies sort the same list, so the allocator can only lose: it pays for machinery that changes
nothing, and its budget controller overshoots at tight budgets.

A correlation of exactly 1.000000 deserves suspicion, so the mechanism was isolated rather than
assumed. **The first explanation attempted here was wrong** — it attributed the collapse to
ToxicChat being a single route, and therefore carrying a single consequence table. That is not the
cause:

| Slice | Spearman(risk, expected loss) |
|---|---:|
| Our corpus, `finops-agent` only | 0.926330 |
| Our corpus, `internal-kb` only | 0.960481 |
| Our corpus, `support-assistant` only | 0.825956 |

Restricted to one route — no consequence variation at all — our own corpus still does not reach 1.0.
Route count is not what drives it.

**The actual cause is that ToxicChat exercises only one harm axis.** It labels toxicity and
jailbreak, jailbreak is a strict subset of toxicity, and the other three axes have no positive
examples for calibration to learn from, so isotonic drives them to zero.

| Corpus | Axes firing per row | Rows firing on >1 axis |
|---|---:|---:|
| ToxicChat (moderation Tier 1) | 1.00 | **0 of 2,000** |
| ToxicChat (our detectors) | 0.60 | 31 of 2,000 |
| Our synthetic corpus | 1.51 | 658 of 1,500 (43.9%) |

With one active axis, `expected loss = risk x 7,000` — a constant multiplier, and therefore a
monotone rescaling of the risk score. Our corpus escapes this because *which* axis fires changes the
price: `hallucination` is priced at ₹5,000 and `pii_leak` at ₹18,000, so two rows with identical
risk scores carry different expected loss. That is the variation the allocator exists to exploit.

Part of the collapse in the moderation run is an artifact of the adapter, which writes the
moderation score onto `unsafe_content` only. But the effect is present without it: under our own
detectors just 31 rows in 2,000 fire on more than one axis, giving 0.999996.

**This sharpens the claim rather than destroying it:**

> Budget-aware allocation beats a tuned fixed-rate policy **when the harm mix varies across
> traffic**, so that equally risky rows carry unequal consequences. Where every flagged row is the
> same kind of harm, expected-loss ranking degenerates to risk ranking and allocation has no
> advantage. Measured on 5,083 real rows.

## What did survive contact with real traffic

**The finite-sample release floor held.** On the moderation-Tier-1 run, Learn-Then-Test certified an
upper bound of **0.0777** against α = 0.15, and the observed unchecked-harm rate on 5,037 released
held-out rows was **0.0639** — inside the bound, non-vacuously, on data the thresholds never saw.
The guarantee machinery transferred even though the detectors did not.

One caveat stated plainly: at α = 0.15 against a 7.12% base rate, the tolerance sits above the harm
rate, so the floor barely binds (0.9% mandatory coverage). A tolerance below the base rate would
force real coverage. The bound is honest; it is not being stressed.

## A bug this found

Fitting the bound on thousands of released rows raised `OverflowError` in
`binomial_upper_bound`. `comb(trials, count)` is an exact Python int and exceeds the float range past
roughly a thousand trials, before the probability factors can scale it back. Our corpus peaks at 475
released rows on one route, so nothing had ever reached it.

Now summed in log space via `lgamma`. All published values are unchanged
(`p(0, 20, δ/21) = 0.2346`, `p(0, 100, δ/21) = 0.0521`), and `tests/test_conformal.py` covers
n = 50,000. The old form raises on the new test; the new one does not.

## What we are entitled to claim now

- Our offline lexical detectors **do not** work on real traffic. Measured, not hedged.
- Our calibration and guarantee machinery **do** work on real traffic, and preserve a competent
  detector's signal almost exactly.
- Allocation's advantage is **conditional on the harm mix varying**, and is absent without it.
- The synthetic-corpus results remain valid as a statement about multi-axis traffic. They are not
  a statement about single-axis traffic, and were never tested as one until now.

## The experiment this points to

The requirement is now precise: **real traffic labelled on more than one harm axis**, so that
equally risky rows can carry unequal consequences.
[BeaverTails](https://arxiv.org/pdf/2307.04657) is the direct fit — 330k QA pairs labelled across
14 harm categories, which map onto several of our axes at once rather than collapsing to one.
[AgentDojo](https://openreview.net/pdf?id=m1YYAQjO3w) is the complementary test, since its tool
calls carry effect classes that our consequence table prices directly.

Note what this does **not** require: more routes. That was the first hypothesis and the data
rejected it.
