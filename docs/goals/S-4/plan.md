---
goal: S-4
title: A JUnit test method can close a review finding on goal.py done row 8
gate: cd install && ./verify.sh
full_gate: cd install && ./install.sh --dry-run && ./verify.sh
milestones:
  M1: {tasks: [T1], e2e: "install/skills/execution-methodology/tests/e2e_run.sh"}
touches: [none]
protected: [docs/decisions/decisions.md]
---

## Outcome

`defines_test` in `goal.py` recognises a JUnit test method in a `.java` or `.kt` file, so a
closure naming one closes its finding (AC1), while an unannotated, disabled, commented, string-only
or near-miss name still does not (AC2), and JavaScript and Python closures are judged as before
(AC3). Spec: [spec.md](spec.md).

## Tasks

### [ ] T1 — defines_test recognises an annotated JUnit method in a .java or .kt file
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
`defines_test(body, name)` (goal.py line 394) takes the file's path as a new third parameter,
`path`, passed by its one caller in `review_findings` (line 439). For a path ending `.java` or
`.kt` it applies only the JUnit rule; every other path keeps today's JavaScript and Python rules
unchanged (AC3). The JUnit rule: drop `//` line comments, `/* … */` blocks and string literals
from the body; split `name` on `.` or `::` into an optional single class name and the method (two
or more qualifiers fail); a class name must appear as `class <Cls>` in the stripped body; then the
method is a test when a run of annotations immediately before its declaration includes one of
`Test`, `ParameterizedTest`, `RepeatedTest`, `TestFactory`, `TestTemplate` (optionally
package-qualified, optionally with a parenthesised argument list that may itself hold one level of
parentheses), no annotation in that run is `Disabled` or `Ignore`, and only modifiers, a return
type and, for Kotlin, `fun` stand between the run and `<m>(`, where `<m>` is the exact name (a
word boundary on both sides) or, in Kotlin, the name in backticks (AC1, AC2). Name the annotation
set `JUNIT_TEST_ANNOTATIONS`, a module constant beside `SKIP_RE`; update the docstring.
`test_closure_requires_an_exact_discoverable_test` (test_goal.py line 491) keeps its rows; a new
test beside it, `test_closure_accepts_an_annotated_junit_method`, writes a `.java` and a `.kt`
test file under `src/test/` and checks each accepted shape of AC1 with `assertRowOk(8)` and each
refused shape of AC2 with `assertRow(8, "R1: closes …")`. Do not touch any other rule, test or
file.

## Decisions

- 2026-10-10 founder: fix the upstream tool so a JUnit closing test counts ("Fix it upstream"),
  committed locally, not pushed; reinstall after the goal closes.

## Parked
