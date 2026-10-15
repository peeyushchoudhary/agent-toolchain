# Roles

Exact model IDs, never aliases; `goal.py review` passes the reviewer's to its CLI:

| Role | Claude | Codex | Effort |
|---|---|---|---|
| Builder | `claude-opus-5-5` (Opus 5.5) | `gpt-6.1-sol` | `high` |
| Scout, read-only | `claude-haiku-5-5` (Haiku 5.5) | `gpt-6-luna` | harness default |
| Reviewer, read-only, the other vendor | `claude-opus-5-5` (Opus 5.5) when Codex is chief | `gpt-6-astra` when Claude is chief | `high` |
| Chief: the founder's own session | either | either | the session's |

- `high` is the effort both harnesses accept.
- `CLAUDE_CODE_EFFORT_LEVEL` overrides an agent file's frontmatter, so no session may export it.
- Cost is recorded (`goal.py cost`), never enforced.
- The caps are structural: one builder per task, one review round per stage, each agent file's
  `maxTurns`, at most five planning questions.
