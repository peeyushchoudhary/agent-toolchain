---
goal: S-3
title: The guard's home-path rule matches only an absolute path, not a package path through users/
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1], e2e: "install/tests/e2e_install.sh"}
touches: [none]
protected: [docs/decisions/decisions.md]
---

## Outcome

`guard.py`'s home-path rule requires that `/Users/` or `/home/` is not preceded by a path or word
character, so a package path through `users/` commits and an absolute home path still does not
(AC1, AC2); `guard.py --self-test` carries a package-path fixture (AC3). Spec: [spec.md](spec.md).

## Tasks

### [x] T1 — a relative path segment before /Users or /home is not a home path; table rows and a self-test fixture
writes: install/skills/execution-methodology/scripts/guard.py, install/skills/execution-methodology/tests/test_guard.py
reads: install/skills/execution-methodology/scripts/guard.py, install/skills/execution-methodology/tests/test_guard.py
tests-may-change: install/skills/execution-methodology/tests/test_guard.py
`HOME_PATH` (guard.py line 22) keeps its pattern. `find()` (line 107) skips a home-rule match when
the text before it ends in a run of path characters `[A-Za-z0-9._-]` whose first character is not
`-`: the match is then a later segment of a relative path (`app/core/` + `users/…`), while a
compiler flag (`-I`, `-L`, `-isystem`) glued to an absolute path still fires. Name that run's
pattern `SEGMENT_BEFORE`, a module constant beside `HOME_PATH`.
`CommitRulesTest.test_staged_content_table` (test_guard.py line 139) gains rows in the table's
shape, with the package path `app/core/users/` + `UserDtos.java` (one string): a staged line holding
it, expecting 0 (AC1); the same path inside backticks, expecting 0 (AC1); the test module's
`HOME_PATH` constant after `a=`, inside backticks, and after `cc -I`, and its `/home` twin inside
parentheses and after `cc -L`, each expecting 1 with "absolute home path" (AC2). `self_test()`
(guard.py line 293) gains that package path as a case expecting 0 and `cc -I` + the fixture home
path as a case expecting 1; its PASS count follows (AC3). Keep the `"/Users" + "/…"` split in both
files. Do not touch any other rule, test or file.

## Decisions

- 2026-10-09 plan review R1 (Astra): a lookbehind that refuses any word character before `/Users`
  would also hide `-I/Users/…`; the rule instead looks at the run before the slash and treats a
  flag (first character `-`) as not a path segment. R2: an absolute path inside backticks gets its
  own row.
- 2026-10-09 T1: the example package path is `app/core/users/…`; the downstream project's own
  package name stays out of this public repository (default).

## Parked
