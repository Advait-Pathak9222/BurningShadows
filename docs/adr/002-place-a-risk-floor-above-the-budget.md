# ADR 002: Place a risk floor above the budget

- Status: accepted
- Date: 2026-08-22

## Context

An economics-only rule can price out a serious check when the budget tightens or a consequence input
is wrong. A hard percentage floor has no statistical interpretation and does not adapt by route.

## Decision

Use a finite score grid and family-wise corrected exact-binomial upper bounds on a separate route
calibration split. Any response at or above the selected threshold receives verification regardless
of shadow price.

## Rejected alternative

A raw score threshold was simpler but could not state a release-loss bound. A first Hoeffding bound
was needlessly loose on 100-row route samples, so the implementation uses a one-sided exact-binomial
bound for each tested threshold.

## Consequences

The floor can exceed the budget. That state is reported as positive budget variance. Exchangeability
and label-definition limits are recorded in `LIMITATIONS.md`.
