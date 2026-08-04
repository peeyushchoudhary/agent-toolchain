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
validation:          # the exact commands, in order, that prove this task
stop_conditions:     # what makes this task stop rather than infer
handoff:             # who receives the report
commit_subject:      # the exact commit subject line
```

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
so history stays readable; `--strict`, which is what a controller runs before minting a card, exits
1. A new card without a title cannot be dispatched.

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

### `gate_risk`

```yaml
gate_risk: [openapi.json, native-sql-inventory.tsv, screen-manifest.json]
```

Each named artifact has a cheap verifier that owns it. The card's `validation` block must run those
verifiers. This is the difference between finding a manifest drift in thirty seconds and finding it
fifty minutes into a full gate.

`none` is a valid and common answer. Say it explicitly rather than omitting the field.

### `validation`

Exact commands, in order. Not "run the tests".

```yaml
validation:
  - "cd acme-api/backend && ./gradlew :fees:test --tests 'com.acme.fees.api.FeesApiTest'"
  - "cd acme-api && ./scripts/contracts.sh verify"
  - "cd acme-api/backend && ./gradlew verifyBackendTestTaxonomy"
```

Never the full release gate. That is a milestone instrument.

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

## Report contract

The implementer writes a full report to a file and returns only a verdict.

**Status vocabulary** — one of `DONE`, `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, `BLOCKED`.

**The verdict returned** is status, commit shas, a one-line test summary, and concerns. Nothing
else. It is short because the orchestrator re-reads it on every subsequent turn.

**The report written to file** carries: files changed; design decisions and why; interfaces produced
that later tasks will consume; the exact commands run with their real output and PASS/FAIL;
pass-to-pass breakage, explicitly, including "none"; surprises and assumptions that turned out
wrong; and commit shas.

Those last three are not optional politeness. Interfaces produced, deferrals, verification actually
run, and corrected assumptions are exactly what gets promoted into the program ledger, and a report
that omits them makes the promotion gate unpassable.

**Never report green without output.** A task whose gate did not run says so in those words.
"Complete" beside "gate not run" is a contradiction, and it has shipped before.
