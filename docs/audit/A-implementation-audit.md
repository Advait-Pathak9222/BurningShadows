# Phase A: implementation audit

Auditor: claude-code. Date: 2026-08-23. Commit audited: `e88f1c9`.
Environment: Windows 11, Python 3.13.4, fresh clone, fresh venv, no GPU, no API key.
No application code was changed to produce this document.

---

## Headline

Three things a judge can find, in order of how badly they hurt:

1. **The eval does not run the product.** `reports/evaluation.*`, the loss-averted curve, and every
   number in the README come from `eval/baselines.py::economic_allocator` — a greedy knapsack that
   never calls `allocate_verification`, never uses the shadow price `lambda`, and never touches the
   budget controller. The file the README tells judges to open first
   (`economics/allocator.py`) is not the file that produced the results.

2. **The corpus is circular, and the circularity is structural rather than lexical.** The 600-row
   corpus contains **10 distinct responses**. Absence of `context_documents` implies harm with
   probability 1.000 across the whole corpus. The one-line rule "flag any row with no context
   documents" scores **precision 1.000, recall 0.743** on the held-out test split with no detector
   at all. Calibrated detector AUC is 1.0000 on two of three routes. There is no ranking problem
   left for an allocator to solve, which is why the allocator cannot beat the baseline.

3. **The conformal bound is violated on held-out data, on the highest-stakes route.** On
   `finops-agent`, observed escaped-harm rate among released test rows is **0.2979 against a target
   alpha of 0.20** (47 released, 14 escapes). `docs/00-assessment.md` lists "conformal upper bounds
   exceed the declared route alpha on held-out data" as an explicit kill criterion. That criterion
   fires. Nobody saw it because the evaluator's `escaped_harm_rate` is structurally incapable of
   reporting it — it prints `0.000000` for every policy at every budget.

The repo is honest about (1) partially and (2) vaguely; it is silent on (3). Set against that: the
code is clean, the house style was followed almost perfectly, `docs/LIMITATIONS.md` is the best
artifact in the repository, and the hash-chained ledger, the Learn-Then-Test routine, the isotonic
calibrator and the streaming gateway are all genuinely implemented. This is a good codebase wrapped
around an evaluation that does not test it.

---

## A1. Does it actually run?

Yes. From a fresh clone it works, and it is fast. This is the strongest part of the submission.

| Step | Command that worked | Time | Result |
|---|---|---:|---|
| Install | `python -m venv .venv` + `.venv/Scripts/python.exe -m pip install -e ".[dev]"` | 2m 02s | clean |
| Data | `python -m controlplane.cli data` | 16.6s | 600 rows, **byte-identical to committed files** |
| Demo | `python -m controlplane.cli demo` | 6.9s | all 8 scenarios, `Audit chain valid: True (98 records checked)` |
| Report | `python -m controlplane.cli report` | 5.2s | regenerates csv/json/md + both figures |
| Tests | `python -m pytest` | 12.6s | 9 passed |
| Lint | `python -m ruff check controlplane tests console` | 2s | All checks passed |
| Typecheck | `python -m mypy controlplane` | 2.9s | **FAILS** |

No errors and no undocumented manual steps in the demo path. `make data` reproduces the committed
corpus bit-for-bit, which is a real reproducibility win and should be said out loud in the pitch.

**`make report` genuinely regenerates.** Results are committed as static files *and* rebuilt from
data. Both figures and `reports/scenarios.json` are rewritten on every run.

### Problems a judge will hit

- **`make check` is broken on a fresh clone.** `mypy` is pinned to `python_version = "3.11"` in
  `pyproject.toml`, but nothing pins numpy. Today's numpy (2.5.2) ships stubs using `type`
  statements that require 3.12, so mypy dies before it checks anything:
  `numpy/__init__.pyi:737: error: Type statement is only supported in Python 3.12 and greater`.
  The brief required `mypy --strict` clean on `controlplane/`. It is not, out of the box.
  Fix is one line — pin numpy, or raise `python_version`.
- **No `make` on Windows.** Not the repo's fault, and the README does supply a PowerShell fallback,
  which worked. Worth keeping.
- **`reports/scenarios.json` does not reproduce across platforms.** Eight `policy_hash` values change
  on a Windows checkout. Cause: `policy/loader.py:50` hashes raw file bytes, and git's
  `core.autocrlf` rewrites the YAML to CRLF. Verified directly: the same `eu.yaml` hashes to
  `09523a45b34e529d` with LF and `5cb483d7384da6ec` with CRLF. So the policy version stamped into
  every audit record is a hash of *the bytes on this machine*, not of the policy. For a component
  whose selling point is forensic reproducibility this is an own-goal, and it is a two-line fix
  (normalise line endings before hashing, or add `*.yaml text eol=lf` to `.gitattributes`).
- **Non-ASCII console output crashes on Windows cp1252.** Corpus text contains the rupee sign. Any
  script that prints a response verbatim dies with `UnicodeEncodeError`. The shipped CLI escapes it
  via `json.dumps` so `make demo` is safe, but the console and any live debugging is not.

---

## A2. Is the substance there?

| Component | Verdict | Evidence |
|---|---|---|
| Allocator decision rule | **real** | `economics/allocator.py`, 131 lines, plain arithmetic, readable in five minutes as required |
| `lambda` shadow price | **real (unused)** | implemented at `allocator.py:84`; never exercised by the eval |
| Budget controller | **thin** | 22 lines, correct form, but misused wherever it is called |
| Conformal / Learn-Then-Test | **real, but invalid as fitted** | correct algorithm; in-sample calibration breaks the guarantee |
| Harm vector | **real** | five axes preserved end to end, never collapsed to one label |
| Evidence regimes / `abstain` | **thin** | real code path, but the regime is read off a corpus field |
| Effect gate | **real** | `effects/effect_gate.py`, genuinely blocks the transfer |
| Blast-radius classification | **real** | `effects/classification.py`, five classes, ordered |
| Multi-turn risk accumulator | **absent** | `ConversationRiskAccumulator` has **zero callers** |
| Tier 0/1/2 cascade | **thin** | Tier 2 is genuinely skippable; Tier 0 and Tier 1 always run |
| Policy packs | **real** | versioned, mtime-based hot reload, stamped into records |
| Hash-chained ledger | **real** | tampering genuinely breaks `verify()`, and a test proves it |
| Feedback loop / recalibration of `r`,`c`,`k` | **stubbed** | see below |

### The parts that are genuinely good

**The ledger.** `ledger/store.py:37` recomputes `record_hash(previous, record)` for every row and
checks the `previous_hash` linkage. `tests/test_ledger.py` edits a row in SQLite behind the store's
back and asserts `verify() == (False, 1)`. That is a real test of a real property. Do not touch it.

**Learn-Then-Test.** `guarantees/conformal.py` is a correct implementation: a 21-point threshold
grid, an exact one-sided binomial (Clopper-Pearson) upper bound found by bisection, Bonferroni
correction at `delta / grid_size`, and selection of the *largest* passing threshold (least checking).
When nothing passes it falls back to `threshold=0.0`, which checks everything. The algorithm is
right. What is fed to it is not — see A3.

**The isotonic calibrator.** `risk/calibration.py` is a correct pool-adjacent-violators
implementation written from scratch in 34 lines. Real work.

**The streaming gateway.** `gateway/app.py:100` starts the assessment as an `asyncio` task and
streams provider tokens concurrently, emitting the verdict as a trailing
`event: controlplane.decision`. The header is honestly set to `pending` during the stream. The
central "text streams, effects wait" claim has a working implementation behind it.

**The allocator itself.** It reads well, the business terms are named, and the comment at
`allocator.py:83` — "At lambda=0 this is exactly the Round 1 rule: r*c*k > v+d" — is exactly the
continuity signal the brief asked for.

### The parts that are not what they look like

**`lambda` is real code with no real caller.** The only places a shadow price is set are hardcoded
demo constants: `scenarios.py:80` uses `shadow_price=10000.0`, `scenarios.py:277,286` use `1500.0`.
These are numbers chosen to force a demo outcome. The budget controller never produces them. A judge
asking "where did lambda=10000 come from?" has no answer in the repo.

**The budget controller is fed the wrong units.** `scenarios.py:116` calls
`controller.update(running_spend / index)` — INR *per interaction* — against
`budget_rate_inr=3.0`, documented as an *hourly* rate. It also runs with `learning_rate=5.0`, which
is 250x the dataclass default of 0.02. The budget-shock demo works only because mean spend per
interaction (~1.85) happens to land just above the halved budget rate (1.8).

**The cascade is one-third real.** `service.py:92` runs Tier 0 and Tier 1 unconditionally on every
interaction. Only Tier 2 is economically gated (`service.py:110`), and when selected it correctly
re-runs detection and re-decides — that part is a genuine cascade. But the spend accounting charges
`v` for whichever tier was "selected" and charges **zero** when `selected_tier is None`, even though
Tier 0 and Tier 1 both ran. The x-axis of the loss-averted-vs-spend curve is therefore not the cost
of the compute performed.

**The delay cost `d` is always exactly zero.** `cost_model.py:27` computes
`delay_ms = max(0, tier_latency - policy.effect_latency_slo_ms)`. Tier 2 latency is 900ms; the
lowest `effect_latency_slo_ms` in any policy is 1500ms. So `d = 0` for every tier on every route,
and the entire `delay_cost_per_ms_inr` table in `config/economics.yaml` is dead configuration. The
`(v_t + d_t)` in the pitch is really just `v_t`.

**The feedback loop is three dataclasses, two of which nothing calls.**

- `ConversationRiskAccumulator` (`feedback/conversation.py`): **zero callers.** The multi-turn
  accumulator the brief made a headline requirement does not exist in any runtime path.
- `ReviewOverride` (`feedback/overrides.py`): **zero callers.** A bare 5-field dataclass with no
  behaviour.
- `BetaBinomialCatchRate`: one caller, `scenarios.py:243`, seeded
  `BetaBinomialCatchRate(caught=14, missed=2)` — fabricated priors, not observed outcomes.

`c` is never recalibrated by anything. `r` is recalibrated only by the one-shot isotonic fit.

**Decision thresholds live in code, not config.** `allocator.py:121,123,127` hardcode 0.35, 0.88 and
0.45; `risk/harm_vector.py:18,21` hardcode blend weights 0.72/0.28 and a floor of 0.38. The brief
said configuration lives in YAML under `config/`. These are the numbers that decide
allow/annotate/hold/abstain/block and they are scattered through modules.

**`abstain` is a real path decided by a corpus field.** `risk/evidence_regime.py` returns
`UNVERIFIABLE` iff `context_documents` and `comparison_samples` are both empty. It is a real branch
that really fires — the demo shows two abstentions — but nothing *analyses* verifiability; it reads
whether the fixture had documents attached. In the gateway the caller supplies these fields, so in
production "unverifiable" means "the integrator sent no documents".

---

## A3. Are the numbers real?

### They reproduce

Every quantitative claim in the README reproduces exactly. At the 40% budget point I measured
allocator spend 384.0, fixed-rate spend 384.0, allocator loss averted 2,813,500, fixed-rate
2,775,500, precision 0.9833 vs 0.9917 — matching the README to the digit. Nothing is hand-typed.
Credit where due: this is rarer than it should be.

The problem is not that the numbers are fabricated. It is that they measure the wrong thing.

### The eval does not use the allocator

`eval/report.py:75` calls `economic_allocator(candidates, target)` from `eval/baselines.py` — 9 lines
of greedy fill by `expected_loss / verification_cost`, after force-including everything above the
conformal threshold. It does not import `allocate_verification`. There is no `lambda`, no budget
controller, no tier selection, no verdict logic, no effect gate.

Worse, `report.py:96` and `report.py:118` take `cost_model.tiers(...)[2]` — **Tier 2 for every
candidate**. The evaluation is a binary "run the LLM judge or not" decision. The three-tier cascade,
which is a headline feature, is never evaluated.

So the shipped result compares a knapsack against a sorted list. Whatever it proves, it does not
prove anything about the system in `controlplane/`.

### The corpus is circular

This is the fatal one. Measured directly from `data/interactions.jsonl`:

```
total rows: 600
distinct responses: 10
distinct (response, label) pairs: 10
responses carrying more than one label: 0
```

Ten templates, repeated ~60x each, each with a deterministic label. The calibration/test split is by
interaction id, so **every test response is byte-identical to a calibration response**. This is not
subtle leakage; the test set is a copy of the calibration set with different ids.

On top of that, the generator plants the detector's own keywords. `sim/traffic.py` writes fixtures
containing strings that appear verbatim in `detectors/tier0_rules.py`:

| Detector constant | Phrase | Fixture that contains it |
|---|---|---|
| `BIAS_PHRASES` | `women are less` | "Women are less suited to this operations role..." (label: bias=1) |
| `UNSAFE_PHRASES` | `steal credentials` | "...harm the customer and steal credentials." (label: unsafe=1) |
| `INJECTION_PHRASES` | `ignore previous instructions` | injection fixture prompt (label: injection=1) |
| `INJECTION_PHRASES` | `reveal the system prompt` | injection fixture prompt |
| `INJECTION_PHRASES` | `bypass policy` | injection fixture response |
| `INJECTION_PHRASES` | `exfiltrate` | injection fixture response |

But the lexical collision is the *lesser* problem. I paraphrased the harmful templates
(label-preserving rewrites: "Women are less suited to..." became "Female applicants tend to
underperform in...") and AUC barely moved (0.9956 to 0.9940). That ruled out keyword matching as the
main driver and pointed at something worse:

```
context_documents present : n=428  harmful= 60  harm rate=0.1402
context_documents absent  : n=172  harmful=172  harm rate=1.0000
```

**Absence of `context_documents` implies harm with probability 1.000.** The trivial classifier "flag
every row with no context documents", on the held-out test split:

```
TP=104  FP=0  FN=36  TN=160     precision=1.0000  recall=0.7429
```

Perfect precision from a rule with no detector in it. And `risk/harm_vector.py:21` floors the
hallucination axis at 0.38 whenever the regime is `UNVERIFIABLE`, while `tier1_models.py:66` returns
~0.52 for any response with no documents and no samples — so the pipeline is wired to key on exactly
this artifact.

Resulting separability on the held-out test split:

| Route | raw AUC | calibrated AUC | distinct scores in 100 rows |
|---|---:|---:|---:|
| support-assistant | 0.8900 | 0.9956 | 5 |
| internal-kb | 0.6563 | **1.0000** | 6 |
| finops-agent | 0.9310 | **1.0000** | 7 |

The isotonic step lifts AUC from 0.66 to 1.00 on internal-kb, because it is fitting a lookup table
over ten memorised score values. This is the whole reason the allocator cannot beat the baseline:
when ranking is already perfect, there is nothing for a smarter ranking rule to win.

### The conformal bound does not hold on held-out data

`service.py:129-133` fits the isotonic calibrators on the calibration set, then computes the LTT
scores **with those same calibrators on those same rows**. Learn-Then-Test requires the score
function to be fixed before the calibration labels are seen. It is not. The thresholds are therefore
selected on in-sample scores and are over-optimistic.

Measured. Calibration-split figures are what the repo reports; test-split figures are what I
computed by releasing every test row scoring below its route threshold and counting true harms:

| Route | threshold | calibration empirical risk | reported upper bound | **test-split escaped-harm rate** | alpha | |
|---|---:|---:|---:|---:|---:|---|
| support-assistant | 0.55 | 0.0000 | 0.0725 | 0.0000 (0/59) | 0.20 | holds |
| internal-kb | 0.65 | 0.0723 | 0.1787 | 0.1519 (12/79) | 0.20 | holds |
| finops-agent | 0.80 | 0.0323 | 0.1419 | **0.2979 (14/47)** | 0.20 | **violated** |

Escaped harm on `finops-agent` jumps **9x from calibration to test**, blows through the declared
alpha, and does it on the route that gates money. This is the single most dangerous fact in the
repository: a judge who checks the guarantee finds it broken on the route the demo is built around.

### Why the repo reports 0.000000 escaped harm everywhere

`eval/metrics.py:88`:

```python
released = [row for row in rows if not row.selected and not row.abstained]
escaped  = sum(row.true_harm for row in released)
```

A row that *was* checked and *was not* caught is excluded from `released`, so it can never count as
an escape. Demonstrated with a single synthetic row — checked, truly harmful, `caught=False`,
`loss_averted=0.0` — the reported `escaped_harm_rate` is `0.0`. The metric assumes checking equals
catching, while `_caught_loss` in the same file models `k < 1`. The two halves contradict each other.

Combined with the circular corpus (where the mandatory conformal set already covers nearly every
harmful row), this produces `escaped_harm_rate = 0.000000` for every policy at every budget — a
column of zeros that looks like a triumph and is an artifact.

### Two more metrics that cannot fail

- **`audit_coverage` is definitionally 1.0.** `metrics.py:53-55` sets
  `effect_count=len(interaction.tool_calls)` and `logged_effect_count=len(interaction.tool_calls)`,
  then `_audit_coverage` divides one by the other. It is `x/x`. Worse,
  `docs/03-assumptions.md` claims this is "Verified from ledger append counts in the evaluation" —
  it is not; the evaluator never reads the ledger. That is a documented claim contradicted by code.
- **p99 latency is a hardcoded constant.** `report.py:130` passes
  `latency_ms=900.0 if selected else 4.0`, and `metrics.py:40` then computes
  `text_latency = min(latency_ms, 12.0)`. The reported "p99 added latency on text = 12.0ms" is
  literally `min(900, 12)`. Nothing is timed. The brief's rule was "Never invent a benchmark number";
  this is a headline Round 1 metric and it is invented. (The detectors *do* record real
  `perf_counter` latencies — they are simply discarded by the evaluator.)

### Calibration quality contradicts the economics

From `reports/evaluation.json`, ECE on the held-out split: support-assistant 0.143, internal-kb
0.181, finops-agent 0.133. So `r` is mis-stated by 13-18 percentage points while AUC is ~1.0 — good
ranking, bad probabilities. That is fine for the Round 1 concession ("good enough to rank, not to
judge") and fatal for `expected_loss = r * c`, which multiplies that 13-18 point error straight into
a rupee figure. A technical judge who opens the reliability diagram will find this.

### Are the baselines steelmanned?

Mostly, and this is to Codex's credit. `fixed_rate` is given **exactly the allocator's realised
spend** (`report.py:83`), so the comparison is genuinely equal-spend, and it ranks by calibrated risk
score, which given AUC of about 1.0 is close to optimal. It is a strong baseline, not a strawman.
`check_all` is charged the honest full cost with no inflation.

The weakness is the opposite of the usual one: because `verification_cost_inr` is identical for
every candidate (always Tier 2), value-density ranking collapses to ranking by `r * c`, and
fixed-rate ranks by `r`. The entire measured difference between the two policies is the `c`
weighting — which is a fair test of the thesis, and the thesis loses:

| Budget | allocator loss averted | fixed_rate | outcome |
|---:|---:|---:|---|
| 10% | 2,633,500 | 2,633,500 | tie |
| 25% | 2,633,500 | 2,633,500 | tie |
| 40% | 2,813,500 | 2,775,500 | **win** (+1.4%) |
| 60% | 3,652,500 | 3,779,200 | **loss** (-3.4%) |
| 80% | 3,779,200 | 3,779,200 | tie |
| 100% | 3,779,200 | 3,779,200 | tie |

It ties at four of six points because the conformal floor consumes the whole budget at the low end
and everything gets checked at the high end. The allocator only has room to act in a narrow middle
band, and there it wins once and loses once. The README states this plainly, which is the right call.

### Budget variance: the budget is not held

`budget_variance` is **2.833 at the 10% budget** and **0.533 at 25%** — the system spends 3.8x its
budget at the tightest setting. This follows from design: `baselines.py:35` force-includes every
mandatory item before considering the budget. `docs/LIMITATIONS.md` and ADR-002 both call this out
honestly as reported infeasibility rather than a silently weakened floor, which is defensible. But
"the business sets an assurance budget" is the first line of the pitch, and at the budgets where
allocation is supposed to matter most, the budget is not met. The README does not mention this.

---

## A4. Will it survive the pitch?

Ten questions, worst-answered first. **Demonstrable** = there is a command or artifact that answers
it. **Arguable** = there is a written answer but no evidence. **Nothing** = no answer.

| # | Question | State | Why |
|---|---|---|---|
| 1 | "Your evaluation doesn't call your allocator. What did you actually measure?" | **Nothing** | `eval/baselines.py` reimplements the decision. No defence exists. |
| 2 | "Show me escaped harm on the route that moves money." | **Nothing** | 0.298 vs alpha 0.20. Fires the repo's own kill criterion. Report says 0.000. |
| 3 | "Your corpus has ten distinct responses. What generalises?" | **Nothing** | LIMITATIONS says "a small set of templates"; it does not say ten, or that no-context implies harm at p=1.0. |
| 4 | "Where do your `c` values come from?" | **Arguable** | `docs/03-assumptions.md` is honest and well-organised, but every `c` is tagged Assumption with no source. No sensitivity analysis is implemented. |
| 5 | "Your detector is unreliable — why is an economic rule on top any better?" | **Arguable** | Good written answer in `00-assessment.md`. Undercut by ECE 0.13-0.18: `r*c` is arithmetic on a 15-point error. |
| 6 | "Regulators want consistent controls, not controls that switch off when the budget runs out." | **Demonstrable** | Best-answered question in the deck. `conformal_floor_coverage_after: 1.0` under a 40% cut, and `_floor_coverage` genuinely recomputes it. |
| 7 | "Parallel checking doesn't help if the wrong answer already streamed." | **Demonstrable** | Conceded in writing, and the effect gate genuinely holds the transfer (`transfer_fired: false`). Honest concession beats a dodge. |
| 8 | "You're a router in front of existing guardrails. What's the moat?" | **Arguable** | `01-landscape.md` positions correctly, but no third-party detector is actually wrapped. Presidio and transformers are declared in `[models]` extras and **never imported anywhere**. The composition claim is unbacked. |
| 9 | "Is your budget actually held?" | **Nothing** | budget_variance 2.83 at 10%. Honest in LIMITATIONS, absent from README and pitch. |
| 10 | "What's your p99 latency overhead?" | **Nothing** | `min(900, 12) = 12`. Not measured. Real `perf_counter` timings exist and are discarded. |

Question 6 is the one to build the pitch on. It is the only place where the demo, the code and the
claim line up, and it is the answer to the objection Codex correctly identified as the sharpest.

### The budget-shock demo, specifically

The brief called this "the money demo. Build it properly." It is under-built:

- Both windows replay **the same 45 interactions** (`scenarios.py:77`), with controller state
  carrying over. It is not a mid-run shock; it is the same traffic twice.
- `lambda_at_cut: 0.0` — lambda never rises during the first window, because mean spend (1.85) sits
  below the budget rate (3.0) and the controller clamps at zero.
- The measured degradation is invisible: loss averted moves 318,789.68 to 318,531.90, a **0.08% drop**
  for a 40% budget cut. Graceful to the point of being indistinguishable from nothing happening.
- Spend falls 83.2 to 71.12, a **14.5% reduction against a 40% cut**. The new budget is not met.
- `learning_rate=5.0` against a default of 0.02 is tuning to make lambda visibly move.

What does work, and is worth protecting: `conformal_floor_coverage_after` is honestly computed by
re-deriving which rows were forced and checking all of them got a tier. It returns 1.0. The floor
holds. That is the demo.

---

## A5. Code quality and provenance

Codex followed the house style closely. Mechanical scans across all `.md`, `.py` and `.yaml`:

| Check | Result |
|---|---|
| Emojis | **0** |
| Banned words (comprehensive, robust, seamless, leverage, delve, cutting-edge, state-of-the-art, powerful, elegant, journey, unlock, empower) | **0** |
| "This is not just X, it's Y" | **0** |
| Banner comments / ASCII dividers | **0** |
| `try/except Exception: pass` | **0** |
| `utils.py`, `*Manager`, `process()`, `handle()`, `helper` | **0** |
| `TODO` / `FIXME` / `XXX` | **0** |
| Functions over 40 lines | **0** |
| Files over 400 lines | **0** (largest: `sim/scenarios.py`, 314) |
| `ruff check` | clean |

That is a better result than most human repos. Real violations:

1. **One giant commit.** `e88f1c9 feat: build responsible AI assurance control plane` is the entire
   repository. **No tags.** The brief said small commits in build order, commit at every milestone,
   tag them. This is the most visible violation and it is unfixable now — do not rewrite history to
   fake it. Going forward, commit properly.
2. **Configuration in code.** Decision thresholds 0.35/0.88/0.45 (`allocator.py:121,123,127`) and
   blend weights 0.72/0.28 plus floor 0.38 (`risk/harm_vector.py:18,21`).
3. **Magic demo constants.** `shadow_price=10000.0` (`scenarios.py:80`), `shadow_price=1500.0`
   (`scenarios.py:277,286`), `BetaBinomialCatchRate(caught=14, missed=2)` (`scenarios.py:243`),
   `learning_rate=5.0` (`scenarios.py:166`).
4. **Dead code.** `feedback/conversation.py` and `feedback/overrides.py` have zero callers.
5. **Unused declared dependencies.** `presidio-analyzer` and `transformers` are in the `[models]`
   extra and imported nowhere. The extra promises a capability that does not exist.
6. **Weak tests.** Nine tests total. `test_gateway.py:21` asserts the decision header is one of five
   valid verdicts — any outcome passes. `test_console.py` is mostly `assert not console.exception`,
   which the brief explicitly bans. `test_conformal.py` tests the bound only on perfectly separated
   scores, so it cannot catch the violation found in A3.
7. **A test that pins a cherry-picked result.** `test_scenarios.py:45` asserts
   `allocator_loss_averted_inr > fixed_rate_loss_averted_inr` at the 40% point — the single budget
   where the allocator wins. It locks in the flattering operating point, and it will fail the moment
   the eval is corrected. It also asserts `verdict` but never `reason`, which the brief required.
8. **Eight scenarios, one test function.** A failure in the first assertion hides the other seven.

### Documentation

`docs/LIMITATIONS.md` is **present and genuinely honest** — the best artifact in the repo. It admits
the templated corpus, states that catch outcomes are pseudo-random draws from assumed `k`, concedes
that streaming cannot retract text, and says outright that the dominance claim fails. Judges will
reward it. It does not currently mention: the ten-template count, the no-context leak, the conformal
violation, the fabricated latency numbers, `audit_coverage` being `x/x`, or the eval/product split.

The **five ADRs are real ADRs**. ADR-002 names a rejected alternative and explains why it was
rejected — a Hoeffding bound was "needlessly loose on 100-row route samples", so it moved to an exact
binomial. That is a decision record from someone who tried both, not a retro-justification.

`docs/00-assessment.md` answers all five required objections seriously and defines explicit kill
criteria. Two of those criteria now fire.

---

## A6. Verdict

### Keep — do not rewrite

- `guarantees/conformal.py` — correct LTT. The inputs are wrong, not the algorithm.
- `ledger/` — hash chain and its tamper test. The one component that is production-shaped.
- `economics/allocator.py` — readable, correctly named, right level of cleverness (none).
- `risk/calibration.py` — correct PAVA isotonic regression, written from scratch.
- `gateway/app.py` — genuinely concurrent streaming with a trailing decision event.
- `effects/` — effect gate and blast-radius classification both work.
- `docs/LIMITATIONS.md`, `docs/00-assessment.md`, the five ADRs — the honesty is the differentiator.
- Deterministic corpus regeneration — `make data` reproduces committed files byte-for-byte.

### Fix — ranked by severity

1. **Rebuild the corpus.** Nothing downstream means anything until harm stops being predictable from
   `context_documents` being empty. Needs: many more surface forms per harm type, harmful rows *with*
   supporting documents, clean rows *without* them, and detector keyword lists that were not written
   by the same hand as the fixtures. This is the root cause of findings 2, 3 and the flat curve.
2. **Make the eval call the product.** Replace `baselines.py::economic_allocator` with
   `allocate_verification` driven by `BudgetController`. Until then no reported number describes the
   system.
3. **Fix `escaped_harm_rate`** so a checked-but-missed harm counts as an escape, and report observed
   escape rate against alpha per route on the **test** split. Publish it even though finops fails.
4. **Fix the conformal fit.** Split calibration into a fitting fold and a threshold-selection fold so
   the score function is fixed before LTT sees the labels. Expect thresholds to drop and coverage
   cost to rise. Report the smaller, defensible number.
5. **Measure latency or delete the metric.** The detectors already record real `perf_counter`
   timings; the evaluator throws them away in favour of `min(900, 12)`.
6. **Fix `audit_coverage`** to read the ledger, or delete it and correct `03-assumptions.md`, which
   currently claims a verification that does not happen.
7. **Normalise line endings before hashing policy** so audit records reproduce across platforms.
8. **Pin numpy** (or raise mypy's `python_version`) so `make check` passes from a fresh clone.
9. **Rebuild budget-shock on two disjoint traffic windows**, with the controller in consistent units
   and a defensible `eta`, and show coverage genuinely reallocating toward high-`c` traffic.
10. **Wire or delete `ConversationRiskAccumulator`.** Right now the multi-turn story has no code.

### Cut

- `feedback/overrides.py` — a dataclass with no behaviour and no callers.
- The `[models]` extra declaring `presidio-analyzer` and `transformers` — nothing imports them.
  Either wrap Presidio behind the `Detector` interface for real (which would substantiate the
  "allocator above detectors" positioning) or stop advertising it.
- `delay_cost_per_ms_inr` in `config/economics.yaml` — provably always multiplied by zero. Either
  set tier latencies against realistic SLOs so `d` can bite, or remove it and drop `d` from the pitch.
- The `test_scenarios.py:45` assertion pinning the 40% win.

### If the judges cloned this today

They would get a good first impression and a bad second one. It installs in two minutes, the demo
runs in seven seconds with no errors, the code is clean and the naming is disciplined,
`LIMITATIONS.md` is more honest than most commercial documentation, and the README concedes up front
that the dominance claim fails — which buys real credibility with a consulting audience. A judge who
reads for ten minutes and runs the demo scores this well: it looks like a careful team that measured
its own idea and reported an inconvenient answer.

A judge who opens `eval/report.py` scores it badly. They find that the evaluation never calls the
allocator, that the loss curve compares a knapsack to a sorted list, that `escaped_harm_rate` is a
column of zeros produced by a metric that cannot count the failure it names, and that p99 latency is
a hardcoded constant. If they check the guarantee — the claimed core differentiator — they find it
violated at 0.298 against alpha 0.20 on the route that moves money, which is a stop condition the
team wrote down itself in `00-assessment.md`. The honest framing is that the thesis has not been
tested yet: the corpus is too degenerate to admit a ranking problem, so the allocator has nothing to
win, and the flat curve is evidence about the corpus rather than about allocation. That is a fixable
problem and there is time to fix it, but it must be fixed before anyone stands up and claims a
number.
