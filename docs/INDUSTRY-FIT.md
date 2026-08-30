# Is the offline version enough for industry, or is an API-based version required?

Short answer: **it is a hybrid, and deciding when to make the API call is the product.**

The question assumes offline and API-based are two competing versions of ControlPlane. They are not.
They are two of the tiers, and the allocator's entire job is choosing between them per request.

---

## First, three different "offline" claims get conflated

| Claim | True? |
|---|---|
| The **gateway** runs offline | **No.** It sits in the request path of an API-served model. It is networked by definition. |
| The **detectors** are offline stubs | **Yes** — Tier 2 is a deterministic stand-in, and this is the real question. |
| The **evaluation** runs offline | **Yes, deliberately.** |

Only the second one is a product question. The third is a methodology choice, and it is defensible
on its own terms: if we ran a frontier model as our judge and posted good numbers, no reader could
tell whether our *allocator* was good or whether the vendor's model was. Freezing detector quality is
what makes the measured gain attributable to allocation. It also means the numbers reproduce exactly
on a judge's laptop, which is not true of any demo built on a live API.

---

## Tier by tier: what has to be local, and what should be a network call

From `config/economics.yaml`:

| Tier | Cost | Latency | Runs on | Should it be an API call? |
|---|---:|---:|---|---|
| **0** — rules, patterns, secrets scanning | ₹0.02 | 4 ms | every request | **No.** It runs on 100% of traffic. A network hop here would cost more than everything it guards. |
| **1** — lexical and grounding signals | ₹0.18 | 70 ms | most requests | **Usually not.** Self-hosted embeddings are cheaper than a hosted API at enterprise volume. |
| **2** — the expensive judge | ₹3.20 | 900 ms | a selected minority | **Yes. This is where an LLM API belongs.** |

Tier 2 costs **160× Tier 0** and adds **225× the latency**. That gap is not an accident of our
configuration — it is the real shape of the problem, and it is precisely why the allocation question
exists at all. If judging were cheap, nobody would need us.

---

## Why "call the API on everything" is the position this project argues against

Running the LLM judge on all traffic is the `check_all` policy, and we measured it:

| Policy | Compute spend | Loss averted | Share of check_all's benefit | Share of its cost |
|---|---:|---:|---:|---:|
| `check_all` | ₹4,800.00 | ₹5,469,400 | 100% | 100% |
| allocator @ 10% budget | **₹480.98** | ₹5,078,000 | **92.8%** | **10.0%** |
| allocator @ 25% budget | ₹1,098.58 | ₹5,407,000 | 98.9% | **22.9%** |
| allocator @ 80% budget | ₹3,839.64 | ₹5,477,300 | **100.1%** | **80.0%** |

**93% of the benefit for 10% of the spend.** And at the 80% budget the allocator does not merely
approach checking everything — it beats it, averting more loss for 20% less compute, because
`check_all` spends its Tier 2 budget on rows where the judge had nothing to find.

The cost argument is the smaller half. The larger half is **latency**: Tier 2 is 900 ms. Running it
on every request adds 900 ms to every answer, which is a product-killing regression regardless of
what it costs. And `config/economics.yaml` prices that delay by effect class —
`financial: 0.0010` per ms, so a 900 ms judge on a payment action costs **₹0.90 in delay alone**,
on top of the ₹3.20 to run it.

An API-first guardrail therefore fails on the project's own premise: it costs more than the
assistant it guards, and it makes the assistant slow. The allocator exists to buy that call only
where it pays.

---

## The API path is already built, not hypothetical

This is worth stating plainly, because "it's only a stub" understates what is in the repository.

- **`controlplane/detectors/base.py`** defines a narrow adapter contract — `run(interaction) ->
  DetectorSignal`. Any detector that satisfies it drops in. Swapping is an interface implementation,
  not a rewrite.
- **`controlplane/detectors/tier2_judge.py`** is the deterministic stand-in, and its own evidence
  string says so: *"deterministic judge stub; replace through the Detector adapter."*
- **`controlplane/detectors/ollama_judge.py`** is a working adapter against a real local LLM over
  HTTP, with span-level prompting and a documented failure mode discovered in testing (the model
  returned `injection_or_exfl` for `injection_or_exfil`, so the prompt uses short axis keys).
- **`controlplane/detectors/presidio_pii.py`** adapts Microsoft Presidio, a real third-party
  detector, behind the same contract.

The allocator never needs to know what a tier *is*. It needs three numbers per tier: cost, catch
rate, latency. Swap the detector, supply the three numbers, and the arithmetic is unchanged.

And the catch rate is not left as a guess. `controlplane/feedback/recalibration.py` holds a
`BetaBinomialCatchRate` that updates from labelled outcomes, which is how the measured Tier 2 catch
rate of **0.950** was recovered against the **0.880** configured, over 398 observations. **Plug in a
better detector and it self-reports its higher catch rate, and the allocator automatically buys more
of it.** That is the property that makes the detector question genuinely orthogonal.

---

## Where offline is a hard requirement rather than a limitation

For a meaningful share of the Indian enterprise market, a guardrail that ships text to a third-party
API is not a preference to be weighed — it is unlicensable:

- **Banking and insurance** under RBI data-localisation direction.
- **Anything under the DPDP Act** where the disclosure itself is the regulated event — note that
  sending a suspected PII leak to an external judge *is* an act of disclosure.
- **Healthcare, defence, government**, and air-gapped deployments generally.

The gateway needs no model weights, hidden states, or log-probabilities, so it works in front of a
vendor model you do not control *and* in front of a self-hosted one. That is a deployment advantage
in exactly the accounts where guardrail vendors struggle.

---

## What genuinely has to change before an enterprise deployment

Being straight about this is more useful than claiming readiness.

| Gap | Severity | Notes |
|---|---|---|
| Tier 2 is a stub | Medium | The adapter exists; a production judge must be built and its catch rate re-measured. The feedback loop handles the re-measurement. |
| Calibration is fit on synthetic traffic | **High** | Isotonic calibrators and the per-route release thresholds do not transfer. Needs roughly 500 labelled rows per route — about four weeks of one reviewer. |
| Consequence table needs Finance sign-off | Low | Sensitivity across a 0.25×–4× band moves 10.9% of tier decisions and flips **0%** of verdicts. Getting it wrong costs money, not safety. |
| Drift breaks the bound silently | **High** | The finite-sample guarantee is valid only for the distribution it was calibrated on. Production needs a drift detector triggering recalibration. Not built. |
| Single-process state | Medium | The ledger and budget controller assume one process. Multi-worker needs shared state. |

---

## The answer

**Offline is sufficient for the benchmark and necessary for part of the market. An API-based Tier 2
is the right production default everywhere else — and ControlPlane is the layer that decides when to
make that call.**

The honest framing for an interview: we are not competing with LLM judges, and we are not avoiding
them. We are the economic layer above them. An enterprise buys the allocation and audit machinery
and plugs in whichever detectors their regulator, budget and latency envelope allow — which is why
the question "offline or API?" is one our architecture is designed to answer per request, at
runtime, rather than once, at procurement.
