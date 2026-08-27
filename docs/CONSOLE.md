# The assurance console

A guide to what each view shows, where the numbers come from, and what to look at first.

The console is a read-and-probe surface over the same committed evidence the reports use. It is not
a second implementation: every figure it draws is either loaded from `reports/` and `docs/results/`,
or recomputed live by the same `AssessmentEngine` the gateway runs.

```bash
make console          # regenerates the report first, then opens http://localhost:8501
```

Without `make`:

```powershell
.\.venv\Scripts\python.exe -m streamlit run console\streamlit_app.py
```

> `make console` depends on `make report`, so the first launch spends about 15 extra seconds
> rebuilding artifacts. If you are about to demo, run `make report` beforehand and then launch
> Streamlit directly — it opens in about three seconds.

---

## How the app is wired

`console/streamlit_app.py` is a single 684-line script. Three cached loaders do all the data access,
which is why switching views is instant after the first load:

| Loader | Cache | Reads | Used by |
|---|---|---|---|
| `load_artifacts()` | `@st.cache_data` | `reports/evaluation.csv`, `reports/evaluation.json`, `reports/scenarios.json` | Overview, Scenarios |
| `load_attention()` | `@st.cache_data` | `docs/results/attention.json` | Reviewer queue |
| `assessment_engine()` | `@st.cache_resource` | corpus + `config/`, writes `data/audit.db` | Decision lab, Audit ledger |

`load_artifacts()` falls back to computing the report in-process if `reports/` is missing, so a
fresh clone still works — it is just slower on first paint. `assessment_engine()` calibrates once on
the 1,500 calibration rows and is then held for the life of the process, which is what makes the
Decision lab feel immediate.

Two controls in the sidebar are **global** — they apply to Overview and Reviewer queue at the same
time:

- **Budget fraction** — `10% / 25% / 40% / 60% / 80% / 100%`, default `40%`. This is the share of
  the full-coverage compute budget the allocator is allowed to spend.
- **Policies** — `allocator`, `fixed_rate`, `check_none`, `check_all`. Default is the first two.
  This filters the comparison chart only.

---

## 1. Overview — does the allocation actually pay?

The landing view. Four metrics across the top, all for the **allocator** at the selected budget:

| Metric | Meaning |
|---|---|
| Loss averted | Rupee value of harm prevented against the do-nothing baseline |
| Compute spend | What the automated checks cost |
| Reviewer spend | What the human reviews cost |
| Attention share of cost | Reviewer spend ÷ total assurance spend |

**Look at the fourth metric first.** At a 40% budget it reads about 91%, and dragging the budget
slider moves it between roughly 85% and 97% without ever going below. That single number is the
project's central finding: the compute budget everyone argues about is a rounding error next to the
salary cost of the people the system escalates to.

Below that:

- **Loss averted against compute spend** — one line per selected policy. The allocator's line sits
  above `fixed_rate` at every budget. Each policy runs the same verdict rule and is charged for the
  reviewer minutes its own verdicts raise; they differ only in *which rows they check*.
- **Per-route release floor** — the finite-sample guarantee per route. The certified bound stays
  under the target α of 0.15 on all three routes. This is the table to point at when someone asks
  what stops the budget from starving safety.
- **Where assurance money actually goes** — a stacked bar across all six budgets. The human-review
  band barely moves while the automated band grows; visually this is the attention finding.
- **Full metric table** — an expander with every column of `evaluation.csv` if someone wants to dig.

---

## 2. Reviewer queue — the finding that follows from the first one

If reviewer time is 85–97% of the cost and capacity is fixed, then the only remaining lever is
**which cases get served first**. This view is that experiment.

Four metrics: cases raised, queue oversubscription, reviewers needed to keep up, and total capacity
in minutes. At a 40% budget the queue is oversubscribed and needs about 5.4 reviewers against the 2
on shift.

The table compares five serving rules at identical capacity on identical cases, so the comparison is
about ordering alone:

| Rule | Role |
|---|---|
| `deadline_density` | shipped |
| `fifo` | baseline |
| `random` | baseline |
| `density` | ablation — the shipped rule with its deadline term removed |
| `deadline` | ablation |

**Do not skip the `density` row.** It beats the shipped rule on both expected loss served and SLA
breaches. That is reported rather than buried, and it is one of the more credible things in the
project — the ablation that undercuts our own default is right there in the default view.

---

## 3. Scenarios — nine hand-built situations

A dropdown of nine scenarios, each with a written view rather than a JSON dump. Every one also has a
**Raw scenario record** expander at the bottom for anyone who wants the underlying numbers.

| Scenario | What it demonstrates |
|---|---|
| `agentic_hold` | A financial action is stopped while the text is still allowed to stream |
| `alert_fatigue` | Precision against loss averted — why a higher-precision policy can be worse |
| `budget_shock` | A 40% mid-stream cut: shadow price rises, spend falls, floor coverage does not move |
| `drift` | A new failure mode appears that calibration has not seen |
| `jurisdiction_switch` | The same request under EU and India policy packs |
| `multi_turn_session` | Risk accumulating across a session rather than a single turn |
| `no_ground_truth` | Nothing can confirm or refute the answer, so the system abstains |
| `overlapping_harm` | Several harm axes fire at once; expected loss sums rather than taking the max |
| `same_response_three_routes` | Identical text, three routes, three different verdicts |

The two worth showing under time pressure are **`budget_shock`** (the floor holds while everything
else gives way) and **`same_response_three_routes`** (the same words are worth different amounts of
checking depending on where they were said).

---

## 4. Decision lab — the only view that computes something new

Everything else reads committed artifacts. This view runs the live engine on text you type.

The form takes a route (`support-assistant`, `internal-kb`, `finops-agent`), a jurisdiction (`eu`,
`india`), a prompt, a model response, and a grounding context. It ships with a worked example: the
context says the renewal fee is ₹499 and refunds run 14 days, and the response claims ₹9,999 and 90
days.

Press **Run decision** and you get:

- a colour-coded verdict badge — allow, annotate, abstain, hold or block — with the reason
- four metrics: expected loss, assurance spend, selected tier, and whether the floor forced the check
- **Calibrated harm** — probability per harm axis, as bars
- **What each tier was worth** — benefit, priced cost and net value for every tier, with the chosen
  one marked. This is the allocator's arithmetic laid out; you can read off *why* it stopped where it
  did.
- the full decision record in an expander

**The one thing to try live:** change the route to `finops-agent` and run the same text again. The
consequence table changes, so the same words become worth more checking and the verdict escalates.
Nothing about the text changed — only what it would cost to be wrong.

Every run appends to the hash chain, which sets up the next view.

---

## 5. Audit ledger — proving nothing was edited

A banner reports whether the chain verifies and across how many records. Below it, the most recent
50 records, and a selector to inspect any single record as JSON.

Each record is hashed together with the hash of the record before it, so altering any earlier row
invalidates every hash that follows.

> **On a fresh clone or a fresh cloud deploy this view starts empty.** `data/audit.db` is
> gitignored, so it does not travel with the repository. Either run `make demo` to populate 1,500
> decisions, or — better for a demo — run a check in the Decision lab first and then open this view
> to watch that decision appear at the end of the chain.

---

## Known behaviour worth expecting

- **First paint is slow, everything after is fast.** The engine calibrates on 1,500 rows on first
  load. Subsequent view switches are cached.
- **The sidebar budget slider does not affect the Decision lab or the Audit ledger.** Those two run
  against the live engine and the chain, not the swept evaluation.
- **The theme is fixed** in `.streamlit/config.toml` — purple `#A100FF` on white.
- **The state is single-process.** The console holds one engine and one SQLite connection. It is an
  inspection surface for one person at a time, not a multi-tenant dashboard.
