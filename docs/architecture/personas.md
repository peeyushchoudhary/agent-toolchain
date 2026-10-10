---
summary: The three Claude agent files the skill ships (builder, reviewer, scout), what each guards against, the evidence and source behind every adopted line, and what was left out and where it lives instead. The lines come from a persona council held on 2026-10-09: four experts (each harness's vendor guidance, open-source practice, prompt craft) and an adversarial synthesis. The council record stays on the founder's machine; this page is its public part.
read-when: Changing a line of an agent file, or asking why a persona says what it says
covers: [install/skills/execution-methodology/agents/**]
last-verified: 2026-10-10
---

# Personas

The agent files are [builder.md](../../install/skills/execution-methodology/agents/builder.md),
[reviewer.md](../../install/skills/execution-methodology/agents/reviewer.md) and
[scout.md](../../install/skills/execution-methodology/agents/scout.md). Each body has `## MUST`,
`## SHOULD`, `## AVOID` and `## REPORT`, one behaviour per line, within a word ceiling that
`test_rules.py` asserts (350, 350, 200). Each has a Codex twin, `agents/<name>.toml`, whose `developer_instructions` is the same body byte
for byte (asserted by the install tests). Model and effort agree with
[roles.md](../../install/skills/execution-methodology/references/roles.md); the decision is
[D30](../decisions/decisions.md#d30--methodology-v71-context-roles-and-planning-documents-s-2).

The council ranked its sources: the methodology's own enforced rules and measurements first, then
primary vendor documentation, then secondary studies, then community files. A rule a gate, lint or
plan already enforces is not restated in a persona.

## What each file guards against

- **builder** (`opus`, `effort: high`, `maxTurns: 80`, `permissionMode: dontAsk`,
  `isolation: worktree`): out-of-scope edits, quiet narrowing or widening of the task, code
  written to the test's inputs instead of the behaviour, tests edited to pass, success claimed
  without the gate's own output, speculative abstraction and adjacent clean-ups, and work started
  from a summary instead of the files.
- **reviewer** (`tools: Read, Grep, Glob`, `opus`, `effort: high`): a review that trusts the
  builder's report, style noise, findings about code the diff did not touch, a finding with no
  scenario, self-filtering that hides defects, and a reviewer that edits or runs tests.
- **scout** (`tools: Read, Grep, Glob`, `haiku`, `maxTurns: 20`): reconnaissance that drifts into
  judging, pasting code or proposing work, and paths named without being opened.

## Adopted lines and their evidence

| Line | File | Evidence and source |
|---|---|---|
| If the task looks wrong, say so in one sentence, then do it as written | builder | The scope-declaration study: out-of-scope actions fell from 17.1% to 0.0% ([arXiv 2605.18583](https://arxiv.org/abs/2605.18583)); the [Opus 5 prompting guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5) |
| Read the `reads:` ranges first; open a file before claiming anything about it; trust no summary | builder | Claude Code [best practices](https://code.claude.com/docs/en/best-practices); softened from a hard read mandate, which GPT-6 guidance says hinders |
| Copy the nearest existing pattern and name the file | builder | Best practices, "follow the pattern" (same page) |
| No helpers or abstractions for one use; no adjacent fixes; report follow-ups | builder | The over-engineering sample in Anthropic's [prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) |
| Report a wrong test as red, never edit it; implement the behaviour, not the test's inputs | builder | Same page ("if any of the tests are incorrect, inform me"); a reward-hacking study ([arXiv 2511.21654](https://arxiv.org/abs/2511.21654)) |
| See the named test fail before the change (SHOULD, behaviour changes only) | builder | The reward-hacking study and one community anecdote; no vendor document, so not a MUST |
| The gate's last line as printed; a gate that did not start is not green | builder | Best practices, "show evidence rather than asserting success" |
| No preambles or questions; default and record | builder | The [Codex prompting guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide); the skill's Authority section |
| Read the whole diff; the builder's report is a claim, not evidence | reviewer | Best practices: a fresh reviewer "sees only the diff and the criteria"; a community skills plugin from the GitHub survey supports the wording |
| Report every defect and class it; the chief filters | reviewer | The Opus 5 guide (report all, filter separately) over correctness-only and confidence-threshold reviewers from the GitHub survey |
| Only diff-introduced defects, one finding each, with a scenario; no style or foreign rigor | reviewer | OpenAI's [code review rules](https://learn.chatgpt.com/docs/code-review?surface=app) |
| Trigger, consequence and closing test; one round; read-only | reviewer | The skill's Review section and `test_rules.py`'s read-only test |
| Run no test or gate | reviewer | A Codex read-only sandbox still executes commands; the chief's `gate.py` receipt is the evidence |
| Non-blocking flags for unused parameters and one-caller abstractions | reviewer | Google's [reviewer guide](https://google.github.io/eng-practices/review/reviewer/looking-for.html) |
| At most 300 words of identifiers; locate, never judge | scout | The Codex [subagents doc](https://learn.chatgpt.com/docs/agent-configuration/subagents): "stay in exploration mode … cite files" |
| Frontmatter keys and their meaning | all | The Claude Code [subagent reference](https://code.claude.com/docs/en/sub-agents) |

The same council fed the chief's planning rules in
[planning.md](../../install/skills/execution-methodology/references/planning.md): tasks
restartable from the plan with verifiable criteria
([Codex exec plans](https://developers.openai.com/cookbook/articles/codex_exec_plans)); what the
builder must not do, stated in the task (the overeager study: adherence falls about 5.6% per extra
function, [arXiv 2605.10039](https://arxiv.org/abs/2605.10039)); no "be thorough" or
"double-check" ([arXiv 2608.01347](https://arxiv.org/abs/2608.01347)).

## Left out, and where it lives instead

- Write sets, protected paths and test immutability: the plan and `goal.py done` rows 4 and 5.
- What to read: the task's `reads:` line, resolved by `docs.py reads`.
- Model, effort, turn cap and tool set: the frontmatter and `roles.md`.
- Push, reset and destructive commands: the builder body keeps "never commit, tag, push or reset";
  pushes pass the pre-push guard and the harness's permission prompts.
- Security questions: `references/security-checklist.md`, handed to the reviewer when `touches:`
  names data, auth or external.
- Formatting, naming case and import order: the project's lint inside the gate.
- `review.md` conformance: the chief's read. Confidence scores: nowhere.
- Role sentences, capability lists, "think step by step", "IMPORTANT": nowhere.
- Repository facts: `AGENTS.md` and the area pages, reached by `reads:` and generated pointers.
- Community machinery nothing parses (status vocabularies, "three empty searches", "re-read your
  diff", "Nit:" prefixes, title and quote lengths): rejected; the report shape and `maxTurns` do
  the work.
- "Write the minimal code to pass": rejected for "implement the behaviour"; tests verify, they do
  not define. "Smallest diff" stays a SHOULD about scope.
- "Terminate only when solved": the packet's stop conditions and the gate line define completion.

## Harness caveats

- `isolation: worktree` branches from the remote default branch unless the founder's settings set
  `worktree.baseRef: "head"`; without it a builder misses the goal branch.
- `permissionMode: dontAsk` is ignored under bypass, accept-edits or auto mode; it matters only
  for a default-mode chief.
- `CLAUDE_CODE_EFFORT_LEVEL` overrides `effort`, so no session exports it.
- No persona is the chief. The skill runs in the root session only (D31): a Claude Code subagent
  has no Agent tool, so it could not dispatch builders or reviewers, and in either harness an
  orchestrating agent above the builders is not a shape this methodology has.
- A builder stopped by `maxTurns` returns a partial report with no gate line; the chief treats it
  as red. The caps 80 and 20 are starting values, to tune from `goal.py cost`.
