# Progressive disclosure

A coding agent should read a short route, not a library. Any task should load **one entry file, one
index row, and one guide** before touching code — and the route must stay true as the code changes.

Disclosure fails in two directions. Too little: the agent explores blindly and rediscovers the
codebase every session. Too much: a 4,000-word instruction file that gets skimmed, so its invariants
may as well not exist.

Implementation: `~/.claude/skills/progressive-disclosure/`.

## Four layers

| Layer | File | Budget | Job |
|---|---|---|---|
| 1. Contract | root `AGENTS.md` (+ `CLAUDE.md` importing it) | ≤ 400 words | Invariants true everywhere, and where to go next |
| 2. Index | `docs/agents/README.md` | ≤ 600 words | Task → **one** guide → **one** verification command |
| 3. Scoped | `<dir>/AGENTS.md` (+ `CLAUDE.md`) | ≤ 40 words | "You are in `web/`; read `../docs/agents/web.md`" |
| 4. README | root `README.md` | — | The **human** front page — see below |

**Layer 3 is the highest-leverage and the most often missing.** Both harnesses load the nearest
entry file by proximity as an agent works in a subtree, so it is the only layer that fires *without
the agent choosing to read anything*. Every source directory should have one.

Keep both filenames per directory: `AGENTS.md` holds the content, `CLAUDE.md` is exactly one line —
`@AGENTS.md` — so Claude and Codex cannot read different contracts.

## Layer 4: the README contract

Layers 1–3 route an *agent*. `README.md` answers a *human* who has never seen the project and is
deciding whether it is real. Different reader, different document; collapsing either into the other
loses one of them.

Seven sections, enforced by `validate_disclosure.py --readme`. Heading wording is flexible — common
synonyms are accepted — but each question must be answered:

| Section | Question |
|---|---|
| Overview | What is this, and what problem does it solve? |
| Current state | What ships today, what is left, where is the plan? |
| Product requirements | Where are the PRDs? A table of links, never the PRD text |
| Architecture | How is it built? **Must contain a diagram in this section** |
| Components | One row per component: responsibility, entry point, deep-dive link |
| Run locally | How do I start it? |
| Working in this repository | The agent route, and how work lands |

**The README indexes; it does not duplicate.** Low-level design lives in
`docs/architecture/<component>.md`, one file per component. A README that inlines every component's
design grows past the point anyone maintains it, and then it is worse than absent — it is
confidently wrong.

Prefer Mermaid to an exported image: GitHub renders it, it diffs line by line, and an agent can
edit it. A PNG satisfies the check but nobody will ever update it.

## Authoring rules

- **Route, don't restate.** A scoped file that explains architecture becomes a fourth copy of the
  truth, and copies drift. Say where you are and what to read next.
- **One verification command per index row.** "Run the tests" is not routing.
- **State an authority order.** Normally: current code and tests > maintained guides > product docs
  > `docs/archive/` (rationale only, never behaviour).
- **Demote history explicitly, by path.** Otherwise agents cite a superseded plan as current.
- **Adding a guide means adding its index row.** An unrouted guide is invisible.

## Validation

```bash
validate_disclosure.py .                    # the route
validate_disclosure.py . --readme           # + the README contract
validate_disclosure.py . --standard         # + the repository taxonomy
validate_disclosure.py . --vs main          # + warn if source changed and README did not
```

| Signal | Meaning |
|---|---|
| `broken-link` (error) | A link or `@import` that does not resolve |
| `missing-make-target` / `missing-script` / `missing-just-recipe` / `missing-task` (error) | A documented command that does not exist |
| `readme-*` (error) | Missing section, no diagram, unlinked PRD or plan, unmentioned component |
| `persona-drift` (error) | Generated agent files no longer match their persona source |
| `orphan-doc` (warn) | A guide in an agent-docs directory that nothing routes to |
| `unscoped-dir` (warn) | A source directory with no layer-3 entry file |
| `over-budget` / `too-deep` (warn) | Disclosure decaying into a dump |
| `stale-path` (warn) | A guide cites a code path that resolves nowhere |
| `standard-*` | Taxonomy violations, unfinished scaffolding, version drift |

Exit 1 on any error, or on warnings with `--strict`. Wire into the repo's gate — in the reference
project it is `make check-docs`, part of `make check`.

## Things the validator learned the hard way

Each of these was a real false positive or miss, fixed in the tool:

- **`@import` is matched against code-stripped text and must look like a path.** A bare Java
  annotation on its own line — `@Entity`, `@RestController` — was being parsed as an import, so
  every design doc quoting Spring reported dozens of broken links.
- **Commands are read only from code spans and fences.** Running the patterns over prose matched
  ordinary English: "make the", "make you", "make active" were all reported as missing targets.
- **History is link-checked but not crawled.** `docs/archive/`, `docs/superpowers/`,
  `docs/eval-reports/`. A plan written months ago *should* cite files that have since moved; that
  is what makes it history. Crawling it buried the one real breakage in 117 correct warnings.
- **Budgets and depth apply to the route only** — `docs/agents/` and entry files. A 2,800-word PRD
  is not a disclosure failure; it is a PRD.
- **A cited filename that exists anywhere is imprecise, not stale.** A guide citing a bare filename
  when the file lives two directories deeper is the case the base-path guesser cannot get right;
  warning on it would be a false positive, so the check stays quiet when the basename exists.

## The learning channel

`docs/agents/lessons.md` is where an agent records something that misled it — dated, two lines,
newest first. It lives in the repo because that is the only place every harness can both read *and*
write: one agent's private memory is invisible to the others, and generated caches are gitignored.

If the correction belongs in a guide, fix the guide instead. Prune a lesson once its guide is fixed.
