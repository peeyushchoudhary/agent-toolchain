# Global instructions for v6

**Authority: current.** The founder applies this by hand to two private files, `~/.claude/CLAUDE.md`
and `~/.codex/AGENTS.md`. The installer never edits either one, and neither does a goal. Apply it
once every project you still drive with v5.1 is migrated, or sooner if you accept that unmigrated
projects lose their global route.

## What to change

1. In each file, find the section headed `# Execution and maintenance route`. It runs from that
   heading to the sentence that begins "User authority, privacy, local verification and deployment
   boundaries".
2. Replace that whole section with the text under "Replacement section" below, the same bytes in
   both files. Keep the heading and the closing sentence exactly as given.
3. Leave `# GitHub` and the operating-model section as they are. The operating model's
   instruction to read `docs/agents/README.md` at project entry still holds.
4. Compare the section across the two files; it must be byte-identical.

## What to remove

Everything the replaced section carried about the previous methodology, which v6 does not use:

- the paragraph that begins "For substantive work, read the project route and approved execution
  guide", including its controller and fresh-worker rules;
- the paragraph that requires `current` runtime status and valid bindings, and the instruction to
  run a runtime-inventory status command from an approved bundle;
- the paragraphs on binding dispatches to a card, light and full dispatches, and the judge roster
  with its per-round limits;
- the paragraphs on maintenance gaps, read-only conformance assessment, and the maintenance skills
  the founder invoked by name.

The instruction to use personas "defined by `agent-personas`" stays, reworded below.

Nothing else in either file needs to move. Projects not yet migrated are unaffected by this
change, because v6 refuses to execute where the v5.1 runtime pin exists and says why; migrate them
with the [migration reference](../../install/skills/execution-methodology/references/migrate.md).

## Replacement section

Copy from the line below to the end of this file, starting at the heading.

```markdown
# Execution and maintenance route

Goal work follows methodology v6, lean goal execution. A goal is a spec, a design and a plan in
the project's goals directory. The execution-methodology skill holds the rules; read its
`methodology.md` and exactly one reference for the work in hand. Builders work from the dispatch
packet and do not load the skill.

The founder's routine touchpoints are exactly two: goal approval, where the spec, design and plan
are approved together with their grants, and merge per milestone. Do not ask for approval of work
the approved plan already decides, and never infer approval from silence. A decision the plan does
not settle is defaulted when it is reversible, sent to an advisor when it is consequential, and
queued for the founder when it is theirs: criteria, scope, durable interfaces, safety policy and any
external or irreversible action. Queued decisions block only the tasks that depend on them.

Machines decide done. `goal.py` and `gate.py` compute completion, scope, test integrity and
freshness from git and executed commands, and report observed results only. A builder never
approves their own work. Judges are read-only and start from a fresh context; at design, plan and
acceptance the reviewer comes from the other vendor than the chief. Each subject gets at most one
correction and one scoped rereview.

Use the personas that `agent-personas` defines, and take model and effort from their frontmatter
rather than choosing in the moment. Run the chief as the root session, never as a subagent under
another long-lived session.

A project that still carries `docs/agents/execution/runtime.json` follows the previous methodology
and must be migrated before v6 executes there; the skill's migration reference describes how.
Installation, project adoption, model activation and deployment remain separate decisions, each
made by the founder.

User authority, privacy, local verification and deployment boundaries remain in force throughout.
```

## Codex differences

The Codex file uses third person in its other sections, and that is fine: only the block above
must match. After applying it, trust the two goal hooks once in Codex (see [codex.md](codex.md)),
or Codex will not run them.
