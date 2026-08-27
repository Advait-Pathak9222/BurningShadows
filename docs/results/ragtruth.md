# RAGTruth: fixing the hallucination axis

Endpoints fixed in [Pre-registration 8](../PREREGISTRATION.md) before the test split was read.
**The primary endpoint passed.** The secondary endpoints are where the useful information is.

Corpus: RAGTruth, 15,090 calibration and 2,700 held-out rows, responses from six LLMs over retrieved
passages, annotated into *evident conflict* and *baseless information*. **MIT licensed** — the only
corpus in this project without a non-commercial clause. Its official split is prompt-disjoint
(0 overlap on `(query, context)`), so unlike BeaverTails it is used as shipped.

---

## Why the axis was broken

`hallucination` scored **0.5215** on BeaverTails. That was not a weak detector, it was a disabled
one: `tier0_rules.py:73` returns early when `context_documents` is empty, and `tier1_models.py:52`
is gated the same way. **Neither ToxicChat nor BeaverTails carries retrieved context**, so on every
row of both corpora the grounding mechanism was switched off. The axis had never been tested.

Supplying the passages RAGTruth ships lifts the hand-written rules from **0.5005 to 0.6198**, and the
number of distinct scores they emit from 226 to 1,179. Replacing Tier 1 with a fitted grounding
scorer takes it to **0.7099**.

---

## Result

| Metric | Value | Pre-registered bar |
|---|---:|---|
| Response-level AUC | **0.7099** | ≥ 0.70 ✓ |
| AUPRC | 0.5636 | — |
| **F1 at a threshold chosen on calibration** | **0.6009** | ≥ 0.52 ✓ |
| best-F1 (oracle threshold) | 0.6027 | not comparable |

The fixed-threshold F1 is the honest one. The threshold (0.38) was chosen on the calibration split
and applied unchanged to test; the oracle number is 0.0018 higher, which says the threshold
transfers.

### Against published detectors on this benchmark

| Method | F1 |
|---|---:|
| LettuceDetect large | 79.22% |
| Fine-tuned Llama-2-13B | 78.7% |
| LettuceDetect base | 76.07% |
| Luna (previous encoder SOTA) | 65.4% |
| GPT-4 Turbo prompting | 63.4% |
| **ControlPlane fitted grounding** | **60.09%** |
| RAGAS Faithfulness | 52.0% |

We sit **above RAGAS Faithfulness and just below GPT-4 Turbo prompting**, and clearly behind the
fine-tuned encoders. For a four-feature logistic regression with no model weights, no network call
and no new dependency, that is a reasonable place to be — but it is not competitive with a purpose-
built detector, and the gap to LettuceDetect is 19 F1 points.

---

## The control, and what it is actually worth

Running the fitted detector with the context withheld gives **AUC 0.5000** — exactly 0.5000.

**That is not evidence.** `GroundingTier1.run` contains an explicit
`if not interaction.context_documents: score = 0.0`, so a constant is returned and the AUC is 0.5 by
construction. An earlier version of this page presented it as "the control that makes the number
mean something". It is a tautology, and an exactly-round number should have prompted that check
immediately.

The control that does carry information is the **hand-written rules**, which have no such early
return on the scoring path and were never designed around this corpus:

| Hand-written Tier 0 + Tier 1 | AUC |
|---|---:|
| Context withheld | 0.5005 |
| Context supplied | **0.6198** |

Same detector, same responses, same labels; the only change is whether the source passages are
present. That 0.12 lift is measured rather than asserted, and it is the evidence that the mechanism
reads support rather than style.

## Where it does not work, which the pooled number hides

| Task type | n | Base rate | AUC |
|---|---:|---:|---:|
| `QA` | 900 | 17.78% | **0.7592** |
| `Summary` | 900 | 22.67% | 0.5941 |
| `Data2txt` | 900 | 64.33% | **0.5323** |

**On data-to-text the detector is barely above chance.** The pooled 0.7099 is carried by QA.

The mechanism explains it. Our features count response tokens absent from the context. In QA the
context is prose and an unsupported claim introduces genuinely new words. In data-to-text the
context is a structured record, and a faithful rendering necessarily introduces surface words —
articles, verbs, connectives, units — that never appear in the source. Unsupported-token ratio is
close to meaningless there, and the 64.33% base rate means there is a lot of harm it is missing.

This is a real limitation of the feature set, not a labelling artifact, and it is the obvious next
thing to fix.

## Conflict against unsupported addition

| Annotation type | n | Positives | AUC |
|---|---:|---:|---:|
| `evident_conflict` only | 2,062 | 305 | 0.6854 |
| `baseless_info` only | 2,231 | 474 | 0.7043 |

Pre-registration 8 predicted we would be better at contradiction than at unsupported addition. **We
were not** — the two are within 0.02, and if anything the ordering is reversed. Recorded as
predicted-and-wrong.

## The release floor

Certified upper bound **0.1408** against α = 0.15 on the selection fold; observed **0.0939** on 522
released held-out rows. Holds, non-vacuously, with 80.7% mandatory coverage — the floor is doing
real work here rather than passing trivially, because the 34.93% base rate sits well above α.

---

## What this changes

- The `hallucination` axis moves from **0.5215 (untested)** to **0.7099 (measured, in band)**.
- The grounding mechanism is shown to read support rather than style, by the hand-written rules
  moving 0.5005 -> 0.6198 on the same rows when the source passages are supplied. The fitted
  detector's 0.5000 without context is a hard-coded return and proves nothing.
- One task type is not solved at all, and that is now on the record rather than averaged away.
- This is the third corpus, and the first with a permissive licence.
