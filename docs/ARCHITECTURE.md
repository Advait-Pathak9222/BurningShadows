# Architecture and component contracts

The build follows the Round 1 architecture without adding an external service. All decisions use
only request, response, context, samples, and proposed tool calls. No path requires model weights,
hidden states, or log probabilities.

```mermaid
flowchart TD
    A[AI use case] --> B[OpenAI-shaped gateway]
    B --> Q{Per-route admission}
    Q -->|normal| C[Blocking preflight]
    Q -->|mandatory only| C
    Q -->|both lanes full| X[503 before generation]
    C --> D[Seeded or adapted model provider]
    D -. text streams .-> U[User]
    D --> E0[Tier 0 rules]
    E0 --> E1[Tier 1 small-model adapter]
    E1 --> E2[Tier 2 judge when selected]
    E0 --> F[Calibrated harm vector and evidence regime]
    E1 --> F
    E2 --> F
    P[Versioned jurisdiction policy] --> C
    P --> H[Allocator]
    G[Consequence, catch, check and delay costs] --> H
    F --> H
    R[Per-route conformal floor] --> H
    H --> V{Verdict}
    V --> U
    V --> K[Effect gate]
    H --> L[Hash-chained ledger]
    K --> L
    L --> N[Feedback and recalibration inputs]
```

## Runtime sequence

1. A per-route token bucket admits the request to a bounded discretionary lane. If that lane is
   rate-limited, queued, or full, a separately bounded lane reserves capacity for mandatory checks.
   Exhausting both lanes returns 503 before provider generation.
2. The gateway resolves route and jurisdiction, loads the policy from YAML, and runs Tier 0 over the
   prompt. A high-confidence injection phrase stops the request before generation.
3. The provider produces text. For a streaming request, token events are emitted while assessment
   runs in a worker thread.
4. Tier 0 checks patterns and context numbers. Tier 1 supplies replaceable grounding, safety, and
   anomaly signals. The seeded build uses lexical adapters so it remains offline.
5. Route-specific isotonic maps transform each harm axis. The evidence regime is grounded,
   ungrounded-but-estimable, or unverifiable.
6. A per-route exact-binomial Learn-Then-Test threshold identifies mandatory checks. When the
   request carries a session id, risk accumulated from earlier turns is deducted from that
   threshold, so history can only make a check mandatory and never optional. The economic
   rule prices each tier with the current shadow price. If Tier 2 is selected, its signal is added and
   the allocation is recomputed. Degraded admission derives a cut line from the same benefit and
   cost terms so discretionary escalation is skipped while a conformal override still selects Tier 1.
7. Text receives allow, annotate, abstain, hold, or block. Financial, irreversible, and configured
   external effects are held or denied independently of text delivery.
8. The ledger appends the full decision terms with a previous-record hash, policy version, and policy
   content hash.

## Code contracts

| Component | Input | Output | Prototype file |
| --- | --- | --- | --- |
| Gateway | OpenAI-shaped request and route header | JSON or SSE text plus decision | `controlplane/gateway/app.py` |
| Admission | Route and configured limits | Normal/degraded lease or explicit overload | `controlplane/runtime/admission.py` |
| Policy | Route and jurisdiction | Validated route policy, version, content hash | `controlplane/policy/loader.py` |
| Tier 0 | Prompt, response, context | Pattern, numeric, PII, and injection scores | `controlplane/detectors/tier0_rules.py` |
| Tier 1 | Response, evidence, samples | Grounding, bias, safety, anomaly scores | `controlplane/detectors/tier1_models.py` |
| Tier 2 | Response and context | Escalated judge scores | `controlplane/detectors/tier2_judge.py` |
| Risk | Detector signals | Five-axis calibrated vector and evidence regime | `controlplane/risk/` |
| Cost | Policy and effect class | Per-tier `c`, `k`, `v`, and `d` terms | `controlplane/economics/cost_model.py` |
| Guarantee | Calibration score/label pairs | Route release threshold and upper bound | `controlplane/guarantees/conformal.py` |
| Allocator | Risk, costs, lambda, floor | Tier, verdict, and arithmetic trace | `controlplane/economics/allocator.py` |
| Effect gate | Tool calls, verdict, policy | Permit, hold, or deny per effect | `controlplane/effects/effect_gate.py` |
| Ledger | Decision trace | SQLite row linked by hashes | `controlplane/ledger/store.py` |
| Refit | Chain scores joined to reviewer labels | A versioned calibration artifact, or a refusal with its reason | `controlplane/learning/refit.py` |

## State and failure boundaries

Policy files are checked for modification on resolution and reloaded in-process. Calibration maps and
the budget controller are process-local in this prototype. Token buckets, queue counters, and
reserved lanes are also process-local, so limits multiply if several gateway workers are started.
The SQLite ledger is local and its append is synchronous. A production multi-worker deployment
would need shared calibration versions, distributed admission state, a windowed controller, durable
queues, identity, and an external append-only audit sink. Those are deployment changes, not new
decision stages.
