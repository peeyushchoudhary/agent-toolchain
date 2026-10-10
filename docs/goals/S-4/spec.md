# S-4 spec: a JUnit test method can close a review finding

**Users and problem.** The founder running a goal in a Java or Kotlin project. `goal.py done` row 8
accepts a `resolved-by <sha> closes <path>::<name>` closure only when `defines_test` finds a
JavaScript `it/test('<name>')` or a Python `def test…`, so a JUnit closing test never counts. Every
blocking finding fixed in such a project stays unclosed, and the milestone never prints DONE.

**What changes for the user.** A closure naming a JUnit test method in a `.java` or `.kt` file
closes its finding, under the same rules a Python or JavaScript test already meets.

**Acceptance criteria.**

- AC1 WHEN a closure names `<file>.java::<m>` or `<file>.kt::<m>` and the file declares a method
  `<m>` carrying `@Test`, `@ParameterizedTest`, `@RepeatedTest`, `@TestFactory` or `@TestTemplate`
  (bare or package-qualified, with or without arguments, other annotations or modifiers between),
  and the fix commit changed the file, THE SYSTEM SHALL accept the closure. A Kotlin `fun <m>(`,
  including a backticked name, counts the same; `<Cls>.<m>` counts when the file declares
  `class <Cls>`.
- AC2 WHEN the named method has no test annotation, carries `@Disabled` or `@Ignore`, appears only
  in a comment or a string, differs from a declared test by a prefix or suffix, or `<Cls>` is not
  declared in the file, THE SYSTEM SHALL name the finding on row 8.
- AC3 WHEN a closure names a JavaScript or Python test THE SYSTEM SHALL judge it as before.

**Non-goals.** Nested-class qualification beyond one class name, JUnit 3 `test…` naming without
annotations, TestNG, Kotest, Spock, C#, Swift, and every other row of `goal.py done`.

**Constraints.** Standard-library Python 3. No downstream project name enters this public
repository; fixtures use neutral names.
