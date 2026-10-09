# Handoff — the Codex side

Codex reads a different set of files from Claude Code. Everything shared has to be either **in the
repository** (both harnesses read it) or **installed** (each harness reads its own copy).

Getting this wrong fails silently: Codex quietly follows an older contract and never announces what
it did not read.

## What Codex reads

| Path | Contents | Kept fresh by |
|---|---|---|
| `~/.codex/AGENTS.md` | Global instructions: operating model, GitHub rules, the goal-execution section | Manual; text in [global-instructions.md](global-instructions.md) |
| `~/.codex/config.toml` | Session and `[agents]` settings | `install.sh` appends `[agents]` once; the rest is manual |
| `~/.codex/agents/*.toml` | Persona definitions | `install.sh`, or `sync_personas.py --scope global` |
| `~/.codex/skills/` | The four published skills | `install.sh` |
| `~/.codex/hooks.json`, `hooks/goal-session.sh` | The goal SessionStart and Stop hooks | `install.sh`; trusted once by you |
| `<repo>/AGENTS.md` | The project contract | Shared with Claude, the same file |
| `<repo>/docs/agents/**` | The route | Shared with Claude, the same files |
| `<repo>/.codex/hooks.json` | Project hooks for a migrated project | Written at migration; trusted once by you |

**The repository layer is genuinely shared.** `AGENTS.md`, the route and the guides are read by
both. That is why knowledge belongs in the repo and only accelerators belong in a harness.

`CLAUDE.md` must be exactly `@AGENTS.md`, one line, so neither harness reads a different contract.

## Setup

Run `install/install.sh`; it does steps 1 to 3 when the Codex home exists. The sections below say
what it did and how to check it.

### 1. Subagents enabled

Codex will not spawn personas without an `[agents]` block. Check:

```bash
python3 -c "import tomllib;print(tomllib.load(open('$HOME/.codex/config.toml','rb')).get('agents'))"
```

The installer appends the block only when none exists, after taking a backup. Its defaults apply
only when a spawned agent specifies neither model nor effort; every persona sets both, so they are a
backstop, and parent session settings are unaffected.

### 2. Personas rendered

```bash
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --scope global --preview --json
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --check
```

Expect four generated personas: advisor, builder, reviewer and security-reviewer. A hand-written
worker file may also be present; the sync leaves it alone because it lacks the generated banner.

### 3. Skills and hooks installed

`install.sh` copies the four skills named in `install/skills/.gitignore` to `~/.codex/skills/` and
registers the goal hooks in `~/.codex/hooks.json`. It never writes trust state. Codex runs a
user-level hook only after you review and trust it, so open Codex once after the first install and
trust the two goal hooks, and again whenever their entries change. An untrusted hook does not run and
says nothing.

### 4. Global instructions

`~/.codex/AGENTS.md` is private and the installer does not touch it. Apply the execution section
from [global-instructions.md](global-instructions.md) to it and to `~/.claude/CLAUDE.md` in the same
sitting. The shared route block must be identical in both files, and `check_toolchain.py` reports
when it is not:

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/check_toolchain.py
```

## Format differences that matter

| | Claude Code | Codex |
|---|---|---|
| File | `.md`, YAML frontmatter, **body = system prompt** | `.toml`, `developer_instructions = '''…'''` |
| Model field | `model:` — alias, ID or `inherit` | `model = "gpt-6.1-sol"` |
| Effort | `effort:` low…max | `model_reasoning_effort` low…max, plus `ultra` |
| Restricting a judge | `tools:` allow-list and a derived deny-list | `sandbox_mode = "read-only"` |

Codex's sandbox is the **stronger** of the two: it constrains what shell commands can do, not just
which tools are offered.

Generated TOML uses literal `'''` strings, which take no escapes. A persona body containing `'''`
would silently truncate the instructions, so the generator raises rather than emitting it.

## Running Codex for goal work

The driver starts Codex sessions with `codex exec --approve-for-me`, which runs in the
workspace-write sandbox, and `review.py` calls it for read-only judging:

```bash
codex exec -s read-only --ignore-user-config --ignore-rules \
  -m <model> -c model_reasoning_effort=<effort> --json -C <dir> "<packet>"
```

- `--ignore-user-config --ignore-rules` keeps the user's MCP servers, apps and hooks out of a judge
- `--json` gives JSONL events including a `turn.completed` usage block
- Outside a git repository, add `--skip-git-repo-check`; run with stdin closed (`< /dev/null`) when
  calling it by hand, because it otherwise blocks reading stdin
- Budget about 23K input tokens per invocation before your content: the base system prompt

## Validation

```bash
# subagents on
python3 -c "import tomllib;print(tomllib.load(open('$HOME/.codex/config.toml','rb'))['agents'])"

# personas and skills present
ls ~/.codex/agents/*.toml ~/.codex/skills/

# installed copies match the repository
cd install && ./verify.sh --installed
```

Then open Codex in a migrated repo and confirm it reads `AGENTS.md` and can spawn a persona by name.

## What Codex does not get

- **`~/.claude/hooks/`** — session-start reporting, the graphify query advisor, lessons injection.
  Claude Code only. Codex gets the two goal hooks through `hooks.json`.
- **`~/.claude/settings.json`** — including `skillOverrides`.

Anything that must apply to both harnesses belongs in the repository, not in a hook or a skill.
Guidance that lives only in one harness silently does not apply to the other, and the failure is
invisible.
