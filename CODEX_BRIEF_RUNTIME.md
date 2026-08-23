# Codex brief: runtime, latency and throughput

Internal working file. **Delete this, `HANDOFF.md` and `audits/` before submission.**

You are working on ControlPlane, a Round 2 entry for the Accenture Innovation Challenge 2026,
Problem Track 1 (Responsible AI Checker). Another agent is working the detection and allocation
side on a second machine. Your lane is the **runtime**: how this thing behaves under concurrency,
what its tail latency is, and what happens when parts of it fail.

---

## 1. What the system is, in one page

Every guardrail product competes on detection quality and latency. We compete on **allocation**.
The business sets an assurance budget; the system spends it where mistakes cost the most.

```
check tier t when   sum_j ( r_j * c_j * k_tj )  >  (1 + lambda) * (v_t + d_t)
```

`r` calibrated harm probability per axis, `c` consequence in rupees, `k` the tier's catch rate,
`v` verification cost, `d` delay cost, `lambda` the shadow price of the assurance budget, raised by
a controller when spend runs ahead of budget.

Two layers, and the distinction is the product: **the budget decides where to look; a conformal
(Learn-Then-Test) floor decides what may never be skipped.** Text streams to the user immediately;
only effects — tool calls, transactions, writes — wait for a verdict.

The honest limit, stated since Round 1 and not to be walked back: detection is good enough to
*rank* answers, not to *judge* them. Ranking is all a budget needs.

## 2. Read these first, in this order

1. `README.md` — what it is and the current measured result.
2. `HANDOFF.md` — live shared state between the two agents. Read it every session, update it at
   the end of every session.
3. `progress.csv` — append-only log: every commit, what it changed, what it measured, and the
   parent SHA to revert to. **Append a row for every commit you make.**
4. `docs/LIMITATIONS.md` — what is simulated and what the numbers do not prove.
5. `audits/A-implementation-audit.md` — an adversarial audit of the first implementation. It
   explains why most of the evaluation was rewritten. Read it before you trust any older number.
6. `docs/PREREGISTRATION.md` — a success criterion locked *before* the work it judges was built.
7. `docs/ARCHITECTURE.md` and `controlplane/economics/allocator.py` — the decision rule in plain
   arithmetic, about 130 lines.

## 3. Non-negotiables

This project's whole character is measured honesty. It has already thrown away two sets of
flattering numbers that turned out to be artifacts. Hold that line.

- **Never invent a benchmark number.** If you claim a speedup, a command in the repo must produce
  it, and the number must be committed. "Roughly 3x" with no harness is worse than no claim.
- **Measure before and after, on the same machine, in the same run.** A latency improvement
  measured against a remembered baseline is not a measurement.
- **Report regressions.** If your change makes something slower or less safe, say so in the commit
  message and in `docs/LIMITATIONS.md`.
- **A metric that cannot fail is a bug.** The audit found `audit_coverage` computing
  `len(tool_calls) / len(tool_calls)` and an escaped-harm rate whose denominator excluded every
  case it was meant to catch. If your new metric cannot come out badly, it is not a metric.
- **`make demo` must keep working with no API key, no network and no GPU.** That is a hard
  requirement. Optional paths go behind extras and are labelled separately.
- **`make check` must stay green** — ruff, `mypy --strict`, and the full test suite.
- **`make data` must stay byte-reproducible.** There is a test for it.

## 4. There is no training in this system

Worth stating plainly so you do not go looking. Nothing is trained. The only fitting is isotonic
calibration plus conformal threshold selection over a 1500-row calibration split, and it takes
seconds. There are no epochs, no gradients, no GPU.

Your targets are serving-side:

- p99 and p99.9 added latency, measured separately for **user-visible text** and for **gated
  effects**, because the whole thesis is that those are different
- sustained throughput in requests per second before tail latency degrades
- behaviour at saturation: what happens when offered load exceeds capacity
- cost per 1000 interactions

## 5. Your scope, and what to leave alone

**Yours:**

| Area | Files |
|---|---|
| Gateway, admission, backpressure | `controlplane/gateway/` |
| Budget controller dynamics | `controlplane/economics/budget_controller.py` |
| Effect gate durability | `controlplane/effects/` |
| Ledger write path | `controlplane/ledger/` |
| New runtime package | `controlplane/runtime/` (create it) |
| Load harness | new, e.g. `controlplane/eval/loadtest.py` |

**Do not touch — another agent is mid-experiment in these, and a pre-registered result depends on
them being stable:**

- `controlplane/sim/traffic.py`, `controlplane/sim/claims.py`, and `data/*.jsonl`. Regenerating the
  corpus invalidates every committed number and the pre-registered comparator.
- `controlplane/service.py::calibrate` and `_split_folds`. The fold split is what makes the
  conformal bound valid; merging the folds re-breaks it silently.
- `controlplane/eval/metrics.py::summarize`. The two escape-rate definitions are deliberately
  distinct. Do not collapse them.
- `controlplane/detectors/ollama_judge.py`, `controlplane/eval/judge_probe.py`.
- `controlplane/economics/allocator.py` — coordinate before changing the decision rule itself.
- `docs/PREREGISTRATION.md` — the point of it is that it was written first.

If you need a change inside someone else's lane, write it in `HANDOFF.md` and leave it.

## 6. The work

Ordered by value. Each names the OS or networking technique it borrows, because that framing is
the pitch: we already argue that assurance budget is a memory-allocation problem, and the runtime
should argue that assurance scheduling is a CPU-scheduling problem.

### 6.1 Admission control and backpressure — highest value

There is no concurrency limit anywhere today. FastAPI dispatches blocking work to the default
`asyncio.to_thread` pool, so at load the pool saturates, queueing is invisible, and tail latency
explodes with no signal. Build:

- a bounded work queue with an explicit per-route concurrency limit
- **token-bucket admission** at the edge
- **load shedding that degrades to the conformal floor** rather than dropping requests: under
  pressure, serve the mandatory check only and skip discretionary spend
- an explicit `degraded: true` in the decision trace when that happens

The point to demonstrate: at saturation the system gives up *discretionary assurance first* and
the guarantee last. That is the thesis, expressed in the scheduler.

### 6.2 Two-phase verification: blocking fast path, async deep path

Everything is inline today, and the streaming path concedes in writing that it cannot retract text
already sent. Split it, the way an OS splits an interrupt handler from its bottom half:

- a **release gate** — Tier 0 plus cheap Tier 1, with a hard latency budget — that genuinely blocks
  before the first token on high-consequence routes
- an **async deep path** — Tier 2 — that runs after release on low-consequence routes and feeds the
  incident record

Which one a route gets is policy, in `config/policies/*.yaml`. This converts our sharpest
unanswered objection ("parallel checking does not help if the wrong answer already streamed") from
a written concession into a per-route architectural choice with a measured latency price.

### 6.3 Circuit breakers, timeouts, bulkheads

If a detector hangs, today you get a 500. Add per-detector timeouts, a circuit breaker, and a
**named failure policy per route** — `fail_closed` for `finops-agent`, `fail_open_with_annotation`
for `internal-kb` — recorded in the trace. Bulkhead the tiers so a slow Tier 2 cannot starve
Tier 0. Every architect asks this within a minute of seeing the diagram.

### 6.4 Effect gate as a durable two-phase commit

`gate_effects` currently returns a list of strings like `"transfer_funds:financial:hold"`. Make it
real: proposed effects land in a table with a **lease and a deadline**, the verdict commits or
aborts, commit is idempotent, and a lease timeout has a defined policy. The `$5,000 transfer` story
is the demo everyone remembers; right now it is a printout.

### 6.5 Budget controller dynamics

`BudgetController.update` is a naive proportional step:
`lambda <- max(0, lambda + eta * (spend_rate - budget_rate) / budget_rate)`.
With per-request spend that is near-continuous and heavy-tailed, it oscillates. Replace with
something with a stability argument — **AIMD, as in TCP congestion control**, or a PI controller
with anti-windup. Then *measure* the lambda trajectory and show convergence, overshoot and settling
time. This is a genuinely nice systems result and it is currently a one-line heuristic.

Watch for **starvation**: under sustained high lambda, low-consequence traffic may never be
checked. The OS answer is **aging**. Measure whether starvation occurs before you fix it.

### 6.6 Ledger write path

`ledger/store.py` was just repaired — a concurrency test showed 64 concurrent appends collapsing to
2 surviving rows. It now holds one pooled connection with WAL and `BEGIN IMMEDIATE` under a lock.
It is correct but serial, and it is on the request path. Consider a single-writer task fed by a
queue, with **group commit** (batch N records per fsync, as journalling filesystems do). Keep
`tests/test_ledger_concurrency.py` passing — it is the regression guard.

### 6.7 Decision replay

Traces already stamp policy version, policy hash and detector versions. Add a versioned calibration
artifact and you can **replay any decision from the ledger and get a byte-identical trace**.
"Why did you allow this?" answered forensically. Mostly plumbing, and very differentiated.

## 7. How to prove it

Build `controlplane/eval/loadtest.py` and a `make loadtest` target that writes
`docs/results/runtime.md`, committed. It must report:

- offered load vs achieved throughput, to the saturation point and past it
- latency distribution — p50, p95, p99, p99.9 — for text and for gated effects **separately**
- what the system sheds under overload, and proof the conformal floor held while it did
- queue depth and wait time over the run
- lambda trajectory: convergence, overshoot, settling time
- a before/after table for every optimisation, measured in the same run on the same machine

Two honesty notes specific to your lane:

- The detectors are regex and lexical stubs; they run in microseconds. **A throughput number
  measured against them describes our harness, not a production cascade.** Label it exactly that
  way, as the repo already does for p99 latency. If you want a number that means something, put a
  real detector behind the interface and report both.
- Machine load skews everything. Record what else was running. The other agent may be saturating a
  local model server on their machine, not yours, but your own test runs will contend with each
  other.

## 8. House style

The repo is read by consultants and architects who see a lot of AI-generated submissions. It must
not look like one.

- No emojis anywhere. No banner comments, no ASCII dividers.
- Comments explain *why*, never restate *what*. Roughly one per fifteen lines of real logic.
- Banned words: comprehensive, robust, seamless, leverage, delve, cutting-edge, state-of-the-art,
  powerful, elegant, journey, unlock, empower. No "not just X, it's Y". No adjective triads.
- Functions under 40 lines, files under 400. Type hints everywhere; `mypy --strict` clean.
- Domain names: `shadow_price`, `escaped_harm_rate`, `effect_gate`, `catch_rate`. Never `data`,
  `result`, `manager`, `utils.py`, `process()`, `handle()`.
- No abstraction with a single implementation. No `try/except Exception: pass`.
- Configuration in YAML under `config/`, not dicts scattered through modules.
- Tests: property-based where there are invariants (hypothesis is already a dependency), and no
  test that only asserts a function returned without raising.
- Conventional commits, imperative mood, small, in the order the work happened. Explain the
  tradeoff where one was made.

## 9. Working agreement

- **Author every commit as the repo owner.** Do not set an agent name as author and do not add
  agent trailers or `Co-Authored-By` lines. This is an official submission and the history has
  already had to be rewritten once to remove them.
- **Never push. Stage and commit only.** The owner pushes.
- Branch per task, `<area>/<short-slug>`. `git pull --rebase origin main` before starting.
- Never force-push. Never rewrite published history.
- Append a row to `progress.csv` for every commit: stage, date, commit, parent to revert to,
  branch, title, what changed, what it measured, test count, status.
- Update `HANDOFF.md` at the end of every session: what changed, why, what is in flight, what is
  broken, what the other agent must not touch, and the current best numbers.
- If you hit a conflict in code you did not write, stop and surface it rather than guessing intent.

## 10. Where things stand right now

- Serving integrity was just repaired: the gateway used to serve **uncalibrated** scores against
  invented thresholds (`0.55 / 0.58 / 0.48`) that no calibration ever produced. It now fits from
  `data/calibration.jsonl` in a FastAPI lifespan and refuses to serve an unfitted route.
- The corpus was rebuilt twice. It now holds 3000 multi-claim paragraphs, 3000 distinct responses,
  harm in exact labelled character spans, and only **3.45% of characters carry harm**.
- `alpha` is 0.15, the feasible frontier for the current detectors. Below about 0.12 no threshold
  passes and the floor demands 100% coverage.
- Current result, honestly: the allocator averts more loss than a tuned blanket-Tier-1 baseline at
  all six budget levels by 1.0% to 5.4%, but **loses on assurance ROI at the three tightest
  budgets**, because checking everything with the cheap tier costs only 270 INR. Round 1 dominance
  is not supported and the README says so.
- The other agent is testing whether a real local judge can localise harm to a clause well enough
  for span-level verification to pay. On the stub detectors it could not: the top-scoring sentence
  was the actually-harmful one only 39% of the time.

Start by reading `HANDOFF.md`, then run `make check` and `make demo` to confirm the repo is green
on your machine before changing anything.
