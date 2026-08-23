# Handoff

Shared state between Claude Code and Codex. Read this first. Update it at the end of every session.

Internal working file. **Delete this and `audits/` before submission.** Nothing in `README.md`,
`docs/` or the code links to either, so both can be removed without leaving dead references.

Last updated: 2026-08-23 (paged verification: Stage 0, M2, and the judge probe).

## Where things stand

`main` is at `0362b27` (Phase A + Phase B, pushed). Current work is on branch
`feat/paged-verification`, one commit ahead: `e5ae957`, not pushed.

Phase A produced `audits/A-implementation-audit.md`. Phase B fixed what it found. We are now
building **ControlPlane v2: paged verification** — applying PagedAttention's mechanisms (paging,
prefix caching, continuous batching, preemption) to the assurance budget rather than to a KV
cache. Read `docs/PREREGISTRATION.md` before looking at any new number: it locks the success
criterion and was written before the work started.

## What changed in Phase B, and why

Three findings from the audit made every previously reported number meaningless. All three are fixed.

1. **The evaluation never called the allocator.** `eval/baselines.py` contained its own
   `economic_allocator`, a greedy knapsack that never touched `allocate_verification`, the shadow
   price, or the budget controller, and priced every candidate at Tier 2 so the cascade was never
   exercised. Deleted. The allocator policy now streams the held-out set through `engine.assess`
   with `BudgetController` live, in matched units of INR per interaction.

2. **The corpus was circular.** 600 rows from 10 response templates, with source documents attached
   only to clean ones. The rule "flag any row with no context documents" scored precision 1.000 and
   recall 0.743 on held-out data with no detector involved, and calibrated AUC hit 1.000 on two of
   three routes. Rebuilt compositionally: 3000 rows, 552 distinct responses, evidence drawn
   independently of the label, loud and quiet realisations of every harm family, clean decoys that
   look like harms. Calibrated AUC is now 0.81 to 0.90.
   `tests/test_corpus_integrity.py` will fail if any of this regresses.

3. **The conformal bound was violated on held-out data.** Thresholds were selected on the same rows
   the isotonic map was fitted on. Escaped harm on `finops-agent` was 0.298 against alpha 0.20 —
   a stop condition named in `docs/00-assessment.md` that nothing measured. Calibration now splits
   into a fitting fold (35%) and a selection fold (65%). alpha moved 0.20 to 0.10, which is the
   feasible frontier: below 0.08 no threshold passes and the floor demands full coverage.

Also fixed: `escaped_harm_rate` could not count a checked-but-missed harm and read 0.000000
everywhere; `audit_coverage` was `len(tool_calls)/len(tool_calls)`; p99 latency was `min(900, 12)`
on a hardcoded constant; a Tier 2 check that had already run could be reported as skipped; scenarios
ran on hardcoded `shadow_price=10000.0`, a seeded beta-binomial prior, and a budget-shock comparison
across two different traffic windows.

MLflow is wired as the experiment spine, optional and inert when absent.

## Current best numbers

Corpus `manifest_version: 2`, seed 20260823, git SHA at time of run `4920e59`.
Experiment `controlplane-r2` in `./mlruns` (local, gitignored — run IDs are for this machine).

| Budget | Allocator averted | spend | ROI | Baseline averted | spend | ROI | Allocator run ID |
|---:|---:|---:|---:|---:|---:|---:|---|
| 10% | 5,640,800 | 608.18 | 9,275 | 5,594,700 | 270.00 | 20,721 | `f3a7871ee5c646088c6bbf62e61b5bf6` |
| 25% | 5,921,800 | 1,173.08 | 5,048 | 5,594,700 | 270.00 | 20,721 | `62d5f1832dd842b084cdb3dfabc17c36` |
| 40% | 6,010,400 | 1,952.24 | 3,079 | 5,972,400 | 1,952.00 | 3,060 | `a02e6973d2d24ea7ba323608d589c8ef` |
| 60% | 6,011,600 | 2,254.24 | 2,667 | 5,995,600 | 2,252.80 | 2,661 | `42401ab2e9cd42248dda325eed3b6ab2` |
| 80% | 6,011,600 | 2,254.24 | 2,667 | 5,995,600 | 2,252.80 | 2,661 | `81a7d84d197c4dfe9293847cedffdff2` |
| 100% | 6,011,600 | 2,254.24 | 2,667 | 5,995,600 | 2,252.80 | 2,661 | `68f418496b104ca281ee369dfe68c5fc` |

Conformal on held-out traffic, alpha 0.10: support-assistant 0.0485, internal-kb 0.0282,
finops-agent 0.0000. All hold. ECE 0.077 to 0.116. Audit: 1500 of 1500 decisions in a valid hash
chain, 215 of 215 effects logged.

Shadow price at end of run: 354.7 at a 10% budget, 46.2 at 25%, 4.7 at 40%, 0.0 at 60% and above.

## The result we have to live with

**The allocator averts more loss than the tuned baseline at all six budgets, but only by 0.3% to
5.8%, and it loses on assurance ROI at the two tightest budgets.** Running the cheap Tier 1 check
over the entire test set costs 270 INR and lands within 1% of the allocator's loss averted. Round 1
dominance is not supported.

Two structural causes, both open:

- Consequence to check cost is about 10,000 to 1, so the economics says buy the best tier for nearly
  everything until the budget binds. The trade-off region is narrow. `c` has no derivation.
- The conformal floor governs *selection*, not *catch quality*, so a blanket cheap policy satisfies
  it trivially. Stating the floor on effective escaped harm would make tier choice matter.

Do not soften this in the pitch without new evidence. `docs/LIMITATIONS.md` carries the full version.

## In flight

**A local-judge probe is running. Its result decides whether paged verification is viable.**

M2 landed the multi-claim corpus (`8041b63`): responses are now 4-7 clause paragraphs, median 5,
3000 distinct responses of 3000 rows, only 3.45% of characters carry harm, and every harmful
clause has an exact span label. alpha moved 0.10 -> 0.15 because realistic paragraphs are harder:
whole-response detector AUC fell 0.81-0.90 -> 0.67-0.76 and at 0.10 no threshold passed on any
route.

**The paging premise failed on the stub detectors.** Scoring sentences separately was no better
than scoring the whole response (hallucination -0.17 AUC, pattern axes unchanged) and the
top-scoring page was the harmful clause only 39% of the time. Those detectors are regex matchers,
so that measures the stub, not the idea. `make judge-probe` (`a86db4a`) re-runs the same question
against a real local judge. If a real judge also fails to localise, paging is dead and
`docs/PREREGISTRATION.md` says what to write.

**Stage 0 of paged verification is done and committed (`e5ae957`).**

Stage 0 repaired six defects found while planning. Three of them would have made the paging work
meaningless:

- **The gateway never calibrated.** It served raw uncalibrated scores against hardcoded
  thresholds 0.55/0.58/0.48 that no calibration produced (fitted: 0.05/0.15/0.05). A FastAPI
  lifespan now fits before serving; `assess()` raises for an unfitted route instead of inventing
  a threshold.
- **The hash chain raced.** A new test showed 64 concurrent appends collapsing to 2 surviving
  rows — writes were silently lost. Fixed with one pooled connection, WAL, busy_timeout and
  `BEGIN IMMEDIATE`.
- **`_score_jitter` keyed on `interaction_id`** while the gateway minted a fresh uuid4 per
  request, so identical content scored differently every call. Now content-keyed. Without this no
  verification cache is possible.

Also: tier-2 escalation reuses Tier 0/1 signals; `HarmVector` accessors no longer call
`model_dump` ~25x per allocation; the report makes one detection pass instead of three; policy
hashes are newline-normalised so audit stamps reproduce across platforms; **`make check` passes
clean on a fresh clone for the first time** (mypy --strict green on 44 files).

Demo 31s -> 18s. Report 22s -> 15s. 27 tests green. Corpus still byte-reproducible, now enforced
by a test.

### The gating problem for M2

Measured on the committed corpus: responses are 37-140 characters, median 80. Naive sentence
segmentation gives a **median of 1 page per response, max 2**. There is nothing to page. M2 is
therefore not "add span labels" — it is generating multi-claim responses of realistic enterprise
length, with harm localised to specific clauses. Until median pages/response is at least 4, any
paging result is a fixture artifact.

### Two design findings that constrain the build

1. **Paging can only save Tier 2 work.** The conformal floor's statistic comes from Tier 0 + Tier
   1 combined and calibrated, so those must run on every page or the committed bound stops
   meaning anything. Tier 2 at 3.20 INR is ~94% of variable cost, so this is fine — but do not
   claim Tier 0/1 savings.
2. **`_caught_loss` draws catch once per interaction.** A paged run that reads 20% of the text
   would still claim a full catch. Coverage-weighted catch
   (`k_eff * checked_units / total_units`) must land **before** `segmenter: sentence_v1` is
   enabled, never after. If the paged curve is generated once with the old catch model, that
   number will be quoted later.

## Known broken or missing

- `ConversationRiskAccumulator` and `ReviewOverride` still have zero callers.
- Running the test suite regenerates `docs/results/` as a side effect, because
  `tests/test_scenarios.py` calls `build_report` against the repo root. Harmless but it dirties
  the working tree.
- The streaming path still emits `x-controlplane-decision: pending` and cannot retract text
  already sent. Only effects are gated after the fact.
- `presidio-analyzer` and `transformers` are declared in the `models` extra and imported nowhere.
- `delay_cost_inr` is identically zero on every route and tier, so `d` never affects a decision.
- The harm vector collapses to one axis on overlapping rows; ungrounded hallucination is not
  separable by the current detectors.
- `mlflow ui` needs the full `mlflow` package. `mlflow-skinny` logs fine but cannot serve.
- The local judge is slow: roughly 87s per row for two calls (whole response plus a page batch)
  on phi3:mini. Ollama concurrency 4 buys about 2.5x and flattens after that.
- `llama3.2:3b` is not usable as a judge. On a fixture with a known answer it scored 0 of 5 with a
  strict prompt and over-flagged every supported claim with a loose one. `phi3:mini` scored 5 of 5.

## Pre-registered success criterion

`docs/PREREGISTRATION.md` locks it. Summary: **assurance ROI at the 10% and 25% budget rows**,
which are the two rows where the tuned baseline currently beats us by 2.48x and 4.10x. Success
requires allocator ROI >= baseline ROI at both, with loss averted not regressing. Partial success
is the ratio falling to 1.5x or below. Anything else is failure and gets written into the README.

The comparator must be re-derived on the **new** corpus with the unpaged allocator. Comparing
new-corpus-paged against old-corpus-flat measures nothing.

## What the other tool must not touch without coordinating

- `controlplane/sim/traffic.py` and the three `data/*.jsonl` files. Regenerating with different
  weights invalidates every committed number and every conformal threshold. `make data` is
  deterministic; if the JSONL diff is non-empty after running it, something changed upstream.
- `controlplane/service.py::_split_folds` and `calibrate`. The fold split is what makes the bound
  valid; merging the folds re-breaks it silently.
- `controlplane/eval/metrics.py::summarize`. The two escape-rate definitions are deliberate and
  distinct. Do not collapse them back into one.
- `tests/test_corpus_integrity.py`. It is the regression guard for the circularity finding and
  now also enforces byte-reproducible generation.
- `docs/PREREGISTRATION.md`. The point of it is that it was written first. Do not edit the locked
  table or the endpoint after results exist.
- `controlplane/ledger/store.py`. The single pooled connection plus `BEGIN IMMEDIATE` is what
  keeps the chain intact under concurrency; `tests/test_ledger_concurrency.py` fails without it.
- `controlplane/sim/claims.py` and `controlplane/sim/traffic.py`. The corpus is the comparator for
  the pre-registered result; regenerating it with different weights invalidates every number.
- `progress.csv`. Append-only log of what each commit changed and what it measured, with the
  parent SHA to revert to.

## Conventions

Branch per task, `<phase>/<short-slug>`. Never commit to `main`. `git pull --rebase origin main`
before starting and before pushing. Conventional commits, imperative, no emojis, trailer
`Tooling: claude-code` or `Tooling: codex`. Never force-push a shared branch.
