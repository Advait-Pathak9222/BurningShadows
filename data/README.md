# Data provenance

`make data` recreates three JSONL files with seed `20260822`:

- `interactions.jsonl`: all 600 interactions;
- `calibration.jsonl`: 300 rows, 100 per route;
- `test.jsonl`: 300 disjoint rows, 100 per route.

The corpus is synthetic. It has 200 rows per route, 300 rows per jurisdiction, 200 late-shift rows,
107 effect-bearing rows, 104 overlapping-harm rows, and 232 rows with at least one harm label. Those
counts are generated from the checked-in files and are not estimates of enterprise prevalence.

Every row contains an interaction id, split, route, jurisdiction, prompt, model response, optional
context documents, optional comparison samples, tool calls, five ground-truth harm values, and a shift
flag. Calibration and test ids do not overlap.

No public benchmark is included. External candidates, licence decisions, and source links are listed
in `docs/06-datasets.md`. The manifest records why gated or restricted sources are excluded from the
offline path.

Regenerate with:

```bash
make data
```

The command overwrites only the three generated JSONL corpus files. It does not download anything.
