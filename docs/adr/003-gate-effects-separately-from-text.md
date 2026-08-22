# ADR 003: Gate effects separately from text

- Status: accepted with route exception
- Date: 2026-08-22

## Context

Blocking every response until an LLM judge returns damages conversational latency. Streaming every
response and tool call creates unacceptable action risk.

## Decision

Run response verification beside streaming and classify each proposed tool call by reversibility and
blast radius. Hold financial and irreversible effects until the verdict permits them. Keep text and
effect latency as separate metrics.

## Rejected alternative

One global blocking pipeline met effect safety but made the cheap support path pay Tier 2 latency.
The opposite streaming-only path failed the Acme transfer scenario because the transaction could fire
before assessment.

## Consequences

Financial actions can be contained without adding judge latency to first token. Harmful text can still
reach a user, so high-consequence text routes must configure a blocking output stage in production.
