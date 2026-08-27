# ControlPlane

**Companies deploying AI assistants cannot check every answer — thorough checking costs more than
the AI itself. So most check a random sample, which spends the same effort on "what are your
opening hours" as on a payment instruction.**

ControlPlane treats this as an allocation problem rather than a detection problem. For every
answer it estimates what the damage would be if that answer were wrong, and buys checking only
where the damage prevented is worth more than the check costs. Underneath sits a per-route safety
floor that the budget cannot override, and every decision is written to a hash-chained ledger where
it can be re-derived from its own arithmetic.

It runs offline against a seeded provider and lexical detector stubs, so the committed evidence
tests the decision system rather than production model quality. No API key, no network call, no GPU.

> **Offline is a property of the evidence, not of the product.** In production the gateway sits in
> front of a model API, and Tier 2 is designed to be an LLM-judge call. Freezing detector quality is
> what makes the measured gain attributable to allocation rather than to a vendor's model — and it
> means anyone can reproduce these numbers exactly.

**Hosted:** [live console](https://controlplane-ai.streamlit.app) — see
[Deployment](docs/DEPLOYMENT.md).

On where an LLM judge belongs, what has to run locally, and what changes before an enterprise
deployment: [Industry fit](docs/INDUSTRY-FIT.md).

---

## What we measured

### 1. Human attention is where assurance money goes

**What the claim means.** Running a guardrail costs money in two places: the automated checks, and
the people who review whatever those checks escalate. Of every rupee spent on assurance, **81 to 97
paise go to the humans**, not the machines. Buying a cheaper or faster model optimises the small
part of the bill.

The arithmetic is a ratio of two configured prices. A reviewer costs ₹1,200/hour and takes 6 minutes
per case, so **one completed review costs ₹120**. The most expensive automated check — a Tier 2 LLM
judge — costs **₹3.20**. A review is **37.5x** an automated check, so it takes only a handful of
escalations to outweigh checking every response by machine.

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

At a fixed reviewer capacity, on identical cases, the shipped queue rule serves **1.57x** the
expected loss that first-in-first-out does from the same **166** completed reviews:

| Serving rule | SLA breaches | Expected loss served | High-value cases shed |
|---|---:|---:|---:|
| **deadline_density** (shipped) | 63 | **₹3,348,580** | **1** |
| fifo (baseline) | 149 | ₹2,129,319 | 16 |
| random (baseline) | 47 | ₹2,816,476 | 9 |
| density (ablation) | **35** | **₹3,875,966** | **1** |
| deadline (ablation) | 160 | ₹2,266,731 | 13 |

The `density` ablation — the shipped rule with its deadline term removed — leads on both axes, and
is reported as the stronger rule. Keeping up with arrivals needs **6.8 reviewers** against the two
the scenario staffs, which is the larger lever.

Full detail: [queue comparison](docs/results/attention.md).

### 2. Authorisation matters more than recognition

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

### 3. The guarantee holds on real traffic — and we know what breaks it

The results above run on a corpus we generated, so the system was run against **five public
benchmarks** — see [the corpus table](#the-corpora) below. Endpoints were pre-registered first.

**The per-route release floor held on all five.** On three of them it held *non-vacuously*, on data
the thresholds never saw:

| Corpus | Observed unchecked harm | α | Released rows |
|---|---:|---:|---:|
| ToxicChat | 0.0712 | 0.15 | 5,083 |
| ToxicChat (calibrated Tier 1) | 0.0639 | 0.15 | 5,037 |
| ToxicChat (human-annotated subset) | 0.1147 | 0.15 | 2,808 |
| BeaverTails | 0.0744 | 0.15 | 9,994 |
| RAGTruth | 0.0939 | 0.15 | 522 |

**On the other two it held vacuously, and that is reported as a limit rather than a sixth and
seventh success.** Aegis (52.8–66.1% harmful) and OR-Bench (33.5%) both have base rates far above
α = 0.15, so the floor demands a check on essentially every row: mandatory coverage 1.0000, zero rows
released unchecked, the bound satisfied by construction and carrying no information.

That yields a rule worth having, computable from two numbers before deployment: **the release floor
is only informative when α exceeds the harm base rate.** An operator whose traffic is a third
harmful at α = 0.15 is not getting a guarantee, they are getting full coverage — and should either
raise α or budget for checking everything.

And we know precisely what breaks it. Fitting a detector on rows that later certify the bound made
it claim 0.1407 while held-out data showed **0.2800** — a violated guarantee. Restoring the
fitting/selection split fixed it. **The discipline is the guarantee**, and both halves of that are
on the record.

### 4. Detection is in band on three benchmarks, and out of band on a fourth

| Benchmark | ControlPlane | Published comparison | Verdict |
|---|---:|---|---|
| ToxicChat (AUPRC) | **0.662** | Llama Guard 0.626 · OpenAI Mod 0.588 · Perspective 0.532 | in band |
| BeaverTails (F1) | **0.749** | band 0.364 – 0.839 | in band |
| RAGTruth (F1) | **0.601** | LettuceDetect 0.792 · GPT-4 prompt 0.634 · RAGAS 0.520 | in band |
| **Aegis (AUPRC)** | **0.811** | band 0.860 – 0.941 | **below band — endpoint failed** |
| OR-Bench (over-refusal) | 13.5% at 66.7% catch | GPT-4o 6.7%/84.9% · Llama-3-70b 37.7%/78.7% | partial |

<p align="center">
  <img src="docs/images/benchmark-comparison.png" alt="ControlPlane against published detectors on three public benchmarks" width="900">
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
0.6321 against the published 0.588. Full detail and every caveat:
[benchmarks](docs/results/benchmarks.md).

### The corpora

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

- **The floor cost** — what the guarantee obliges at any price — is **₹46.26** on our test corpus,
  0.96% of full Tier-2 coverage. A budget below it is *infeasible*: the floor wins and the run
  reports the overspend rather than silently skipping a mandatory check. Which of the two gives is
  an operator's decision, not ours.
- **The blanket-coverage boundary** is `c_tier1 / c_tier2` = `0.18 / 3.20` = **5.625%**. Above it,
  checking every row at Tier 1 is affordable and no selective policy can beat blanket coverage. It
  came out at exactly 5.6250% on Aegis and OR-Bench too, because it is arithmetic rather than a
  property of any corpus.

### 6. What allocation is, and is not, worth

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

### 7. Endpoints were fixed before the work started

Each significant claim has a pre-registration written in advance stating what would count as
success. Results are reported against those criteria whether or not they were met, and the record
of how each result was reached — including a queue-model defect that was recorded before it was
corrected — is preserved in [the pre-registrations](docs/PREREGISTRATION.md) and in
[the queue provenance notes](docs/results/attention.md).

---

## Evidence at a glance

Every figure below is computed and committed. None are typed by hand.

| Question | Result |
|---|---|
| Does allocation beat a tuned fixed-rate policy? | Not universally. At matched actual spend it wins **5 of 7** budgets here, 4 of 7 and 3 of 7 on BeaverTails, 3 of 7 on OR-Bench and **1 of 7** on Aegis. See [allocation regime](docs/results/allocation-regime.md). |
| Does allocation beat checking everything? | At a 10% budget it averts **₹5,078,000** for **₹480.98**, against **₹5,469,400** for **₹4,800** — 92.8% of the benefit for 10.0% of the compute. |
| Does the per-route release floor hold? | Observed unchecked harm **0.0560 / 0.0714 / 0.0529** against α **0.15**, over **339 / 476 / 397** released rows. Mandatory coverage **32.2% / 4.8% / 20.6%**. Vacuous on Aegis and OR-Bench, where the base rate exceeds α. |
| Are the risk scores calibrated? | Expected calibration error **0.008 – 0.043** by route. |
| Do consequence assumptions move decisions? | Across a **0.25x–4x** band, **10.9%** of tier decisions change and the verdict flip rate is **0%** — consequence prices a check but does not enter the release rule. |
| Is the audit trail complete? | **1,500 of 1,500** decisions and **205** reviews in one valid chain; **224 of 224** proposed effects logged. |
| Is the detector catch rate measured or assumed? | Measured. Labelled Tier 2 catch rate **0.928** against **0.880** configured, over **359** observations. |
| Does the allocator stay inside its budget? | Yes, once governed: **1.00x–1.03x** of budget across the grid, against up to **3.75x** before. The floor costs **₹46.26** and a budget below that is reported infeasible rather than silently breached. |
| What does it do to safe traffic? | Refuses **13.5%** of adversarially-hard safe prompts on OR-Bench, against 6.7%–91.0% for published models. |

<p align="center">
  <img src="docs/images/baselines.png" alt="Allocation policies and reviewer-queue serving rules compared" width="820">
</p>

Loss and cost figures are arithmetic over synthetic traffic and scenario-configured consequences.
They describe this implementation and its assumptions. Machine-readable sources:
[results](docs/results/results.json) · [queue](docs/results/attention.json) ·
[PII](docs/results/pii.json) · [sensitivity](docs/results/sensitivity.json) ·
[Aegis](docs/results/aegis.json) · [OR-Bench](docs/results/orbench.json).

---

## Architecture

The gateway uses only the request, the response, the supplied context, and any proposed tool calls.
It needs no model weights, hidden states, or log probabilities. Text may stream while verification
runs; actions that change something wait behind a separate gate.

<p align="center">
  <img src="docs/images/architecture.png" alt="ControlPlane architecture: admit, observe, decide, act and prove" width="880">
</p>

| Plane | What it does |
|---|---|
| **Admit** | A per-route token bucket and bounded lanes decide whether there is capacity. If not, the request is refused before the model generates anything. |
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
  <img src="docs/images/traced-request.png" alt="A single request traced through all nine decision stages" width="820">
</p>

Component contracts and the full request sequence: [architecture notes](docs/ARCHITECTURE.md).

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

Run the full quality gate with `make check` (ruff, mypy and 124 tests). Every result above can be
regenerated:

| Command | Writes |
|---|---|
| `make report` | [`docs/results/summary.md`](docs/results/summary.md) — allocation, floor, calibration, audit |
| `make attention` | [`docs/results/attention.md`](docs/results/attention.md) — reviewer-queue comparison |
| `make pii-probe` | [`docs/results/pii.md`](docs/results/pii.md) — disclosure detection and ablations |
| `make sensitivity` | [`docs/results/sensitivity.md`](docs/results/sensitivity.md) — the consequence sweep |
| `make loadtest` | [`docs/results/runtime.md`](docs/results/runtime.md) — admission control under load |

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
| `controlplane/effects/` | Independent effect gating |
| `controlplane/ledger/` | Hash-chained decision and review records |
| `controlplane/eval/` | Reproducible evaluation, ablation, sensitivity and runtime commands |
| `config/` | Versioned policies, economics, runtime limits |
| `data/` | Seeded synthetic calibration and held-out traffic |
| `docs/results/` | Machine-readable results and their written interpretations |
| `console/` | The Streamlit inspection console — see [the console guide](docs/CONSOLE.md) |
| `site/` | The static project page deployed to Vercel |
| `tests/` | Invariants, failure behaviour, reproducibility, regression coverage |

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
