---
goal: S-1
title: Simplify the execution methodology to v7 (D29)
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1, T2, T3, T4, T5], e2e: "install/tests/e2e_install.sh"}
  M2: {tasks: [T6, T7, T8, T9], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [none]
protected: [docs/decisions/decisions.md#D1-D19]
---

## Outcome

`install/` ships the v7 shape to both harnesses from one source: one `plan.md` format, `gate.py`
receipts, an eight-row mechanical `goal.py done`, `run.sh` for unattended runs, one adversarial
review by the other vendor at design, plan and merge with no rounds, one guard installed with the
skill. Always-loaded prose is at or under 1,350 words; `install/` non-test code is measured and
recorded; `docs/` states current state in about 4,300 words; `e2e_run.sh` runs a two-task goal for
real in each harness on its own fresh repository and exits 0. `verify.sh` is green after every task.
Decision record: D29. The v7 design is written into `docs/architecture/methodology.md` by T8.

## Format notes (frozen with this plan; T2 teaches `goal.py` to read them)

`milestones:` names each milestone's tasks and its e2e command; a milestone is done when `done`
holds for its tasks and PASS receipts exist on HEAD's tree for `full_gate` and its `e2e`. Task
lines: `### [ ] Tn — title`, then `writes:` and optional `tests-may-change:` lines, then prose.
Ticks: `[ ]`, `[x]` (gate green, committed as `[Tn]`), `[!]` parked with a Parked line. Every task's
`writes` include `docs/**` for reference repairs only: when a task deletes a file, it removes or
rewrites the docs rows and links that name it in the same commit, so the link check and the
pre-commit route check stay green; new documentation waits for T8.

## Tasks

### [ ] T1 — decision record D29, this plan, the index row
writes: docs/decisions/decisions.md, docs/README.md, docs/goals/S-1/plan.md

### [ ] T2 — `goal.py` v7; cut the review loop and the driver together
writes: install/skills/execution-methodology/**, install/hooks/goal-session.sh, install/install.sh, install/verify.sh, install/README.md, install/tests/test_install.py, docs/**
tests-may-change: install/skills/execution-methodology/tests/**, install/tests/test_install.py
Delete together, because they import or test each other: `review.py`, `run_goal.py`,
`goal-session.sh` and its registrations, `smoke_goal.py`, `smoke_review_closure.py`,
`test_review*.py`, `test_run_goal.py`, `references/review.md`, `references/escalation.md`,
`references/explainer-template.html`, `agents/openai.yaml`; every reference to them in `SKILL.md`,
`methodology.md`, `run.md`, `planning.md` (minimal edits; T6 rewrites these files).
`goal.py` (≈300 lines): a parser for this plan's format (frontmatter `milestones:`, task lines,
`writes:`/`tests-may-change:` lines, Decisions, Parked); `lint`; `status`; `next`; `resume` (≤150
words: title, Outcome, status, last 20 progress lines; this replaces `goal-session.sh`); `packet`
(plain text: Outcome, diff stat, the done table with evidence, receipts, findings with resolution
shas, Decisions, Parked, widenings); `stop-hook` (15 lines: run `done`, block with the unmet rows up
to three times, then allow); and `done` with exactly these rows: (1) every task of the milestone
`[x]`, or `[!]` with a Parked line; (2) clean tree; (3) every commit since `goal/<id>/approved`
names one `[Tn]` or is plan-only (`<id>:` prefix, diff limited to ticks, Decisions, Parked, or a
`writes:` widening); (4) each `[Tn]` commit's paths lie inside Tn's `writes` **as read from
`plan.md` at that commit's parent**, and no `writes` glob at HEAD intersects `protected`; (5) no
existing test modified or deleted outside `tests-may-change`, no `skip/only/xfail` marker added;
(6) frontmatter, Outcome, Format notes and task headers identical to the approved commit's; (7)
PASS receipts for `full_gate` and the milestone's `e2e` whose `tree` equals HEAD's; (8)
`.runs/<id>/review.md` with `reviewed: <sha>` where `<sha>` is an ancestor of HEAD, every commit in
`<sha>..HEAD` is a `[Tn][Rn]` fix commit named by a `- [x] Rn resolved-by <sha> closes <test
path::name>` line (the test exists at HEAD and changed in that commit) or a `removed-by <sha>` line
(that commit's diff removes the paths the finding names), no `- [ ] BLOCKING` line remains, and the
row-7 receipts are on HEAD. `guard`, `attempt`, `evidence` and the envelope are deleted.
New `scripts/run.sh` (≈60 lines): `<goal> --harness claude|codex --sessions N`; one session =
`claude -p "$(goal.py resume)"` with a settings file registering the Stop hook, or `codex exec
--sandbox workspace-write --ask-for-approval never "$(goal.py resume)"`; stops on DONE, PARKED,
STALLED (two sessions with no new tick or `[Tn]` commit), sessions exhausted; macOS notification;
`packet.md` on DONE. `install.sh` registers `goal.py stop-hook` for both harnesses in place of the
old hook block. `test_goal.py` (≈300 lines) plants: an out-of-scope edit followed by a retrospective
widening (row 4 names the commit); a `@skip` added to an existing test (row 5); a review file whose
`reviewed:` is followed by a non-fix commit, and a fix commit without a closing test (row 8); plus
the parser on this very plan (nine tasks, two milestones). One test for `run.sh` with a fake harness
command. From this task on, `done` rows 3–8 apply to S-1 itself.

### [ ] T3 — cut graph context and the SessionStart report hooks
writes: install/hooks/**, install/skills/.gitignore, install/skills/graph-navigation/**, install/skills/progressive-disclosure/scripts/install_hooks.py, install/skills/progressive-disclosure/tests/test_install_hooks_*.py, install/install.sh, install/verify.sh, install/tests/test_install.py, docs/**
tests-may-change: install/skills/progressive-disclosure/tests/test_install_hooks_*.py, install/tests/test_install.py
Delete `graphify-query-advisor.py`, `graphify-session-lessons.sh`, `preflight.sh`,
`disclosure-check.sh` and their registrations; the `graph-navigation` skill and its `.gitignore`
line; the graph blocks, guard blocks and `--graph-only` in `install_hooks.py` and their tests
(`_graph_only`, `_guard`; `_scope` and `_deps` keep their non-graph cases). `install/hooks/` is empty
afterwards and removed.

### [ ] T4 — one guard, shipped inside the skill; `git-hooks.sh`
writes: install/skills/execution-methodology/scripts/guard.py, install/skills/execution-methodology/scripts/git-hooks.sh, install/skills/execution-methodology/tests/test_guard.py, install/skills/execution-methodology/tests/test_git_hooks.py, install/skills/progressive-disclosure/**, install/tests/**, install/verify.sh, install/install.sh, .gitignore, docs/**
tests-may-change: install/skills/progressive-disclosure/tests/**, install/tests/**
New `guard.py` (size follows coverage; ≈150 lines expected): staged content and commit messages for
home paths, emails, the private-name list and secret patterns; the pushed range for secrets and
files over 10 MB; direct push to the default branch; `--self-test`. It carries its own secret
patterns (today `push_guard.py` imports them from `validate_disclosure.py`). `test_guard.py` runs it
against every case of `identifier_guard_selftest.py` and `push_guard_selftest.py`: every blocking
case blocks, every legitimate push passes; only then are `identifier_guard*.py`, `push_guard*.py`,
`install_hooks.py` and its remaining tests deleted. New `git-hooks.sh` (≈60 lines) writes
pre-commit, commit-msg and pre-push through `git rev-parse --git-path hooks`, honouring
`core.hooksPath`, pointing at the installed skill's `guard.py` and refusing when that file is absent;
`test_git_hooks.py` covers the `core.hooksPath` case and the absent-guard refusal. `verify.sh` runs
`guard.py` over this tree in place of `identifier_guard`. The builder runs `git-hooks.sh` on this
repository so its own pre-commit and pre-push use the new guard (a local `.git/hooks` write; the
Decisions line records it).

### [ ] T5 — cut the checkers; a link check; M1's e2e script
writes: install/skills/progressive-disclosure/**, install/skills/.gitignore, install/verify.sh, install/install.sh, install/tests/**, AGENTS.md, docs/**
tests-may-change: install/skills/progressive-disclosure/tests/**, install/tests/**
Delete `check_github.py`, `check_toolchain.py`, `migrate_to_standard.py` and its selftest,
`validate_disclosure.py`, their tests, `hermetic.py` (moved to `install/tests/`), `SKILL.md`,
`references/standard.md`, then the empty `progressive-disclosure` skill and its `.gitignore` line.
`verify.sh` gains a 20-line Python link check over `AGENTS.md`, `README.md` and `docs/**` (relative
links resolve; `decisions.md#dNN` anchors exist), replacing the route validator in the gate and in
the pre-commit hook written by T4. Root `AGENTS.md` gate line updated. New
`install/tests/e2e_install.sh`: installs into a disposable `HOME` for both harnesses with the real
`install.sh`, asserts the skill, `goal.py`, `guard.py` and one Stop-hook registration per harness
are present, runs `goal.py --help` from each installed copy, and exits 0. **M1 ends here**: the
other vendor's diff review of `goal/S-1/approved..HEAD`, `done` for M1, merge.

### [ ] T6 — the instructions; cut personas
writes: install/global.md, install/skills/execution-methodology/SKILL.md, install/skills/execution-methodology/methodology.md, install/skills/execution-methodology/references/**, install/skills/execution-methodology/agents/reviewer.md, install/skills/execution-methodology/tests/test_rules.py, install/skills/agent-personas/**, install/skills/.gitignore, install/install.sh, install/verify.sh, install/tests/test_size.py, install/tests/test_install.py, AGENTS.md, docs/**
tests-may-change: install/skills/execution-methodology/tests/test_rules.py, install/tests/test_size.py, install/tests/test_install.py, install/skills/agent-personas/tests/**
`SKILL.md` ≤900 words / ≤200 lines: the per-task loop, the `plan.md` format, the done contract in
words, authority boundaries (defaults and logs; parks for the founder), the review procedure (the
other vendor's adversarial reviewer at design, plan and merge; one round; blocking closed by test or
removal), the resume procedure. `references/design.md` ≈150 words (one-page design format and the
design-review prompt). `agents/reviewer.md` ≈120 words: the adversarial reviewer prompt run through
the other vendor's read-only CLI. New `install/global.md` ≤150 words. Root `AGENTS.md` ≤300 words.
Delete `methodology.md`, `run.md`, `planning.md`, `migrate.md`; the `agent-personas` skill, its
`.gitignore` line and its tests; `install.sh` stops rendering personas; `verify.sh` drops the
render-parity block. `test_size.py` becomes one assertion (always-loaded files ≤200 lines each,
≤1,350 words in total); `test_rules.py` reads the new files or is deleted.

### [ ] T7 — `install.sh` and `verify.sh` rewritten to the new file set
writes: install/install.sh, install/verify.sh, install/README.md, install/tests/test_install.py, install/preserve_selftest.sh, install/skills/README.md, docs/**
tests-may-change: install/tests/test_install.py
`install.sh` ≈120 lines: copy `global.md` to `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` after
backing up any existing file to `<name>.bak-<date>`; copy the skill (with `guard.py`, `run.sh`,
`git-hooks.sh`, `agents/`) to both homes; register one Stop hook per harness; `--dry-run`;
`--uninstall` removes every file and registration it installs and restores the backups;
`--retire-v5` extended with every v6 file T2–T6 deleted. Rollback is therefore `./install.sh
--uninstall` on the v7 tree, then `git checkout methodology/v6-base -- install && cd install &&
./install.sh`. `verify.sh` ≈120 lines: the unittest suites, `guard.py --self-test`, the size test,
`guard.py` over the tree, the link check, a dangling-name check for every deleted component name
(`review.py`, `run_goal`, `sync_personas`, `graphify`, `preflight`, `validate_disclosure`,
`check_github`, `install_hooks`, `identifier_guard`, `push_guard`, `agent-personas`,
`progressive-disclosure`, `graph-navigation`), `--installed` parity against both homes. Delete
`preserve_selftest.sh` and `skills/README.md`.

### [ ] T8 — `docs/` rewritten to current state
writes: README.md, docs/**, NOTES-break-tests.md
Target about 4,300 words: root `README.md` ≤500; `docs/README.md` one index ≤150;
`docs/architecture/methodology.md` ≤700 (the v7 design and accepted risks, from the council papers);
`docs/architecture/repository-standard.md` ≤300; `docs/decisions/decisions.md` with every D-id as a
one-line row and full text for D2, D3, D4, D17, D18, D29; `docs/product/measurements.md` ≤600
(dated, plus the pilot table and the `install/` line count); `docs/runbooks/github.md` ≤300,
`codex.md` ≤250, new `migrate-v5.md` ≤200 (the per-project migration commit, including the pilot's);
`docs/archive/README.md` ≤120 pointing at `goal/F-3/*`, `methodology/v6-base` and
`archive/v6-followups-2026-10-09`. Delete `docs/agents/**`, `lean-execution.md`,
`operating-model.md`, the F-3 spec and plan, `improvements-weekly.md`, `assets/readme/**`,
`runbooks/global-instructions.md`, `NOTES-break-tests.md`. History and the tags keep them.

### [ ] T9 — local end-to-end run; install, uninstall and rollback rehearsal; measurements
writes: install/skills/execution-methodology/tests/e2e_run.sh, docs/product/measurements.md
`e2e_run.sh`: for each harness separately, creates a fresh scratch repository with a two-task
`plan.md`, runs `run.sh --harness <h> --sessions 3` for real, and asserts that harness's `goal.py
done` prints DONE and its `packet.md` exists; then, in disposable homes, runs `install.sh`,
`install.sh --uninstall`, the D29 rollback (`git checkout methodology/v6-base -- install` from a
temporary worktree, `install.sh`), and diffs installed files and registrations at each step against
the expected sets. Records in `measurements.md`, dated: both harnesses' wall time and session counts,
`install/` non-test and test line counts (the design expected ≈2,300 non-test with the one guard),
always-loaded words, and the recurring operating cost of one unattended session. **M2 ends here**:
the other vendor's diff review, `done` for M2, merge.

## Decisions

- 2026-10-09 founder: shape B; one replacement guard; F-3 merged as the base (`methodology/v6-base`),
  F-4 and F-5 archived (`archive/v6-followups-2026-10-09`); S-1 approved with two milestones.
- 2026-10-09 founder: the other vendor's adversarial reviewer runs at design, plan and merge, one
  round each, no grant. For S-1: no design page (touches none; the council design had two Astra
  passes); this plan was reviewed once by Astra before the approval tag (below); the M1 and M2 diff
  reviews are Astra's, written to `.runs/S-1/review.md` in the row-8 format.
- 2026-10-09 Astra plan review, round 1: BLOCK, 11 blocking and 1 non-blocking. All resolved in this
  plan, no second round (D29): tasks that import or test each other are deleted together (the review
  loop with the driver; the guards after the checkers' consumers are gone; personas with the size
  and rules tests); every cut task repairs the docs rows and links that name what it deletes; the
  parser and all eight `done` rows are assigned to T2 with the planted cases; `milestones:` carries
  each milestone's e2e, and M1's is a real install into disposable homes created in T5; row 8 binds
  `reviewed:` to an ancestor of HEAD with only recorded fix commits after it; the guard ships inside
  the skill and `git-hooks.sh` refuses when it is not installed; `install.sh` gains `--uninstall`
  with backups and the retire list covers T6's deletions; T9 runs each harness on its own fresh
  repository and measures `install/` line counts. The pilot migration (old T12) leaves this plan: it
  is the pilot repository's own first commit, described in `migrate-v5.md`.
- 2026-10-09 widening: T2 `writes` gains `install/README.md`, which names the driver and the session
  hook T2 deletes; the repair belongs to the deleting commit (Format notes).
- 2026-10-09 until T2 lands, the per-task check is `verify.sh` green plus a `[Tn]` commit; `done`
  rows 3–8 apply from T2 on.

## Parked

- Replacing the private global instruction files with `global.md` (founder, at the global install;
  `install.sh` backs them up first).
- Stranded product branches (founder, separate from the pilot; archive is the council's default).
- Push of `main` and tags (founder, after M2).
- Pilot on the OS project (founder decision 2026-10-09, replacing the council's astrology-app
  pick): the founder migrates it by hand after M2 using `migrate-v5.md`, works its milestones, and
  reviews how the methodology did after one week; the four-week stop rule still applies.
