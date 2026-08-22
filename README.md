# ControlPlane.ai prototype

ControlPlane allocates a fixed assurance budget across AI interactions. It combines a per-route
finite-sample verification floor with the Round 1 economic rule:

```text
sum(risk_j * consequence_j * catch_rate_tj) > (1 + shadow_price) * (check_cost_t + delay_cost_t)
```

The guarantee determines which traffic may not be skipped. The allocator chooses which additional
checks are worth buying. Response text can stream while verification runs; proposed financial,
irreversible, or external effects wait for the decision.

This repository is a CPU-only competition prototype. It needs no API key, network call, or GPU at
runtime.

## Run in ten minutes

Python 3.11 or newer is required.

```bash
make install
make demo
make console
```

The console opens at `http://localhost:8501`. On PowerShell without `make`, use:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m controlplane.cli demo
.\.venv\Scripts\python.exe -m streamlit run console\streamlit_app.py
```

Regenerate the evaluation and run all checks with:

```bash
make report
make check
```

## What to inspect first

1. `controlplane/economics/allocator.py` contains the expected-loss decision in plain arithmetic.
2. `controlplane/guarantees/conformal.py` learns the mandatory per-route release threshold.
3. `reports/scenarios.json` records the eight named competition scenarios.
4. `reports/evaluation.md` compares check-none, check-all, fixed-rate, and economic allocation.
5. `docs/LIMITATIONS.md` states where the current evidence is insufficient.

## Current measured result

`make report` evaluates 300 held-out synthetic rows after fitting on a separate 300-row calibration
split. At 40% of the nominal full-check spend, the allocator and fixed-rate baseline both spend INR
384. The allocator averts INR 2,813,500 of simulated loss versus INR 2,775,500 for fixed-rate, while
its intervention precision is slightly lower: 98.33% versus 99.17%.

The allocator does not dominate the baseline across the full curve. It ties at 10%, 25%, 80%, and
100%, wins at 40%, and loses at 60%. This fails the strongest Round 1 dominance claim. The result is
useful only as an implementation check on labelled fixtures; it is not evidence of production loss
reduction.

The generated figures are:

- `reports/figures/loss_averted_vs_spend.png`
- `reports/figures/reliability_by_route.png`

## Request path

The FastAPI endpoint accepts an OpenAI-shaped request at `POST /v1/chat/completions`. A blocking
Tier 0 preflight resolves policy and rejects known injection patterns before the provider runs. The
seeded provider then returns or streams text. Tier 0 and Tier 1 estimate the harm vector; Tier 2 runs
only when selected. The allocator applies the conformal floor and shadow-priced cost rule, the effect
gate holds sensitive tool calls, and SQLite records the trace in a hash chain.

Start the API with `make api`, then send:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H "content-type: application/json" \
  -H "x-controlplane-route: support-assistant" \
  -d '{"model":"controlplane-sim","messages":[{"role":"user","content":"What is the renewal fee?"}],"context_documents":["The renewal fee is INR 499."]}'
```

## Real versus simulated

Real code paths include policy hot reload and hashing, preflight blocking, detector composition,
isotonic calibration, the exact-binomial finite-grid risk test, budget allocation, effect gating,
streaming, ledger integrity checks, metrics, and the console.

The model provider, detector scores, catch-rate priors, consequence amounts, token/check prices, and
latency values are simulated. Public datasets considered for the next evaluation are documented in
`docs/06-datasets.md`; none are downloaded or redistributed by the offline demo.

## Repository map

```text
controlplane/   gateway, policies, detectors, risk, economics, guarantees, effects, ledger
console/        Streamlit assurance console
config/         EU and India route policies plus tier economics
data/           seeded JSONL corpus and its manifest
docs/           assessment, sources, compliance map, ADRs, proposal, and limitations
reports/        regenerated metrics, scenarios, tables, and figures
tests/          properties, conformal behavior, scenarios, gateway, and ledger tampering
```

The architecture and component contracts are in `docs/ARCHITECTURE.md`. Dataset licensing and
provenance are in `data/README.md` and `data/dataset_manifest.yaml`.
