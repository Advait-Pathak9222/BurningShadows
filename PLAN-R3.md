# Round 3 plan: where the project stands, and who does what

Internal working file. **Delete this, `HANDOFF.md`, `CODEX_BRIEF_JENISH.md` and `audits/`
before submission.** Nothing in `README.md`, `docs/` or the code links to any of them.

Written 2026-08-25 against `main` at `e5fd7ae`.

---

## 1. Where the project stands: 7 / 10

Not a hedge — the number is built from parts, and the parts point at different work.

| Dimension | Score | Why |
|---|:--:|---|
| Technical depth | **9** | A working system, not a slide deck. Isotonic calibration, Learn-Then-Test with exact binomial bounds and Bonferroni correction, a shadow-price dual, a hash-chained ledger that survives concurrency, bounded admission control, a reviewer queue that is a second allocator. 68 tests, `mypy --strict` clean over 55 files, byte-reproducible corpus, offline demo. |
| Methodological integrity | **9.5** | Rare, and it is the strongest differentiator we have. We audited our own implementation and published the audit. We rebuilt a corpus that was scoring 1.000 AUC for the wrong reason. We found and fixed a conformal violation *we* introduced. We deleted two metrics for being tautologies. We pre-register endpoints before running them. Almost nobody in a hackathon does this. |
| Originality | **8** | "Verification is capital allocation, not a detection contest" is a genuinely different frame. The attention-economics finding — 90-98% of assurance cost is human, not compute — is non-obvious, measured, and reframes the whole category. |
| Evidence quality | **6** | The headline advantage over a tuned blanket-Tier-1 baseline is 1.0% to 5.4% on loss averted, and we lose on ROI at the two tightest budgets. Honest, and thin. One of three routes has a **vacuous** conformal bound. `c` — the input every rupee figure depends on — has no derivation and no sensitivity analysis. |
| Problem-statement coverage | **6.5** | Human-in-the-loop: done. Feedback loop: done. **Multi-turn compounding risk: not done** — `ConversationRiskAccumulator` has zero callers, and it is named explicitly in the problem statement. "We compose with third-party detectors" is positioning; `presidio-analyzer` is declared in `pyproject.toml` and imported nowhere. |
| Presentation and consistency | **5** | The weakest dimension and the cheapest to fix. `README.md` quotes numbers that contradict `docs/results/summary.md` — different alpha, different loss averted, different escape rates. A judge who cross-checks one number against another finds a contradiction, and everything else we claim gets read through that. |

**Weighted, that is a 7.** The engineering is competition-winning; the story around it is not yet
telling the truth the engineering supports.

### The two things that would cost us the most, in order

1. **`README.md` disagrees with the committed results.** README says alpha 0.10 and 5,640,800
   averted. `docs/results/summary.md` says alpha 0.15 and 5,184,700. Both are in the repo. This is
   not a rounding difference — it is a stale section that survived a corpus regeneration. Everything
   we have built on being unusually honest is undone by one contradiction a judge can find in
   ninety seconds.
2. **The competitive claim is weak on its own terms.** Beating a tuned baseline by 1-5% is not the
   Round 1 story. Section 3 says what to do about it, and it is not spin — it is that the current
   comparison is measured wrong, in *both* directions, and fixing it is the honest move regardless
   of which way the number goes.

### Two defects found and fixed while writing this

Both were live on `main` this morning.

- **The audit trail was losing 19% of effects.** `_audit_coverage` sized its read window by
  interaction count. Once reviews joined the decision chain the read paged off the oldest
  decisions and every effect on them vanished: 182 of 224, coverage 0.8125. `docs/00-assessment.md`
  lists "more than 1% of proposed effects lack an audit record" as a **stop condition**. We were
  tripping our own kill criterion and reporting it in a table without noticing. Now 224 of 224.
- **A vacuous guarantee was printing as a passing one.** `support-assistant` releases zero rows
  unchecked, so its bound is satisfied by construction. The table said `holds`. It now says
  **vacuous**, with the share of traffic the floor made mandatory.

Fixed in `c5cc876`, both with tests that fail against the previous behaviour.

---

## 2. How the two lanes stay conflict-free

The instruction: Codex works somewhere other than `main`, in a place called `jenish`, and the two
are merged when both are done.

**Recommendation: `jenish` is a branch, checked out in its own directory on the Codex machine.**
A literal `jenish/` folder inside the repo would mean two copies of the `controlplane` package,
two test suites and two Makefiles, and the merge would be a manual reconciliation of duplicated
source rather than a merge. A branch gives the same isolation and merges in one command.

Isolation is not what prevents conflicts, though. **Disjoint file ownership is.** Git only
conflicts when both sides touch the same lines of the same file, so if no file has two owners,
`git merge jenish` cannot conflict. That is the whole mechanism, and it holds no matter how long
the branches diverge.

### The ownership manifest

| Owned by **Codex** (`jenish`) | Owned by **Claude Code** (`main`) |
|---|---|
| `controlplane/gateway/**` | `controlplane/detectors/**` |
| `controlplane/effects/**` | `controlplane/risk/**` |
| `controlplane/ledger/**` | `controlplane/guarantees/**` |
| `controlplane/runtime/**` | `controlplane/review/**` |
| `controlplane/economics/budget_controller.py` | `controlplane/economics/{allocator,cost_model}.py` |
| `controlplane/eval/{loadtest,runtime_report}.py` | `controlplane/eval/{report,metrics,baselines,judge_probe,tracking}.py` |
| `config/runtime.yaml` | `controlplane/{models,service,cli}.py`, `controlplane/sim/**`, `controlplane/feedback/**` |
| `tests/test_{admission,gateway,ledger,ledger_concurrency,loadtest}.py` | `config/economics.yaml`, `config/policies/**`, `config/judge.yaml` |
| `docs/results/runtime*.md`, `docs/RUNTIME_*.md` | every other test, `data/**`, `console/**` |
| `progress-jenish.csv` | `README.md`, `Makefile`, `pyproject.toml`, all other `docs/**`, `progress.csv` |

### The five rules that make it hold

1. **No file has two owners.** If a change needs a file the other lane owns, it does not happen —
   it gets requested, and the owner makes the change before the other side starts.
2. **No shared append-only file.** This is where our last merge actually conflicted. `progress.csv`
   stays mine; Codex logs to `progress-jenish.csv`. At merge they concatenate, and git never has to
   reconcile two sets of appended rows.
3. **Codex writes prose only into files it owns.** Its findings go to `docs/results/runtime.md` and
   `docs/RUNTIME_LIMITATIONS.md`. I fold them into `README.md` and `docs/LIMITATIONS.md` at
   integration time. Two agents editing the same paragraph of a README is the most reliable way to
   produce a conflict and the least valuable one to have.
4. **New shared types live in the owner's package.** Codex's lease and breaker types go in
   `controlplane/runtime/models.py`, never in `controlplane/models.py`.
5. **I pre-place every seam before Codex starts.** Make targets, config stubs, the progress file.
   Codex adds new files and edits its own; it never needs to touch a file it does not own, so it
   never has a reason to break rule 1.

### Merge procedure

```bash
git checkout main && git pull
git merge jenish --no-ff        # expected: zero conflicts
make check && make demo && make report && make loadtest
tail -n +2 progress-jenish.csv >> progress.csv   # concatenate the logs
```

If that merge reports a conflict, a rule was broken. Fix the rule, not just the conflict.

---

## 3. My lane: evidence, correctness, narrative

Ordered by value per hour, not by dependency.

### C1 — Audit-window and vacuous-bound fixes — **done** (`c5cc876`)

### C2 — Pre-registration 2 — **done** (`e5fd7ae`)

### C3 — One decision path for allocator and baselines — **done** (`ecb9ddd`)

**Result: partial success against the pre-registered endpoint.** The allocator does not beat
the tuned baseline on total-cost ROI at 10% or 25%, so the primary endpoint fails; the partial
bar is met, with the ratio falling from 2.28x and 3.76x to 1.006x and 1.016x. The gap closes
because the attention bill is 30-70x the compute bill and both policies pay it in full, not
because allocation improved. Written into README and LIMITATIONS in those words.

**The comparison this opened up, and did not run:** attention spend is identical across every
policy that raises more than a shift's worth of cases, because capacity is fixed and the queue
saturates. What differs is *what gets shed*. Whether our shedding rule — deadline first, then
expected loss per reviewer minute — beats FIFO or random at the same capacity is the comparison
that would actually differentiate the product, and nobody has run it. **This is now the highest
value item on the list** and it is tracked below as C3b.

<details><summary>Original scope</summary>

The comparison is measured wrong in both directions, and both errors are documented in our own
`LIMITATIONS.md`:

- Only the allocator is charged for the reviewer minutes its verdicts consume. The baselines get
  human review for free — at INR 120 a case against INR 0.18 a Tier 1 check, that is the entire
  cost structure being handed to the other side.
- Only the allocator may block or abstain, and a response that never reaches anyone counts as
  fully averted. That one flatters *us*.

The fix is one decision path where the two policies differ only in **which rows get checked and at
what tier** — the thing actually under comparison. Both run the shipped verdict rule, both may
block or abstain, both are charged their own attention.

Pre-registered at `e5fd7ae` before implementation, because the change could go either way, and
with an explicit guard: a policy that looks cheaper because it overloaded the queue and shed the
overflow has not saved money, it has moved unreviewed risk off the books. If the winner also sheds
more, the result is inconclusive.

**Done when** `summary.md` reports total assurance ROI next to compute-only ROI for every policy,
with cases raised and shed per policy, and the outcome is written into `README.md` whichever way it
falls.

</details>

### C3b — Does our attention allocation beat a naive queue? **[next, highest value]**

The finding from C3 is that compute allocation barely moves total cost, because attention dominates
and every policy saturates the same fixed capacity. So the question that decides whether this
product is differentiated is not *which rows get a Tier 2 check*. It is **which cases get the
reviewer's hour**.

We already have the mechanism — the queue serves by deadline, then by expected loss per reviewer
minute, and sheds what capacity cannot absorb. What we have never done is compare it against the
alternatives every real review desk actually uses: FIFO, random, and highest-score-first. At a fixed
166 cases of capacity against 244-396 raised, the difference between those rules is the difference
between catching the expensive misses and catching whatever arrived first.

This is the strongest remaining experiment in the project, and unlike the compute comparison it is
one where nobody else is even trying.

**Done when** loss averted and escaped harm are reported per shedding rule at matched capacity,
pre-registered before it is run, and the result is written down whichever way it goes.

### C4 — Consequence sensitivity analysis — **done** (`1879071`)

15.0% of decisions flip across a 0.25x-4x band against the 20% stop condition, so it passes.
Reported alongside: the worst single draw is 22.3% and does breach, and 54% of decisions move
under at least one of 48 draws. The finding worth the most is that tier selection moves and the
verdict never does — `c` prices a check and does not enter the release rule.

<details><summary>Original scope</summary>

`c` is promised a sensitivity analysis in **five** documents — the kill criteria in
`docs/00-assessment.md`, the risk table in `docs/07-business-proposal.md`, the deliverables list in
`docs/05-scope-proposal.md`, `docs/adr/001`, and the next-evidence list in `docs/LIMITATIONS.md` —
and implemented in none. The Phase A audit flagged it. It is the most-promised, least-delivered
thing in the repo.

It is also the answer to the sharpest business objection we have written down ourselves:
*"Your `c` values are made up. Enterprises cannot price a hallucination."* The answer is not a
better guess. It is: **here is how much the decision moves across the plausible range, and here is
the stop condition we set ourselves.**

`make sensitivity` sweeps low/base/high consequence per route, reports the share of decisions that
flip tier or verdict, and tests it against the 20% stop condition already written in
`docs/00-assessment.md`. If more than 20% flip, that goes in `README.md` as a finding about
readiness for unattended use — which is exactly what the assessment says it means.

**Done when** `docs/results/sensitivity.md` is committed, regenerated by a command, and the stop
condition is evaluated rather than asserted.

</details>

### C5 — R4: multi-turn risk, wired in

`ConversationRiskAccumulator` has zero callers. Multi-turn compounding risk is named in the problem
statement. This is a rubric line item we currently score nothing on, and the class already exists.

**Done when** a two-turn scenario shows the second turn checked at a higher tier than the same turn
would have been alone, and the session state is in the decision trace.

### C6 — R5: Presidio behind the Detector interface

"We compose with existing safety products rather than replacing them" is our stated moat answer, and
right now `presidio-analyzer` is declared in `pyproject.toml` and imported nowhere. Offline,
CPU-only, pip-installable, fits the existing interface without touching the demo path.

**Done when** a labelled PII comparison against the regex baseline is committed, reporting whichever
way it goes — including if Presidio loses.

### C7 — Documentation resync — **done** (`af36d4a`)

<details><summary>Original scope</summary>

`README.md`, `docs/LIMITATIONS.md`, `HANDOFF.md` and the console caption all quote pre-regeneration
numbers. Every figure in prose gets re-derived from `docs/results/results.json`, and the
pre-registration gets a dated addendum rather than an edit — the point of a pre-registration is that
it was written first.

Cheap, and it is worth more than any single feature on this list.

</details>

### C8 — The dead `d` term

`delay_cost_inr` is identically zero on every route and tier, because every tier's latency sits
below every route's effect SLO. So the headline equation carries a variable that never fires. Either
demonstrate it live under a tight-SLO route, or state plainly that on the shipped configuration the
rule is `r*c*k > (1+lambda)*v`. Not stating it is the option we do not have.

### C9 — Tier 0 is never selected

Tier 1 dominates it on value density at these prices, so a third of the cascade is dead weight in
every run. Either it earns its place at some price point or the cascade is two tiers and we say so.

### C10 — Judge probe rerun

`make judge-probe`, roughly an hour, needs Ollama and `phi3:mini`. The decoding bug that invalidated
the first run is fixed. Its localisation rate is what decides whether paged verification is viable.
Runs in the background; blocks nothing.

### C11 — Business case rebuilt on C3 and C4

Whatever C3 and C4 produce, the business case is rewritten on it. If C3 fails, the case rests on the
cost-structure finding alone, which is still defensible and still the most interesting thing we
know.

### C12 — Pre-submission cleanup

Delete `HANDOFF.md`, `CODEX_BRIEF_JENISH.md`, `PLAN-R3.md`, `audits/`, `progress-jenish.csv`.
Verify zero dead references afterwards. Already rehearsed once; it left no dangling links.

---

## 4. Codex's lane: runtime, durability, operations

Full brief in `CODEX_BRIEF_JENISH.md`. Summary and ordering:

| # | Item | Why it is worth doing | Done when |
|---|---|---|---|
| **J1** | Tune admission against a stated SLO | Its own `LIMITATIONS.md` entry says the bounded path is a **regression at 80 RPS** — 10 of 120 rejected, both p99s worse. Rejecting 503 of 600 to protect a tail is only defensible if an objective says so. This removes a documented defect. | The SLO is stated first, the sweep is committed, and the chosen limits are justified against it |
| **J2** | Effect gate as a durable two-phase commit | The highest-value item on either lane. `gate_effects` returns strings like `"transfer_funds:financial:hold"`. Make it a lease with a deadline, commit or abort on verdict, idempotent commit, defined expiry policy per route. **Fail-safe on expiry is mandatory.** Shares a clock with the review queue — a held effect *is* a review case — so reuse `review_sla_minutes` rather than inventing a second deadline. | A lease that expires never permits, commit is idempotent under replay, and a test proves both |
| **J3** | Circuit breakers, timeouts, bulkheads | A hung detector still yields a 500. Per-detector timeouts, a breaker, a named per-route failure policy (`fail_closed` for `finops-agent`, `fail_open_with_annotation` for `internal-kb`) recorded in the trace as `degraded`. Bulkhead the tiers so a slow Tier 2 cannot starve Tier 0. | A hung detector degrades to a named policy instead of a 500, and the trace says which |
| **J4** | Budget controller dynamics | There are now **two** controllers — compute and attention — and `update` is a naive proportional step against heavy-tailed spend. Replace with something carrying a stability argument (AIMD, or PI with anti-windup). Then measure **starvation**: under sustained high lambda, does low-consequence traffic ever get checked? The OS answer is aging. Measure before fixing. | The lambda trajectory is committed with convergence, overshoot and settling time, and starvation is measured either way |
| **J5** | Ledger group commit | Correct but serial and on the request path. A single-writer task fed by a queue, batching N records per fsync as journalling filesystems do. `tests/test_ledger_concurrency.py` is the regression guard and must keep passing. | Throughput improvement measured same-run, chain still verifies under concurrency |
| **J6** | Decision replay | Left until after J2, since leases give it something worth replaying. | A decision is reconstructible from the ledger alone |

**Ordering rationale:** J1 first because it is bounded and deletes a stated negative. J2 second
because it converts our weakest safety claim into our strongest. J3-J5 after.

### What Codex must not touch

`controlplane/sim/traffic.py`, `controlplane/sim/claims.py`, `data/*.jsonl` — the corpus is the
comparator for a pre-registered result; regenerating it with different weights invalidates every
committed number and every conformal threshold.

`service.py::calibrate` and `_split_folds` — the fold split is what makes the bound valid.

`eval/metrics.py::summarize` — the two escape-rate definitions are deliberate and distinct.

`economics/allocator.py`, `docs/PREREGISTRATION.md`, `tests/test_corpus_integrity.py`,
`controlplane/review/**` — read them, reuse them, do not edit them.

---

## 5. Sequence

**Now to handoff (me, before Codex starts):** pre-place the seams. Make targets Codex will need,
`progress-jenish.csv`, the brief. Codex must never have a reason to edit a file I own.

**Parallel phase:** I run C3, C7, C4, C5, C6, with C10 in the background. Codex runs J1 through J5.
Neither blocks the other at any point; the ownership manifest is what guarantees it.

**Integration:** merge `jenish` into `main` (expect zero conflicts), concatenate the progress logs,
run the full gate, fold Codex's findings into `README.md` and `docs/LIMITATIONS.md`.

**Submission:** C11 rewrites the business case on the final numbers, C12 deletes the working files,
final gate, push.

### The gate, every time, both lanes

```bash
make check      # ruff + mypy --strict + pytest, all clean
make data       # corpus must reproduce byte-for-byte
make demo       # offline, no key, no network
make report     # regenerates docs/results/
make loadtest   # runtime lane
```

---

## 6. What I will not do

No authentication, multi-tenancy, or telemetry backend — undifferentiated, and they would eat the
time the evidence needs. No new detector families. No corpus regeneration. No paged verification
until the judge probe says whether a real judge can localise harm; the pre-registration already says
what gets written down if it cannot.
