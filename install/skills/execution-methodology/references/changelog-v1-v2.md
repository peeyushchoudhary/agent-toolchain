# Changelog, v1.1 – v2.1

Preserved verbatim from the methodology body when v3.0 moved it here. A rule that was assumed and a
rule that cost a gate run are not worth the same, and the difference is invisible once both are
prose. This records which is which, so a later revision knows what it is allowed to cheapen.

## v1.1 — after the first full trial

Earned. Every item below came from something that actually went wrong.

- **`test-judge` keeps a shell, stated as an exception** (principle 3). Unexecuted greens were the
  single largest failure class in the trial: a cached `UP-TO-DATE` reported as a pass, a `--tests`
  filter silently matching nothing, a wrapper's exit code masking a failing gate.
- **A full-diff review before the commit gate, not a scoped one.** Severity across review rounds
  looked like it was falling monotonically; it was not. The two rounds that broke the curve were
  both full-diff passes. Scoped review flatters itself.
- **Cards are validated before dispatch, and the orchestrator refuses otherwise.** The trial's first
  card named a test class that does not exist — which Gradle ignores silently and reports green —
  omitted the test proving its own invariant, and mandated an invariant its own stop condition
  forbade satisfying.
- **`exclusive_writes` must be proven disjoint from in-flight cards.** The orchestrator dispatched
  two concurrent writers onto one write set. It caught itself; nothing structural stopped it.
- **An orchestrator cannot wait.** Agents cannot block on long-running commands — they end their
  turn and must be resumed. Twice this was misread as a stalled agent.

Removed, because the trial showed them to be cost without benefit.

- **`allowed_reads`** was never enforceable. An agent must read to orient, so the validator could
  only ever warn, and the field became a thing to satisfy rather than a constraint.
- **`adversarial_probes`** duplicated by role what `reviewer` and the validator personas already do.
- **`tier` renamed to `persona`**, which is what the field always meant.

Still assumed, and not yet tested by anything.

- The three human gates sit at the right places. Only the back half of the chain has been run
  end to end; the design and plan gates have not been exercised on a real feature.
- The two-tier ledger's promotion gate holds under a stop that happens mid-task rather than between
  tasks.
- The validation tiers are calibrated. They have been used, but never in a case where the cheaper
  tier would have missed something the dearer one caught.

Known wrong and not yet fixed: the trial's own distillation in the project ledger records four fix
rounds. There were five.

## v1.5 — exact card schemas and executed-test evidence

- The validator now covers all seventeen task-card fields, reports unknown fields, and makes strict
  validation an exact-schema check while preserving named diagnostics for obsolete fields.
- Java tests have one-to-one path/FQCN `Create` and `Retain` declarations and exact Gradle class
  filters, plus explicit pre/post phases so one immutable card validates both phases.
- The shared JUnit result verifier binds the exact direct-XML directory to a single-use
  nonce/timestamp start boundary, proves required classes and counts from XML, rejects ambiguous or
  inconsistent results, and emits a new JSON receipt bound to that start artifact.
- JUnit evidence detects accidental pre-existing, same-content, unchanged, malformed, replayed,
  failed, errored, skipped, or count-inconsistent results. It does not detect a cache restore that
  writes plausible valid XML after the boundary. Exact runner rerun settings prevent cache use;
  Gradle requires exact `--rerun-tasks`. It is **not tamper-resistant** against a deliberate local
  writer controlling both XML and evidence files; it is not hostile-writer attestation.

## v1.6 — one approved outcome and causal repair authority

- Plans now freeze one Goal Capsule, and cards reference it through existing fields without a new
  schema or materializer.
- Every dispatch names a criterion or invariant and observable delta; material ambiguity returns to
  a human gate, while bounded non-material ambiguity proceeds under a recorded assumption.
- The first slice is byte-real and uses native primitives where sufficient. Impossible states fail
  closed without speculative machinery; reachable failure, concurrency, retry, privacy, and
  authorization paths remain tested.
- Findings are classified before repair. Same-cause recurrence after one independently reviewed
  repair reopens Gate 2, and a third distinct ordinary repair requires human continue/replan
  authority. Distinct safety findings remain uncapped and can block release.
- Optional budgets trigger mission review only. Independent review, full-diff review, test
  judgement, local E2E, and final acceptance are unchanged.

## v2.0 — direct validation processes

This is a major version because v1 scalar validation entries and v2 direct-process mappings are
operationally incompatible in both directions; treating the change as minor would let adopted v1
repositories receive only a warning while their cards fail validation.

- Every validation entry now names exactly one working directory and argument vector. Shell text,
  grouping maps, and legacy scalar commands are rejected instead of partially interpreted.
- The validator decodes that structure once and shares one immutable command record across Gradle,
  Java selector, pytest, cacheability, module-placement, migration, and gate-risk checks.
- Executable evidence comes only from `argv[0]`; shell-looking later arguments are data and cannot
  lend Gradle or pytest execution evidence.
- The exact rejected shell basename set is `sh`, `bash`, `dash`, `zsh`, `ksh`, `mksh`, `csh`,
  `tcsh`, `fish`, `ash`, `pwsh`, `powershell`, `cmd`, and `cmd.exe`. Unlisted wrappers remain
  direct processes and never lend evidence about an executable nested in their later arguments.
- v1 cards are invalid under v2 because their validation items are scalar shell strings. v2 cards
  are invalid under v1 because the old validator flattens their mappings instead of decoding direct
  processes; this is an intentional bidirectional incompatibility, not a rolling compatibility
  mode.
- Migration moves a leading working-directory change into `cwd`, writes the executable and each
  argument as separate `argv` values, and splits multiple processes into separate entries. If
  orchestration is indivisible, put it in a repository script with a shebang and invoke that script
  directly. Then rerun strict pre- and post-validation.
- Repository-relative `argv[0]` values containing `/` resolve from `cwd` and must stay within the
  repository. They must name an executable regular file and, for direct text scripts, start with a
  byte-zero `#!` shebang. Bare PATH names remain unchecked and absolute executable behaviour is
  unchanged.
- Exact nested Java selectors normalize `$` to `.`, but only the complete member-type chain in the
  containing source (with comments and strings removed) or its exact immutable `Create` declaration
  establishes existence. Capitalization never does.

## v2.1 — bounded pre-gate adversarial review

- The existing read-only `reviewer` now has design and plan modes before Gate 1 and Gate 2; no
  persona, schema field, hook, or cross-harness default was added.
- Each pre-gate reviewer starts fresh with named artifact paths and no author conversation or
  rationale. Domain specialists remain additive, and implementation review is unchanged.
- `PASS` is valid and no finding quota exists. Blocking findings carry reproducible evidence tied
  to a frozen criterion or invariant; preferences, speculative hardening, and invented requirements
  cannot block.
- One author correction and one scoped rereview are permitted. Same-cause recurrence returns design
  to Gate 1 or plan to Gate 2, terminating the automatic review loop.
