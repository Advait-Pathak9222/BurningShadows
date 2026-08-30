<div align="center">

# ControlPlane

**Checking every AI answer costs more than generating it. Checking a random sample
spends the same effort on "what are your opening hours" as on a payment instruction.
ControlPlane prices the difference.**

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](#run-it-locally)
[![Licence](https://img.shields.io/badge/licence-MIT-green)](LICENSE)
[![Runs offline](https://img.shields.io/badge/runs-offline%20%C2%B7%20no%20key%20%C2%B7%20no%20GPU-6D28D9)](#run-it-locally)
[![Console](https://img.shields.io/badge/live-console-FF4B4B?logo=streamlit&logoColor=white)](https://controlplane-ai.streamlit.app)

</div>

For every answer, ControlPlane estimates what the damage would be if that answer were wrong, and
buys checking only where the damage prevented is worth more than the check costs. Underneath sits a
per-route safety floor the budget cannot override, and every decision lands in a hash-chained ledger
where it can be re-derived from its own arithmetic.

---

## What it buys you

### Money

<table>
<tr>
<td width="50%" valign="top">

**92.8% of the protection for 10% of the compute**

Over 1,500 held-out interactions, the allocator averts **₹50,78,000** of expected loss for
**₹480.98** of checking. Checking every answer with the most expensive tier averts ₹54,69,400 — for
**₹4,800**.

</td>
<td width="50%" valign="top">

**Spend lands where you set it**

A shadow price alone cannot bound spend; it is a soft penalty that cannot price out a mandatory
check. Once the budget governor reserves the floor's cost, spend lands at **1.00x–1.03x** of budget
across the grid, against **3.75x** before.

</td>
</tr>
</table>

At two million interactions a year, that is **₹6.4 lakh** against **₹64 lakh** to check everything —
before a single reviewer is paid. And reviewers are where the money actually goes: at the budgets
worth running, **81 to 98 paise in every assurance rupee** is human time, not compute.

### Latency

Words stream while checking runs; only actions wait behind the verdict. So the two latencies are
different quantities, and the effect gate is the only one anybody waits on.

Under overload the choice is between slowing everyone down and refusing some people. Bounded
admission takes the second, which keeps the tail flat and makes the refusal visible:

| At 400 offered RPS | Text p99 | Effect p99 | Achieved RPS | Rejected |
|---|---:|---:|---:|---:|
| Unbounded | 540.6 ms | 1508.1 ms | 198.4 | 0 |
| **Bounded admission** | **26.2 ms** | **104.1 ms** | 63.7 | 499 |
| | **20x tighter** | **14x tighter** | | |

**Read the last two columns before the first two.** Bounded is not free: it turns 499 requests away
and its throughput is a third of unbounded's. What it buys is that the requests it does serve are
served properly, and the ones it cannot serve are told so, rather than everybody quietly waiting
half a second. Under degradation every served request still completed its mandatory assessment,
none bought a Tier 2 check, and no rejected request ever generated text.

Full table, including the 20 and 80 RPS points where bounded costs almost nothing:
[runtime results](docs/results/runtime.md).

---

> **Offline is a property of the evidence, not of the product.** Everything above runs against a
> seeded provider and lexical detector stubs — no API key, no network call, no GPU. The latency
> figures therefore measure the scheduler and not a production model; they are reported because the
> *shape* is a property of the admission design rather than of anything a vendor supplies.
>
> Freezing detector quality is also what makes the measured cost gain attributable to *allocation*
> rather than to a vendor's model, and it is why anyone can reproduce these numbers exactly. On
> where an LLM judge belongs and what changes before an enterprise deployment:
> [industry fit](docs/INDUSTRY-FIT.md). To see it running: [live console](https://controlplane-ai.streamlit.app)
> and [deployment notes](docs/DEPLOYMENT.md).

---

## Architecture

The gateway uses only the request, the response, the supplied context, and any proposed tool calls.
It needs no model weights, hidden states, or log probabilities. Text may stream while verification
runs; actions that change something wait behind a separate gate.

<p align="center">
  <img src="docs/images/architecture.png" alt="ControlPlane architecture across four planes: admit, observe, decide, and act and prove" width="1000">
</p>

| Plane | What it does |
|---|---|
| **Admit** | A per-route token bucket and bounded lanes decide whether there is capacity. A preflight Tier 0 scan then reads the prompt on its own and refuses it outright above an injection score of 0.70. Both happen before the model generates anything, so a refused request pays for neither generation nor checking. |
| **Observe** | Tier 0 rules and Tier 1 signals score the answer on five harm axes. Isotonic calibration turns those scores into probabilities, and the evidence regime records what can be checked at all. |
| **Decide** | The release floor marks what must be checked. The allocator prices each remaining tier against the budget's shadow price. Tier 2 runs only when it is selected, and the decision is recomputed with its signal. |
| **Act & prove** | A verdict of allow, annotate, abstain, hold or block covers the text. Proposed effects are permitted, held or denied independently. Everything is appended to the hash chain. |

The decision rule prices each candidate check without letting the budget relax the route floor:

```text
expected loss = calibrated risk × consequence
check when  expected loss × catch rate  >  (1 + shadow price) × check cost
```

### One request, end to end

Held-out row `cp-02477`: a finance-route request carrying a `transfer_funds` call, where the model
echoes back an attempt to exfiltrate a secret the source says must never be repeated.

<p align="center">
  <img src="docs/images/traced-request.png" alt="One held-out request traced through all nine decision stages" width="900">
</p>

Component contracts and the full request sequence: [architecture notes](docs/ARCHITECTURE.md).
Both diagrams are hand-authored SVG and regenerate from their own source, so a figure cannot drift
away from the system it describes: [architecture.html](docs/images/architecture.html) and
[traced-request.html](docs/images/traced-request.html), rendered with
`chrome --headless --screenshot`.

---


## What we measured

### 1. Human attention is where assurance money goes

**What the claim means.** Running a guardrail costs money in two places: the automated checks, and
the people who review whatever those checks escalate. Of every rupee spent on assurance, **81 to 98
paise go to the humans**, not the machines. Buying a cheaper or faster model optimises the small
part of the bill.

The arithmetic is a ratio of two configured prices. A reviewer costs ₹1,200/hour and takes 6 minutes
per case, so **one completed review costs ₹120**. The most expensive automated check — a Tier 2 LLM
judge — costs **₹3.20**. A review is **37.5x** an automated check, so it takes only a handful of
escalations to outweigh checking every response by machine.

**The reviewer rate is derived, not measured, and it is the number to push on.** ₹1,200/hour is a
₹10,00,000 base at a 1.8x loading over 1,500 productive hours. That sits at the *top* of a
defensible band, which is the end that flatters this argument, so the whole band and what it does
to the conclusion are worked through in [assumptions](docs/03-assumptions.md). The short version: at
the budgets the knee curve recommends, human attention is 91% to 98% of the bill anywhere between
₹300 and ₹1,800 an hour. The claim survives its own sensitivity analysis; at 100% coverage on a
₹300/hour desk it does not, and that is stated there too.

Over 1,500 held-out interactions, with 166 reviews completed at the configured capacity (₹19,920 of
attention), against the compute the allocator actually spends:

| Compute budget | Automated checking | Human review | **Attention share** | Cases raised |
|---:|---:|---:|---:|---:|
| 10% | ₹480.98 | ₹19,920 | **97.6%** | 246 |
| 25% | ₹1,098.58 | ₹19,920 | 94.8% | 327 |
| 40% | ₹1,920.18 | ₹19,920 | 91.2% | 344 |
| 60% | ₹2,812.84 | ₹19,920 | 87.6% | 406 |
| 80% | ₹3,839.64 | ₹19,920 | 83.8% | 484 |
| 100% | ₹4,800.00 | ₹19,920 | 80.6% | 569 |

The share falls as the compute budget rises simply because the numerator grows; even at a 100%
budget — checking every response with the most expensive tier available — **four fifths of the bill
is still people**.

This one does not depend on a corpus. It is the ratio of a reviewer-hour to a check, and it holds
wherever that ratio holds. Halve the review cost or double the check cost and the share moves, but
an operator can compute their own number from two figures they already know.

Raising the compute budget raises the number of cases needing a person, because more checking finds
more to escalate. Reviewer capacity is fixed, so the queue saturates and what differs between
policies is which cases get served. That makes serving order worth measuring.

At a fixed reviewer capacity, on identical cases, the shipped queue rule serves **1.59x** the
expected loss that first-in-first-out does from the same **166** completed reviews:

| Serving rule | SLA breaches | Expected loss served | High-value cases shed |
|---|---:|---:|---:|
| **deadline_density** (shipped) | 65 | **₹3,430,681** | **2** |
| fifo (baseline) | 139 | ₹2,162,224 | 15 |
| random (baseline) | 47 | ₹2,816,476 | 9 |
| density (ablation) | **48** | **₹3,798,647** | **2** |
| deadline (ablation) | 150 | ₹2,200,133 | 15 |

Every rule above pays the same **20% sampling reserve**: one slot in five is filled uniformly at
random rather than by the rule. That reserve is what makes the calibrator refittable at all — see
[section 8](#8-the-system-can-relearn-and-refuses-to-relearn-badly) — and it is charged to every
rule here, because a serving figure measured without it is one no deployment can reach.

The `density` ablation — the shipped rule with its deadline term removed — leads on both axes, and
is reported as the stronger rule. Ordering is still the smaller lever: keeping up with arrivals at
this budget needs **3.0 reviewers** against the two the scenario staffs, rising to **6.8** at full
Tier-2 coverage. No serving rule substitutes for that.

Full detail: [queue comparison](docs/results/attention.md).

<details>
<summary><b>2. Authorisation matters more than recognition</b> — Why pattern matching cannot work here, and what replaced it <b>(AUC 0.5881 → 0.9879)</b></summary>
<br>
The earlier pattern-matching PII detector scored **0.5881 AUC**. Measuring the ceiling explained
why: a *perfect* shape-only detector reaches **0.5869** on this corpus, so pattern matching had
nothing left to give.

|  | Harmful | Permitted |
|---|---:|---:|
| **Contains PII-shaped text** | 37 | **309** |
| **No pattern to match** | **57** | 1,097 |

309 held-out rows carry a real identifier in a permitted disclosure — a support agent reading a
customer their own work address — and 57 genuine leaks contain no recognisable pattern at all.

Scoring **whether a disclosure is grounded in the authorised source**, rather than whether it looks
like personal data, changes the result:

| Detector | AUC | Precision | Recall | Rows flagged |
|---|---:|---:|---:|---:|
| Pattern rules | 0.5881 | 0.11 | — | — |
| Perfect shape-only detector (ceiling) | 0.5869 | — | — | — |
| Microsoft Presidio | 0.5825 | 0.0747 | high | 1,044 of 1,500 |
| **ControlPlane** | **0.9879** | **1.000** | **0.766** | 72 |

Presidio answers "does this text contain personal data" accurately. The question a business needs
answered is whether this requester may receive this value on this route — and that answer lives in
the evidence, not the words. Mechanism-by-mechanism attribution and ablations:
[PII probe](docs/results/pii.md).

</details>
<details>
<summary><b>3. The guarantee holds on real traffic — and we know what breaks it</b> — The release floor on five public conditions, and the rule for when it is worth having</summary>
<br>
The results above run on a corpus we generated, so the system was run against **five public
benchmarks** — see [the corpus table](#the-corpora) below. Endpoints were pre-registered first.

**The per-route release floor was never violated on held-out data.** On five conditions it held
*non-vacuously* — meaning rows were actually released unchecked and the bound still bound:

| Corpus | Observed unchecked harm | α | Released rows |
|---|---:|---:|---:|
| ToxicChat | 0.0712 | 0.15 | 5,083 |
| ToxicChat (OpenAI moderation as Tier 1) | 0.0645 | 0.15 | 5,041 |
| ToxicChat (human-annotated, OpenAI Tier 1) | 0.1156 | 0.15 | 2,811 |
| BeaverTails | 0.0744 | 0.15 | 9,994 |
| RAGTruth | 0.0933 | 0.15 | 525 |

**Elsewhere it held vacuously, and that is reported as a limit rather than as more successes.**
Aegis (52.8–66.1% harmful), OR-Bench (33.5%), BeaverTails at its natural 55.8% rate, and ToxicChat's
human-annotated subset under our own lexical Tier 1 all leave the floor demanding a check on
essentially every row: mandatory coverage 1.0000, zero rows released unchecked, the bound satisfied
by construction and carrying no information.

That yields a rule worth having, computable from two numbers before deployment: **the release floor
is only informative when α exceeds the harm base rate.** An operator whose traffic is a third
harmful at α = 0.15 is not getting a guarantee, they are getting full coverage — and should either
raise α or budget for checking everything.

And we know precisely what breaks it. Fitting a detector on rows that later certify the bound made
it claim 0.1407 while held-out data showed **0.2800** — a violated guarantee. Restoring the
fitting/selection split fixed it. **The discipline is the guarantee**, and both halves of that are
on the record.

</details>
<details>
<summary><b>4. Detection is in band on two benchmarks, and out of band on a third</b> — Benchmark results against published detectors, including the endpoint we failed</summary>
<br>
Read the **null** column before the score. On an imbalanced corpus, a policy that flags every
single row scores `2p/(1+p)`, which can look respectable and beat published numbers while detecting
nothing. The margin over that null is the only part that is ours.

| Benchmark | ControlPlane | Flag-everything null | Margin | Published comparison | Verdict |
|---|---:|---:|---:|---|---|
| ToxicChat (AUPRC) | **0.597** | 0.071 | +0.526 | Llama Guard 0.664 · OpenAI Mod 0.588 · Perspective 0.532 | in band ¹ |
| RAGTruth (F1) | **0.601** | 0.518 | +0.083 | LettuceDetect 0.792 · GPT-4 prompt 0.634 · RAGAS 0.520 | in band ² |
| BeaverTails, natural 55.8% harm (F1) | 0.747 | **0.716** | **+0.031** | none quoted ³ | margin only ³ |
| BeaverTails, corrected 7% harm (F1) | **0.165** | 0.139 | +0.026 | none quoted ³ | margin only ³ |
| **Aegis (AUPRC)** | **0.811** | 0.661 | +0.151 | band 0.860 – 0.941 | **below band — endpoint failed** |
| OR-Bench (AUC) | 0.784 | 0.500 | +0.284 | operating point below | partial ² |

¹ **This number is largely OpenAI's, not ours.** Pre-registration 6 substitutes OpenAI's bundled
moderation score as the Tier 1 signal; ControlPlane supplies calibration, the floor and the
allocator around it. With our own lexical Tier 1 the same corpus scores far lower.

² Uses a detector fitted on that corpus (`fitted_grounding`, `fitted_bayes_bow`). These are
**evaluation adapters**, fitted on the calibration fold and *not wired into the serving path*.

³ **BeaverTails carries no published comparison, and the band we used to quote has been
withdrawn.** An audit of every published figure on this page could not trace the "0.364 - 0.839"
band we had been printing to any source, so it is gone. It should never have been there for a
second reason: our BeaverTails label is our own mapping of the corpus's 14 categories onto five
harm axes, so no published F1 is measured on the same target and any band would compare two
different questions. What survives is the margin over the trivial null, which is small. The
headline was also misleading in its own right: 0.749 was measured at the natural 55.8% harm rate,
where flagging every row already scores 0.716. At a deployment-realistic 7% prevalence the same
pipeline scores **0.165**. Both rows are shown; previously only the flattering one was.

**Where every published number in that table comes from.** Each was re-checked against its primary
source on 29 August 2026, and the constants in
[`external_probes.py`](controlplane/eval/external_probes.py) carry the same citations.

| Figure | Source |
|---|---|
| ToxicChat AUPRC — Llama Guard 0.664, OpenAI Mod 0.588, Perspective 0.532 | [Llama Guard, arXiv:2312.06674](https://arxiv.org/abs/2312.06674) |
| RAGTruth F1 — LettuceDetect 0.792, Llama-2-13B 0.787, Luna 0.654, GPT-4 Turbo 0.634, RAGAS 0.520 | [LettuceDetect, arXiv:2502.17125](https://arxiv.org/abs/2502.17125), Table 2 |
| Aegis AUPRC — Perspective 0.860, OpenAI Mod 0.895, Llama Guard Base 0.930, Llama Guard Defensive 0.941 | [Aegis model card](https://huggingface.co/nvidia/Aegis-AI-Content-Safety-LlamaGuard-Defensive-1.0), reporting [arXiv:2404.05993](https://arxiv.org/abs/2404.05993) |
| OR-Bench refusal — Claude-3-Opus 91.0%, Llama-3-70b 37.7%, Mistral-large 9.7%, GPT-4o 6.7% | [OR-Bench, arXiv:2405.20947](https://arxiv.org/abs/2405.20947), Table 2 |
| OR-Bench toxic catch — 98.1% / 78.7% / 72.8% / 84.9% | Same paper, Table 3, converted from the acceptance rates it reports |
| BeaverTails | **No published band.** See note 3 above. |

<p align="center">
  <img src="docs/images/benchmark-comparison.png" alt="ControlPlane against published detectors on five public benchmarks, with the trivial null shown behind each score" width="900">
</p>

**[Aegis](docs/results/aegis.md) is a failure and is reported as one.** 0.811 AUPRC is below
Perspective API, the weakest published system on that benchmark. Two things it taught us are worth
more than the score: our shipped lexical detectors flagged **100% of its rows** while scoring an F1
that *looks* competitive purely because the base rate is 66% — a flag-everything policy scores 0.796
there — and our PII mechanism drops from 0.9879 on our corpus to **0.5834** on Aegis, which is the
sharpest available confirmation that it measures authorisation and not recognition.

**[OR-Bench](docs/results/orbench.md) is the first measurement of what we do to safe traffic.** On
prompts that state-of-the-art models refuse despite being safe, we refuse **13.5%** — a third of
Llama-3-70b's 37.7% — while catching 66.7% of genuinely toxic prompts against its 78.7%. GPT-4o and
Mistral-large beat us on both axes; Claude-3-Opus and Llama-3-70b do not.

The harness was validated before it was trusted: our AUPRC for OpenAI Moderation on ToxicChat is
0.6321 against the published 0.588 — a 0.044 gap we cannot fully account for, most likely split or
aggregation differences, and it bounds how precisely any of these comparisons can be read.

Every figure in this section is regenerated by `make benchmarks`, which writes each result file and
the comparison page from them. Full detail and every caveat:
[benchmarks](docs/results/benchmarks.md).

</details>
<details>
<summary><b>The corpora</b> — The six corpora, their licences, and what each one was for</summary>
<br>
Six corpora, five of them public and none of them ours to grade. Every number above names the one it
came from, and each external corpus has a pre-registration written before it was run.

| Corpus | Rows (cal / test) | Base rate | Axes labelled | Licence | What it tests |
|---|---:|---:|---:|---|---|
| [Synthetic](data/dataset_manifest.yaml) | 1,500 / 1,500 | 15.6% | 5 | generated here | The decision system, with span-level ground truth |
| [ToxicChat](https://huggingface.co/datasets/lmsys/toxic-chat) | 5,082 / 5,083 | 7.1% | 2 | CC-BY-NC-4.0 | Real user traffic, and a published AUPRC to check our harness against |
| [BeaverTails](https://huggingface.co/datasets/PKU-Alignment/BeaverTails) | 70/30 of 330k | 7% and 55.7% | 4 | CC-BY-NC-4.0 | Multi-axis harm, and prevalence correction |
| [RAGTruth](https://arxiv.org/abs/2401.00396) | 15,090 / 2,700 | 34.9% | 1 | **MIT** | Grounding — the only corpus that supplies retrieved context |
| [Aegis 1.0](https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-1.0) | 10,798 / 1,199 | 52.8% / 66.1% | 3 | **CC-BY-4.0** | Human-annotated multi-axis harm, incl. the only public `pii_leak` labels |
| [OR-Bench](https://huggingface.co/datasets/bench-llms/or-bench) | 997 / 977 | 33.5% | 3 | **CC-BY-4.0** | Over-refusal: adversarially hard *safe* prompts |

Two of the six are non-commercial, so no commercial claim rests on them alone. Every external corpus
is downloaded on first use and cached under `data/external/`; `make demo` never touches the network.

```bash
make toxicchat     # ToxicChat probe
make benchmarks    # Aegis and OR-Bench
```

</details>
### 5. The budget is a budget

A shadow price is a soft constraint. It cannot bound spend on its own, and ours did not: at the
tightest setting the allocator **spent 3.75x its budget** while the fixed-rate baseline it was
compared against was held to the budget exactly. Two things defeat the price — the conformal floor
is not discretionary and cannot be priced out by design, and a row worth several thousand rupees
stays worth checking at any λ the controller reaches.

`BudgetGovernor` fixes it by *reserving* the floor's own cost: discretionary spending stops once
committed spend plus the expected remaining floor cost reaches the budget, and the allocator degrades
to mandatory-only rather than overspending. The floor rate is estimated on calibration rows, never on
the traffic being rationed.

| Budget | Before | **After** |
|---:|---:|---:|
| 1.0% | 3.75x | **1.03x** |
| 3.0% | 2.30x | **1.01x** |
| 5.6% | 1.65x | **1.00x** |
| 10% | 1.38x | **1.00x** |
| 25%–100% | 0.92x–1.00x | 0.92x–1.00x |

No conformally-forced row goes unchecked under enforcement, on any budget tested.

**How the budget is set.** It is configuration, not a learned quantity. `config/economics.yaml`
declares `gateway_budget_rate_inr: 0.75` — assurance rupees per served interaction — and the
evaluation sweeps a grid expressed as a fraction of full Tier-2 coverage. What *is* dynamic is the
shadow price: `BudgetController` raises λ when observed spend runs ahead of the target and lowers it
when it runs behind, so the cut line moves with live traffic while the budget itself stays where the
operator put it.

Two numbers make a budget honest, and both are now computed and reported:

- **The floor cost** — what the guarantee obliges at any price — is **₹51.84** on our test corpus,
  1.08% of full Tier-2 coverage. A budget below it is *infeasible*: the floor wins and the run
  reports the overspend rather than silently skipping a mandatory check. Which of the two gives is
  an operator's decision, not ours.
- **The blanket-coverage boundary** is `c_tier1 / c_tier2` = `0.18 / 3.20` = **5.625%**. Above it,
  checking every row at Tier 1 is affordable and no selective policy can beat blanket coverage. It
  came out at exactly 5.6250% on Aegis and OR-Bench too, because it is arithmetic rather than a
  property of any corpus.

<details>
<summary><b>6. What allocation is, and is not, worth</b> — When budget-aware allocation beats a tuned fixed rate, and when it does not</summary>
<br>
Budget-aware allocation is **not** universally better than a well-ranked fixed-rate policy, and
saying otherwise would not survive a judge with the repository open. At matched actual spend the
allocator wins 5 of 7 budgets on our corpus, 4 of 7 on BeaverTails, 3 of 7 at its natural
prevalence, 3 of 7 on OR-Bench and **1 of 7 on Aegis**, with gains between −20% and +11%.

Where it helps is characterised rather than asserted, and it needs **two** conditions:

1. **The harm mix must vary**, so equally risky rows carry unequal consequences. Measured as
   `Spearman(risk, expected loss) < 1`.
2. **Blanket coverage at the cheapest effective tier must be unaffordable**, i.e. the budget must
   sit below the 5.625% boundary above.

Aegis is what made this precise. It is the **first public corpus where condition 1 holds** —
Spearman 0.816, against 1.000000 on ToxicChat and 0.998494 on BeaverTails — and the allocator still
wins only 1 of 7 budgets there, because condition 2 fails: below the boundary the conformal floor
already obliges ₹215.82 of the ₹216 that blanket Tier 1 costs, so there is nothing left to allocate.

**The precondition is necessary but not sufficient**, and both conditions are computable from the
cost model and the label structure before deploying anything. Full measurements:
[allocation regime](docs/results/allocation-regime.md).

</details>
<details>
<summary><b>7. Endpoints were fixed before the work started</b> — Pre-registration, and the results that came back negative</summary>
<br>
Each significant claim has a pre-registration written in advance stating what would count as
success. Results are reported against those criteria whether or not they were met, and the record
of how each result was reached — including a queue-model defect that was recorded before it was
corrected — is preserved in [the pre-registrations](docs/PREREGISTRATION.md) and in
[the queue provenance notes](docs/results/attention.md).

</details>
### 8. The system can relearn, and refuses to relearn badly

The calibration map used to be fitted once, at startup, off a seeded file, and never again — so the
map that turns a raw score into a probability never saw live traffic, and every conformal threshold
sat on top of it. `make relearn` closes that loop. It joins the raw scores now carried in the ledger
to the per-axis labels reviewers give, refits the isotonic maps on the fitting fold, re-selects the
thresholds on the disjoint one, and writes a versioned artifact.

**The gate is the point, not the refit.** `learn_then_test` cannot fail: with no passing threshold
it returns 0.0, which releases nothing and satisfies the bound by checking everything. So a release
is refused when the sample is too thin, when the threshold collapses to full coverage, when
calibration error exceeds an absolute ceiling, or when it regresses against the map already
serving. Artifacts are bound to a detector fingerprint and a mismatch loads nothing, because
serving a map fitted against different detectors corrupts every probability while spend barely
moves — measured here, a cruder map changed **22.4% of tier decisions and removed all 80 blocks
while total spend stayed within 0.3%**.

**Most reviewer labels cannot be learned from, and that is the interesting part.** The queue serves
by expected loss per reviewer minute, so harmful rows are likelier to be reviewed *within* the
raised population. That is selection happening inside a stratum, and no stratum-level weight undoes
it: the value-ordered sample runs **37.2% harmful against 18.4% in the traffic it has to price**,
and inverse-probability weighting moved that to 38.2%. The same offline map that scores ECE
0.008–0.043 on the test set scores **0.1425** on it.

So only two designs qualify: rows drawn by the **20% sampling reserve** described above, and the
fixed-rate audit of released rows. Everything the serving rule chose is used for catch rates and
excluded from the fit. On this corpus that leaves 73 usable pairs against the ~100 per route the
bound needs, so `make relearn` currently **refuses on all three routes and says so**:

```
Labelled pairs joined from the chain: 73
  REFUSED   finops-agent: too few rows: 6 fitting (need 40), 12 selection (need 60)
```

That is the mechanism working. A live desk accumulates labels across days; a single pass over 1,500
rows does not. What the reserve costs is visible in the queue table above — the shipped rule moved
from 1.57x to 1.59x, because the reserve costs FIFO more than it costs a value-ordered rule.

---


## Evidence at a glance

Every figure below is written by a committed command — `make report`, `make attention`,
`make pii-probe`, `make sensitivity` or `make benchmarks` — into a tracked file, and
`./run_submission.sh` fails if any of them stops reproducing byte-for-byte.

Two things that are **not** measurements and should not be read as such: the rupee consequences per
harm axis and the ₹120 reviewer cost are **configured assumptions** from
[`config/`](config/economics.yaml), so every monetary figure inherits them. The sensitivity sweep
exists to bound how much that matters.

| Question | Result |
|---|---|
| Does allocation beat a tuned fixed-rate policy? | Not universally. At matched actual spend it wins **5 of 7** budgets here, 4 of 7 and 3 of 7 on BeaverTails, 3 of 7 on OR-Bench and **1 of 7** on Aegis. See [allocation regime](docs/results/allocation-regime.md). |
| Does allocation beat checking everything? | At a 10% budget it averts **₹5,078,000** for **₹480.98**, against **₹5,469,400** for **₹4,800** — 92.8% of the benefit for 10.0% of the compute. |
| Does the per-route release floor hold? | Observed unchecked harm **0.0560 / 0.0714 / 0.0529** against α **0.15**, over **339 / 476 / 397** released rows. Mandatory coverage **32.2% / 4.8% / 20.6%**. Vacuous on Aegis and OR-Bench, where the base rate exceeds α. |
| Are the risk scores calibrated? | Expected calibration error **0.008 – 0.043** by route. |
| Do consequence assumptions move decisions? | Across a **0.25x–4x** band, **10.9%** of tier decisions change and the verdict flip rate is **0%** — consequence prices a check but does not enter the release rule. |
| Is the audit trail complete? | **1,500 of 1,500** decisions and **205** reviews in one valid chain; **224 of 224** proposed effects logged. |
| Is the detector catch rate measured or assumed? | Measured. Labelled Tier 2 catch rate **0.930** against **0.880** configured, over **365** observations. |
| Does the allocator stay inside its budget? | Yes, once governed: **1.00x–1.03x** of budget across the grid, against up to **3.75x** before. The floor costs **₹51.84** and a budget below that is reported infeasible rather than silently breached. |
| What does it do to safe traffic? | Refuses **13.5%** of adversarially-hard safe prompts on OR-Bench, against 6.7%–91.0% for published models. |

<p align="center">
  <img src="docs/images/baselines.png" alt="Allocation policies and reviewer-queue serving rules compared" width="820">
</p>

Loss and cost figures are arithmetic over synthetic traffic and scenario-configured consequences.
They describe this implementation and its assumptions. **Wall-clock latency is not reported here at
all**: it timed lexical stubs, so it measured the machine rather than the decision system, and it was
not even stable between two runs on the same machine — which dirtied committed files on every run.
Latency is characterised in [`runtime.md`](docs/results/runtime.md) instead, where it is labelled as
a harness measurement and an empty sample is reported as `null` rather than as a perfect 0.0. Machine-readable sources:
[results](docs/results/results.json) · [queue](docs/results/attention.json) ·
[PII](docs/results/pii.json) · [sensitivity](docs/results/sensitivity.json) ·
[Aegis](docs/results/aegis.json) · [OR-Bench](docs/results/orbench.json).

---


## Run it locally

Python 3.11 or newer. The default path needs no API key, network call, model download, or GPU.

```bash
git clone https://github.com/Advait-Pathak9222/BurningShadows.git
cd BurningShadows
make install
make demo        # ~18s: builds the corpus, calibrates, runs the scenarios, verifies the chain
make console     # opens the inspection console at http://localhost:8501
```

<p align="center">
  <img src="docs/images/console.png" alt="The ControlPlane assurance console" width="880">
</p>

The console has five views over the same committed evidence. What each one shows, where its numbers
come from, and what to look at first: [console guide](docs/CONSOLE.md).

**One command, from a clean clone:**

```bash
./run_submission.sh     # venv, install, full gate, demo, report, byte-identity check
```

It runs the offline path only — no API key, no network, no GPU — and fails loudly if any committed
artifact does not reproduce byte-for-byte. Individual targets:

| Command | Writes |
|---|---|
| `make report` | [`docs/results/summary.md`](docs/results/summary.md) — allocation, floor, calibration, audit |
| `make attention` | [`docs/results/attention.md`](docs/results/attention.md) — reviewer-queue comparison |
| `make pii-probe` | [`docs/results/pii.md`](docs/results/pii.md) — disclosure detection and ablations |
| `make sensitivity` | [`docs/results/sensitivity.md`](docs/results/sensitivity.md) — the consequence sweep |
| `make loadtest` | [`docs/results/runtime.md`](docs/results/runtime.md) — admission control under load |
| `make relearn` | `data/learned/` — refits the calibrator from reviewer labels, or refuses and says why |
| `make toxicchat` | [`docs/results/toxicchat.json`](docs/results/toxicchat.json) — ToxicChat probe (downloads) |
| `make benchmarks` | [`docs/results/benchmarks.md`](docs/results/benchmarks.md) + Aegis, OR-Bench, BeaverTails, RAGTruth JSON (downloads) |

`make check` runs ruff, `mypy --strict` and the test suite. The two download targets fetch each
corpus at a **pinned commit revision** and verify its SHA-256 before use, so a corpus re-uploaded
upstream fails loudly rather than silently changing what these numbers mean.

On PowerShell without `make`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m controlplane.cli demo
.\.venv\Scripts\python.exe -m streamlit run console\streamlit_app.py
```

Experiment tracking is optional: with `pip install -e ".[tracking]"`, every `make report` writes one
MLflow run per policy and budget to `./mlruns`.

---


## Repository map

| Path | Purpose |
|---|---|
| `controlplane/gateway/` | OpenAI-shaped API, streaming, and admission integration |
| `controlplane/runtime/` | Bounded concurrency, reserved mandatory capacity, load harnesses |
| `controlplane/detectors/` | Tiered detector interfaces, offline stubs, disclosure logic, optional adapters |
| `controlplane/risk/` | Per-axis calibration and evidence regimes |
| `controlplane/guarantees/` | Per-route finite-sample release thresholds |
| `controlplane/economics/` | Cost model, budget controller, allocator |
| `controlplane/review/` | Human-review economics and queue strategies |
| `controlplane/learning/` | Refits the calibration maps from reviewer labels, and the gate that can refuse one |
| `controlplane/effects/` | Independent effect gating |
| `controlplane/ledger/` | Hash-chained decision and review records |
| `controlplane/eval/` | Reproducible evaluation, ablation, sensitivity and runtime commands |
| `controlplane/corpora/` | External-benchmark loaders, each pinned to a commit and checksummed |
| `config/` | Versioned policies, economics, runtime limits |
| `data/` | Seeded synthetic calibration and held-out traffic |
| `docs/results/` | Machine-readable results and their written interpretations |
| `console/` | The Streamlit inspection console — see [the console guide](docs/CONSOLE.md) |
| `site/` | Static project page, publishable to any host (see [Deployment](docs/DEPLOYMENT.md)) |
| `tests/` | Invariants, failure behaviour, reproducibility, regression coverage |
| `run_submission.sh` | Clone-and-run reviewer entrypoint: gate, demo, report, byte-identity check |
| `LICENSE` | MIT for this code; the external corpora keep their own licences and are not vendored |

**Worth reading first:** [`allocator.py`](controlplane/economics/allocator.py) holds the decision in
plain arithmetic, and [`conformal.py`](controlplane/guarantees/conformal.py) holds the guarantee
that overrides the budget.

## Scope and assumptions

Every assumed input is listed with its status and source in
[the assumptions register](docs/03-assumptions.md). The evaluation boundary — corpus provenance,
calibration assumptions, multi-worker considerations, and the evidence we would want next — is
documented in [Limitations](docs/LIMITATIONS.md). Policy packs are versioned control mappings and
are intended to be reviewed alongside legal and operational sign-off.

For the commercial framing, see the [business proposal](docs/07-business-proposal.md).

## Licence and data

The code and the generated synthetic corpus are **MIT** ([`LICENSE`](LICENSE)).

**No external dataset is vendored here.** The five evaluation corpora are downloaded at run time
into `data/external/`, which is untracked, each at a pinned commit revision whose SHA-256 is
verified before use. They keep their own licences: RAGTruth is MIT, Aegis and OR-Bench are
CC-BY-4.0, and **ToxicChat and BeaverTails are CC-BY-NC-4.0**. Results derived from the two
non-commercial corpora are reported for research and evaluation only, and no commercial claim in
this repository rests on them alone.
