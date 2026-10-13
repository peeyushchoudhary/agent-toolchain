# Closing findings and the milestone

## Findings

Findings go to `.runs/<id>/review.md`:

```
reviewer: <vendor model> (read-only), <date>, <stage>
reviewed: <full sha>
verdict: PASS | BLOCK
## Findings
- [ ] BLOCKING R1 <defect>
  paths: <glob>, <glob>
```

Never reclass a blocking finding. Close it with a `[Tn][Rn]` fix commit that adds or changes its
test, then tick it and add under it, above `paths:`, `- [x] R1 resolved-by <sha> closes <test
path>::<name> cause: <c>`; or remove the work: `- [x] R1 removed-by <sha> cause: <c>`. `<c>` is
`context` (the packet lacked it), `logic` (the build was wrong) or `spec` (the criteria were).
Park non-blocking findings.

## Milestone close

Clean tree → `gate.py receipt --goal <id> --name full_gate --cmd "<full_gate>"` and `--name e2e
--cmd "<e2e>"` → merge review (fix commits need fresh receipts) → `goal.py done` prints DONE →
`goal.py packet` writes the PR body. Once the merge review passes and `done` prints DONE, the chief
pushes the branch and opens the PR; the founder merges and tags. Next milestone: same branch.
Record failures present at approval once with `gate.py baseline`; diagnose any new failure, never
rerun until green.

A `full_gate` or `e2e` receipt that failed only on named tests, because the machine was loaded, may
be completed once instead of rerun whole: `gate.py receipt ... --rerun-failed "<one plain command
running each failed test>" --cause "<evidence>"`. `gate.py` accepts it only when:

- each failure's log shows a timeout or resource error and no assertion;
- another recorded run overlapped the failed one, or the load reached the CPU count;
- an earlier PASS receipt of the same command exists, and the failed run executed as many tests and
  printed as many suite summaries as it, with no fail-fast flag (Gradle needs `--continue`);
- the output is unittest, pytest or Gradle, and the rerun's own output reports each failed test as
  passed: run it verbosely, or with `--junit`.

Otherwise, or when the rerun fails, run the full receipt again. A failure that reproduces alone gets a
fix. An assertion failure that passes alone means one test depends on another: fix it and run the
full gate.
