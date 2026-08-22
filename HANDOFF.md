# Handoff

Shared state between Claude Code and Codex. Read this first. Update it at the end of every session.

Last updated: 2026-08-23 by claude-code.

## Where things stand

Branch `verify/mlflow-harness`, based on `main` at `e88f1c9`. Not merged. Not pushed yet.
`main` has not moved since the first implementation.

Phase A produced `docs/audit/A-implementation-audit.md`, an audit of `e88f1c9`. Phase B acted on it.
Read the audit before touching the evaluation — it explains why most of it was rewritten.

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

Nothing. Phase B is complete and committed. Waiting on approval of the corrected curve before
Phase C (the improvement backlog).

## Known broken or missing

- `make check` fails on a fresh clone: mypy is pinned to `python_version = "3.11"` while unpinned
  numpy ships stubs needing 3.12. Not yet fixed.
- Policy hashes are taken over raw file bytes, so a CRLF checkout stamps different audit hashes than
  an LF one. Not yet fixed. Add `*.yaml text eol=lf` or normalise before hashing.
- `ConversationRiskAccumulator` and `ReviewOverride` still have zero callers.
- `presidio-analyzer` and `transformers` are declared in the `models` extra and imported nowhere.
- `delay_cost_inr` is identically zero on every route and tier, so `d` never affects a decision.
- The harm vector collapses to one axis on overlapping rows; ungrounded hallucination is not
  separable by the current detectors.
- `mlflow ui` needs the full `mlflow` package. `mlflow-skinny` logs fine but cannot serve.

## What the other tool must not touch without coordinating

- `controlplane/sim/traffic.py` and the three `data/*.jsonl` files. Regenerating with different
  weights invalidates every committed number and every conformal threshold. `make data` is
  deterministic; if the JSONL diff is non-empty after running it, something changed upstream.
- `controlplane/service.py::_split_folds` and `calibrate`. The fold split is what makes the bound
  valid; merging the folds re-breaks it silently.
- `controlplane/eval/metrics.py::summarize`. The two escape-rate definitions are deliberate and
  distinct. Do not collapse them back into one.
- `tests/test_corpus_integrity.py`. It is the regression guard for the circularity finding.

## Conventions

Branch per task, `<phase>/<short-slug>`. Never commit to `main`. `git pull --rebase origin main`
before starting and before pushing. Conventional commits, imperative, no emojis, trailer
`Tooling: claude-code` or `Tooling: codex`. Never force-push a shared branch.
