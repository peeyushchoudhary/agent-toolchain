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
| (no hook registration: `run.sh` registers the Stop hook per unattended session) | — | — |

A global file whose content differs is backed up beside it as `<name>.bak-<YYYYmmdd-HHMMSS>` first;
an equal one is not touched. The skill is staged and swapped in by rename, so a failed copy leaves
the working install intact. Files an earlier install left in the skill are kept and reported. The installer registers no
hook; it removes any `goal.py stop-hook` entry an older install left in `settings.json` or
`hooks.json` (a file that is not valid JSON is refused), because `run.sh` registers that hook per
unattended session and two registrations would race.

`--uninstall` removes the skill directories and the hook entries whose command names
`goal.py stop-hook` (a hook file left empty is deleted), removes a global file only when it is still
an unmodified copy of `global.md`, and then moves the newest backup back. Run twice, the second run
changes nothing.

`--retire-v5` deletes exactly the marked list in `install.sh`: the v5.1 skills and the v6 support
skills, the v6 hook scripts and their registrations, persona renders that carry the renderer's
GENERATED marker, and files inside the skill that v6 or v5.1 shipped and v7 does not (including the
installed `tests/`). Anything else is reported and left in place. It is skipped if an install step
failed. Any failed step makes the script exit 1, naming the step.

## Rollback

From the repository root:

```bash
(cd install && ./install.sh --uninstall)                   # on the v7 tree
git rm -r -q install && git checkout methodology/v6-base -- install && (cd install && ./install.sh)
```

`git rm` comes first because a plain checkout overlays v6 on v7 and keeps the v7-only files, which
the v6 installer would then copy. `skills/execution-methodology/tests/e2e_run.sh` rehearses this sequence in a temporary clone.

## The gate

`./verify.sh` runs, from the repository root: the skill's unittest suite; the installer suite
(`tests/`, including the always-loaded size ceiling); `guard.py --self-test`; the guard over the
whole tree (`tests/tree_scan.py`); the docs link check (`tests/link_check.py`); the docs page check
(`docs.py lint`: every page's frontmatter and the generated index); a scan for names of
deleted components outside the records that may cite them; and `install.sh --dry-run` against a
scratch home. Each check prints `verify: <id> ok` or `FAIL: <id> (verify.checks)`; unittest output is
unchanged. The last line is `verify: PASS` or `verify: FAIL (<n> checks)`. `./verify.sh --installed`
adds a read-only parity check: in each home the skill and global file are byte-equal to this tree and
no Stop registration remains.
