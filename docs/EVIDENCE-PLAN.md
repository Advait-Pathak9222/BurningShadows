# Strengthening the evidence: real corpora and honest baselines

The one weakness a judge can defend attacking is that every number comes from a corpus we generated.
This is the plan to fix it, in priority order, with the trap that would quietly destroy our result
stated first.

---

## The trap: most safety benchmarks would break our result, not strengthen it

The obvious move is to grab a well-known safety benchmark — HarmBench, AdvBench, a jailbreak set —
and report numbers on it. **That would actively damage the project**, and it is worth understanding
why before any data is downloaded.

Those benchmarks are **balanced adversarial sets**: roughly half the rows are harmful by
construction. ControlPlane's entire thesis is triage under scarcity — expected loss is
`risk × consequence`, and the allocator earns its keep by *declining* to check rows where that
product is small. If half the corpus is harmful, almost every row clears the threshold, the
allocator checks nearly everything, and it converges to `check_all` with extra steps. We would have
spent the effort to prove our own contribution is worthless.

**The property we need is a realistic base rate**, and it is the single most important selection
criterion. Our synthetic corpus runs at roughly 6–9% harm. Any replacement has to be in that
neighbourhood or be *composed* to be.

A second criterion follows from what our detector actually scores. The disclosure mechanism asks
whether a statement is **grounded in the authorised source**, so a dataset without context documents
cannot exercise our strongest component at all.

> **A third criterion, learned the hard way.** The ToxicChat run
> ([results](results/toxicchat.md)) failed its pre-registered endpoint, and the cause was that the
> corpus labels **one** harm axis. With a single active axis the consequence multiplier is constant,
> `risk x consequence` reduces to a rescaling of `risk`, and the allocator is sorting the same list
> as the baseline it is being compared against — it cannot win by construction.
>
> **A corpus must be labelled on more than one harm axis to test allocation at all.** This is not the
> same as needing more routes: restricted to a single route, our own corpus still gives 0.83–0.96,
> because *which* axis fires changes the price. Check the axis coverage of any candidate corpus
> before spending a day on the ingest.

---

## Recommended corpora, in priority order

### 1. ToxicChat — the single highest-value addition

| | |
|---|---|
| **Source** | `lmsys/toxic-chat` on Hugging Face |
| **Size** | ~10,165 unique prompts (20,330 rows across two versions) |
| **Licence** | CC-BY-NC-4.0 — fine for competition and research, **not** for commercial use |
| **Base rate** | **7.22% toxicity** |

This is **real user traffic** from the Vicuna online demo, not curated prompts — messy, multi-turn,
and with the base rate we need almost exactly. Inter-annotator agreement is 96.11%.

Three things make it unusually well suited to us:

- The **7.22% toxicity rate** is close to our corpus's harm rate, so the allocation problem survives
  contact with it.
- It carries a separate **`jailbreaking`** label alongside `toxicity`, which maps onto our
  `injection_or_exfil` axis as a distinct harm rather than a subtype.
- Every row already ships **`openai_moderation`** scores. That is a *free, pre-computed,
  industry-standard baseline* — we can report ControlPlane against OpenAI's moderation endpoint on
  identical rows without making a single API call, which keeps the offline promise intact.

Schema per row: `conv_id`, `user_input`, `model_output`, `human_annotation`, `toxicity`,
`jailbreaking`, `openai_moderation`. That maps onto our `Interaction` with no structural work —
`prompt`, `response`, and two harm axes of ground truth.

**What it buys:** the sentence "validated on 10,000 rows of real user–assistant traffic" replaces
"synthetic corpus" in the README. That alone moves the evidence rating more than anything else on
this list.

### 2. RAGTruth — for the hallucination axis and the grounding mechanism

| | |
|---|---|
| **Source** | RAGTruth (`wandb/RAGTruth-processed` is a clean mirror) |
| **Size** | 17,790 rows (15,090 train / 2,700 test) |
| **Licence** | **MIT** — the most permissive on this list |
| **Structure** | query + **context passages** + model response + **span-level** hallucination labels |

Responses were generated naturally by six different LLMs (GPT-3.5, GPT-4, Mistral-7B, three Llama-2
variants), then annotated span by span into *evident conflict* (contradicts the context) and
*baseless information* (unsupported by it).

This is the only dataset here that exercises our **grounding** logic properly, because it actually
ships the source documents the answer was supposed to be faithful to. The two annotation types map
cleanly onto how our disclosure detector reasons about support.

**A bonus we should not waste:** span-level labels mean we can report per-span precision, which is
much stronger evidence than response-level AUC and is exactly the granularity our Tier 0 `Match.span()`
already produces.

### 3. Text Anonymization Benchmark (TAB) — real-world proof of our best claim

| | |
|---|---|
| **Source** | `github.com/NorskRegnesentral/text-anonymization-benchmark` |
| **Size** | 1,268 English European Court of Human Rights cases (1,014 train / 127 test) |
| **Structure** | PII spans annotated **DIRECT**, **QUASI**, or **no-mask** |

**This is the most important find on the list for our strongest claim.** Human annotators marked
14% of PII spans as direct identifiers, 56% as quasi-identifiers needing masking, and — critically —
left **30% of PII-shaped spans unmasked** as not requiring anonymisation.

That is our "authorisation beats recognition" thesis, observed independently, by trained annotators,
on real legal documents. We argued from a synthetic 2×2 that a large fraction of PII-shaped text is
a *permitted* disclosure and that any shape-based detector must therefore fail. TAB is a real corpus
where roughly a third of the PII-shaped spans are exactly that.

Presidio, by construction, flags on shape. On TAB it must over-flag the 30% no-mask spans. **That is
a head-to-head we can win on real data, on the claim we most want to defend.**

### 4. BBQ — the bias axis, if there is time

58,492 instances across nine social dimensions, each in **ambiguous** and **disambiguated** form.
The ambiguous variants are the interesting ones for us: the correct answer is "unknown", which lines
up with our `abstain` verdict and the evidence-regime machinery. Licensed for **non-commercial
research** only.

### 5. AgentDojo / InjecAgent — the tool-call gate

We gate proposed effects independently of the text, and almost nothing in the literature evaluates
that. These two do:

- **AgentDojo** — 97 user tasks and 629 security cases across banking, Slack, travel and workspace
  suites, with up to 18 tool calls per task. Multi-turn and realistic.
- **InjecAgent** — 1,000 examples designed to trigger unauthorised tool calls, split into direct-harm
  and data-stealing objectives.

The banking suite in AgentDojo maps almost directly onto our `finops-agent` route and its
`transfer_funds` effect class. This is the most defensible place to show that gating effects
separately from text is a real design decision rather than a flourish.

---

## Reframing the baseline comparison — this matters more than the datasets

The instinct is to benchmark ControlPlane *against* Llama Guard, WildGuard or ShieldGemma.
**We would lose that comparison, and we should not run it**, because those are dedicated detector
models and our Tier 2 is a keyword stub. Losing it would also be answering a question nobody asked:
we are not a detector.

Recent benchmarking of open-weight guard models hands us a much better experiment. The measured
picture is that these models have **non-overlapping strengths at very different costs**:

| Guard | Size | Reported behaviour |
|---|---|---|
| ShieldGemma | 2B | Highest precision at **82.20%**, but **misses 54.51%** of unsafe content |
| Llama Guard 3 | 8B/1B | Strongest on multi-category moderation, MLCommons-aligned taxonomy |
| WildGuard | 7B | Highest precision on benign sets; **0.889** in-domain but **0.278** F1 out-of-domain |

The published conclusion is that no single model wins and that pairing models with non-overlapping
strengths is the right approach. **That is a tiering problem, and tiering under a budget is precisely
what we built.** A cheap 2B model that is precise but misses half, and an expensive 8B model that
catches more, *is* a Tier 1 / Tier 2 decision.

So the experiment to run is:

> At a fixed assurance budget on ToxicChat, does ControlPlane's allocation between ShieldGemma
> (cheap Tier 1) and Llama Guard 3 (expensive Tier 2) avert more expected loss than
> (a) ShieldGemma on everything, (b) Llama Guard on everything, (c) random sampling of Llama Guard
> at matched spend?

This is winnable, honest, and genuinely novel. It tests our actual contribution — allocation — while
using other people's detectors as the tiers, which is exactly how the product is meant to work. And
it converts the guard models from competitors into components, which is the strategic position we
want anyway.

The `BetaBinomialCatchRate` machinery already re-measures a swapped detector's catch rate from
labelled outcomes, so plugging these in is the flow the system was designed for.

---

## Suggested order of work

| Step | Effort | What it retires |
|---|---|---|
| 1. ToxicChat ingest + refit calibration and release thresholds | ~1–2 days | "Everything is synthetic" |
| 2. Report against the bundled `openai_moderation` baseline | ~2 hours | "No comparison to industry tools" |
| 3. RAGTruth ingest for the hallucination axis | ~1–2 days | "The grounding claim is untested" |
| 4. TAB head-to-head against Presidio | ~1 day | Proves the authorisation thesis on real data |
| 5. The ShieldGemma / Llama Guard allocation experiment | ~2–3 days | "Why not just use a guard model?" |

**If only one thing gets done, do step 1 and 2 together.** Real traffic plus a real baseline, from a
single dataset, in under two days.

---

## Things to be careful about

- **Licences differ and must be recorded.** RAGTruth is MIT. ToxicChat and BBQ are non-commercial.
  That is fine for this submission but belongs in the assumptions register, and it constrains any
  commercial framing in the business proposal.
- **Recalibration is mandatory, not optional.** Isotonic calibrators and the per-route conformal
  thresholds are fit to the current corpus and will not transfer. Every new dataset needs its own
  fitting/selection split, and the fold discipline that kept the bound honest must be preserved —
  fitting and selecting on the same rows previously made the bound optimistic by roughly 9×.
- **Route and consequence structure has to be assigned, and that is a modelling choice.** None of
  these corpora carry our routes or consequence tables. Whatever mapping we choose must be
  pre-registered *before* the run, or we lose the methodological high ground that is currently the
  project's best feature.
- **Do not quietly drop the synthetic corpus.** Keep it as the reproducible offline default so
  `make demo` still runs with no network. Real corpora become an additional, clearly-labelled
  evaluation, not a replacement.
