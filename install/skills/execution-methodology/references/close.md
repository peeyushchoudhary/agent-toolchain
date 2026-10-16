# Closing findings and the milestone

## Findings

`goal.py review --chief <claude|codex> --stage <design|plan|merge>` sends
[the reviewer prompt](../agents/reviewer.md) and `.runs/<id>/<stage>-review-packet.md` to the other
vendor's CLI with the exact model and effort in [roles.md](roles.md), and writes `<stage>-review.md`
(`review.md` for merge, never over an existing one). `done` refuses a `review.md` whose reviewer line
names another model:

```
reviewer: <cli> <model> at <effort> (read-only), <date>, <stage>
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
pushes the branch and opens the PR. Then, in this order:

1. The PR's head is the commit `done` passed; it is the milestone's.
2. Once the founder says to merge, run `gh pr merge <n> --merge`, adding `--delete-branch` only
   when the milestone is the goal's last.
3. `git tag goal/<id>/<milestone> <head>` at that head commit, not at the checkout `gh` switched,
   then `git push --atomic origin goal/<id>/approved goal/<id>/<milestone>`. If a re-approval moved
   an approval tag an earlier milestone pushed, add
   `--force-with-lease=refs/tags/goal/<id>/approved:<sha>`, `<sha>` being what `git ls-remote`
   shows for it; both tags go, or neither.
4. Run `goal.py cleanup --goal <id> --apply`. It removes only the worktrees recorded with `own`,
   and their branches, whose work `origin/main` holds.

Archiving or untracking anything at a close follows [repository.md](repository.md#lifecycle).

Next milestone: same branch.

With `full_gate: modules`, the full gate is `gate.py receipt --goal <id> --modules all`. After a
failure, the same command keeps passed modules and retries a failed one once on the same tree; a
second failure needs a fix commit.

Record failures present at approval once with `gate.py baseline`; diagnose any new failure, never
rerun until green beyond that one retry.
