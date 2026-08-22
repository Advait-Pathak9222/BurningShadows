# Limitations

## What is simulated

- The default model returns seeded text and never calls an external API.
- Tier 1 is lexical rather than MiniCheck, NLI, or a hosted groundedness model. Tier 2 is a
  deterministic judge stub.
- Consequence amounts, check prices, delay prices, tier latency, and initial catch rates are scenario
  assumptions from YAML. They are not customer measurements or vendor prices.
- The 600 rows are generated from a small set of templates. The reported loss, precision, escape,
  latency, and ROI values describe those templates only.
- Catch outcomes in the evaluator are deterministic pseudo-random draws from assumed `k`; they are
  not observed detector catches.

## What the experiment proves and does not prove

The experiment proves that the code composes a route risk floor with expected-loss allocation,
preserves effects under a budget shock, emits repeatable records, and can be compared at equal spend.
It does not prove that economic allocation reduces real incidents.

The strongest claim fails on the current curve. The allocator wins at the 40% point, loses at 60%,
and ties elsewhere. Its precision at 40% is also slightly below fixed-rate. Larger and less templated
external evaluations are required before claiming dominance. The synthetic loss scale makes ROI look
large and must not appear in a customer business case without measured consequence ranges.

The evaluator counts one audit decision for every effect-bearing evaluation row. The scenario path
also writes and verifies the SQLite hash chain. This demonstrates code coverage, not operational log
delivery under crashes, queue loss, or multi-worker concurrency.

## Guarantee limits

The finite-grid exact-binomial test assumes calibration examples and deployment traffic are
exchangeable and labels implement the same escaped-harm definition. Drift, route mixing, selective
labels, delayed outcomes, or policy changes can invalidate the bound. The Bonferroni correction covers
the tested threshold grid, not arbitrary future thresholds.

An upper bound at or below alpha is a statement about the defined release loss under those conditions.
It is not a guarantee that each response is safe. With only 100 calibration rows per route, the floor
is conservative and can cost more than the stated budget. The budget variance in low-budget report
rows exposes that infeasibility instead of weakening the floor.

## Safety gaps

- Streaming verification cannot retract harmful text already shown. Only input injection is blocked
  before generation in the current gateway. Routes with high textual consequence need a blocking
  output check.
- Lexical grounding misses paraphrases, multi-hop errors, table reasoning, date logic, and consistent
  falsehoods. The new shifted injection phrase is missed deliberately to exercise drift handling.
- Regex PII rules miss many identifiers, languages, and contextual disclosures and can flag benign
  account-like text.
- Harm axes are summed. Correlated consequences may be double counted, while unmodelled harms receive
  zero economic weight.
- The unverifiable path abstains but does not yet rewrite the answer or persist a human review queue.
- Conversation risk accumulation exists as a local component but is not stored across gateway workers.

## Operational gaps

There is no tenant authentication, authorization, rate limiting, consent capture, reviewer identity,
case-management integration, key service, or signed policy release. SQLite hash chaining makes edits
detectable after the first changed row; it does not stop deletion, rollback, or replacement of the
whole database. Ledger appends are synchronous, so the component contract's future asynchronous sink
is not represented.

Policy files contain a legal-control mapping, not legal advice or a compliance determination. Dates
were checked against official sources on 22 August 2026, but a production release needs counsel review
and effective-date handling.

## Next evidence needed

1. Evaluate grounded factuality on gated LLM-AggreFact without training leakage.
2. Evaluate bias on BBQ and prompt injection on a licence-cleared attack set.
3. Replace assumed `k` with shadow-mode labels and retain a random audit slice to reduce selection
   bias.
4. Run consequence low/base/high sensitivity with Finance and Risk owners.
5. Benchmark first-token and gated-effect latency on target hardware and a real provider.
6. Repeat the equal-spend curve across seeds, languages, routes, and an unseen failure taxonomy.
