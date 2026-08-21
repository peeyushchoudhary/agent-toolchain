# JUnit executed-test evidence

The nonce-receipt protocol that proves a Gradle/JUnit gate *ran*, fresh, and produced exactly the
declared tests. Moved verbatim from the methodology body in v3.0; the protocol and tooling are
unchanged from v1.5.

## The protocol

For JUnit, console output is not the count. Create a new start artifact immediately before the test
task:

```bash
python3 start_junit_run.py --results RESULT_DIR --output START.json
```

It contains a 256-bit nonce, timestamp, exact result path, and hashes of any direct XML already
present. Run the task with cache bypassed, then invoke:

```bash
python3 verify_junit.py --results RESULT_DIR --start-receipt START.json \
    --expect FQCN=N [--expect FQCN=N ...] --output RECEIPT.json
```

Every direct XML file must have both mtime and ctime strictly after the start boundary. The verifier
records the start hash and nonce and creates a consumption marker, so a valid pre-existing result or
a reused run receipt cannot certify a later invocation. Each expected class must have exactly its
declared testcase count — not merely a nonzero or aggregate minimum. JUnit failures, errors, and
skips all fail evidence verification. Cleaning remains good hygiene, but it is no longer the
freshness security boundary.

Exact `--rerun-tasks` is the sole Gradle freshness flag. `clean`, `cleanTest`, qualified clean
tasks, exclusions, properties, option operands, and every other token do not count.

## What this evidence does and does not detect

The shared JUnit result verifier binds the exact direct-XML directory to a single-use
nonce/timestamp start boundary, proves required classes and counts from XML, rejects ambiguous or
inconsistent results, and emits a new JSON receipt bound to that start artifact.

JUnit evidence detects accidental pre-existing, same-content, unchanged, malformed, replayed,
failed, errored, skipped, or count-inconsistent results. It does not detect a cache restore that
writes plausible valid XML after the boundary. Exact runner rerun settings prevent cache use;
Gradle requires exact `--rerun-tasks`. It is **not tamper-resistant** against a deliberate local
writer controlling both XML and evidence files; it is a freshness and consistency check inside that
trust boundary, not hostile-writer attestation.

## Tracing a criterion to an executed test

`trace_check.py` diffs three sets and prints the gaps: REQUIRED (the criteria in feature specs),
DECLARED (the coverage map and the `covers:` of each ```test block in the feature plan) and
EXECUTED (the ids carried by testcases in XML this protocol already certified). It writes nothing,
exits 0 clean, 1 on findings and 2 when an input could not be read.

```bash
python3 trace_check.py --root . --evidence .work/reports/EX-01-junit.json [--evidence ...]
```

**What it proves, and what it does not.** It proves a test **carrying that id ran and passed**
inside a verified green run. It does **not** prove the test asserts anything: `void ac2() {}`
passes and is counted. No line of its output may be read as "the criterion is met", only as "a test
claiming it ran". The plan's `assert` and `and_not` fields and one reviewer round close that gap;
no checker does.

**The carrier is the test's own name.** Measured over 51,604 result files and 267,943 testcases on
one real backend: `<property>` elements number **zero**, so `@Tag` and JUnit properties never reach
the XML this protocol reads. `name=` and `classname=` always do.

```
<behaviour>__F<feature>_AC<n>      resendsInWindow__F7_AC2      one test, many ids: __F7_AC2_AC4
F-7/AC-2                           the same id in prose: a coverage row, a `covers:` line
```

**Both attributes are read, and this is not belt-and-braces.** 3.0% of those testcases (8,063) are
parameterised and render as `name="[2] 2026-12-31, 26"` — the method name is not in the file at
all. Keying on `name=` alone makes every table-driven test invisible, fires the "no executed test"
rule on criteria that *are* tested, and makes "stop writing parameterised tests" the cheapest way
to a green checker. That is a bookkeeping rule dictating test design. So the id may sit on the
class instead, and the count of testcases attributable to **neither** is printed on every run: an
unattributable testcase is not a pass, it is a test this mechanism cannot see.

**A bare `AC-4` in a test name is refused, not guessed at**, because most feature specs in a real
corpus have an AC-4 and an unqualified id names none of them in particular. Inside a plan the
file's own `feature:` key qualifies it, so a bare id there is unambiguous and correct.

| rule | finding |
|---|---|
| `T0` | an input that cannot be trusted: an approved-or-later spec parsing to no criteria, a plan with no `feature:`, a coverage row with an unknown level |
| `T1` | a criterion in an approved-or-later spec with no row in its plan's coverage map |
| `T2` | a coverage row or planned test naming a criterion the spec does not declare |
| `T3` | a criterion whose level is not `none` and which no executed test carries |
| `T4` | an executed test citing an id no spec declares, or citing one without its feature |
| `T5` | a criterion in the absence claim AND carried by a coverage row — two answers |
| `T6` | an executed test citing an id the spec retired in `withdrawn:` |
| `T7` | *(`--commit RANGE` only)* a criterion whose id ARRIVED in that range on a test whose body the range never touched |
**Why this is not grep.** The executed set never comes from the source tree. It comes from XML the
verifier above already bound to a single-use nonce, proved count-consistent, skip-free and green. A
string in a comment cannot enter it and a disabled test cannot enter it.

**The window is closed at both ends.** The start receipt is a *lower* bound only, so XML written
after the gate went green still satisfies it — a second, narrower `--tests '*AC4*'` run would read
as proof. `trace_check.py` therefore also requires each file's mtime to be no later than the
receipt's `verified_at_utc`, and requires the file count, the class set and the testcase total
still to match what was certified. A result directory that moved on since the receipt was issued
ends the run with exit 2 rather than reporting a clean trace.

**An absent input is named, never silent.** No feature plans, or no `--evidence`, exits 0 and says
which input was missing. "Traced clean" and "traced nothing" must never print the same way.

## T7 — an id that arrived without the work

T3 asks one question: did a test carrying this id run and pass. **Renaming an already-green test
answers it in full.** Scanned across four sibling repositories: **1,073 Java test files, 5,866
`@Test` methods, and zero of them carrying a criterion id.** The migration T3 asks for is therefore
a bulk rename of about six thousand methods, and the cheapest way to finish that migration is to
change nothing else. This is not a theoretical shortcut; it is the default path.

```bash
python3 trace_check.py --root . --evidence .work/reports/EX-01-junit.json --commit F6..HEAD
```

`--commit` takes one commit or an `A..B` range, the same way `plan_waves.py --commit` does. For
every criterion T3 reports green, T7 asks whether that criterion's id **arrived inside the range**,
and if it did, whether the test carrying it also had **body lines added, changed or removed** there.
A rename writes one signature line and no body line, so T7 fires on it.

**What T7 proves and does not prove.** It proves the range touched that test's body. It does **not**
prove the body asserts anything — a body changed to `{ /* TODO */ }` satisfies T7 exactly as a real
assertion does, because "the body changed" is all a diff can say. It also fires on an **honest**
rename: a commit that improves a test's name without touching its body looks identical to one that
farms coverage, and T7 cannot tell them apart. Carry the id in the commit that writes the test.

**It parses no language.** T7 matches the executed test's own `name=` (or `classname=` when the id
lives there) against changed line numbers in a diff, and bounds the body by indentation alone: from
the line the id arrived on, forward until a non-blank line indented no further. Java closes on `}`
at the signature's indent, Python on the next `def`, and neither is named anywhere in the rule. A
Java-shaped rule was rejected deliberately — an assertion-token regex flags 0.55% of 5,866 Java test
methods and 4.30% of 32,141 Python test functions, an eightfold difference that is the "a rule
matched a WORD not a STRUCTURE" failure waiting to happen.

**Three decisions that came out of the corpus, not out of fixtures.**

- **"Arrived" is decided against the LEFT side of the range, not against the added lines.** One real
  project keeps a pinned-defect registry that names its own test methods in string literals, so
  editing that registry made long-standing tests look newly named: **18 of 494 judgeable methods,
  3.6%**, all false. A token is new only when the file it lands in did not already contain it.
- **A removed body line counts as a touched body.** The single disagreement in 581 judgeable methods
  of another repository was a commit that renamed a test and moved eight of its assertion lines into
  a new one: the body changed by subtraction. This costs the rename check nothing, because renaming
  deletes the signature line and never a body line.
- **Only the file that owns the class can answer for it.** `classRegistryIsComplete` exists in
  several suites of one real project, and a repository-wide token search let an unrelated file's
  added body satisfy the claim.

**An id older than the range is counted, never passed.** T7 has no opinion on work that predates
`RANGE`, and every run prints how many criteria fell into that bucket, next to how many it judged.
An inert T7 has to read as inert.

