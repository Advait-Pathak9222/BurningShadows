# Phase 0 assessment

## Steelman of the thesis

Enterprise AI assurance is usually sold as a detection problem: add a better safety classifier, a stronger factuality check, or another policy filter. That framing misses the operating decision. A reliable check consumes money and time, and the loss from a missed error varies sharply by route. Re-reading an internal draft and validating a payment instruction should not receive the same assurance spend merely because their detector scores match. ControlPlane treats verification as a scarce resource. Each response receives an overlapping harm vector, route-specific consequence estimates, measured checker catch rates, and a priced verification option. A controller converts the hourly assurance budget into a shadow price, so checking expands when capacity is cheap and contracts toward the highest expected-loss traffic when the budget tightens.

Economics alone is too permissive for a safety control. A per-route finite-sample risk test therefore creates a minimum verification floor before the allocator spends any discretionary budget. The model output can stream while verification runs, but irreversible effects remain held. When neither source evidence nor repeated-sample disagreement is available, the system abstains instead of inventing certainty. The idea does not require access to model weights or logits and can compose with existing safety products. Its claim is deliberately narrow: detectors need to rank risk well enough for a budget to allocate checks; they do not need to become final judges.

## Strongest objections

### 1. "You are just a router in front of existing guardrails. Where is the moat?"

That is partly true at the gateway layer. Routing, retries, and policy hooks are already offered by LiteLLM, Portkey, Bifrost, and cloud platforms. The differentiator must be the decision record and its learning loop: route-specific calibrated harm, cost, catch-rate posteriors, finite-sample floors, and a budget dual that can be evaluated against equal-spend baselines. If those pieces are only configuration labels, there is no moat. The defensible asset would be each tenant's accumulated calibration, incident-cost, override, and shadow-mode outcome history.

### 2. "Your `c` values are made up. Enterprises cannot price a hallucination."

The prototype's values are assumptions, not findings. Production onboarding should start with ranges and decision classes rather than a false point estimate: remediation labour, customer compensation, regulatory exposure, transaction value, and reversibility. Sensitivity analysis must show whether a decision changes across the range. If small changes to `c` flip most decisions, the product is not ready for unattended use. The ledger exposes every term so Finance and Risk can challenge it.

### 3. "If your detector is unreliable, an economic rule built on it is unreliable too."

Correct. Calibration cannot create information that a detector lacks. The system measures reliability and catch rate on held-out labels, carries a beta-binomial estimate for `k`, and adds a guarantee floor. The current guarantee is only valid under exchangeability between calibration and deployment data. Drift breaks that premise; the response is detection, shadow labels, and recalibration, not a claim that conformal methods solve drift.

### 4. "Parallel checking does not help when the answer is wrong and already streamed."

This objection holds for harmful text. The effect gate prevents a transfer, write, or external message from firing, but it cannot make already-read text unseen. Text routes still need pre-release blocking where the consequence demands it. The prototype reports text latency and effect latency separately and does not claim that parallel verification removes textual exposure.

### 5. "Regulators want consistent controls, not controls that switch off when the budget runs out."

The conformal floor is intended to preserve a consistent minimum. The budget only controls checks above it. This works only if the risk target, calibration population, and release definition are accepted and monitored. A very small route sample can make the floor so conservative that it consumes the entire budget. In that case the controller must report infeasibility; it must not silently weaken the floor.

## Kill criteria

The thesis is falsified for this prototype if the allocator's loss-averted-per-rupee does not exceed the fixed-rate baseline at equal spend across the scenario set. The current seeded test is a partial result: allocation improves loss averted at some budgets but does not dominate at every budget. That is a failed full-strength claim and a reason to test on larger, less templated data before pitching dominance.

Additional stop conditions are:

- conformal upper bounds exceed the declared route alpha on held-out data;
- more than 1% of proposed effects lack an audit record;
- raising the shadow price increases coverage;
- the budget shock drops mandatory conformal checks;
- route consequence ranges are so uncertain that more than 20% of decisions flip in sensitivity analysis;
- p99 text overhead exceeds the route SLO in the offline path.

