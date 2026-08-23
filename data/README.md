# Data provenance

`make data` recreates three JSONL files with seed `20260824`:

- `interactions.jsonl`: all 3000 interactions;
- `calibration.jsonl`: 1500 rows, 500 per route;
- `test.jsonl`: 1500 disjoint rows, 500 per route.

The corpus is synthetic. Counts in `dataset_manifest.yaml` are computed from the checked-in files
and are not estimates of enterprise prevalence.

## What this corpus is built to avoid

An earlier version of this generator produced 600 rows from 10 response templates, and attached
source documents only to the clean templates. That made harm perfectly predictable from row
structure: the rule "flag any row with no context documents" scored precision 1.000 and recall 0.743
on the held-out split with no detector involved, and calibrated detector AUC reached 1.000 on two of
three routes. Any evaluation built on it measured the fixture, not the system.

This version is generated compositionally and holds three properties, each checked by
`tests/test_corpus_integrity.py`:

1. **Evidence availability carries no label information.** Sources are drawn independently of harm.
   Observed harm rate is 0.164 for grounded rows and 0.174 for unverifiable rows.
2. **Detection is imperfect in both directions.** Every harm family emits a loud realisation that
   uses obvious markers and a quiet one that does not, so recall stays below one. Clean decoy
   families — policy discussion naming protected attributes, refusals that name the unsafe topic,
   PII that the supplied record permits, and formatting drift on grounded numbers — resemble the
   loud harmful forms, so precision stays below one.
3. **Calibration and test are exchangeable.** The split is i.i.d. within each route. That is what
   the conformal bound assumes, so a split by template family would invalidate it.
4. **Responses are divisible.** Each response is a paragraph of four to seven independently
   labelled clauses, median five. An earlier version emitted single sentences (median 80
   characters), which made span-level verification impossible to evaluate at all.

Only **3.45% of characters carry harm**, and every harmful clause has an exact character span.
That gap between what must be read and what must be checked is what paged verification targets.

Detector trigger vocabulary was not consulted while writing the generator. Some overlap between
fixture wording and detector keywords remains and is expected; what matters is that it no longer
determines the label.

Every row carries an interaction id, split, route, jurisdiction, prompt, model response, optional
context documents, optional comparison samples, tool calls, five ground-truth harm values, and a
shift flag. Calibration and test ids do not overlap.

No public benchmark is included. External candidates, licence decisions, and source links are listed
in `docs/06-datasets.md`.

Regenerate with:

```bash
make data
```

The command overwrites only the three generated JSONL corpus files. It does not download anything.
