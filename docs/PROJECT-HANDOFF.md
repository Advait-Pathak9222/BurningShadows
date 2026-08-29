# ControlPlane project handoff

This is the first document to give the person making the submission video. It explains the product
story, the system behind it, the prototype, and the safest way to demonstrate it. The detailed
sources remain [`ARCHITECTURE.md`](ARCHITECTURE.md), [`CONSOLE.md`](CONSOLE.md), and
[`PITCH-SCRIPT.md`](PITCH-SCRIPT.md).

## The project in one minute

Enterprises cannot afford to run the most expensive safety check on every AI response. Randomly
sampling a fixed percentage is cheap, but it spends the same amount of attention on a harmless FAQ
and a payment instruction.

ControlPlane makes safety checking an allocation decision:

1. Estimate the probability of five kinds of harm.
2. Multiply each probability by the consequence of that harm on this route.
3. Estimate how much each detector tier can prevent.
4. Buy the tier whose expected benefit exceeds its budget-adjusted cost.
5. Enforce a per-route release floor even when the budget says not to spend.
6. Gate tool effects separately from text and record the complete decision in a hash chain.

The core rule is:

```text
expected loss = calibrated risk × consequence
run a check when expected loss × catch rate > (1 + shadow price) × check cost
```

The shadow price rises when the budget is tight, so discretionary checks become harder to justify.
The release floor is not discretionary and cannot be priced away.

The simplest pitch line is:

> ControlPlane is not another guardrail model. It is the economic and audit layer that decides
> when a guardrail is worth running—and proves why it made that decision.

## What is actually built

This is a working offline prototype, not a slide-only architecture. It includes:

- an OpenAI-shaped FastAPI gateway, including streaming;
- per-route admission control and a pre-generation injection check;
- three replaceable detector tiers;
- five-axis risk calibration;
- a finite-sample release floor for each route;
- an economic allocator and a hard budget governor;
- separate gating for financial and other irreversible effects;
- a capacity-constrained human-review queue;
- a hash-chained SQLite decision ledger;
- feedback and catch-rate recalibration machinery;
- a Streamlit console over the same engine and committed evidence;
- seeded, reproducible evaluation plus five public benchmark corpora.

The default path uses a seeded model provider and lexical detector stubs. That choice makes the
evaluation reproducible without an API key, network, GPU, or changing vendor model. It does not mean
the production design forbids model APIs: Tier 2 is exactly where an LLM judge adapter belongs.

## Architecture from request to proof

### 1. Admit

Files: `controlplane/gateway/`, `controlplane/runtime/`, and
`controlplane/detectors/tier0_rules.py`.

- A route-specific token bucket and bounded concurrency lanes protect the service under load.
- A reserved lane keeps capacity for mandatory work when discretionary work is saturated.
- If both lanes are exhausted, the gateway returns 503 before paying for model generation.
- A prompt-only Tier 0 preflight can reject a clear injection attempt before generation.

Why this design: safety controls that overload the application are not usable. Admission happens
before generation to avoid spending on work that cannot be served, and mandatory capacity is kept
separate so load shedding cannot silently remove the safety floor.

### 2. Observe

Files: `controlplane/detectors/` and `controlplane/risk/`.

- Tier 0 uses very cheap rules for patterns, secrets, injection, and numeric contradictions.
- Tier 1 provides richer grounding, safety, bias, and anomaly signals.
- Tier 2 is the expensive judge and only runs if the allocator selects it.
- Isotonic calibration maps raw detector scores to probabilities on five harm axes:
  hallucination, unsafe content, bias, PII leak, and injection/exfiltration.
- The evidence regime records whether a claim is grounded, estimable without ground truth, or
  unverifiable.

Why this design: the allocator needs probabilities rather than arbitrary detector scores because it
multiplies risk by consequence. A tiered interface also lets an enterprise replace the prototype
detectors without rewriting the economic decision.

### 3. Decide

Files: `controlplane/guarantees/` and `controlplane/economics/`.

- A Learn-Then-Test conformal threshold identifies responses that may not be released unchecked.
- The cost model supplies detector cost, expected catch rate, latency cost, and route-specific harm
  consequences.
- The allocator exposes the benefit, priced cost, and net value of every candidate tier.
- The `BudgetGovernor` reserves expected mandatory-floor cost before allowing discretionary spend.
- A budget controller updates the shadow price as actual spend moves above or below target.

Why this design: an economic optimizer alone can starve safety when money is tight, while a hard
check-everything rule defeats the purpose of allocation. The floor and allocator solve different
problems: the floor states what cannot be skipped; the allocator spends the remaining budget where
it prevents the most expected loss.

### 4. Act and prove

Files: `controlplane/effects/` and `controlplane/ledger/`.

- Text receives one of five verdicts: allow, annotate, abstain, hold, or block.
- Tool calls and other effects are classified and gated independently. Text can be readable while a
  proposed transfer remains on hold.
- The full arithmetic trace, policy version, policy content hash, and previous-record hash are
  appended to SQLite.

Why this design: the consequence of showing text is different from the consequence of moving money
or changing an external system. Separating them avoids an all-or-nothing verdict. Hash chaining
makes later edits detectable and leaves a record whose decision can be re-derived.

### 5. Learn

Files: `controlplane/feedback/` and `controlplane/review/`.

- Review outcomes update a beta-binomial estimate of each tier's catch rate.
- Multi-turn session risk can only tighten a later mandatory threshold; it cannot make a check
  optional.
- The reviewer queue compares FIFO, random, shipped, and ablated serving policies under identical
  capacity.

Why this design: detector quality changes after deployment, so the allocator should update the
quantity it uses rather than hard-code permanent confidence. Human attention is modelled explicitly
because it dominates the assurance bill in the configured scenarios.

## The evidence story

The strongest findings are useful, but each needs its boundary stated on camera.

1. **Human review dominates assurance cost.** Across the six compute budgets, reviewer attention is
   about 81%–98% of total assurance cost. A completed review is configured at ₹120, versus ₹3.20
   for the most expensive automated check. These prices are scenario assumptions, so the ratio—not
   a universal rupee claim—is what transfers.
2. **Authorisation beats recognition for disclosure safety.** A pattern detector and Microsoft
   Presidio both struggle because permitted disclosures can contain real PII and harmful disclosures
   can contain no recognisable PII shape. Grounding the disclosure in the authorised source raises
   the prototype's held-out AUC to 0.9879, with precision 1.0 on the synthetic corpus.
3. **The release floor held on held-out traffic, but can become vacuous.** It is informative only
   when the target alpha exceeds the traffic's harm base rate. On very harmful corpora it forces a
   check on everything and therefore proves nothing about selective release.
4. **Allocation helps, but the margin over a tuned cheap baseline is modest.** It averts more loss
   at all six budgets, by roughly 0.4%–3.6%. Blanket cheap checking remains a strong strategy.
5. **The project reports failures.** Aegis is below its pre-registered benchmark band, and the
   `density` queue ablation beats the shipped `deadline_density` rule. Show these: they make the
   evidence more credible, not less.

The committed evidence is generated offline from a 3,000-row seeded corpus (1,500 calibration and
1,500 held-out rows). Public probes cover ToxicChat, BeaverTails, RAGTruth, Aegis, and OR-Bench. The
external loaders pin immutable revisions and verify SHA-256 digests.

## Streamlit simulator walkthrough

Start from a prepared environment:

```powershell
.\.venv\Scripts\python.exe -m controlplane.cli report
.\.venv\Scripts\python.exe -m streamlit run console\streamlit_app.py
```

Open `http://localhost:8501`. First load calibrates the engine; later view changes use cached data.

### Demo 1: the thesis in one click—Decision lab

1. Open **Decision lab**.
2. Leave the pre-filled prompt, response, and grounding context unchanged.
3. Point out the mismatch: the source says a ₹499 renewal fee and 14-day refunds; the response says
   ₹9,999 and 90 days.
4. Run it first as `support-assistant`.
5. Explain the verdict, expected loss, selected tier, and **Forced by the floor**.
6. In **What each tier was worth**, explain benefit, priced cost, and net value. This is the
   transparent allocator arithmetic.
7. Change only the route to `finops-agent` and run again.
8. Explain that the words did not change; only the consequence table changed. That is why a finance
   route can justify more checking or a stronger verdict.

What to say:

> Traditional guardrails ask whether the text looks dangerous. ControlPlane also asks what it would
> cost to be wrong here. The same answer can be a support inconvenience or a financial incident.

### Demo 2: prove the live decision—Audit ledger

1. Immediately open **Audit ledger**.
2. Point to the green chain-verification banner.
3. Select the newest row and open its JSON.
4. Connect it to the decision just run: risk vector, costs, tier, verdict, policy hash, and previous
   hash are all recorded.

Be precise: the prototype makes edits detectable; it does not prevent deletion or replacement of
the entire database. A production deployment needs an external append-only sink.

### Demo 3: show the economic finding—Overview

1. Open **Overview** at the default 40% budget.
2. Point first to **Attention share of cost**—about 91% at this setting.
3. Move the budget from 10% through 100%; the share moves from roughly 98% to 81%.
4. Show **Loss averted against compute spend** and compare `allocator` with `fixed_rate`.
5. Show **Per-route release floor**: the certified bound is under alpha on every route.
6. Show the stacked cost chart: human cost remains the larger block.

Do not describe the rupee amounts as customer-measured savings. They are arithmetic over configured
consequences. The transferable result is the allocation mechanism and its sensitivity analysis.

### Demo 4: show scientific honesty—Reviewer queue

1. Open **Reviewer queue**.
2. Explain that every policy gets the same cases, capacity, and 166 completed reviews.
3. Compare the shipped rule with FIFO to show why serving order matters.
4. Then point directly to `density`, which beats the shipped rule on expected loss served and SLA
   breaches.

What to say:

> This ablation beats the rule we shipped, and we kept it in the default view. The next design
> change should remove or replace the deadline term while preserving route fairness.

### Demo 5: one optional scenario

If time permits, use one scenario—not all nine:

- **Budget shock** shows the shadow price rising after a 40% cut while floor coverage stays fixed.
- **Same response, three routes** shows route-specific consequences without editing text live.
- **Agentic hold** shows why effects are gated separately from text.
- **Drift** is the best choice when asked what can break the guarantee.

Every scenario has a raw-record expander. Use it only if a judge asks for the exact fields.

## Recommended five-minute video structure

| Time | Screen | Message |
|---:|---|---|
| 0:00–0:30 | Landing page | Checking everything is too expensive; random sampling wastes scarce attention. |
| 0:30–0:55 | Architecture/formula | Price expected loss, buy valuable checks, and keep a non-negotiable floor. |
| 0:55–2:05 | Decision lab | Run the worked example, then change only the route. Expose the tier arithmetic. |
| 2:05–2:25 | Audit ledger | The live decision is appended to a verified hash chain. |
| 2:25–3:15 | Overview | Human review, not compute, dominates configured assurance cost. |
| 3:15–3:45 | Reviewer queue | Serving order matters; openly show the ablation that beats the shipped rule. |
| 3:45–4:20 | Evidence/README | Reproducibility, public benchmarks, pre-registration, and honest failures. |
| 4:20–5:00 | Landing page | ControlPlane decides when to call guardrails and proves the decision. Ask for real enterprise traffic next. |

Use two Streamlit browser tabs—one left on Decision lab and one on Overview—to avoid waiting for
view reruns during the recording. Run one Decision lab check before recording so the engine is warm
and the ledger is populated.

## Questions the presenter should be ready for

### Why not run an LLM judge on every answer?

That is the `check_all` baseline. It adds the highest cost and latency to every response, including
low-consequence ones. ControlPlane decides when that judge has enough expected value to justify the
call, while the floor still forces mandatory checks.

### Is this only synthetic?

The economic loss figures and the core seeded evaluation are synthetic and should be presented that
way. The mechanism is also probed on five public corpora. Those probes include successes, partial
results, and an explicit failed endpoint; none substitutes for customer traffic.

### Is the offline Tier 2 production-ready?

No. It is a deterministic stand-in used to isolate and reproduce the allocator experiment. The
detector adapter contract, a local Ollama adapter, and a Presidio adapter demonstrate replaceability.
A production judge must be integrated and its catch rate recalibrated.

### What breaks the guarantee?

Distribution drift, route mixing, changed label definitions, selective labels, or reusing data for
both score fitting and threshold selection. The current prototype does not include a production
drift trigger, and that is a high-severity gap.

### What would be needed for a pilot?

Roughly 500 labelled rows per route, Finance sign-off on consequences and operating costs, a chosen
production detector stack, drift-triggered recalibration, shared multi-worker state, identity and
tenant controls, a durable review queue, and an external audit sink.

## Safe recording checklist

- Run the report before opening Streamlit.
- Run one Decision lab decision to warm the engine and seed the ledger.
- Keep a second browser tab on Overview.
- Use 125%–150% browser zoom and hide notifications.
- Keep `docs/images/architecture.png` open as a fallback.
- Never debug live; fall back to the committed landing page and evidence tables.
- Never claim the rupee values are customer-measured.
- Say plainly when a benchmark or ablation did not favour the project.

## Working directly on `main`

The handoff branch is `main`, as requested. Before accepting a suggested change:

```powershell
git switch main
git pull --ff-only origin main
git status --short
```

Make one focused change, then run:

```powershell
.\.venv\Scripts\python.exe -m ruff check controlplane tests console
.\.venv\Scripts\python.exe -m mypy controlplane
.\.venv\Scripts\python.exe -m pytest -q
```

For UI changes, also open the console and exercise Decision lab plus Audit ledger. Commit only after
the evidence and narration still agree. Do not update a result number by hand when it has a generated
source; regenerate it through the corresponding `make` or CLI target.
