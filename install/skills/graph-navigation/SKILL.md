---
name: graph-navigation
description: Use before running any graphify command against an existing graphify-out/graph.json — locating a symbol, tracing how one component reaches another, or finding the blast radius of a change before editing. Also use when a graphify query returned unrelated nodes, test mocks, or loggers instead of an answer, or when a read-only constraint makes it unclear which graph commands are safe to run.
---

# Graph navigation

`graphify query` seeds BFS from **literal** case-folded substring matches — no stemming, no
synonyms, no cross-language mapping. Prose questions seed on weak tokens and return noise. Symbol
names seed correctly. Reach for `query` last, not first.

Nothing in this file is an answer about your repo. Every command below must be run for real; the
graph output you get is the evidence, and it still has to be confirmed in source.

**Safe under a read-only constraint.** `explain`, `affected`, `path`, and `query` only read
`graphify-out/graph.json` — they write nothing. A read-only investigation is not a reason to skip
them. Only `update`/`extract`/`save-result`/`reflect` write, and they write to `graphify-out/`,
which is generated navigation data rather than source.

## Step 0 — get an anchor symbol

The ladder needs a symbol name. If you don't have one, find it before climbing:

```bash
grep -oE '"label": *"[^"]*"' graphify-out/graph.json | sed 's/.*: *"//;s/"$//' | sort -u | grep -i <fragment>
```

Class-like names come back bare (`CaregiverInviteService`); methods come back dotted
(`.acceptOfAlreadyUsedInvite()`). Feed the bare class name to `explain`.

Guessing a plausible class name and running `explain` on it is fine, but a miss means the name is
wrong, not that the thing is absent — grep the graph's own labels rather than guessing twice.

## The ladder

Work down this list. Stop as soon as you have a source location worth opening.

| Step | Command | Returns |
|---|---|---|
| 1 | `graphify explain "<Symbol>"` | The node, its source line, degree, ranked neighbors |
| 2 | `graphify affected "<Symbol>" --depth 1` | Reverse traversal — candidate callers |
| 3 | `graphify path "<A>" "<B>"` | Shortest path between two known symbols |
| 4 | `graphify query "<Sym> <Sym>" --context calls --budget 800` | Subgraph, when you have no single anchor |

`--context` is repeatable (`calls`, `imports`, `references`, …). `--budget` caps output tokens.

**Before step 4 with a concept rather than a symbol:** do the required vocab expansion in
`~/.claude/skills/graphify/references/query.md` (Step 0) — read `graphify-out/.vocab.txt` and seed
only with tokens that appear in it. Do not invent tokens.

## The graph over-reports. Always confirm.

Edges are extracted, not proven. Three failure modes, all observed in practice:

- **False dependents.** A class can appear in `affected` output because another file *mentions* it
  in a doc comment, with no import and no call. Before citing X as a dependent of Y, grep X for an
  actual call site (`grep -n "ySymbol\.\|YSymbol " path/to/X.java`), not just an import line.
- **Import-line hits.** `explain` and `affected` frequently cite a file's `L1` import or its
  constructor reference. That locates the *file*, not the logic. Open it and find the real code.
- **Ambiguous paths.** `path` prints a match-ambiguity warning and can return a long chain through
  unrelated nodes (test runners, `UUID`, plan files) when no real edge path exists. A path that
  routes through obvious noise is a non-answer — drop it and read source instead.

`query` is the noisiest, but no command on the ladder is authoritative. The graph tells you where
to look; the source tells you what is true.

## Then read the source

The ladder returns locations, not explanations. Tracing a multi-hop flow (entry → transform →
persist) normally means opening several of the files it names and reading them properly. Budget for
that; it is not a failure of the ladder.

When several candidates surface, prefer the one whose profile, annotations, or package match the
behavior you're chasing, and say which you ruled out.

## Traps

- **`context_filter=['call']` is the Python API form.** The truncation hint prints it, but the CLI
  flag is `--context calls`. Copying the hint verbatim into a shell fails.
- **`graphify query --help` is parsed as a query for the word "Help"** — it returns nodes, not
  help. Subcommands have no `--help`. Only `graphify --help` works.
- **Blast radius is `affected`, not `query`.** Run it before editing any shared service.

## Close the loop

After a query that changed your understanding, record the outcome so later sessions inherit it:

```bash
graphify save-result --question "<original question>" --answer "<what you concluded>" \
  --nodes Symbol1 Symbol2 --outcome useful    # or: dead_end | corrected --correction "..."
```

This writes to `graphify-out/`, which is generated navigation data, not source — it is compatible
with a read-only investigation of the codebase. Skip it only if you were told to touch nothing at
all on disk.

`graphify reflect --if-stale` folds those into `graphify-out/reflections/LESSONS.md`. Preferred
sources and known dead ends live there; a SessionStart hook surfaces it automatically.

## Keeping the graph current

| Change | Command |
|---|---|
| Code only | `graphify update .` (or a project's `make graph-update`) |
| Docs, images, broad refactor | full rebuild: `graphify extract . --mode deep --backend <backend>` |
| Refactor deleted files, shrink guard tripped | review the counts, then `GRAPHIFY_FORCE=1` |

A graph older than the working tree will confidently cite lines that have moved. Compare its
timestamp against the latest commit before trusting it.
