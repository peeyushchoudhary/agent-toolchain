---
name: project-migration
description: Use when a repository is already under the standard — it has the route, the git hooks, the methodology — but its product documents predate the product-definition layer, so specs carry no bound front matter and no owner. Also use when check_conformance.py reports "product definition" as the failing check on an otherwise conforming repository. Not for setting a project up; that is project-onboarding.
disable-model-invocation: true
---

# Migrating an onboarded repository's documents

`project-onboarding` is for a repository that is **not yet set up** — no route, no hooks, no remote.
This is the opposite precondition: the repository IS onboarded, and the thing that is behind is its
**product documents**, written before the schema that now binds them existed. Different starting
state, different reader, different moment.

**Report before write.** Steps 1 and 2 write nothing and print exactly what step 3 would touch. Run
both, read both, then decide. You run this by hand.

## The five steps

| | Command | Writes |
|---|---|---|
| 1 | `check_conformance.py <repo>` | nothing |
| 2 | `migrate_to_standard.py <repo> --product` | nothing |
| 3 | `migrate_to_standard.py <repo> --product --apply` | backup, then `git mv` |
| 4 | `sync_methodology.py --repo <repo> --adoption-check`, then `--repo <repo>` | the render |
| 5 | `check_conformance.py <repo> --only "product definition"` | nothing |

### 1 — Triage

```bash
python3 "$HOME/.claude/skills/project-conformance/scripts/check_conformance.py" <repo>
```

Nine checks: personas, route, hooks, identifier guard, methodology, github, plugin surface,
preflight, product definition. It ends with a repair plan naming every file `--fix` would touch,
before touching anything.

**Exit 2 is not passing.** `2` means at least one check did not RUN, and it outranks `1`. A
repository with one broken checker and eight clean ones has not been checked. Read the text; never
the exit code alone.

### 2 — Plan

```bash
python3 ".../progressive-disclosure/scripts/migrate_to_standard.py" <repo> --product
```

Prints each rename, and each front-matter key it would add — `id`, `title`, `prd`, `status`,
`updated` — with the value it derived. What it could not derive it says out loud, per document, as
`REFUSED TO DERIVE`, and what it will not migrate at all it lists under `NOT MIGRATED`. On a real
corpus it closed with:

```
  0 field(s) left as TODO and 1 document(s) skipped. Nothing was invented to fill them.
```

That line is the point of the step. A skipped document is a judgement handed back, not a failure.

### 3 — Apply

```bash
python3 ".../migrate_to_standard.py" <repo> --product --apply
```

Backs up first. Moves with `git mv` in a git repository so history follows the file. Rewrites every
markdown link that pointed at a moved path, resolving it against the file's *original* directory.

Verify on the numbers it prints, not on the absence of an error:

```
  verification:
    body words   before N   after N   IDENTICAL
    links        checked N   broken 0
```

`IDENTICAL` means the plan moved files and headers only. `DIFFER — THE PLAN IS WRONG, IT TOUCHES
PROSE` means stop.

### 4 — Adopt

```bash
python3 ".../execution-methodology/scripts/sync_methodology.py" --repo <repo> --adoption-check
python3 ".../sync_methodology.py" --repo <repo>
```

`--adoption-check` **always exits 0** — it is written for a session hook. Its answer is in the text,
so read it.

The render also reports the repository's persona configuration: which validators ship in
`docs/agents/personas/`, which declare `covers:`, and which horizontal concerns in the product
definition are owned by **nobody**. It proposes the `covers:` line and names the file; it never
writes into a persona. Add the lines yourself. A binding a script guessed is a binding nobody holds.

### 5 — Confirm

```bash
python3 ".../check_conformance.py" <repo> --only "product definition"
```

The report always names what was excluded, so a narrowed run cannot be mistaken for a whole one.

## Three things that bite

**Commit or stash first.** The migrator refuses a dirty tree and is right to — `--apply` on
uncommitted work leaves you with no clean state to return to. `--force` exists and is not advised.
Prefer a `git worktree`: the migration gets its own clean tree and its own branch.

**The A4 trap.** `updated:` is each file's OWN last commit date, as the document's history states
it. Once you COMMIT the migration, `spec_check` rule A4 compares that value against the migration
commit and disagrees. Re-date the headers **in the same commit**, or expect A4 to name every
migrated file exactly once. The migrator prints this warning; it is repeated here because the
warning scrolls past and the failure arrives a step later.

**`--fix` is not confined to the repository you name.** `check_conformance.py --fix` calls
`sync_personas.py --repo R`, and that command also regenerates `~/.claude/agents` and
`~/.codex/agents` and **prunes both of those machine-global trees**. Naming one repository does not
scope the write to it. Read the repair plan before `--fix`, every time.

## What this deliberately does not finish

`status:` and `reviewed_by:` are left for a person. That is not an omission to patch later:
inventing them would forge the review record the product-definition layer exists to hold. The
migration puts the fields in place, correctly empty, and stops.

## This skill is user-invoked, in both harnesses

A migration is a stage transition — it promotes a repository from one declared state to another —
and a model may not authorise its own promotion. `disable-model-invocation: true` holds the Claude
Code half; `agents/openai.yaml` holds the Codex half, which does not read that key. Explicit
invocation still works in both.
