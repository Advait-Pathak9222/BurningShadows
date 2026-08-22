# Methods used in the prototype

## Conformal risk control and Learn-Then-Test

Conformal risk control extends split conformal prediction from coverage to bounded expected monotone loss. Learn-Then-Test frames candidate hyperparameters as statistical tests and selects those whose risk can be certified with finite samples. The useful property here is that the guarantee does not depend on the detector being a calibrated neural probability or on access to model internals. [Conformal Risk Control](https://arxiv.org/abs/2208.02814) and [Learn Then Test](https://arxiv.org/abs/2110.01052) are the primary references.

We define loss as a harmful response released without verification. `guarantees/conformal.py` evaluates a finite score grid per route and uses a family-wise corrected exact binomial upper bound. It selects the largest release threshold whose bound is at or below alpha. That threshold becomes a non-negotiable verification floor; the economic allocator can only add checks.

The guarantee assumes calibration and future interactions are exchangeable and that labels match the deployed definition of harm. Distribution shift, label delay, route mixing, and a manipulated abstention policy can invalidate the interpretation. Small route samples also produce a conservative floor. The console therefore shows abstention and the bound alongside coverage.

## Small-model grounding and LLM-AggreFact

MiniCheck treats grounding as claim-document entailment and reports that its 770M parameter FT5 variant reaches GPT-4-level accuracy on its benchmark at about 400 times lower cost. LLM-AggreFact aggregates grounded factuality datasets across summarisation, retrieval-augmented generation, and post-hoc checking. See the [MiniCheck paper](https://aclanthology.org/2024.emnlp-main.499.pdf) and [benchmark card](https://huggingface.co/datasets/lytang/LLM-AggreFact).

The offline build uses a lexical entailment stub behind the same `Detector` adapter that a MiniCheck, DeBERTa NLI, or hosted groundedness service would implement. Context-backed interactions receive a grounded evidence regime; unsupported numbers and low overlap raise hallucination risk. The stub makes no benchmark claim.

Entailment can miss errors that require multi-hop reasoning, tables, dates, or world knowledge. Lexical overlap is especially easy to fool and can reject paraphrases. LLM-AggreFact is gated for evaluation use and must not be silently included as training data.

## Self-consistency and semantic entropy

SelfCheckGPT observes that samples tend to agree when a black-box model has stable knowledge and diverge around fabricated content. Semantic entropy groups semantically equivalent answers before measuring uncertainty, which is more meaningful than token-level diversity. See [SelfCheckGPT](https://arxiv.org/abs/2303.08896) and [semantic entropy](https://doi.org/10.1038/s41586-024-07421-0).

For ungrounded but estimable cases, the stub compares response tokens with supplied comparison samples. A real adapter would sample the provider several times, cluster claims by entailment, and price the extra tokens as verification cost. No log probabilities are required.

Consistency is not truth: a model can repeat the same false statement. Sampling also raises cost and latency, and provider temperature settings affect the signal. When neither evidence nor meaningful samples exist, this build returns `unverifiable` rather than treating consistency as proof.

## Probability calibration

Calibration asks whether events scored near a probability occur at that frequency. Platt scaling fits a sigmoid; isotonic regression learns a monotone non-parametric mapping; reliability diagrams and expected calibration error compare confidence with empirical frequency. [Guo et al.](https://arxiv.org/abs/1706.04599) show why uncalibrated neural confidence should not be taken at face value.

`risk/calibration.py` includes a pair-adjacent-violators isotonic calibrator and ECE calculation. Calibration is fit only on the calibration split and evaluated on the test split. Route separation is retained because a 0.6 score need not mean the same thing in support and FinOps.

Isotonic calibration overfits small sets and is piecewise constant. ECE depends on binning and can hide local errors. Calibration quality also decays after drift, so plots are monitoring evidence rather than a permanent certificate.

## Cascades and selective evaluation

FrugalGPT shows that cascades can choose among heterogeneous model calls to trade quality against inference cost. Cascaded selective evaluation applies a similar escalation idea to model judging. See [FrugalGPT](https://arxiv.org/abs/2305.05176) and [Cascaded Selective Evaluation](https://openreview.net/attachment?id=UHPnqSTBPO&name=pdf).

Tier 0 rules and Tier 1 small-model stubs create a cheap ranking signal. Tier 2 runs only when expected avoided loss exceeds shadow-priced cost or a floor requires escalation. The implementation exposes each tier's benefit, direct cost, adjusted cost, and selection reason.

Cascade errors are correlated. A cheap first stage can suppress the exact cases a later stage would catch, and routing policy learned on one traffic mix can fail on another. Shadow-mode samples and the fixed scenario suite are therefore required.

## Beta-binomial catch rate

A beta prior with binomial observations gives a closed-form posterior for a checker's catch probability. It keeps early estimates away from unjustified zero or one values and makes the sample count visible.

`feedback/recalibration.py` updates caught and missed labels with a Beta(2,2) prior. The mean becomes `k` for a tier and route. The drift scenario injects a new prompt-attack pattern, lowers the Tier 1 posterior, and recommends escalation to Tier 2 while recalibration occurs.

The result is only as good as the shadow-mode labels. Selective labelling creates verification bias because checked traffic differs from unchecked traffic. A random audit slice is still required even when it appears economically wasteful.

