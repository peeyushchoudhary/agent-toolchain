# The task card

One card per task, generated from the approved plan. The card is the implementer's entire world: it
does not read the plan, and it reads nothing the card does not name.

Cards live in the plan's scratch workspace. They are durable — a card and its report are what carry
decisions to the next plan, and they survive the workspace deletion by being promoted into the
program ledger's distillation.

## Schema

```yaml
id:                  # stable identifier — appears in the commit subject and the ledger
title:               # the card's NAME: one line, ≤ 72 characters, unique in the workspace.
                     # This is what prose, dispatches, and status reports lead with.
goal:                # one sentence: what is true after this task that was not before
persona:             # developer | senior-developer — which persona implements this card,
                     # decided by the planner, not at dispatch

prerequisites:       # task ids that must be complete first
exclusive_writes:    # paths ONLY this task may write — this is the parallelism contract
forbidden_paths:     # paths that must not change, even incidentally

context_acquisition: # a numbered recipe the agent RUNS, in order
frozen_values:       # verbatim values, never re-derived
invariants:          # what must remain true, and what fails closed if it does not
instructions:        # the work
tests:               # the tests to write, and the existing pattern to follow

gate_risk:           # bookkeeping artifacts this task touches
validation:          # direct {cwd, argv} processes, in order, that prove this task
stop_conditions:     # what makes this task stop rather than infer
record_to:           # docs/product/milestones/M<n>-<slug>.md — where a RECORD goes
handoff:             # who receives the report
commit_subject:      # the exact commit subject line
```

These eighteen keys are the complete current schema. Do not add local convenience keys: unknown
fields are ignored with a warning, and `--strict` rejects them. A title-bearing card is treated as
current and a missing field is an error. Titleless sealed cards retain the documented compatibility
diagnostic, but strict mode still rejects their omissions. `prerequisites`, `forbidden_paths`, and
`frozen_values` may be explicitly empty (`[]`); they may not be omitted.

Path globs are constraints only in `exclusive_writes` and `forbidden_paths`. A glob elsewhere is a
warning, as is a path expression in either path field that matches nothing today. Strict validation
rejects both. For a new file, put its exact repository-relative file path in `exclusive_writes`.
Strict pre-validation accepts that absent literal without warning; it does not extend this exception
to globs, metacharacters, directories, absolute paths, or `..` escapes. Strict post-validation
requires every write entry to resolve. This means a typo in an intended new-file literal is
deliberately caught post-implementation, when absence is distinguishable from planned creation.
Exact extensionless filenames such as `backend/core/Dockerfile` and `backend/core/.gitignore` are
valid file literals; a trailing slash or an existing directory is not.

`forbidden_paths` does not require the opposite existence rule. An absent normalized exact literal
is proof that the fence currently holds and is clean in both phases. An existing forbidden path or
matching boundary is also valid as long as it does not overlap `exclusive_writes`. An absent glob,
absolute path, escape, or metacharacter expression is not proof and remains a strict finding.

The approved plan owns one Goal Capsule; **there is no Goal Capsule field on the card**. Reference
the relevant criterion and invariant IDs through the existing `goal`, `invariants`, `tests`,
`frozen_values`, `exclusive_writes`, and `stop_conditions`. The card does not copy the capsule,
create a materialized form, or derive another authority. One primary outcome observation is always
accompanied by the named safety, negative, compatibility, and adjacent-regression invariants needed
to trust it; it is not a total cap on findings.

## The fields that carry the weight

### `id` and `title` — work is referred to by name, never by bare number

```yaml
id: TC-60
title: Hook roster is written once, not twice
```

Two rules, and both are machine-checked by `validate_card.py`:

1. **Every card has a title**: one line, non-empty, at most 72 characters, and not a restatement of
   the id. Seventy-two is the git subject-line convention — the place a title most often ends up
   quoted — and it still fits on an 80-column line after the id and two spaces. If the name will not
   fit, the detail belongs in `goal`.
2. **`id` and `title` are both unique across the cards in the workspace directory.** That directory
   is the scope because it is the one thing two controllers working at the same time share. The same
   id in a *different* plan's workspace is a different, legitimate card and is not a collision.

Why the pair rather than the number alone:

- **The number alone collides silently.** Two controllers each minted a card numbered `TC-60` within
  minutes of each other; one clobbered the other, and the work came back only because a human
  happened to notice. Nothing in the toolchain objected. Now the second one cannot be validated.
- **The number alone carries no meaning.** A status line reading `TC-52, TC-53, TC-54, TC-55` needs
  a translation table every time it is read, and fourteen such ids look like backlog volume where
  fourteen names would have shown a map of fourteen distinct problems.

The id keeps its job — it is the stable key in the commit subject, the ledger, and `prerequisites`,
and it must never be reused or renamed. The title is the half a reader can understand without
looking anything up. Lead with the title in prose and dispatches; keep the id beside it.

Cards sealed before this rule have no title. Re-validating one reports a WARNING and still exits 0,
so history stays readable. `--strict` promotes that warning to a non-zero exit, so a caller that
wants a titleless card refused has an invocation available that refuses it.

Be precise about what that does and does not guarantee: **`--strict` is available, not automatic.**
Nothing in this toolchain runs it for you — no hook, no gate, no conformance check — and the
dispatch contract permits dispatching over a warning that has been read. A missing title is
therefore a warning a controller is expected to notice, not a barrier that stops it.

### `exclusive_writes`

This is not documentation, it is the concurrency contract. Two tasks may run at the same time only
if their write sets are disjoint, and the orchestrator enforces that by reading these fields. A card
that lists a shared manifest, registry, or generated artifact here can never run concurrently with
anything.

Be exact. A glob that accidentally covers a shared file will serialize the whole plan or, worse,
will not.

### `context_acquisition`

A numbered list of things the agent **does**, not a description of context it should have. Prose
here becomes an agent reading whatever it feels like.

```yaml
context_acquisition:
  - "./scripts/agent-context.sh backend"        # branch, ledger head, index freshness
  - "read docs/agents/README.md — the backend row only"
  - "read <the repository's binding-invariants file>"
  - "read docs/agents/lessons.md — sections: 'Gradle', 'Testcontainers'"
  - "IF relationships are unclear: graphify query 'payroll statutory assignment'"
  - "Read nothing else unless this card names it. Do not read the plan."
```

The last line matters as much as the rest. Without it an agent reads the plan, the plan's siblings,
and half the ledger, and arrives at the work with a full context window and no room to think.

### `frozen_values`

Inline what must never be paraphrased. A retrieval step can get a payload shape subtly wrong, and
the consumer finds out later:

```yaml
frozen_values:
  - "POST /api/v1/fees/invoices/{id}/collect  request: {mode, reference?, amount_paise}"
  - "                                         response: {receipt_no, pdf_url}"
  - "event: fees.payment.recorded"
  - "receipt number format: RCP-<YY>-<zero-padded 5>, per school per fiscal year"
  - "migration version: V189"
```

The rule of thumb: if getting it wrong would only be discovered by a *different* task, freeze it
here.

Freeze the relevant Goal Capsule criterion/invariant IDs and any bounded non-material assumptions
the implementer may rely on. Ambiguity that changes acceptance, safety, authority, or an
irreversible boundary is a `stop_conditions` entry and returns to the appropriate human gate. When
the request is vague, planning proposes the capsule for approval before generating cards.

A frozen appendix may repeat future migration filenames that the card explicitly fences. A higher
version paired to an exact `forbidden_paths` migration literal is treated as fencing evidence, not
as the migration this card intends to create. This is deliberately narrow: an unpaired higher
version, or the same future migration mentioned operationally in `exclusive_writes`, instructions,
tests, or validation, remains a drift finding.

### `gate_risk`

```yaml
gate_risk: [openapi.json, native-sql-inventory.tsv, screen-manifest.json]
```

Each named artifact has a cheap verifier that owns it. The card's `validation` block must run those
verifiers. This is the difference between finding a manifest drift in thirty seconds and finding it
fifty minutes into a full gate.

`none` is a valid and common answer. Say it explicitly rather than omitting the field.

### `validation`

Exact direct processes, in order. Not "run the tests" and not shell text. Each item has exactly
`cwd` and `argv`: `cwd` is `.` or an existing normalized repository-relative directory with no
symlink component, and `argv` is a non-empty sequence of non-empty strings. The validator does not
invoke or approximate a shell.
Legacy scalar commands, grouping mappings, shell interpreters, pipelines, redirects, environment
assignments, and compound commands are invalid. Put unavoidable orchestration in a repository
script with a shebang, then name that script directly. The rejected shell basename set is exactly
`sh`, `bash`, `dash`, `zsh`, `ksh`, `mksh`, `csh`, `tcsh`, `fish`, `ash`, `pwsh`, `powershell`,
`cmd`, and `cmd.exe`. Shell-looking argument values are data; unlisted wrappers are direct
processes but never lend nested executable evidence.

**A path is not a behaviour.** `writes` and `exclusive_writes` model which FILES a task may touch,
and the loop's own limits section says so plainly: two tasks with disjoint write sets can still
break each other through shared state, a changed default, or an ordering nobody declared. Nothing in
this toolchain can see that, and no glob ever will.

So when a task changes something a user can observe — a route's response, a screen, a migration's
effect on existing rows, a job's timing — `validation` must name a command that EXERCISES it, not
only one that compiles or unit-tests it. A browser driver, an HTTP call against a started service, a
migration applied to a seeded copy and read back: whatever the repository already owns. This is a
requirement on WHAT the command does, not a new field, because `validation` is already arbitrary
`argv` and adding a field would be a second place to state the same thing.

The check that cannot be written here is the one that matters: nothing verifies that a command is
behavioural rather than nominal. `trace_check.py` proves a test with a criterion's id ran and
passed, and T7 proves its body changed in the range — neither proves it drove the product. That gap
is stated rather than closed, because a checker that guessed at behaviour from a command line would
be the tenth in this repository to report a clean exit over something it never read.

This value shape is **task-card validation contract v2**. v1 cards are invalid under v2 because
they contain scalar command strings; v2 cards are invalid under v1 because the old validator
flattens mappings rather than decoding processes. To migrate, move a leading directory change into
`cwd`, make the executable and every argument separate `argv` items, and split multiple processes
into separate entries. For indivisible orchestration, invoke a repository script directly. Run
strict pre- and post-validation after conversion; there is no legacy mode.

```yaml
tests:
  - "Retain: acme-api/backend/fees/src/test/java/com/acme/fees/api/FeesApiTest.java :: com.acme.fees.api.FeesApiTest"
validation:
  - cwd: acme-api/backend
    argv:
      - ./gradlew
      - :fees:test
      - --tests
      - com.acme.fees.api.FeesApiTest
      - --rerun-tasks
  - cwd: acme-api
    argv: [./scripts/contracts.sh, verify]
  - cwd: acme-api/backend
    argv: [./gradlew, verifyBackendTestTaxonomy]
```

Never the full release gate. That is a milestone instrument.

### Exact Java test declarations and phases

Every Java test named by a card uses one of these exact declarations in `tests`:

```yaml
tests:
  - "Create: backend/core/src/test/java/com/acme/core/WidgetRetryTest.java :: com.acme.core.WidgetRetryTest"
  - "Retain: backend/core/src/test/java/com/acme/core/TenantIsolationTest.java :: com.acme.core.TenantIsolationTest"
```

The repository-relative path must map mechanically to the FQCN. `Retain` must already exist at that
exact path. Before implementation, `Create` may be absent only when `exclusive_writes` covers its
exact path. Declarations and exact Java Gradle `--tests` class selectors are one-to-one: every
declaration has exactly one selector and every selector has exactly one declaration. Prose-only
`tests` entries and wildcard filters cannot satisfy this. A class shell with no JUnit annotation is
not a test. The direct Gradle `argv` itself must carry its selector. `--rerun-tasks` is the only
accepted Gradle freshness proof. `clean`, `cleanTest`, qualified clean tasks, exclusions,
properties, option operands, and every other token do not count. An active v2 card that used a
clean task as freshness evidence must add the exact `--rerun-tasks` member; historical cards are
not rewritten. The working directory belongs in `cwd`; a later argument cannot name another
process or lend flags. If two processes are required, declare two validation entries. A direct
`--tests` requires one non-empty, non-option operand; missing and empty operands invalidate the
whole validation field before any dependent check runs.

Run the same immutable card in both phases:

```bash
validate_card.py CARD --repo REPO --strict --phase pre
validate_card.py CARD --repo REPO --strict --phase post
```

### `--phase mid` — drift, caught before the commit

```bash
validate_card.py CARD --repo REPO --phase mid     # at every turn boundary, mid-task
```

`mid` runs the `pre` checks and adds one comparison: every path with an uncommitted change in
`REPO`, against this card's `exclusive_writes` and `forbidden_paths`, using the same glob
intersection `plan_waves.py` W7 uses **after** the commit. A path no write glob covers is an ERROR;
so is an uncommitted change to a forbidden path.

It is the same question W7 asks, asked while the answer is still free to act on: an uncommitted edit
reverts, a committed one costs a round. **56 real cards were matched to the commit their own
`commit_subject` names, out of 187 read across four repositories. Of 558 files compared, 116 were
written outside what the card allowed — 99 that no write glob covers and 17 inside a
`forbidden_paths` glob — across 25 of the 56 cards, 9 of which broke a fence they declared
themselves.** Cost is one `git status`: 19–39 ms measured on four real repositories.

Two things it will report that are not code drift, and both are correct. Writes to the workspace's
own bookkeeping — the report, the ledger, the register — are reported when the card does not
declare them; the fix is one line in `exclusive_writes`, not a filter, because a filter would have
to match project-specific file *names*. And the card file itself is the single exemption: a card
cannot be required to declare itself.

`pre` is the default and permits an owned absent `Create`. `post` requires it to exist at the
declared path, contain a real package plus top-level class resolving to the declared FQCN, and
contain a JUnit test declaration. Comments and strings do not satisfy source declarations. Do not relabel
`Create` to `Retain`; the phase records which assertion is being checked.

`Retain` is never an absent-path promise: its exact file must exist even in pre phase. In post phase
both `Create` and `Retain` paths must exist and pass the source checks, alongside every production or
other file named by `exclusive_writes`.

For nested Java types, normalize `$` to `.` and declare the containing outer source path with the
full nested FQCN. Only the exact member-type chain in source, after comments and strings are removed,
establishes existence; capitalization, a local class, or a partial outer match does not. An owned
exact `Create` can be absent in pre phase and must contain the complete chain in post phase.

When a validation `argv[0]` contains `/` and is not absolute, resolve it from the command `cwd`. It
must stay inside the repository and name an executable regular file. Direct text scripts require a
byte-zero `#!` shebang; executable binaries are accepted. Bare PATH names remain unchecked and
absolute executable behaviour is unchanged. A root failure is reported once and suppresses
dependent evidence findings for that validation block.

### JUnit XML execution evidence

JUnit evidence is bound to a newly created single-use start receipt. Choose a new receipt path for
every run, create it immediately before the test task, and pass that exact artifact to the verifier.
Never point the verifier at `build/`, a module root, or the repository: it scans only XML files
directly inside the directory named on the command line.

```bash
rm -rf backend/core/build/test-results/test
python3 <execution-methodology>/scripts/start_junit_run.py \
  --results backend/core/build/test-results/test \
  --output .work/reports/EX-01-<run-id>-start.json
cd backend && ./gradlew :core:test \
  --tests 'com.acme.core.WidgetRetryTest' \
  --tests 'com.acme.core.TenantIsolationTest' --rerun-tasks
cd .. && python3 <execution-methodology>/scripts/verify_junit.py \
  --results backend/core/build/test-results/test \
  --start-receipt .work/reports/EX-01-<run-id>-start.json \
  --expect com.acme.core.WidgetRetryTest=1 \
  --expect com.acme.core.TenantIsolationTest=1 \
  --output .work/reports/EX-01-<run-id>-junit.json
```

Both receipt paths must be new and outside the result directory. The start receipt binds the exact
result path and snapshots hashes of any direct XML already there, then records a 256-bit nonce and
nanosecond boundary. Every final XML must differ from any same-named pre-run content and have mtime
and ctime strictly after that boundary; same-time and older files fail even if otherwise valid. The
verifier atomically creates `<start>.consumed` before inspecting XML, so a failed attempt cannot be
repaired and replayed under the same nonce. It records the start receipt's SHA-256 and nonce in a
successful output. It also fails missing, zero-byte, or unparseable XML; zero tests; absent expected
classes; and duplicate suite identities or count inconsistencies. JUnit failures, errors, and skips
all fail evidence verification. The final JSON includes
the absolute result path, result-file count, classes, totals, exact expected/observed class counts,
start identity, and
UTC timestamps. Cleaning the exact result directory remains recommended defense in depth, but the
start boundary—not cleanup discipline—is the freshness check.

The verifier detects accidental pre-existing, same-content, unchanged, malformed, replayed, failed,
errored, skipped, and count-inconsistent results. It does not detect a cache restore that writes
plausible valid XML after the boundary. Exact runner rerun settings prevent cache use; Gradle
requires exact `--rerun-tasks`. The receipt is **not tamper-resistant**: a deliberate local writer
controlling both XML and evidence files can fabricate them. Treat it as freshness and consistency
evidence within that trust boundary, never as hostile-writer attestation.

When a Codex `test-judge` must run a gate that writes, the controller freezes writers and binds the
referent to a committed tree or to `HEAD` plus a canonical manifest of paths, types, modes,
content/link hashes, status, tracked deletions, and non-ignored untracked files. It materializes a
manifest-equal standalone copy under a fresh temporary root with no source `.git` relationship,
hard links, ignored outputs, unresolved external objects, or escaping symlinks. Because the outer
judge is read-only, request approval for the **exact sandbox-launch** command only. The approved
nested sandbox launch is:

```text
env CODEX_HOME=<temporary-home> codex sandbox -p gate -P copy-write -C <copy> -- <exact gate argv>
```

Approval moves only the launcher outside the outer boundary; it never runs the gate unsandboxed.
The launcher immediately enters the custom inner profile, which grants source read, copy write, and
network disabled.

Record the referent and manifest hash, commands, exit code, verbatim failures, counts/skips, and an
unchanged-source recheck. Stop on identity ambiguity, mismatch, sandbox failure, cached/zero/skipped
execution, a required bypass, or failed cleanup. The source stays read-only. Plain nested execution
cannot widen the outer sandbox, and plain unsandboxed gate execution is forbidden. For Gradle,
exact `--rerun-tasks` is the sole freshness evidence; `cleanTest` does not qualify.

### The fix/record rule — the binding answer to "I found something else"

**This is the rule. Run it per finding, at the moment you find it, before you touch anything.**

> **FIX it** only if all three are true:
>
> 1. **OWNED** — the change lands inside `exclusive_writes` and touches no `forbidden_paths`.
> 2. **LINKED** — it advances a criterion or invariant id **already written on this card**
>    (`invariants`, `frozen_values`, `goal`). Not one you can argue for. One that is there.
> 3. **TRIGGERED** — you can paste a command and its observed output, **or** this card's own
>    `validation` block fails because of it. A mechanism argued from reading the source is not a
>    trigger.
>
> **Otherwise RECORD it** in the register at `record_to` and carry on with the task.

All three read fields already on the card, so the rule costs **zero model calls and zero extra
reading**. Question 1 is a path comparison — `validate_card.py CARD --repo REPO --phase mid` answers
it against your actual working tree. Question 2 is a lookup in a list you have already read.
Question 3 is a terminal you already have open. Only "is this output really the trigger" is
judgement, and it is narrow: **no pasted output, no trigger.**

The rule is deliberately one-sided. It bounds over-fixing, not under-fixing, because over-fixing is
what has actually happened: one measured milestone produced 51 cards, 230 reports, 64 review
artifacts and 37 fix rounds, with card creation flat at 14 → 18 → 14 per day for three days and
three cards subdividing rather than closing. A human stopped it by hand with a severity floor.
**Fixing every found issue with no floor did not converge.** This is that floor, applied at
find-time instead of afterwards by a person.

**Safety findings bypass the rule.** They always have; nothing here changes that.

**A RECORD is not a dropped finding.** It becomes an entry in the milestone's `## Deferred`
register — six keyed lines — where `spec_check.py` rule E lints it and refuses to let the owning
milestone ship while it is unowned. Recording takes about a minute. Fixing takes a round.

### `record_to`

```yaml
record_to: docs/product/milestones/M4-fees.md
```

The one field the fix/record rule adds, and the only one it needs: the register a RECORD goes to.
`validate_card.py` checks that the path is a milestone document and that it **exists** — a register
that is not there is indistinguishable from an empty one, which is exactly how deferrals were lost
before. All 187 cards measured across four real repositories predate this field, so its absence is
a WARNING that still exits 0; `--strict` fails it. This is the migration policy `title` already
uses, and it is the same policy: fail closed on history that cannot be edited and nothing gets
adopted.

### `stop_conditions`

What makes this task hand back rather than infer. The cheap implementation persona is only safe because
it refuses to improvise, and this field is where that refusal is made concrete:

```yaml
stop_conditions:
  - "the payload shape needed is not in frozen_values"
  - "a shared interface or module boundary would have to change"
  - "a migration is required"
  - "an existing green test turns red and the cause is not obviously this task"
```

Also stop when a repair cannot name the frozen criterion/invariant it advances and its observable
delta; when proof machinery would acquire durable authority, persistence, compatibility, recovery,
or a reusable API; when the same causal mechanism recurs after one independently reviewed repair;
or when a third distinct ordinary repair needs human continue/replan authority. Distinct safety
findings do not share a counter and may still block release. Budgets trigger human review only and
never change a gate verdict.

**A stop is not the answer to an unrelated finding.** Run the fix/record rule above first: most
findings that feel like a stop are a RECORD, and stopping the task to report one costs a dispatch
round to move a line into a register. Stop when the CARD cannot proceed — the entries above are all
of that shape. Record when the card can proceed and something else is wrong.

## Report contract

The implementer writes a full report to a file and returns only a verdict.

**Status vocabulary** — one of `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, `BLOCKED`.

**The verdict returned** is status, commit shas, a one-line test summary, and concerns. Nothing
else. It is short because the orchestrator re-reads it on every subsequent turn.

**The report written to file** carries: files changed; design decisions and why; interfaces produced
that later tasks will consume; the exact commands run with their real output and PASS/FAIL;
pass-to-pass breakage, explicitly, including "none"; surprises and assumptions that turned out
wrong; and commit shas.

For every review finding, the report also records its capsule criterion/invariant, reachable input
or state, observable consequence, evidence, category, causal class, disposition, and owner. The
card's stable identity remains unchanged across repairs; attempt renaming cannot reset causal
history.

Those last three are not optional politeness. Interfaces produced, deferrals, verification actually
run, and corrected assumptions are exactly what gets promoted into the program ledger, and a report
that omits them makes the promotion gate unpassable.

**Never report green without output.** A task whose gate did not run says so in those words.
"Complete" beside "gate not run" is a contradiction, and it has shipped before.
