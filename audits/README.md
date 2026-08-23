# Audits

Internal working documents. **Delete this folder before submission.**

These are adversarial reviews of our own build, written to find what a judge would find. They are
useful to us and confusing to a reader who has not been part of the process, because they describe
problems that have since been fixed.

Nothing outside this folder links to anything inside it. `README.md`, `docs/` and the code are
self-contained, so removing `audits/` (and `HANDOFF.md`) leaves no dead references. Check with:

```bash
grep -rn "audits/" --include=*.md . | grep -v '^./audits/'
```

That should return only `HANDOFF.md` and `CODEX_BRIEF_RUNTIME.md`, both of which are also
removed before submission.

| File | What it covers |
|---|---|
| `A-implementation-audit.md` | Audit of commit `e88f1c9`, the first implementation. Found that the evaluation never called the allocator, that the corpus made harm predictable from row structure, and that the conformal bound was violated on held-out data. Phase B fixed all three. |

Findings that outlive the audit belong in `docs/LIMITATIONS.md`, which is a submission artifact and
already carries them.
