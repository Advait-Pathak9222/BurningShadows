# ControlPlane — five-minute pitch script

Team BurningShadows · Accenture Innovation Challenge 2026 · Track 1, Responsible AI Checker

This is a **navigation script**: what is on screen at every moment, what to click, what to say, and
what to do when something misbehaves. Times are cumulative against a 5:00 budget.

---

## Before you start — the ten-minute setup

Do this **before** you are in the room, not while the judges watch.

```bash
cd BurningShadows
make report                 # pre-builds artifacts so the console opens in ~3s, not ~18s
.venv/Scripts/python.exe -m streamlit run console/streamlit_app.py
```

Then **run one Decision lab check and leave it there.** This does two things: it proves the engine
is warm, and it seeds the audit chain so the ledger view is not empty. Reset the form afterwards.

**Browser tabs, left to right, in this order.** Muscle memory matters more than you think when you
are nervous — you want to move by tab position, never by typing a URL.

| # | Tab | URL |
|---|---|---|
| 1 | Landing page | your `*.vercel.app` deployment |
| 2 | Console — Decision lab | `http://localhost:8501` |
| 3 | Console — Overview | `http://localhost:8501` *(second window, on Overview)* |
| 4 | Repository | `https://github.com/Advait-Pathak9222/BurningShadows` |

Two console tabs is deliberate. Switching views inside Streamlit costs a second of re-render and
breaks your rhythm; switching browser tabs is instant.

**Checklist:**

- [ ] `make report` has been run — console opens fast
- [ ] One Decision lab check already run, so the ledger has records
- [ ] Notifications silenced, screen at 125–150% zoom (judges are reading tables from a distance)
- [ ] Laptop plugged in, terminal window kept open but behind the browser
- [ ] `docs/images/architecture.png` open in an image viewer as a fallback if the site is slow

---

## The script

### 0:00 – 0:30 · The problem
**Screen: Tab 1, landing page, top of hero.**

> "Every enterprise deploying an AI assistant hits the same wall. You cannot check every answer —
> thorough checking costs more than the AI itself. So what almost everyone does is sample: check 5%
> at random. Which means you spend exactly the same effort on *'what are your opening hours'* as you
> do on a payment instruction.
>
> That is not a safety strategy. That is a coin flip with a budget attached."

*Do not scroll yet. Let the headline sit.*

---

### 0:30 – 0:55 · The reframe
**Screen: Tab 1, scroll to the "The reframe" card and the formula.**

> "Our claim is that the industry has been asking the wrong question. Everyone asks *'is this answer
> harmful?'* — a detection problem, with no budget attached. We ask *'is checking this answer worth
> what it costs?'* That is an allocation problem. And allocation problems have optimal solutions.
>
> So we price it." *(point at the formula)* "Expected loss is calibrated risk times consequence. We
> buy a check when the loss it prevents exceeds what it costs — where lambda is the shadow price of
> the budget, and it rises as the budget tightens."

*One sentence on the floor, because a judge will ask:*

> "And underneath all of it there is a per-route safety floor that the budget cannot override. Some
> checks are mandatory no matter how expensive the money gets."

---

### 0:55 – 2:10 · Watch it decide, then watch it prove
**Screen: Tab 2, console, Decision lab. This is the heart of the pitch — do not rush it.**

The form is pre-filled. Read it out:

> "Here is one request. The grounding document says the renewal fee is ₹499 and refunds run 14 days.
> The model has answered ₹9,999 and 90 days. It is confidently wrong."

**Click `Run decision`.**

> "Verdict, with the reason. Expected loss. What we spent. Which tier we selected — and whether the
> floor forced it."

**Point at "What each tier was worth".**

> "This is the part I would ask you to look at. That is the allocator's arithmetic, exposed. For
> every tier: what it would have been worth, what it cost once the shadow price is applied, and the
> net. You can read off *why* it stopped where it did. There is no model in this decision you have
> to trust — it is arithmetic you can check."

**Now the move that lands it. Change Route to `finops-agent`. Run again.**

> "Same words. Same text, character for character. Different route — so a different consequence
> table. And the verdict escalates.
>
> Nothing about the language changed. What changed is what it would cost to be wrong. That is the
> whole thesis in one click."

**Switch to Audit ledger.**

> "And the decision I just made in front of you is now the last record in a hash chain. Every record
> is hashed with the hash of the one before it, so editing any earlier row breaks every hash that
> follows. Fifteen hundred decisions, one valid chain. When a regulator asks why this answer was
> released in March, the answer is not a log line — it is a record you can re-derive the arithmetic
> from."

---

### 2:10 – 3:10 · Where the money actually goes
**Screen: Tab 3, console, Overview.**

**Point at the fourth metric, "Attention share of cost".**

> "Now the finding we did not expect. A completed human review costs ₹120. Our most expensive
> automated check costs ₹3.20. That is a 37.5× gap — and once you count both, human review is between
> 81 and 98 percent of what assurance actually costs."

**Drag the budget slider from 10% to 100%. Let them watch the number move.**

> "It never goes below 80. The compute budget that every vendor in this space competes on is a
> rounding error next to the salary cost of the people you escalate to."

**Switch to Reviewer queue.**

> "Which changes what the problem even is. If reviewer time is the cost and capacity is fixed, the
> lever is not *how much* you check — it is *whose case gets served first*. Same capacity, same
> cases, five different serving rules. Ours serves 1.57× the expected loss that first-in-first-out
> does from the same 166 reviews."

**Point at the `density` row. Do not skip this.**

> "And here is a row I want to draw your attention to rather than hide. `density` is our own rule
> with one term removed — and it beats what we shipped, on both axes. It is in the default view of
> our own console. We would rather be caught reporting it than caught hiding it."

---

### 3:10 – 3:50 · Authorisation beats recognition
**Screen: Tab 1, landing page, scroll to Finding 2.**

> "One more. Our first PII detector scored 0.5881 AUC — barely better than a coin. Instead of
> tuning it, we measured the ceiling: how well could a *perfect* pattern detector possibly do on
> this data? 0.5869. Pattern matching had nothing left to give."

**Point at the 2×2.**

> "Because 309 rows carry a real identifier inside a *permitted* disclosure — a support agent
> reading a customer their own address. And 57 genuine leaks contain no recognisable pattern at all.
> Any shape-based detector must get both wrong. Microsoft Presidio scores 0.5825 here and flags
> 1,044 rows out of 1,500 — it is not broken, it is answering a different question."

> "So we changed the question. Not *does this look like personal data*, but *is this disclosure
> grounded in the source this requester was authorised to see*. 0.9879, at precision 1.0, flagging
> 72 rows instead of 1,044."

---

### 3:50 – 4:25 · Why you can believe any of this
**Screen: Tab 4, the repository README.**

> "Everything I have shown you regenerates from one command on your machine. No API key, no network
> call, no GPU — so you get the same numbers we did, which is not true of any demo built on a
> vendor API.
>
> Every significant claim has a pre-registration written *before* the run, stating what would count
> as success. We report against it whether or not we met it. There is a queue-model defect in there
> that we recorded before we fixed it, and the ablation you just saw that beats our own shipped
> rule."

> "183 tests, strict type checking, and an assumptions register that lists every input we could not
> measure along with where it came from."

---

### 4:25 – 5:00 · The close
**Screen: Tab 1, landing page, back to the top.**

> "So: ControlPlane is not another guardrail model. It is the layer that decides *when it is worth
> running one* — and proves what it decided.
>
> The mechanism transfers to any enterprise today. Three of the six inputs it needs — check cost,
> reviewer cost, delay cost — are on a finance dashboard already. The consequence table needs a
> sign-off conversation. The catch rates it measures and corrects itself. The only genuinely new
> thing an enterprise has to produce is about 500 labelled rows per route — roughly four weeks of
> one person.
>
> What we would want next is exactly what we could not get in a hackathon: a real corpus. Everything
> else is built."

---

## If something goes wrong

| Failure | Do this |
|---|---|
| Streamlit is slow or hangs | Do not wait. Switch to Tab 1 — the landing page has the same tables. Say "the console is doing a cold calibration, here are the same numbers" and continue. |
| Streamlit is dead | `Ctrl+C` in the terminal, relaunch. Meanwhile keep talking over Tab 1. Never debug on camera. |
| Decision lab returns something unexpected | Say so. "That is a different verdict than I expected — the arithmetic is on screen, let me read it." Reading your own trace out loud *is* the demo. |
| Audit ledger is empty | You skipped the setup step. Run one Decision lab check now and come back — it takes four seconds and demonstrates the append live. |
| No internet | Everything except Tab 1 is local. The whole demo survives. Say it out loud: "this is running entirely on this laptop." |
| You are running long at 3:10 | Cut the PII section to one sentence: "we also found that authorisation beats recognition — 0.59 to 0.99 AUC, it's on the site." Go straight to the close. |

---

## Questions you should expect

**"It's fully offline and uses no API — is that not a limitation?"**
> Offline is a property of our *evidence*, not the product. ControlPlane is a gateway; in production
> it sits in front of a model API and Tier 2 is designed to be an LLM-judge API call. What is
> offline is the committed benchmark, and that is deliberate: if we ran a frontier model as our
> judge and got good numbers, you could not tell whether our allocator was good or whether the
> vendor's model was. Freezing detector quality is what makes the measured gain attributable to
> allocation. It also means you reproduce our numbers exactly. And for banks and hospitals under
> data-residency rules, a guardrail that ships text to a third party is often the one thing they
> cannot buy.

**"Why not just use an LLM judge on everything?"**
> Because that costs more than the assistant it is guarding. That is the premise of the whole
> project. We are the layer that decides when an LLM judge is worth calling.

**"Your numbers are synthetic."**
> Yes, and that is stated on the front page and in `docs/LIMITATIONS.md`. The rupee amounts describe
> this implementation and its assumptions. What transfers is the mechanism and the sensitivity
> result: across a 0.25×–4× band on the consequence table, 15.8% of tier decisions change and the
> verdict flip rate is 0%. Getting the consequence table wrong costs you money, not safety.

**"What happens when the traffic drifts?"**
> That is a real gap and it is written down. The finite-sample bound is valid for the distribution
> it was calibrated on; drift breaks it silently. The `drift` scenario shows the failure mode. The
> honest answer is that production needs a drift detector triggering recalibration, and we have not
> built it.

**"How is this different from Guardrails / NeMo / Presidio?"**
> Those are detectors. We measured Presidio directly — it is on the site. It is good at what it
> does. None of them price a check against a budget, and none of them produce a record you can
> re-derive a decision from. We are not competing with them; we decide when to call them.

**"Why should a shadow price beat a well-tuned threshold?"**
> At six of six budgets it averts more loss than a tuned fixed-rate policy, and at the 80% and 100%
> budgets it beats checking *everything* — more loss averted for 28% less compute. But be careful
> with this one: the margins over the tuned baseline are 0.4–3.6%, which is honest but not dramatic,
> and we say so.

---

## The three sentences, if you get thirty seconds instead of five minutes

> "Checking every AI answer costs more than the AI. So we stopped treating responsible AI as a
> detection problem and started treating it as an allocation problem: price the damage of each answer
> being wrong, and buy checking only where it pays — under a safety floor the budget cannot override.
>
> Doing that surfaced something we did not expect: 85 to 97 percent of assurance cost is human
> review, not compute, which means the real lever is which case a reviewer sees first.
>
> Every number regenerates offline from one command, and every decision is in a hash chain you can
> re-derive."
