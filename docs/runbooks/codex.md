# Handoff — the Codex side

Codex reads a different set of files from Claude Code. Everything shared has to be either **in the
repository** (both harnesses read it) or **mirrored** (each harness reads its own copy).

Getting this wrong fails silently: Codex quietly follows an older contract and never announces what
it did not read.

## What Codex reads

| Path | Contents | Kept fresh by |
|---|---|---|
| `~/.codex/AGENTS.md` | Global instructions — operating model, GitHub rules, persona directive | Manual mirror of `~/.claude/CLAUDE.md` |
| `~/.codex/config.toml` | Session and `[agents]` settings | Manual |
| `~/.codex/agents/*.toml` | Persona definitions | `sync_personas.py --scope global` |
| `~/.codex/skills/` | Mirrored skills | `install_hooks.py --scope global` |
| `<repo>/AGENTS.md` | The project contract | Shared with Claude — same file |
| `<repo>/docs/agents/**` | The route | Shared with Claude — same files |
| `<repo>/.codex/agents/*.toml` | Project personas | `sync_personas.py --repo <repo> --scope project` |

**The repository layer is genuinely shared.** `AGENTS.md`, the route, the guides, and
`docs/agents/personas/` are read by both. That is why knowledge belongs in the repo and only
accelerators belong in a harness.

`CLAUDE.md` must be exactly `@AGENTS.md` — one line — so neither harness reads a different contract.

## Setup

### 1. Enable subagents

Codex will not spawn personas without this. Check first:

```bash
python3 -c "import tomllib;print(tomllib.load(open('$HOME/.codex/config.toml','rb')).get('agents'))"
```

If `None`, back up and append:

```bash
cp ~/.codex/config.toml ~/.codex/config.toml.bak-$(date +%Y%m%d-%H%M%S)
cat >> ~/.codex/config.toml <<'EOF'

[agents]
enabled = true
default_subagent_model = "gpt-5.6-terra"
default_subagent_reasoning_effort = "medium"
max_concurrent_threads_per_session = 6
EOF
python3 -c "import tomllib;tomllib.load(open('$HOME/.codex/config.toml','rb'));print('valid')"
```

Append at the end — a new top-level table is safe there. These defaults apply only when a spawned
agent specifies neither model nor effort; every persona sets both, so they are a backstop. **Parent
session settings are unaffected.**

For pre-Gate 1 design review, pre-Gate 2 plan review, and their scoped rereviews, spawn `reviewer`
with `fork_turns: "none"`. The default full-history fork is useful for ordinary delegated work but
is not independent review; a prompt that says to ignore inherited history does not make it fresh.
Pass named artifact paths only. A scoped rereview additionally names the persisted original finding,
correction or diff, corrected artifact, and governing frozen artifacts.

### 2. Render the personas

```bash
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --scope global --preview --json
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --scope global
```

Writes `~/.codex/agents/*.toml`. Verify:

```bash
python3 - <<'PY'
import tomllib, pathlib
for f in sorted((pathlib.Path.home()/".codex"/"agents").glob("*.toml")):
    d = tomllib.loads(f.read_text())
    assert d.get("name") and d.get("description") and d.get("developer_instructions")
    print(f"  {d['name']:24} {d.get('model','-'):16} {d.get('model_reasoning_effort','-'):8} {d.get('sandbox_mode','write')}")
PY
```

Expect 14 generated personas. A hand-written `grok_worker.toml` may also be present — the sync
leaves it alone because it lacks the generated banner.

### 3. Mirror the skills

```bash
python3 ~/.claude/skills/progressive-disclosure/scripts/install_hooks.py --scope global --preview --json
python3 ~/.claude/skills/progressive-disclosure/scripts/install_hooks.py --scope global
ls ~/.codex/skills/
```

The published declaration includes `methodology-management`; onboarding and migration remain
explicit compatibility routes, while conformance remains available for implicit read-only
assessment. Read the installed declaration rather than relying on a restated count. `graphify` may
also be present because its vendor installs it; this repository neither publishes nor manages it.

`install.sh` discovers the published skills from `install/skills/.gitignore` and mirrors that
declaration to Codex. `install_hooks.py` instead mirrors the fixed `MIRRORED_SKILLS` tuple in
`check_toolchain.py`; when adding a managed skill, update that roster before `install_hooks.py` can
mirror it. Re-run the appropriate command after a change. Skills are mirrored, not rendered.

### 4. Mirror the global instructions

The shared execution/maintenance route must be byte-identical across `~/.claude/CLAUDE.md` and
`~/.codex/AGENTS.md`. Verify:

```bash
python3 - <<'PY'
from pathlib import Path
heading = "# Execution and maintenance route\n"
a = Path("~/.claude/CLAUDE.md").expanduser().read_text().split(heading, 1)[1]
b = Path("~/.codex/AGENTS.md").expanduser().read_text().split(heading, 1)[1]
print("shared route identical:", a == b)
PY
```

There is no automation for this. When you change one, change the other in the same sitting.

## Format differences that matter

| | Claude Code | Codex |
|---|---|---|
| File | `.md`, YAML frontmatter, **body = system prompt** | `.toml`, `developer_instructions = '''…'''` |
| Model field | `model:` — `opus`/`sonnet`/`haiku`/`fable`/ID/`inherit` | `model = "gpt-5.6-sol"` |
| Effort | `effort:` low…max | `model_reasoning_effort` low…max, plus `ultra` |
| Restricting a judge | `disallowedTools: Write, Edit` | `sandbox_mode = "read-only"` |

Codex's sandbox is the **stronger** of the two: it constrains what shell commands can do, not just
which tools are offered.

Generated TOML uses literal `'''` strings, which take no escapes. A persona body containing `'''`
would silently truncate the instructions, so the generator raises rather than emitting it.

## Running Codex non-interactively

Not used by the persona system — dispatch stays in-harness — but useful, and these were all found
the hard way:

```bash
codex exec --json --skip-git-repo-check -s read-only \
  -m gpt-5.6-terra -C <dir> --output-last-message out.md "<prompt>" < /dev/null
```

- `--skip-git-repo-check` — it refuses to run outside a git repo without this
- `< /dev/null` — it otherwise blocks reading stdin
- `-s read-only` | `workspace-write` | `danger-full-access`
- `--json` gives JSONL events including a `turn.completed` usage block
- **Budget ~23K input tokens per invocation** before your content — the base system prompt

## Validation

```bash
# subagents on
python3 -c "import tomllib;print(tomllib.load(open('$HOME/.codex/config.toml','rb'))['agents'])"

# personas present and valid
ls ~/.codex/agents/*.toml | wc -l

# skills mirrored
ls ~/.codex/skills/

# in a repo: project personas rendered
ls <repo>/.codex/agents/ 2>/dev/null
python3 ~/.claude/skills/agent-personas/scripts/sync_personas.py --repo <repo> --scope project --check
python3 ~/.claude/skills/execution-methodology/scripts/sync_methodology.py --repo <repo> --status-json
```

Then open Codex in a migrated repo and confirm it reads `AGENTS.md` and can spawn a persona by name.

## What Codex does not get

- **`~/.claude/hooks/`** — session-start reporting, the graphify query advisor, lessons injection.
  Claude Code only. Codex has its own `.codex/hooks.json` mechanism, currently unused.
- **`~/.claude/settings.json`** — including `skillOverrides`.

Anything that must apply to both harnesses belongs in the repository, not in a hook or a skill.
Guidance that lives only in one harness silently does not apply to the other, and the failure is
invisible.
