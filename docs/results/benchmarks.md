# Metrics matrix: how we compare against published numbers

Every figure in the left block is measured by our harness on held-out data. Every figure in the
right block is taken from a published paper. The point is not to win — it is to know where we sit.

Two things must be said before the tables, because getting either wrong makes the comparison
meaningless.

**ROC-AUC and AUPRC are not interchangeable on imbalanced data.** At a 7% base rate the same
detector scores 0.9390 ROC-AUC and 0.6321 AUPRC. Published guard-model papers report **AUPRC**, so
that is the column to compare, and quoting our ROC-AUC against their AUPRC would inflate us by ~0.3.

**Our F1 is best-F1 over all thresholds**, which is an oracle-threshold upper bound. Published F1
figures use a fixed operating point. Our F1 column is therefore optimistic by construction and
should be read as a ceiling, not a like-for-like score.

---

## Harness validation against an independent published number

Before comparing ourselves, we checked the harness on a detector someone else has already measured.

| Measurement | Value |
|---|---:|
| OpenAI Moderation on ToxicChat, **our** AUPRC | 0.6321 |
| OpenAI Moderation on ToxicChat, **published** (Llama Guard paper, Table 2) | 0.588 |

Within 7.5%, and the gap has a known cause: the published figure uses the `1123` release and ours
uses the larger re-annotated `0124` split. **Our measurement pipeline agrees with an independent
published result on the same detector**, which is the precondition for anything below being
meaningful.

---

## ToxicChat — real user traffic, 7.12% harm, 5,083 held-out rows

| Detector | ROC-AUC | AUPRC | best-F1 | Precision | Recall |
|---|---:|---:|---:|---:|---:|
| ControlPlane lexical, scoring the response | 0.4838 | 0.1881 | 0.3120 | 0.3302 | 0.2956 |
| ControlPlane lexical, scoring the prompt | 0.6290 | 0.3204 | 0.4145 | 0.3082 | 0.6326 |
| **ControlPlane pipeline, OpenAI Mod as Tier 1** | **0.9377** | **0.6623** | 0.6455 | 0.5789 | 0.7293 |
| OpenAI Moderation, raw bundled score | 0.9390 | 0.6321 | 0.6209 | 0.5126 | 0.7873 |

**Published anchors on ToxicChat (AUPRC), from the Llama Guard paper:**

| Model | AUPRC |
|---|---:|
| Llama Guard | 0.626 |
| OpenAI Moderation API | 0.588 |
| Perspective API | 0.532 |

### What this says

Our pipeline reaches **AUPRC 0.6623**, above the published Llama Guard figure of 0.626. **That is
not a claim that we beat Llama Guard**, for two reasons worth stating plainly:

1. The detection is OpenAI's, not ours. We supply calibration and Tier 0 on top of a bought signal.
2. Our harness reads ~7.5% high against the published baseline on the same scores. Discounting our
   0.6623 by that factor lands at roughly 0.616 — **level with Llama Guard, not above it.**

The defensible sentence is: *ControlPlane's calibration layer, given a commodity moderation score,
lands in the same band as a purpose-built 8B guard model on real traffic.* That is a good place to
be for a layer that is not trying to be a detector.

One genuinely interesting detail: our pipeline scores **higher AUPRC than the raw score it consumes**
(0.6623 against 0.6321). Isotonic calibration plus the Tier 0 signals adds something on top of the
moderation endpoint rather than merely passing it through.

---

## BeaverTails — 10,000 held-out rows, prompt-disjoint split

| Condition | Detector | Base rate | ROC-AUC | AUPRC | best-F1 |
|---|---|---:|---:|---:|---:|
| Natural | fitted Naive Bayes, any harm | 55.76% | 0.7660 | 0.8027 | **0.7491** |
| 7% corrected | fitted Naive Bayes, any harm | 7.44% | 0.7203 | 0.1860 | 0.2932 |
| 7% corrected | fitted NB, `pii_leak` | 0.60% | **0.8090** | 0.0758 | 0.1912 |
| 7% corrected | fitted NB, `unsafe_content` | 6.16% | 0.7509 | 0.1832 | 0.2944 |
| 7% corrected | fitted NB, `bias` | 1.92% | 0.6193 | 0.0564 | 0.1348 |

**Published anchor:** content-moderation models evaluated on BeaverTails in QA mode report F1 in a
band of roughly **39.5% to 73.8%**, depending on model and prompt template.

### What this says

At the comparable distribution — natural prevalence, which is what the published band uses — our
**best-F1 of 0.7491 sits at the top of that band**. The detector producing it is a bag-of-words
multinomial Naive Bayes in numpy, roughly 60 lines, no dependencies, fitted on the calibration fold
in seconds.

The caveat matters: best-F1 is an oracle threshold. A fair fixed-threshold comparison would land
lower. The honest reading is *competitive with the published band*, not *at the top of it*.

The 7% rows are not comparable to the published band at all — F1 collapses when the base rate does,
which is a property of the metric, not the detector. ROC-AUC is the column that survives the
prevalence change, and it moves only 0.766 → 0.720.

---

## Where we are genuinely strong, and where we are not

| Capability | Our number | Nearest published comparison | Verdict |
|---|---|---|---|
| Calibration on a bought signal | AUPRC 0.6623 (ToxicChat) | Llama Guard 0.626 | **Level**, after discounting harness drift |
| Fitted per-axis detector | F1 0.7491 (BeaverTails natural) | Published band 39.5–73.8% | **Competitive**, with an oracle-threshold caveat |
| PII on a corpus we built | AUC 0.9879 | Presidio 0.5825 on the same rows | **Strong, but on our own corpus** |
| Hand-written lexical rules on real traffic | AUC 0.6290 | OpenAI Mod 0.9390 | **Clearly behind** |
| `hallucination` axis on BeaverTails | AUC 0.5215 | — | **No signal.** 21 positives; the axis is untested |

The last two rows are the honest ones. Our own detectors do not transfer, and one axis has no
measurable signal at all on real data.

---

## Reproducing this

```bash
make toxicchat      # writes docs/results/toxicchat.json
```

The metrics matrix itself is committed at
[`metrics_matrix.json`](metrics_matrix.json), and the BeaverTails run at
[`beavertails.json`](beavertails.json). Both corpora are CC-BY-NC-4.0, so none of this supports a
commercial claim.
