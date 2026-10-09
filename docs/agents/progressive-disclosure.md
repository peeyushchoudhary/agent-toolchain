# Progressive disclosure

A coding agent should read a short route, not a library. Any task should load **one entry file, one
index row, and one guide** before touching code — and the route must stay true as the code changes.

Disclosure fails in two directions. Too little: the agent explores blindly and rediscovers the
codebase every session. Too much: a 4,000-word instruction file that gets skimmed, so its invariants
may as well not exist.

This is a convention, not a tool: `install/verify.sh` checks only that links resolve.

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

Seven sections. Heading wording is flexible — common
synonyms are accepted — but each question must be answered:

| Section | Question |
|---|---|
| Overview | What is this, and what problem does it solve? |
| Current state | What ships today, what is left, where is the plan? |
| Product requirements | Where are the PRDs? A table of links, never the PRD text |
| Architecture | How is it built? Mermaid by default; an explicitly declared local image may use the checked text-and-hash alternative |
| Components | One row per component: responsibility, entry point, deep-dive link |
| Run locally | How do I start it? |
| Working in this repository | The agent route, and how work lands |

**The README indexes; it does not duplicate.** Component designs live in
`docs/architecture/<component>.md`; link them from the front page.

Mermaid remains the default. An explicit image choice requires local image bytes bound by SHA-256
and a readable text description. Visual review checks meaning and private identifiers. See the
[visual sources](../assets/readme/README.md).

## Authoring rules

- **Route, don't restate.** A scoped file that explains architecture becomes a fourth copy of the
  truth, and copies drift. Say where you are and what to read next.
- **One verification command per index row.** "Run the tests" is not routing.
- **State an authority order.** Normally: current code and tests > maintained guides > product docs
  > `docs/archive/` (rationale only, never behaviour).
- **Demote history explicitly, by path.** Otherwise agents cite a superseded plan as current.
- **Adding a guide means adding its index row.** An unrouted guide is invisible.

## The learning channel

`docs/agents/lessons.md` is where an agent records something that misled it — dated, two lines,
newest first. It lives in the repo because that is the only place every harness can both read *and*
write: one agent's private memory is invisible to the others, and generated caches are gitignored.

If the correction belongs in a guide, fix the guide instead. Prune a lesson once its guide is fixed.
