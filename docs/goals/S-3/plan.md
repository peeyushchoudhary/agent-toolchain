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

### [ ] T1 — anchor HOME_PATH with a lookbehind; table rows and a self-test fixture
writes: install/skills/execution-methodology/scripts/guard.py, install/skills/execution-methodology/tests/test_guard.py
reads: install/skills/execution-methodology/scripts/guard.py, install/skills/execution-methodology/tests/test_guard.py
tests-may-change: install/skills/execution-methodology/tests/test_guard.py
`HOME_PATH` (guard.py line 22) becomes `(?<![A-Za-z0-9._-])/(?:Users|home)/([A-Za-z0-9._-]{2,})`,
still case-insensitive. `CommitRulesTest.test_staged_content_table` (test_guard.py line 139) gains
rows in the table's shape, with the package path `app/core/users/` + `UserDtos.java` (one
string): a staged line holding it, expecting 0 (AC1); the same path inside backticks, expecting 0
(AC1); the test module's `HOME_PATH` constant after `a=`, and its `/home` twin inside parentheses,
expecting 1 with "absolute home path" (AC2). `self_test()` (guard.py line 293) gains that package
path as a case expecting 0 and its PASS count follows (AC3). Keep the `"/Users" + "/…"` split in
both files. Do not touch any other rule, test or file.

## Decisions

- 2026-10-09 T1: the example package path is `app/core/users/…`; the downstream project's own
  package name stays out of this public repository (default).

## Parked
