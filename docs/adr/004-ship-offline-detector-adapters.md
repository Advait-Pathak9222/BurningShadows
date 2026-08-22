# ADR 004: Ship offline detector adapters

- Status: accepted for competition build
- Date: 2026-08-22

## Context

Judges must run the repository without an API key, network, GPU, or model download. A real local NLI
model would improve grounding evidence but makes first-run reliability and package size worse.

## Decision

Ship deterministic Tier 0, lexical Tier 1, and judge-stub Tier 2 implementations behind a named
detector contract. Keep real Presidio and transformer packages in an optional extra and do not use
their results in the checked-in report.

## Rejected alternative

Downloading a model on first run violated the offline requirement and made benchmark provenance
unclear. Claiming the lexical stub represented MiniCheck accuracy was also rejected.

## Consequences

The system path is executable and repeatable, but detector quality is not validated. The next pilot
must replace adapters and regenerate every metric under a labelled external evaluation.
