# Scope proposal and delivered cut

## Must

- OpenAI-shaped FastAPI gateway with a deterministic offline provider.
- Versioned EU and India policy packs with route resolution and content hashes.
- Three detector tiers behind one adapter contract; Tier 2 runs only when selected.
- Five-axis harm vector and three evidence regimes.
- Readable expected-loss allocator and non-negative shadow-price controller.
- Per-route finite-sample guarantee floor.
- Effect classification and blocking for financial or irreversible actions.
- Hash-chained SQLite audit ledger.
- Seeded 600-interaction corpus with calibration/test separation and late shift.
- Eight named scenarios, three baselines, metrics, report, and console.
- Tests for mathematical invariants, scenarios, gateway, and ledger tampering.

## Should

- A real Presidio adapter and one local NLI adapter behind optional extras.
- Reliability plots for each harm axis and route, not only aggregate ECE helpers.
- Reviewer queue persistence and override workflow.
- Consequence-range sensitivity chart.
- A stable windowed controller with anti-windup and alerting when the floor alone exceeds budget.

## Could

- LiteLLM or Bifrost integration instead of owning the full gateway surface.
- A real provider adapter and streaming benchmark harness.
- Signed policy releases and external append-only ledger storage.
- Conversation-level risk persistence across multiple gateway workers.

## Brief changes I would make

1. Replace "escaped harm <= alpha" with a precisely defined loss, population, time window, and treatment of abstentions. Otherwise the claim can be gamed by not releasing uncertain cases.
2. Do not promise distribution-shift safety from a standard conformal calibration. The finite-sample guarantee needs exchangeability; the drift path is monitoring and recalibration.
3. Split text safety from effect safety. Streaming protects latency but exposes text before an asynchronous verdict. High-consequence text routes still need blocking output checks.
4. Treat the budget controller as a control-system design, not one update equation. A production controller needs windows, caps, anti-windup, and an infeasibility state.
5. Do not say allocation is uncontested whitespace. Portkey and gateways already have routing, budgets, and guardrail orchestration. The narrower claim is risk-bounded, expected-loss allocation with a trace that can be tested.
6. Keep synthetic data for the no-key demo, but do not use it as detector evidence. External benchmark evaluation is a separate milestone.

## Result of the current cut

The build covers the must list with deterministic stubs. Its evaluation is intentionally not a victory lap: the allocator wins at some equal-spend points and loses at others. The kill criterion remains open. That result is more useful for Round 2 than an unqualified dominance claim.

