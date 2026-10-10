# S-4 spec: a JUnit test method can close a review finding

**Users and problem.** The founder running a goal in a Java or Kotlin project. `goal.py done` row 8
accepts a `resolved-by <sha> closes <path>::<name>` closure only when `defines_test` finds a
JavaScript `it/test('<name>')` or a Python `def test…`, so a JUnit closing test never counts. Every
blocking finding fixed in such a project stays unclosed, and the milestone never prints DONE.

**What changes for the user.** A closure naming a JUnit test method in a `.java` or `.kt` file
closes its finding when JUnit would run it; anything JUnit would skip or cannot run still does not.

**Acceptance criteria.**

- AC1 WHEN a closure names `<file>.java::<m>` or `<file>.kt::<m>` with a bare method name, the fix
  commit changed the file, and the file declares a concrete method `<m>` (a body follows its
  parameters and any `throws` clause) that is annotated `@Test`, `@ParameterizedTest`,
  `@RepeatedTest`, `@TestFactory` or `@TestTemplate`, bare or qualified only by a JUnit package, is
  neither `private` nor `static`, and sits in a top-level class or in classes marked `@Nested`,
  with no `@Disabled…` or `@Ignore` on it or on any class around it, THE SYSTEM SHALL accept the
  closure.
- AC2 WHEN any condition of AC1 fails THE SYSTEM SHALL name the finding on row 8, and AC2 wins over
  AC1. That covers a name only in a comment, string, text block or raw string; a near-miss name; an
  annotation from another namespace; a method with no body; an interface method; an unmarked
  nested class; and a qualified closure name.
- AC3 WHEN a closure names a JavaScript or Python test THE SYSTEM SHALL judge it as before.

**Non-goals.** Kotlin backticked names, `Class.method` closures for Java or Kotlin, interface
default methods, JUnit 3 naming, TestNG, Kotest, Spock, C#, Swift, and every other row of
`goal.py done`.

**Constraints.** Standard-library Python 3. No downstream project name enters this public
repository; fixtures use neutral names.
