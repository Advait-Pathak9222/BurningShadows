# ADR 005: Use a local hash-chained ledger

- Status: accepted for prototype
- Date: 2026-08-22

## Context

The decision needs policy and economic terms that can be checked after an incident. A plain log row
does not reveal editing. An external immutable store would add infrastructure that the requested
architecture and offline demo do not need.

## Decision

Append canonical decision JSON to SQLite with the previous record hash and a SHA-256 record hash.
Provide a verifier and a tampering test. Store policy version and content hash inside the trace.

## Rejected alternative

A JSONL audit log was readable but weak under concurrent append and query. A hosted ledger broke the
no-network run and added a service beyond the architecture map.

## Consequences

Edits inside the chain are detectable. Deletion, database rollback, full replacement, identity, and
durable replication are unsolved. Production needs an external append-only sink and signed releases.
