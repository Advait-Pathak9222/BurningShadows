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

**Hosted:** [live console](https://controlplane-ai.streamlit.app) ·
[project page](https://controlplane.vercel.app) — see [Deployment](docs/DEPLOYMENT.md).

---

## Three findings

### 1. Human attention is where assurance money goes

A completed review costs **₹120**. The most expensive automated check costs **₹3.20**. Once both
are counted, human review accounts for **85% to 97%** of operating assurance cost.

| Budget | Automated checking | Human review | Attention share | Cases raised |
|---:|---:|---:|---:|---:|
| 10% | ₹660.90 | ₹19,920 | **96.8%** | 295 |
| 25% | ₹1,066.36 | ₹19,920 | 94.9% | 308 |
| 40% | ₹1,882.26 | ₹19,920 | 91.4% | 340 |
| 60% | ₹2,972.30 | ₹19,920 | 87.0% | 410 |
| 80% | ₹3,470.60 | ₹19,920 | 85.2% | 453 |
| 100% | ₹3,470.60 | ₹19,920 | 85.2% | 453 |

Raising the compute budget raises the number of cases needing a person, because more checking finds
more to escalate. Reviewer capacity is fixed, so the queue saturates and what differs between
policies is which cases get served. That makes serving order worth measuring.

At a fixed reviewer capacity, on identical cases, the shipped queue rule serves **1.57x** the
expected loss that first-in-first-out does from the same **166** completed reviews:

| Serving rule | SLA breaches | Expected loss served | High-value cases shed |
|---|---:|---:|---:|
| **deadline_density** (shipped) | **49** | **₹3,584,692** | **1** |
| fifo (baseline) | 148 | ₹2,279,871 | 22 |
| random (baseline) | 33 | ₹2,309,114 | 21 |
| density (ablation) | 28 | ₹4,258,434 | 1 |
| deadline (ablation) | 160 | ₹2,258,118 | 18 |

The `density` ablation — the shipped rule with its deadline term removed — leads on both axes, and
is reported as the stronger rule. Keeping up with arrivals needs **5.4 reviewers** against the two
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

### 3. Endpoints were fixed before the work started

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
| Does allocation beat a tuned fixed-rate policy? | More loss averted at **6 of 6** budgets, by 0.4–3.6%; better compute ROI at **4 of 6**. At the tightest budget, **₹5,315,700** averted for **₹660.90** against **₹5,224,700** for **₹270**. |
| Does allocation beat checking everything? | At the 80% and 100% budgets, yes — **₹5,479,500** averted for **₹3,470.60**, against **₹5,476,400** for **₹4,800**. More loss averted for 28% less compute. |
| Does the per-route release floor hold? | Observed unchecked harm **0.0618 / 0.0716 / 0.0642** against α **0.15**, over **372 / 475 / 436** released rows. Mandatory coverage **25.6% / 5.0% / 12.8%**. |
| Are the risk scores calibrated? | Expected calibration error **0.030 – 0.046** by route. |
| Do consequence assumptions move decisions? | Across a **0.25x–4x** band, **15.8%** of tier decisions change and the verdict flip rate is **0%** — consequence prices a check but does not enter the release rule. |
| Is the audit trail complete? | **1,500 of 1,500** decisions and **299** reviews in one valid chain; **224 of 224** proposed effects logged. |
| Is the detector catch rate measured or assumed? | Measured. Labelled Tier 2 catch rate **0.950** against **0.880** configured, over **398** observations. |

<p align="center">
  <img src="docs/images/baselines.png" alt="Allocation policies and reviewer-queue serving rules compared" width="820">
</p>

Loss and cost figures are arithmetic over synthetic traffic and scenario-configured consequences.
They describe this implementation and its assumptions. Machine-readable sources:
[results](docs/results/results.json) · [queue](docs/results/attention.json) ·
[PII](docs/results/pii.json) · [sensitivity](docs/results/sensitivity.json).

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
git clone https://github.com/Jenish3119/BurningShadows.git
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
