# Roles

| Role | Claude | Codex | Effort |
|---|---|---|---|
| Builder: frontier tier | `opus` | `gpt-6.1-sol` | `high` |
| Scout: cheap tier, read-only | `haiku` | `gpt-6-luna` | harness default |
| Reviewer: the other vendor's strongest reasoning model, read-only | when Codex is chief | when Claude is chief | `high` |
| Chief: the founder's own session | either | either | the session's |

- `high` is the effort both harnesses accept; use it where a role sets one.
- `CLAUDE_CODE_EFFORT_LEVEL` overrides an agent file's frontmatter, so no session may export it.
- Cost is recorded (`goal.py cost`), never enforced: no budget stops a goal.
- The caps are structural: one builder per task, one review round per stage, each agent file's
  `maxTurns`, at most five planning questions.
