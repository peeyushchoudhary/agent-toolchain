# Historical methodology rationale

This file preserves the evidence and reasoning that led from versions 3 through 5. It is **not
current authority**. Current behavior is defined by `../methodology.md`, the executable loop, and
the maintained scripts and tests. Where a historical rule differs, the current source wins.

## Why the history moved

The canonical method used to carry its own changelog beside operative rules. Readers had to decide
whether an old measurement, a correction, or the newest sentence governed. The same review policy
was then restated in `SKILL.md` and the loop, and those copies diverged. Moving this rationale keeps
the measurements available without asking an executor to interpret history at runtime.

## Version 5: unattended execution and stage-specific review

Version 5 added an executable controller loop. Before it, `plan_waves.py`, card validation, JUnit
receipts, trace checking, and milestone sealing existed as separate instruments with no procedure
that said when to run each one. The loop made status derive from git, calculated a continuous ready
set, checked mid-task and committed writes, drained deferrals, verified criterion evidence, and
sealed a tree before acceptance.

The change was driven by direct failures:

- a milestone-scoped `--commit` option was parsed but never called, so a cross-feature stray write
  passed every test until a live fixture executed the documented command;
- wave barriers idled independent tasks even though their declared dependencies allowed them to
  proceed;
- ledger status grew large, costly, and self-attested while commit history already held the facts;
- a gate name in prose could drift from its parser without any failing test.

The command-document tests therefore parse commands from the loop, compare flags with the real
parsers, and execute those same lines against temporary repositories. The Mermaid diagram is tied
to the loop table rather than maintained as a free-standing second procedure.

Version 5 also corrected a flat review-width rule. Across 1,051 round-marked artifacts in the
measured corpus, design/plan artifacts produced blocking findings more often than implementation
diffs, and multiple design lenses cited substantially different anchors. That supported distinct
lenses at design and plan, while implementation stayed one semantic reviewer plus a command-running
`test-judge`. Project domain validators were more useful at definition/design than after code was
already written.

An implementation-selection score was later proposed from overlap, dependency fan-in, warnings,
and retries. It never became a durable interface or executable admission rule, and later policy
removed it: every governed task now receives its initial full-diff review, so ranking review
eligibility is undefined and unnecessary.

## Version 4.2: derive schedules and committed write conformance

Version 4.2 replaced prose wave lists with task blocks and a derived schedule. A task declared its
id, dependencies, lane, writes, criteria, and intentional serialization. `plan_waves.py` checked
dangling edges, cycles, duplicate ids, intersecting glob sets, feature size, milestone membership,
and later each named commit's actual paths.

The motivating 51-task corpus contained 164 intersecting write-set pairs, including 37 pairs in the
same computed wave, plus dangling dependencies. Quietly serializing them would have made the plan
look green while preserving ambiguous ownership, so collisions remain findings for the planner.
The glob checker is deliberately conservative and does not expand against the filesystem because
planned outputs often do not exist yet.

Continuous readiness was measured against barrier waves on the same graph and saved work across
tested worker counts. The useful invariant was the declared dependency/write graph, not a compiled
concurrency number. `--limit` therefore remained an operator bound while readiness was recalculated
against the actual in-flight set.

Commit checking was added after 4 of 83 files in a measured card sample landed outside the declaring
task's write set, all inside another task's set. Qualified task ids were required at milestone
scope so the checker could identify the correct plan-local task. Ordinary commit prose stayed
silent; task-shaped ids that resolved nowhere remained visible.

The 2026 revision tightened admission: lane is no longer inferred and writes may not be empty. This
removed the historical ambiguity where a missing lane silently became light and an empty boundary
could enter the schedule.

## Version 4.1: check product definition and test evidence

Version 4.1 made feature definition machine-readable without pretending a structural checker could
judge product quality. Feature specs gained current-state front matter, acceptance criteria,
horizontals, edge-case declarations, validator routing, and owned deferrals. `spec_check.py` checked
those shapes and printed limits rather than treating a clean parser result as product approval.

JUnit evidence was tightened after exact-looking Gradle filters could execute zero tests and still
return success. The nonce protocol records the results directory immediately before a run, then
verifies fresh XML, class names, counts, failures, skips, and single use. `trace_check.py` consumes
that verified evidence and compares criterion ids, while stating that an id proves only that a
named test ran, not that its body asserts the criterion.

Milestone sealing bound the cross-feature command to a clean tree and stored its receipt outside the
repository. This prevented a receipt from travelling to a different clone or surviving a changed
tree. It also kept evidence generation separate from authorization: a green seal never authorized
a push, merge, or production action.

## Version 4.0: make process cost observable

Version 3 named a process budget but left it to intention. In one measured repository, process
share rose from 4% to 75% over eight weeks while product output fell sharply. Version 4 introduced
`ratio_meter.py`, classifying committed churn as product, product thinking, process, generated, or
cleanup. The current target and bands came from that work: 10% process target, warning above 15%,
failure above 30%, and no failure below 500 classified lines.

The cleanup exemption matters. A meter that counted removal of obsolete bookkeeping as new process
cost would preserve the very corpus it was meant to shrink. Weekly trend reporting remained a
report, while the merge-range meter became the enforceable gate input.

Workspace caps were added after measured workspaces accumulated hundreds of reports, raw captures,
diff snapshots, and oversized cards. The durable lesson was to preserve verdicts and evidence,
while using git for diffs and one ledger line for failed dispatches.

## Version 3.1: goal-bound execution

Version 3.1 required each dispatch and repair to advance a named Goal Capsule criterion or invariant
with an observable delta. This addressed tasks that were locally correct yet unrelated to the
approved outcome, and review loops that invented broader products one plausible hardening request at
a time.

The spec became a ceiling as well as a floor. Current-scope defects stayed blocking; preferences,
speculative future hardening, and newly invented requirements did not. Findings were classified
before repair so a harness defect, invalid frozen assumption, external fact, evidence gap, safety
issue, or scope change took its own route.

## Version 3.0: bounded review and two lanes

Version 3 separated ordinary bounded work from tasks that moved durable contracts or safety
surfaces. Light work avoided a full card; full work kept explicit frozen values, strict boundary
checks, and stronger evidence. The intended benefit was less process on routine changes without
weakening authorization, privacy, money, migration, and published-interface work.

It also introduced compact structured verdicts, fresh read-only judges, finding classification,
growth checks, and a bounded correction/rereview cycle. This responded to review lineages reaching
round numbers in the teens, repeated panels producing the same verdict, and reviewed artifacts
growing far beyond their original scope.

One early interpretation said the controller should apply a final semantic correction and close
automatically when the review budget ended. That was unsafe: a numeric cap cannot turn an unresolved
semantic defect into READY. The current method instead leaves unresolved semantic work INCOMPLETE;
only a fully mechanical application may close after independent executable confirmation.

Another early loop retained a separate five-round fix cap beside the two-round review procedure.
That contradiction is historical. The current method has one initial full task-diff review and one
scoped correction review, with gate return or incomplete state when the issue remains.

## Durable conclusions

The changes above left a few stable conclusions that current source still embodies:

- derive status and conformance from plans, git, and executable receipts;
- keep product decisions in current-state artifacts and rationale in clearly labelled history;
- isolate judges by tool restriction and context, and never treat their verdict as authorization;
- use a light branch only after explicit plan admission, and retain review, gate, and commit checks;
- use a full card for durable boundaries and safety surfaces, preserving exact schema and evidence
  contracts in their maintained references;
- measure process in real units and state the limits of every measurement.
