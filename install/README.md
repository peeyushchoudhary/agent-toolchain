# Installing

Needs Python 3.10+ (the installer refuses older) and git. Claude Code, Codex or both; the Codex
side is skipped, and says so, when `$CODEX_HOME` (default `~/.codex`) does not exist.

```bash
cd install
./install.sh --dry-run     # print every action, write nothing (combines with the flags below)
./install.sh               # install or update; a second run changes nothing
./install.sh --uninstall   # remove what install.sh installed; restore the newest global-file backup
./install.sh --retire-v5   # install, then delete the named v5.1 and v6 leftovers
./verify.sh                # the repository gate
```

## What installs where

| Source | Claude Code | Codex |
|---|---|---|
| `global.md` | `~/.claude/CLAUDE.md` | `$CODEX_HOME/AGENTS.md` |
| `skills/execution-methodology/` (`SKILL.md`, `references/`, `agents/`, `scripts/`; not `tests/`) | `~/.claude/skills/` | `$CODEX_HOME/skills/` |
| `agents/{builder,reviewer,scout}.md` (in the skill), marked | `~/.claude/agents/` | — |
| `agents/{builder,reviewer,scout}.toml` (in the skill), marked | — | `$CODEX_HOME/agents/` |

A global file whose content differs is backed up beside it as `<name>.bak-<YYYYmmdd-HHMMSS>` first;
an equal one is not touched. The skill is staged and swapped in by rename, so a failed copy leaves
the working install intact. Files an earlier install left in the skill are kept and reported. The installer registers no
hook: the founder's open session is the chief and resumes a goal from `goal.py resume`. The one edit
it makes to `settings.json` or `hooks.json` is to drop the Stop registration a v7.0 install wrote
(the file is backed up first; one holding nothing else is removed).

Each installed agent file carries the line `# installed by execution-methodology install.sh;
uninstall removes an unchanged copy` (a `.md`'s second line, inside its frontmatter; a `.toml`'s
first); the copy inside the skill stays unmarked. An agent file of the same name without that line
is left alone and reported; a marked one is overwritten when it differs. No settings file is
written: when `~/.claude/settings.json` has no `worktree.baseRef`, the installer prints a reminder to
set `"worktree": {"baseRef": "head"}` ([codex.md](../docs/runbooks/codex.md)).

`--uninstall` removes the skill directories, removes a global file only when it is still
an unmodified copy of `global.md`, and then moves the newest backup back. It removes a marked agent
file only while it still equals the marked shipped copy; an edited one is left in place and reported,
and an unmarked one is never touched. Run twice, the second run
changes nothing.

`--retire-v5` deletes exactly the marked list in `install.sh`: the v5.1 skills and the v6 support
skills, the v6 hook scripts and their registrations, persona renders that carry the renderer's
GENERATED marker, and files inside the skill that v5.1, v6 or v7 shipped and v7.1 does not (including
the installed `tests/` and v7's launcher script). Anything else is reported and left in place. It is skipped if an install step
failed. Any failed step makes the script exit 1, naming the step.

## Rollback

From the repository root:

```bash
(cd install && ./install.sh --uninstall)                   # on the v7.1 tree
git rm -r -q install && git checkout methodology/v6-base -- install && (cd install && ./install.sh)
```

`git rm` comes first because a plain checkout overlays v6 on v7.1 and keeps the v7.1-only files, which
the v6 installer would then copy. To return to v7 instead, check out `goal/S-1/M2` in place of
`methodology/v6-base`.

## The gate

`./verify.sh` runs, from the repository root: the skill's unittest suite; the installer suite
(`tests/`, including the always-loaded size ceiling); `guard.py --self-test`; the guard over the
whole tree (`tests/tree_scan.py`); the docs link check (`tests/link_check.py`); the docs page check
(`docs.py lint`: every page's frontmatter, the generated index and the generated pointer files);
`docs.py stale`, printed as a warning that never fails the gate; a scan for names of
deleted components outside the records that may cite them; and `install.sh --dry-run` against a
scratch home. Each check prints `verify: <id> ok` or `FAIL: <id> (verify.checks)`; unittest output is
unchanged. The last line is `verify: PASS` or `verify: FAIL (<n> checks)`. `./verify.sh --installed`
adds a read-only parity check: in each home the skill, the global file and the marked agent files are
byte-equal to this tree.
