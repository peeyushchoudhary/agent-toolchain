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

A `full_gate` or `e2e` receipt that failed only on named tests, because the machine was loaded, is
completed once, not rerun whole: `gate.py receipt ... --rerun-failed "<command naming each failed
test and any that did not run>" --cause "<evidence>"`. `gate.py` accepts it only when each failure
is a timeout or resource error, another recorded run overlapped it or the load reached the CPU
count, and the rerun passes. A failure that reproduces alone gets a fix. An assertion failure that
passes alone means one test depends on another: fix it and run the full gate.
