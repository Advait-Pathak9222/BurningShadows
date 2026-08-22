# Dataset plan

The shipped 600-row corpus is synthetic and contains no copied benchmark rows. The repository does
not yet declare a source licence. Public datasets are listed for external validation but are not
downloaded by `make demo`, so the judge path stays offline and does not redistribute gated data.

| Dataset | Use | Access and licence decision | Prototype decision |
| --- | --- | --- | --- |
| [LLM-AggreFact](https://huggingface.co/datasets/lytang/LLM-AggreFact) | Grounded factuality and claim-document support | 59,740 dev/test examples on the current card; CC BY-ND 4.0; gated; evaluation only, no pretraining or fine-tuning | Recommended first external Tier 1 evaluation. Do not vendor. |
| [BBQ](https://github.com/nyu-mll/BBQ) | Ambiguous and disambiguated QA bias across protected dimensions | CC BY 4.0 | Use as a separate fairness evaluation; do not translate its US social categories into incident costs without local review. |
| [Protect AI prompt-injection validation](https://huggingface.co/datasets/protectai/prompt-injection-validation) | Prompt-attack detector evaluation | Public card with 3,227 examples reported by downstream model cards; licence metadata was not clear in the inspected card | Do not vendor until licence review. |
| [Lakera PINT benchmark](https://github.com/lakeraai/pint-benchmark) | Generalisation test for prompt-injection scanners | Benchmark code and dataset connectors | Use to compare an optional detector adapter; keep vendor benchmark claims separate. |
| [AI4Privacy pii-masking-400k](https://huggingface.co/datasets/ai4privacy/pii-masking-400k) | Multilingual PII detection and masking | Academic/non-commercial terms; redistribution and derivatives require permission | Not included. Seek permission or choose a permissive alternative before any commercial pilot. |
| [SelfCheckGPT WikiBio annotations/code](https://github.com/potsawee/selfcheckgpt) | Ungrounded consistency and hallucination ranking | Research repository; source-specific terms must be checked before redistribution | Use only in an isolated research evaluation. |

## Shipped schema

Each JSONL interaction contains:

- stable interaction id and split;
- route and jurisdiction;
- prompt, response, grounding documents, and optional comparison samples;
- proposed tool calls and effect class;
- a five-axis ground-truth harm vector;
- a distribution-shift marker.

`make data` always recreates the same 600 rows from seed `20260822`. Route weighting creates more near-miss false positives for the internal route and more factual failures for FinOps, which gives the allocator a reason to differ from raw-score ordering. That weighting is a scenario design choice, not a prevalence estimate.
