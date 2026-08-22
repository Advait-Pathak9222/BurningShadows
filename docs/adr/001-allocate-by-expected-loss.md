# ADR 001: Allocate checks by expected avoided loss

- Status: accepted for experiment
- Date: 2026-08-22

## Context

A fixed risk threshold ignores that the same detector score has different consequences in an
internal draft and a financial action. Checking all traffic removes the decision but violates the
budget premise.

## Decision

Rank optional checks by the sum of calibrated harm probability, route consequence, and tier catch
rate, then compare that benefit with shadow-priced check and delay cost. Keep every term in the trace.

## Rejected alternative

We tested fixed top-score selection as the equal-spend baseline. It sometimes beats the allocator on
the seeded curve, including at 60% budget. We retain it as the benchmark instead of claiming the
economic rule is settled.

## Consequences

Route economics can change coverage without changing the detector. The method is only as credible as
`c` and `k`, so sensitivity and labelled shadow traffic are production prerequisites.
