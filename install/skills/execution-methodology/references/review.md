# Review

Review spends model judgement, so it runs only where it has measured yield. Designs drew about
0.74 blockers per artifact; ordinary implementation tasks about 0.09, and those are already covered
by the gate, the guards and milestone acceptance.

## Where review runs

| Point | Reviewer | Why here |
| --- | --- | --- |
| Design, before approval | cross-vendor reviewer | the highest measured yield |
| Plan, before approval | cross-vendor reviewer | decomposition, write sets, gates, proofs, milestone sizing |
| Task with `risk: safety` | security-reviewer | the best catch record, including fail-open guards |
| Task with `risk: boundary` or `data` | reviewer, matching lens | durable interfaces and data changes are expensive to unwind |
| Milestone acceptance | cross-vendor reviewer | one whole-diff review catches what per-task review would, at a fraction of the cost |

There is no default review of ordinary tasks.

**Cross-vendor.** At design, plan and acceptance the reviewer comes from the other vendor than the
chief. A reviewer from the same vendor shares the builder's blind spots; in a measured comparison
only the cross-vendor reviewer caught an invented API. If the other vendor's quota is exhausted, use
the same vendor in a fresh context and record why in the verdict header.

**Lenses.** The reviewer reads with the lens the subject needs: design, plan, boundary, data or
acceptance. The data lens, for designs and tasks marked `risk: data`, checks that the migration
parses and applies to a scratch database, that backfill and rollback are stated, that a migration
contract test exists and runs in the gate, that an index exists for every new query plan, and that
retention and erasure paths are covered.

## Judge isolation

Judges are read-only by construction, not by instruction, because an instruction can be ignored
and a missing tool cannot. `scripts/review.py` builds the packet and makes a one-shot call:

- Codex: `codex exec -s read-only --ignore-user-config --ignore-rules`
- Claude Code: `claude -p --tools Read,Grep,Glob --strict-mcp-config --setting-sources project,local`

Neither call loads the user's MCP servers, apps, hooks, plugins or other integrations, so a judge has no mutating
surface besides the sandboxed shell. An allow-list of tools alone would only pre-approve those
tools without removing the others. Both run with `GOAL_ROLE=judge`, so the Stop hook lets them end,
and at the model and effort in the reviewer persona's frontmatter.

A judge gets a fresh context: the frozen criteria, the subject (document, task diff or milestone
diff), the evidence record at acceptance and, for a rereview, the finding and its correction. It
does not get the builder's reasoning or the chief's opinion, which would anchor it.

## Findings

The reviewer reports everything it finds. It is not told to be conservative, because current
models follow that literally and under-report. Each finding carries a class:

- `correctness`, `safety` or `requirement` **blocks**, but only when the finding names a reachable
  trigger and an observable consequence. Without both, it cannot be verified or closed.
- `other` (style, hardening, preference, methodology form) **never blocks**. These findings are
  listed as optional in the explainer, and the founder can promote one.

## Closure

1. Where it can, turn a blocking finding into a test that fails before the fix and passes after
   it. The gate then proves closure and no rereview is needed.
2. Otherwise run one scoped rereview of the correction: the finding, the fix, nothing else.
3. If the subject is still blocked after that rereview, the loop ends:
   - **design or plan:** the issue goes to the founder at approval;
   - **risk review:** the task is parked;
   - **acceptance:** the milestone is NOT READY and is queued for the founder with the advisor's
     recommendation attached.

Each subject gets at most one correction and one scoped rereview. `review.py` refuses a third round
on a subject, and no escalation buys an extra round. A renamed attempt is the same subject.
The cap is what guarantees a review loop ends; earlier runs without one looped on the same
subject.

## Acceptance

Acceptance reviews the whole milestone diff against the criteria and the evidence record, and
names the tree it judged. `goal.py done` accepts only a PASS verdict that names the milestone's
candidate tree, so any commit after the verdict needs a new one.

A large milestone may declare `acceptance: [<partition>, …]` to split acceptance across parallel
reviewers over disjoint file partitions. Each partition has its own round cap, and completion needs
a current PASS from every declared partition. Deletions are summarised by path rather than read
line by line.

## Verdict files

Verdicts are written under `.runs/<goal>/verdicts/`:

- `M<n>-acceptance.md`, or `M<n>-acceptance-<partition>.md` for a partitioned milestone;
- `T<n>-security.md` for a safety review;
- design, plan, boundary, data and advisor verdicts beside them.

The first line is `VERDICT: PASS` or `VERDICT: BLOCK`. Header lines follow as `key: value`:
`vendor`, `model`, `effort`, `tree` and `round`, plus the fallback reason when the same vendor
judged. The findings come after, each with its class, trigger, consequence and the path it
concerns. `goal.py done` and `goal.py evidence` read the first line and the header.
