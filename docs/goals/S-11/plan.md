---
goal: S-11
title: Explicit immutable-test migrations and isolated gate execution
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_modmap.py'
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1, T2, T3, T4, T5, T6], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [interface]
protected: [docs/decisions/decisions.md#D1-D40]
---

## Outcome

An optional approval-frozen `docs/goals/<id>/test-migrations.json` can declare
one exact replacement of a literal Python test-file command (AC1). It binds
unchanged original files, a named successor population and a generated preservation check;
DONE additionally requires fresh module, individual-successor and preservation
receipts on the candidate tree (AC2). The read-only
`goal.py migration-proofs --goal <id>` emits their exact commands as version-1 JSON. Missing or inconsistent declarations and
proofs refuse the exception, while existing command/count/coverage protections
continue to reject undeclared shrinkage and intermediate command laundering
(AC3). Both gate modes strip the four inherited pytest controls without changing
explicit commands or interpreters (AC4). The current standard full gate, installed
round-trip E2E, other-vendor review and DONE remain mandatory; public documentation
states the narrower exception and its evidence limits (AC5).

Spec: [spec.md](spec.md). Design: [design.md](design.md).

## Tasks

### [x] T1 — Validate an exact immutable-test migration and its proof descriptors
writes: install/skills/execution-methodology/scripts/migrations.py, install/skills/execution-methodology/tests/test_modmap.py, docs/goals/modules.json
reads: docs/goals/S-11/spec.md, docs/goals/S-11/design.md#interfaces, install/skills/execution-methodology/scripts/modmap.py, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_modmap.py
tests-may-change: install/skills/execution-methodology/tests/test_modmap.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_modmap.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_docs.py' && python3 -m unittest discover -s install/tests -t install/tests && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
AC1, AC2, AC3. Implement the standard-library-only `migrations.py` boundary in design
Interfaces 1–2: `MigrationError(ValueError)`, `parse(text, baseline_map, read)`,
`allowed(entries, current_map, read)`, `proofs(entry)` and
`proof_ok(descriptor, receipt, tree)`. `read(path)` returns a tracked Git mode and
bytes or `None`. Keep the literal command grammar, generated preservation command, exact string bindings,
retained file order, closed schema and `BYTES_ONLY` claim from the design. The
helper imports neither goal nor gate. Receipt path/key construction belongs to
the existing gate functions, not this helper.

Append `MigrationTest` to the existing `test_modmap.py`, copying `ModMapTest`'s
pure unittest pattern. Named test
`test_closed_declaration_binds_exact_python_replacement` accepts a real hash-bound
declaration and exposes the exact module, successor and preservation descriptors.
Add `test_historical_claim_other_than_bytes_only_is_rejected`: accept only
`historical_claim: BYTES_ONLY` and reject `REPLAYED`, other strings and other
JSON types (design review R1). Add table-driven rejection tests for
unknown/duplicate JSON keys, booleans in
integer fields, malformed paths/hash/modes, duplicate module/source/successor
entries, symlink/untracked originals, missing originals, retained-file loss or
reordering, interpreter/count/replaces changes, discovery/filter/operator commands,
empty successor populations, raw command control characters and third commands. Test proof checks for wrong tree,
command/module, failed/skipped/baselined/zero-count test results, contradictory
PASS metadata, negative counts and non-integer counts. Run the generated preservation command against real temporary files: pass on
matching bytes and refuse missing, changed, unreadable or symlinked inputs without
Python assertions. Preservation may execute zero tests;
successors and the replacement module may not. Preserve every existing test and
assertion. Do not change a map command, add a new test file, dependency, executor,
receipt format or configuration. T3 grows module ownership after this commit.

### [x] T2 — Isolate inherited pytest controls in the shared gate runner
writes: install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
reads: docs/goals/S-11/spec.md, docs/goals/S-11/design.md#interfaces, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_gate.py
tests-may-change: install/skills/execution-methodology/tests/test_gate.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_modmap.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_docs.py' && python3 -m unittest discover -s install/tests -t install/tests && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
AC4. In `gate.run`, pass `Popen` a copy of `os.environ` with exactly
`PYTEST_ADDOPTS`, `PYTEST_PLUGINS`, `PYTEST_XDIST_WORKER` and
`PYTEST_XDIST_WORKER_COUNT` removed. Keep the parent environment, unrelated child
variables, command text, chosen interpreter, count parsing and receipt keys intact.

Copy `GateCase`, `CheckTest` and `ModulesTest` real subprocess fixture patterns.
Append `GateEnvTest.test_cmd_and_module_children_strip_inherited_pytest_controls`
and `test_explicit_command_assignment_and_unrelated_environment_are_preserved`.
Launch genuine standard-library unittest children with all four hostile variables
set in the gate's inherited environment; each child asserts its observed values
and actually runs tests. Exercise both command and module CLI modes, verify their
actual counts and unchanged command/key identity, and prove an explicit assignment
inside the command still reaches its child. No simulated summaries, optional
pytest dependency, new skip, map prefixes, general environment sandbox or unrelated
runner changes. Preserve all existing assertions.

### [x] T3 — Enforce approval-bound structural admission and protected history
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, docs/goals/modules.json
reads: docs/goals/S-11/spec.md, docs/goals/S-11/design.md#interfaces, install/skills/execution-methodology/scripts/migrations.py, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py, docs/goals/modules.json
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_modmap.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_docs.py' && python3 -m unittest discover -s install/tests -t install/tests && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
needs: T1, T2
AC1, AC3. Integrate the helper through `lint`, `protected_entries` and
`commit_findings`. Before approval validate the working declaration against the
committed map/sources; afterward use only the tag's declaration and baseline.
Read original identities as tracked Git mode plus raw bytes, never replacement-
decoded `file_at` text. The declaration and originals are implicit protected
paths throughout every commit. Refuse post-approval introduction/change, missing
or mismatched sources and a third module command even when restored later.
Keep existing plain-goal/fake-context behavior without the artifact.

Admit only the exact authorized test substitution; preserve the three-argument
`map_shrinks` default and all other D38 findings, including count, needs, shared
and path loss. Reject a changed `replaces` accompanying an exception. Add only
`install/skills/execution-methodology/scripts/migrations.py` to `modmap.paths`;
all existing module commands, counts, needs and shared entries stay unchanged.

Copy `ModuleRowTest` and repository fixture patterns. Append
`MigrationAdmissionTest.test_only_exact_approved_migration_is_admitted` and
negative fixtures for post-approval/changed declarations, wrong/missing original
hashes or symlink modes, mutate/restore history, restored third commands,
missing activated successors and simultaneous undeclared shrinkage. Keep
`test_unapproved_map_change_fails_row_4`,
`test_a_maintained_map_may_grow_but_never_shrink`,
`test_an_invalid_map_between_commits_cannot_hide_a_shrink` and
`test_a_file_deleted_and_restored_cannot_hide_a_lost_path` unchanged and passing.
Do not implement DONE proofs or presentation here; T4 supplies those before
milestone acceptance. No installed edits, tag movement, new plan field or skip.

### [x] T4 — Require exact-tree proofs and expose their canonical commands
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: docs/goals/S-11/spec.md, docs/goals/S-11/design.md#interfaces, install/skills/execution-methodology/scripts/migrations.py, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_modmap.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_gate.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_goal.py' && python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_docs.py' && python3 -m unittest discover -s install/tests -t install/tests && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
needs: T3
AC2, AC3. Use T3's admitted declaration, `proofs` and `proof_ok` in DONE row 7.
Applied migrations require the candidate tree's module receipt, an independently
run receipt per successor and the generated preservation receipt. Reuse
`gate.receipt_path` and `gate.module_key`; no new registry or receipt type.
An unapplied migration needs no successor receipts. Module proofs use
`gate.py receipt --goal <id> --modules <module>`; successors use
`receipt --goal <id> --cmd <exact>`;
preservation uses `receipt --goal <id> --cmd <exact> --count none`. `tests: false` means
that last flag is mandatory; all test proofs retain positive executed counts.
Keep the standard full/E2E and review requirements intact.

Add the read-only `goal.py migration-proofs --goal <id>` version-1 JSON CLI
exactly as designed. Approval HTML and normal packets expose the declaration,
BYTES_ONLY limits, exact commands, count-none instruction and proof gaps.
Copy `DoneTest` and approval-renderer fixture patterns. Append
`MigrationGoalTest.test_exact_approved_migration_requires_fresh_proofs` and
`test_migration_proofs_cli_emits_exact_command_json`, covering pre/post approval,
no declaration, unapplied declarations, invalid metadata and typed descriptors.
Reject missing/stale/wrong-command/wrong-module/zero-test/skipped/baselined or
contradictory receipts. Test a genuine zero-count preservation PASS taken with
`--count none`; never waive missing evidence or alter existing full/E2E rules.
No map, interpreter, installed-copy, history or dependency changes.

### [ ] T5 — Rehearse the migration using installed CLIs in disposable homes
writes: install/skills/execution-methodology/tests/e2e_run.sh, install/tests/test_install.py
reads: docs/goals/S-11/spec.md, docs/goals/S-11/design.md#interfaces, install/skills/execution-methodology/tests/e2e_run.sh, install/tests/test_install.py, install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/scripts/gate.py, install/skills/execution-methodology/scripts/migrations.py
tests-may-change: install/skills/execution-methodology/tests/e2e_run.sh, install/tests/test_install.py
gate: python3 -m unittest discover -s install/tests -t install/tests
needs: T4
AC1, AC2, AC3, AC4, AC5. Extend the existing per-harness installed flow in `e2e_run.sh`; retain
its current goal loop, retry, install/uninstall byte-identity and v6 rollback
checks. Add a disposable generic migration goal with real unittest test files,
original hashes, all committed before approval. The preservation command comes
from the installed `goal.py migration-proofs --goal <id>` JSON, not
fixture-specific checker source or copied shell text.
Show rejection of command/digest mismatches in separate disposable negative
repositories cloned from the approved fixture. Their bad commits are never
part of the success fixture's history. Do not restore a committed bad change or
reset/re-tag history to reach success (design review R2). In the untouched valid
fixture, commit its exact replacement and show DONE refuses
missing proofs, then run the replacement module, each successor alone and the
generated preservation check through the installed gate with `--count none` to obtain real receipts. Assert immutable
bytes, exact-tree proof binding, successful DONE and inherited environment
isolation. Existing merge-review fixtures stay explicitly labeled fixtures;
do not call a fake review an independent review.

Extend `E2ERunTest.test_e2e_run_rehearses_install_identity_and_rollback` to assert
the migration/proof/environment labels from that same single script execution.
Keep its install-identity/rollback assertions and final summary regex valid.
Never read credentials, call a provider, push, modify a real home, add a second
full E2E invocation, skip or dependency. The milestone E2E is the same script run
separately on the accepted clean tree; unit tests alone do not establish it.

### [ ] T6 — Document the precise source contract and reconcile current status
writes: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/test-migrations.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/references/modules.md, install/skills/execution-methodology/references/planning.md, install/skills/execution-methodology/tests/test_rules.py, docs/architecture/methodology.md, docs/architecture/repository-standard.md, docs/decisions/decisions.md, docs/product/measurements.md, docs/README.md, README.md
reads: install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/references/close.md, install/skills/execution-methodology/tests/test_rules.py, install/tests/test_size.py, docs/goals/S-11/spec.md, docs/goals/S-11/design.md#interfaces, install/skills/execution-methodology/references/modules.md, install/skills/execution-methodology/references/planning.md, docs/architecture/methodology.md, docs/architecture/repository-standard.md, docs/decisions/decisions.md#d38, docs/product/measurements.md, README.md
tests-may-change: install/skills/execution-methodology/tests/test_rules.py
gate: python3 -m unittest discover -s install/skills/execution-methodology/tests -t install/skills/execution-methodology/tests -p 'test_rules.py' && python3 -m unittest discover -s install/tests -t install/tests && cd install && ./install.sh --dry-run && ./verify.sh --no-suites
needs: T5
AC5. Put the full current protocol in new `references/test-migrations.md`, at
most 400 whitespace words. Add its `MIGRATIONS` Path constant, entry to
`SKILL_FILES` and `REFERENCE_WORDS[MIGRATIONS] = 400` in `test_rules.py`.
Keep every existing reference, agent and always-loaded ceiling and assertion
unchanged; this extends the checked file set instead of relaxing any limit.
The current modules/planning/close pages are 199/398/399 words with limits
200/400/400. Give them concise pointers, rewriting existing wording within those
same ceilings while preserving their existing requirements and checked phrases.

Change only SKILL.md's DONE row 7 among always-loaded prose, to this exact
12-word replacement (the old row is also 12; the combined ceiling remains 1350):

```markdown
7. PASS receipts on HEAD's tree: `full_gate`, milestone `e2e`, declared [migration proofs](references/test-migrations.md).
```

In close.md point to the new proof procedure, including `migration-proofs`
retrieval and preservation `--count none`, while retaining the full/E2E/review/
DONE sequence. The new reference covers the closed declaration, approval/history
protection, unchanged rejection rules, exact proof retrieval/flags, zero-skip/
zero-baseline eligibility, goal-scoped preservation and re-approval trust limits.
Update architecture and repository-standard readers; append D41 as D38's narrow
amendment, retaining D1–D40 verbatim.

Update README's Current state, add the migrations helper's Components row,
describe goal.py's `migration-proofs`, and add the command under Run locally.
Record only completed prior task checks/diagnostics/samples in measurements.md,
with command, measured tree and limitations. Final close receipts/logs remain
under ignored `.runs/` and in the PR packet: never edit tracked measurements
after taking final receipts and claim they still bind the changed tree. Generate
docs/README.md if needed. No installed-parity, merge, release or live-provider
claim is implied.

Append `Planning.test_frozen_test_migration_contract_is_explicit` to verify the
new reference and pointers, receipt/count-none language and preservation limits.
Keep `Budgets.test_each_reference_is_within_its_word_ceiling` unchanged and passing
with all original ceilings. Add `Close.test_close_names_migration_proofs` for
the close procedure. Preserve existing rules tests and agent/global bodies.
No installer, hook, historical goal, installed-copy or unrelated prose changes.

## Decisions

- 2026-10-20 T4: reuse existing receipt readers/keys for strict exact-tree proofs and shared canonical CLI/presentation descriptors. Hoist task-independent protected paths once per lint invocation. Preserve unborn no-declaration approval through a nonfatal tree lookup; its new regression failed before the fix. A cancelled partial run is diagnostic only. Final builder/chief gates passed 328 run / 0 failed / 0 skipped; chief 570.14 seconds (default).

- 2026-10-20 T4: the third-task full sample passed 393 run / 0 failed / 0 skipped with verify: PASS in 766.08 seconds on tree f58ead6297ca2a80e08d97e4bfbe7b531867ff6a. Completed runtime exceeds 600 seconds, so subsequent full validation is at milestone close. The clean sample worktree was removed (default).

- 2026-10-20 T3: use raw Git modes/bytes and check migration identities before commit-subject early exits; preapproval uses committed HEAD metadata. Preserve the legacy map-shrink function and every existing assertion. Corrected a proposed mode-only assertion to retain ordinary frozen-test protection and added a second valid task commit fixture. Helper ownership was already accepted in T1. Builder/chief gates passed 321 run / 0 failed / 0 skipped; chief 533.36 seconds (default).

- 2026-10-20 T3: the third accepted task triggers a standard full-gate sample on a recorded detached checkout. A private runner uses an 1800-second ceiling plus 20 seconds for owned-process cleanup so the full command can finish; this is separate from unchanged task ceilings. Only an actual completed full-gate runtime determines future sampling (default).

- 2026-10-20 T1: pure helper uses globally unique declaration paths, rejects selectors/response-file arguments and requires typed consistent proof counts. Original tests remain intact. Builder and chief selected gates passed 311 run / 0 failed / 0 skipped; chief 380.69 seconds. Removed the superseded approval-wait note after the founder-approved tag was placed (default).

- 2026-10-20 T1: the installer coverage test failed because the new helper
  must have ownership in its introducing task. Widened T1 writes to the already
  maintainable modules.json and moved its single additive modmap.paths row from
  T3 timing to T1; T3 verifies the existing row. This supersedes the original
  incidental ownership timing, preserves all commands/counts/needs/shared paths
  and keeps the selected gate and existing coverage assertion unchanged (default).

- 2026-10-20 T2: copied the environment in the shared runner and used real
  standard-library unittest children to verify all four controls, command/module
  checks and receipts, explicit assignments, interpreter identity and unchanged
  parent/unrelated environment; no pytest dependency (default). Chief gate:
  300 run / 0 failed / 0 skipped, PASS in 375.39 seconds.

- 2026-10-20 planning: one optional fixed-path declaration and one pure helper,
  generating the preservation command from approved original hashes rather than
  requiring a pre-existing project checker; with no module-map/frontmatter schema change or new receipt type (default).
- 2026-10-20 planning: support only literal Python test-file replacement; defer
  discovery, arbitrary shell commands and historical-replay claims (default).
- 2026-10-20 planning: append helper tests to the existing modmap suite and grow
  its path ownership; this goal changes no existing module command (default).
- 2026-10-20 planning: dispatch T1 and T2 to separate builders, then commit their
  gates serially before T3. T4, T5 and T6 follow their committed needs (default).
- 2026-10-20 planning: use explicit whole-component task gates including the migration
  consumer chain (modmap, gate, goal, install, repository) for T1–T4, the entire
  installer suite for T5, and rules/install/repository for T6. The shared map
  change only grows helper ownership; guard/hooks do not import goal/gate. The
  unchanged full gate covers all other components. No selector edge or existing
  module command changes (default).
- 2026-10-20 planning: a planning full-gate diagnostic reached its 580-second
  ceiling and exited 124 without a verdict. This is neither a functional PASS nor
  proof that runtime exceeds 600 seconds. Measure component commands alone; retain
  every-third-task full samples while full runtime is unknown, switching to the
  skill's close-only rule only if an actual completed runtime exceeds 600 seconds
  (default). Any full-gate failure stops dispatch; no new baseline is admitted.
- 2026-10-20 planning: source-only scope; an approved implementation does not
  authorize push, merge, release or installation into real harness homes (default).
- 2026-10-20 planning: measured component families serially through
  `gate.py check`: modmap 9 tests / 3.24 s; gate 72 / 62.80 s; goal and docs
  173 / 286.66 s; installer 44 / 49.58 s; rules plus non-test verification
  34 / 2.72 s. All exited 0, PASS, with zero failed/skipped tests. These are
  unchanged-source planning measurements, not implementation acceptance (default).

- 2026-10-20 planning: design R1 resolved in the proposal by making `BYTES_ONLY`
  the sole accepted claim value and naming its T1 rejection test. Implementation
  verification remains pending that task; no test pass is claimed (default).
- 2026-10-20 planning: design R2/R7/R8/R9 settled by isolated negative E2E
  repositories, the additive `migration-proofs` JSON command, Boolean descriptor
  semantics and explicit output changes: lint/history findings, row-7 proof gaps,
  approval declaration/commands and packet evidence gaps (default).
- 2026-10-20 planning: design R3/R4/R5/R6 limits documented: no skips/baselines in
  an applied replacement; protection ends with this goal unless a repository or
  later goal retains it; a new Founder-approved baseline remains a trust boundary;
  grammar supports only `python3` and `./py` (default).

- 2026-10-20 planning: the combined T1–T4 consumer gate passed in 392.00 s,
  `gate: PASS · exit 0 · 298 run / 0 failed / 0 skipped`; it includes modmap,
  gate, goal/docs, installer and every non-test check. Individual component
  timings above size the same families; full validation is still separate
  (default).

- 2026-10-20 planning: final T6 rules/install/repository gate passed in 51.36 s,
  `gate: PASS · exit 0 · 78 run / 0 failed / 0 skipped` (default).

- 2026-10-20 planning: plan review R1 resolved in the proposal with a new
  400-word reference and checked-file enumeration; existing word ceilings stay
  unchanged. Plan R2/R4 are covered by row-7/close pointers and README component
  and command entries; R3 explicitly uses preservation `--count none` (default).
- 2026-10-20 planning: plan R5 keeps final close evidence in ignored logs/PR
  packet; tracked measurements cite only earlier completed trees. Plan R6 splits
  structural admission (T3) from proof enforcement/presentation (T4), followed by
  E2E (T5) and documentation (T6); first two tasks remain parallel (default).

## Parked

- Design R3/R4/R5/R6 extensions: support for retained skips/baselines, a permanent
  cross-goal preservation registry, cryptographic approval history and additional
  interpreter paths are outside this goal. Their limits are documented in T6;
  none is required for the supported version-1 migration.
