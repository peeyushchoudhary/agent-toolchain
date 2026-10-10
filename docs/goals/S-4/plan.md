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

`defines_test` in `goal.py` recognises a runnable JUnit test method in a `.java` or `.kt` file, so a
closure naming one closes its finding (AC1), while an unannotated, disabled, bodiless, commented, string-only
or near-miss name still does not (AC2), and JavaScript and Python closures are judged as before
(AC3). Spec: [spec.md](spec.md).

## Tasks

### [x] T1 — defines_test recognises a runnable JUnit method in a .java or .kt file
writes: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py
reads: install/skills/execution-methodology/scripts/goal.py, install/skills/execution-methodology/tests/test_goal.py, install/skills/execution-methodology/tests/fixtures/goal_fixture.py
tests-may-change: install/skills/execution-methodology/tests/test_goal.py
`defines_test(body, name)` (goal.py line 394) takes the file's path as a new third parameter,
`path`, passed by its one caller in `review_findings` (line 439). For a path ending `.java` or
`.kt` it applies only the JUnit rule below; every other path keeps today's JavaScript and Python
rules unchanged (AC3). The closure line's parser (line 423) does not change.

The JUnit rule, failing closed at each step (AC1, AC2):
1. `name` with a `.` or `::` in it fails: only a bare method name closes.
2. Blank out `//` comments, `/* … */` blocks, text blocks and Kotlin raw strings (`"""…"""`),
   string literals and character literals, keeping newlines and every other character's position,
   so braces left in the body are code.
3. Find each declaration of `<m>`: the exact name, a word boundary on both sides, then `(`, where
   the text before it on the declaration is only annotations, modifiers, a return type, generic
   parameters and, for Kotlin, `fun`. A declaration counts only when, after its balanced parameter
   list and any `throws` clause, the next token is `{` (Java or Kotlin) or `=` (a Kotlin expression
   body); `;` or anything else is a declaration without a body and does not count.
4. The annotation run immediately before it (annotations, each with an optional balanced argument
   list, separated only by whitespace and modifiers) must hold one of `JUNIT_TEST_ANNOTATIONS` =
   `Test`, `ParameterizedTest`, `RepeatedTest`, `TestFactory`, `TestTemplate`, either bare or
   qualified by one of `JUNIT_PACKAGES` = `org.junit.jupiter.api.`, `org.junit.jupiter.params.`,
   `org.junit.` (the last for JUnit 4 `@Test` only). Any other qualifier does not count. The run
   must hold no `@Disabled…` (any annotation whose simple name starts `Disabled`) and no `@Ignore`.
   Its modifiers must not include `private` or `static`.
5. Walk the brace depth from the file's start to the declaration. Each enclosing `{` must open a
   `class` declaration, never an `interface`, `enum`, `record`, `object` or method body. The
   outermost class may carry any annotations but no `@Disabled…` or `@Ignore`; every inner class
   must carry `@Nested` and none of those disabling annotations.
6. The closure holds when at least one declaration passes 3–5.

Name the two sets as module constants beside `SKIP_RE`, and update the docstring.

Tests. `test_closure_requires_an_exact_discoverable_test` (test_goal.py line 491) keeps its rows
(AC3). A new test beside it, `test_closure_accepts_an_annotated_junit_method`, writes its Java and
Kotlin files under `tests/` (fixture task T2's `tests/**` writes cover them, so row 4 stays clean;
check with `assertRowOk(8)` on a positive row first). It assembles every `@Disabled` and `@Ignore`
fixture string at runtime, the way `SKIP_DECORATOR` (line 30) does, so S-4's own row 5 sees no skip
marker. Accepted rows (AC1): Java `@Test void m() {}`; `@org.junit.jupiter.api.Test`; JUnit 4
`@org.junit.Test public void m()`; `@ParameterizedTest @ValueSource(ints = {1, 2})` before
`void m(int x)`; `@Timeout(5) @DisplayName("a (b)")` between `@Test` and the method; a `throws`
clause; `@TestFactory Stream<DynamicTest> m()`; a method in a `@Nested class Inner`; Kotlin
`@Test fun m() {}` and `@Test fun m() = runTest {}`. Refused rows (AC2): no annotation; `@Test`
with `@Disabled`; `@Test` with `@DisabledOnOs(...)`; a disabled outer class; `@Ignore` JUnit 4;
`@org.testng.annotations.Test`; `@Test abstract void m();`; `@Test void m();` in an `interface`;
a method in an unmarked inner class; `private` and `static` methods; the method only in a `//`
comment, in a `/* */` block, in a string, in a Java text block and in a Kotlin raw string; a
`@Test` on the previous method with `m` declared after it unannotated; the names `m2` and `xm`
against `m`; and `Outer.m` and `Outer::m`. Do not touch any other rule, test or file.

## Decisions

- 2026-10-10 plan review (codex gpt-6) R1–R9, resolved in the spec and plan before approval. R1:
  only a concrete method with a body counts; `private` and `static` fail. R2: a qualified closure
  name fails, and an inner class must be `@Nested`. R3: a disabled enclosing class fails. R4:
  Kotlin backticked names are a non-goal, so the closure parser does not change. R5: AC2 wins over
  AC1. R6: only the JUnit packages qualify an annotation. R7: disabling fixture strings are built at
  runtime. R8: the fixture module is read, and the fixture files go under `tests/`. R9: the accepted
  and refused rows are named.
- 2026-10-10 founder: fix the upstream tool so a JUnit closing test counts ("Fix it upstream"),
  committed locally, not pushed; reinstall after the goal closes.
- 2026-10-10 T1 (builder, default): `@Nested` counts bare or as `org.junit.jupiter.api.Nested`.
  Braces inside parentheses (annotation arrays, lambda arguments) are not enclosing classes. A
  top-level Kotlin function is refused. `=` opens a body only in `.kt`. A Kotlin declaration starts
  after a line holding more than annotations and lowercase words.

## Parked

- Step 3 refuses a Kotlin method with an explicit return type (`fun m(): Unit = …`). Kotlin nested
  block comments and a class header split after `:` are refused too. All fail closed; a follow-up
  goal can widen them.
