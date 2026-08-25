# Codex brief: the `jenish` lane — runtime, durability, operations

Internal working file. **Delete this, `HANDOFF.md`, `PLAN-R3.md` and `audits/` before
submission.** Nothing in `README.md`, `docs/` or the code links to any of them.

This supersedes `CODEX_BRIEF_RUNTIME.md`. Read that file for the system background in sections 1
onward; read **this** file for what to do, where you may write, and how the merge works.

---

## 0. Set up

```bash
git checkout main
git pull origin main
git checkout -b jenish
```

Work on `jenish` only. Never commit to `main`. Push `jenish` when a milestone is green.

Before you start, run the gate and confirm it is clean on your machine, so a later failure is
yours and not inherited:

```bash
make check      # ruff + mypy --strict + pytest — 77 tests, all clean
make demo       # offline, no key, no network
make loadtest
```

Conventional commits, imperative mood, no emojis. **No agent trailers of any kind** — no
`Co-Authored-By`, no `Tooling:`. This is an official competition submission, the history was
rewritten once already to remove agent attribution, and every commit on `main` now carries only a
human author. Keep it that way; check with `git log --format='%an %ae'` before you push.

---

## 1. The merge contract — read this before writing a line

The two lanes merge with **zero conflicts**, and the mechanism is not isolation. It is that no file
has two owners. Git only conflicts when both sides touch the same file; if the ownership manifest
holds, `git merge jenish` cannot conflict no matter how long the branches diverge.

### Files you own — write freely

```
controlplane/gateway/**
controlplane/effects/**
controlplane/ledger/**
controlplane/runtime/**                  (including runtime/commands.py, already stubbed for you)
controlplane/economics/budget_controller.py
controlplane/eval/loadtest.py
controlplane/eval/runtime_report.py
config/runtime.yaml
tests/test_admission.py
tests/test_gateway.py
tests/test_ledger.py
tests/test_ledger_concurrency.py
tests/test_loadtest.py
docs/results/runtime*.md
docs/RUNTIME_*.md
progress-jenish.csv
```

Plus any **new** file inside those directories. New tests go in `tests/test_runtime_*.py` or
`tests/test_effects_*.py`, which are yours by construction because they do not exist yet.

### Files you must not touch — no exceptions

```
README.md            Makefile             pyproject.toml       progress.csv
controlplane/models.py                    controlplane/service.py
controlplane/cli.py                       controlplane/detectors/**
controlplane/economics/allocator.py       controlplane/economics/cost_model.py
controlplane/eval/report.py               controlplane/eval/metrics.py
controlplane/eval/baselines.py            controlplane/eval/sensitivity.py
controlplane/review/**                    controlplane/risk/**
controlplane/guarantees/**                controlplane/sim/**
config/economics.yaml                     config/policies/**
data/**                                   console/**
docs/** except docs/results/runtime*.md and docs/RUNTIME_*.md
every test not listed as yours
```

### The seams are already placed, so you never need to break the rule

I put these on `main` before writing this brief, precisely so you do not have to edit a file I own:

- **`make slo-sweep`, `make chaos`, `make replay`** already exist in the `Makefile` and already
  dispatch into `controlplane/runtime/commands.py`, which is **yours**. Implement the three
  functions in that file. Do not add targets to the `Makefile` and do not add branches to `cli.py`.
- **`progress-jenish.csv`** is your log. Same columns as `progress.csv`, one row per commit. We
  concatenate at merge time, so neither side ever appends to a file the other side appends to.
  That is where our last merge actually conflicted.
- **`config/runtime.yaml`** is yours for every knob you need. Do not add runtime keys to
  `config/economics.yaml`.

### Four rules

1. **New shared types go in `controlplane/runtime/models.py`**, never in `controlplane/models.py`.
   Lease, breaker state, failure policy — all of it lives in your package.
2. **Write prose only into files you own.** Your findings go in `docs/results/runtime.md` and a new
   `docs/RUNTIME_LIMITATIONS.md`. I fold them into `README.md` and `docs/LIMITATIONS.md` at
   integration. Two agents editing one README paragraph is the most reliable way to manufacture a
   conflict and the least useful one to have.
3. **If you need a change in a file I own, stop and write it down** in `progress-jenish.csv` with
   status `blocked`. Do not make the change. I will make it on `main` and you rebase.
4. **Rebase on `main` before you push**, every time: `git pull --rebase origin main`. If that
   rebase conflicts, a rule was broken — tell me rather than resolving it.

---

## 2. What changed on `main` since your last work

- **The audit trail was losing 19% of effects.** `_audit_coverage` sized its ledger read by
  interaction count; once reviews joined the chain the read paged off the oldest decisions.
  Reported 182 of 224 effects logged. `docs/00-assessment.md` names ">1% of proposed effects lack an
  audit record" as a stop condition, so we were failing our own kill criterion. Now 224 of 224.
  **Relevant to you:** `LedgerStore.records()` returns `sequence DESC`. Any caller you write must
  size its window by the verified chain length, not by an interaction count.
- **A vacuous conformal bound now says so.** `support-assistant` releases zero rows unchecked, so
  its bound holds by construction. It reported `holds`; it now reports `vacuous`.
- **Consequence sensitivity is measured.** `make sensitivity` sweeps `c` over a 0.25x-4x band.
  15.0% of decisions flip against a 20% stop condition. Tier selection moves; the verdict never
  does.
- **Reviewer attention is a second budget.** A verdict of abstain, hold or block raises a case
  priced in reviewer minutes with a per-route SLA, served by a queue that sheds what capacity
  cannot absorb. Attention is 90-98% of total assurance cost; the queue is 2.4x oversubscribed;
  intervention precision is 0.328.
- **Catch rate is measured, not configured.** Tier 2 at 0.905 against a configured 0.880, Tier 1 at
  0.605 against 0.680, from reviewer labels plus a stratified audit slice.

---

## 3. Your queue, in order

Each item leaves `make check` green, `make demo` offline, and the corpus byte-reproducible. Each
gets a row in `progress-jenish.csv` and its own commit.

### J1 — Tune admission against a stated service objective

Your own `docs/LIMITATIONS.md` entry says the bounded path is a **regression at 80 offered RPS**:
10 of 120 rejected, text p99 up from 16.30 to 39.20 ms, effect p99 up from 97.28 to 116.50 ms. And
at 400 RPS it rejects 503 of 600 to protect a tail. Rejecting 84% of traffic is only defensible if
an objective says so. Until then it is a defect, not a tradeoff.

**State the objective first, in `docs/RUNTIME_PREREGISTRATION.md`, before you run a sweep.**
Something falsifiable, for example: effect p99 under 150 ms and rejection under 1% up to a declared
capacity, with throughput not regressing below the unbounded path at or under that capacity. Then
sweep concurrency, queue capacity, rate and burst against it and commit the sweep, not just the
winner.

The result you must not produce is a tuned configuration with no stated objective behind it. If no
configuration satisfies the objective, that is the finding, and it goes in
`docs/RUNTIME_LIMITATIONS.md`.

**Done when** the objective is committed before the sweep, the sweep is reproducible by
`make slo-sweep`, and the chosen limits are justified against the objective rather than against a
single favourable number.

### J2 — The effect gate as a durable two-phase commit

The highest-value item on either lane. `gate_effects` currently returns strings like
`"transfer_funds:financial:hold"`. Our strongest safety claim — *effects wait for a verdict* — is
backed by a string.

Make it real:

- A proposed effect takes a **lease with a deadline**. The lease is durable: it survives process
  restart, because a held transfer that a crash silently releases is the exact failure this whole
  product exists to prevent.
- The verdict **commits or aborts** the lease. Commit is **idempotent** — replaying it must not
  fire the effect twice.
- Lease expiry has a defined per-route policy, and **fail-safe on expiry is mandatory**. A lease
  that runs out must never silently permit. Prove it with a test that expires a lease and asserts
  the effect did not fire.
- **The lease deadline and the review SLA are the same clock.** A held effect *is* a review case.
  Read `controlplane/review/queue.py` before you design the interface and reuse
  `review_sla_minutes` from the route policy. Do not invent a second deadline; two clocks that can
  disagree about the same held transfer is a bug we would rather not build.

`controlplane/review/**` is read-only for you. Import from it; do not edit it.

**Done when** an expired lease provably never permits, commit is idempotent under replay, the lease
survives a restart, and the trace records the lease id and its outcome.

### J3 — Circuit breakers, timeouts, bulkheads

A hung detector still yields a 500. Add per-detector timeouts, a breaker with a stated open/half-open
policy, and a **named per-route failure policy** — `fail_closed` for `finops-agent`,
`fail_open_with_annotation` for `internal-kb` — recorded in the decision trace as `degraded` with
the policy that fired. Bulkhead the tiers so a slow Tier 2 cannot starve Tier 0.

`make chaos` exercises it: hang a detector, kill one, make one slow, and show what each route does.

**Done when** a hung detector degrades to its named policy instead of a 500, and the trace says
which policy fired and why.

### J4 — Budget controller dynamics

More urgent than when this was first written, because there are now **two** controllers: compute
shadow price and, shortly, attention. `BudgetController.update` is a naive proportional step, and
per-request spend is heavy-tailed.

Replace it with something that carries a stability argument — AIMD as in TCP congestion control, or
PI with anti-windup — and **measure the lambda trajectory**: convergence, overshoot, settling time,
against the current controller on the same trace.

Then check for **starvation**: under sustained high lambda, does low-consequence traffic ever get
checked at all? The OS answer is aging. **Measure before fixing.** A starvation fix with no
starvation measurement is a change nobody can evaluate.

`controlplane/economics/allocator.py` and `cost_model.py` are read-only for you. The controller is
yours; the rule it feeds is not.

**Done when** the trajectory comparison is committed with convergence, overshoot and settling time,
and starvation is measured and reported either way.

### J5 — Group commit on the ledger

Correct but serial, and on the request path. A single-writer task fed by a queue, batching N records
per fsync the way journalling filesystems do. `tests/test_ledger_concurrency.py` is the regression
guard and must keep passing — it is what proved the chain forked under 64 concurrent appends.

**Done when** the throughput improvement is measured same-run, and the chain still verifies under
concurrency.

### J6 — Decision replay

After J2, because leases give it something worth replaying. A decision reconstructible from the
ledger alone: same inputs, same policy version, same terms, same outcome.

---

## 4. Standards

Every number you commit must be **regenerated by a committed command** and labelled with what it
measures. The load harness uses stub detectors and a declared blocking hold, so it measures the
scheduler, not production detector capacity — keep saying so.

Report the cost of every improvement. Your admission work was good precisely because it said the
bounded path was a regression at 80 RPS instead of quoting only the 400 RPS tail win. Keep that
standard. A result that only looks good is not a result.

If something fails, that goes in `docs/RUNTIME_LIMITATIONS.md` in the same commit as the attempt.
We have written down every negative result in this project and it is the most credible thing about
it.

---

## 5. When you are done

```bash
make check && make demo && make loadtest && make slo-sweep
git pull --rebase origin main
git push -u origin jenish
```

Then tell me. I merge `jenish` into `main`, concatenate the progress logs, and fold your findings
into `README.md` and `docs/LIMITATIONS.md`.

If the rebase or the merge conflicts, do not resolve it. A rule in section 1 was broken, and the
fix belongs in the rule rather than in the conflict.
