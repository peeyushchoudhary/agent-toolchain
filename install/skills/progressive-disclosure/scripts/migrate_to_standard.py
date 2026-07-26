#!/usr/bin/env python3
"""Plan (and optionally apply) a repository's migration to the shared structure standard.

Dry-run by default: prints an itemised plan and writes nothing. `--apply` executes it, and only
after taking a backup. Moves use `git mv` in a git repository so history follows the file.

Every markdown link that pointed at a moved path is rewritten by resolving the link against the
file's *original* directory, mapping it through the move table, and re-rendering it relative to the
file's *new* directory — so `../docs/agent/x.md` from a nested scoped guide lands correctly.

Usage:
  migrate_to_standard.py [ROOT]                  # plan only, writes nothing
  migrate_to_standard.py [ROOT] --apply          # back up, then execute
  migrate_to_standard.py [ROOT] --apply --force  # allow a dirty git tree (not advised)
  migrate_to_standard.py [ROOT] --no-create      # only rename/move; create nothing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_disclosure import (  # noqa: E402
    MD_IMPORT, MD_LINK, REQUIRED_DOC_DIRS, RENAMES, STANDARD_VERSION, strip_code,
    tracked_files, walk_files,
)

DIR_PURPOSE = {
    "agents": ("Agent routing", "Current. The index and area guides that route a coding agent."),
    "architecture": ("Architecture", "Current. How the system is built; defer to code when they disagree."),
    "product": ("Product", "Current intent. Interpret through shipped behaviour."),
    "decisions": ("Decisions", "Current. Accepted decision records; supersede earlier proposals."),
    "runbooks": ("Runbooks", "Current. Operational procedures meant to be followed literally."),
    "archive": ("Archive", "**Not authoritative.** Superseded and point-in-time material, kept for rationale only."),
}


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def is_git(root: Path) -> bool:
    return (root / ".git").is_dir()


def dirty(root: Path) -> int:
    if not is_git(root):
        return 0
    out = run_git(root, "status", "--porcelain").stdout
    return len([ln for ln in out.splitlines() if ln.strip()])


def detect_commands(root: Path) -> list[str]:
    """Real commands from this repo, so generated skeletons never invent a gate."""
    cmds: list[str] = []
    mk = root / "Makefile"
    if mk.is_file():
        targets = re.findall(r"^([a-zA-Z][\w.-]*)\s*:(?!=)", mk.read_text(encoding="utf-8", errors="replace"),
                             re.MULTILINE)
        for want in ("check", "test", "lint", "build"):
            if want in targets:
                cmds.append(f"make {want}")
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
            for want in ("test", "lint", "typecheck", "build"):
                if want in scripts:
                    cmds.append(f"pnpm {want}")
        except (json.JSONDecodeError, OSError):
            pass
    return cmds


def plan_moves(root: Path) -> list[tuple[Path, Path]]:
    moves: list[tuple[Path, Path]] = []
    for legacy, target in RENAMES.items():
        src, dst = root / legacy, root / target
        if src.exists() and not dst.exists():
            moves.append((src, dst))
    docs = root / "docs"
    if docs.is_dir():
        for f in sorted(docs.glob("RUNBOOK*.md")) + sorted(docs.glob("*RUNBOOK*.md")):
            if f.is_file():
                moves.append((f, docs / "runbooks" / f.name.lower()))
    return moves


def post_move_exists(p: Path, moves: list[tuple[Path, Path]]) -> bool:
    """Will `p` exist once the planned moves have run?

    Creates are computed against the post-move tree. Otherwise a file arriving via a move — say
    docs/agent/README.md landing at docs/agents/README.md — still looks missing, and the create
    step would overwrite it with a skeleton.
    """
    for src, dst in moves:
        if p == dst and src.exists():
            return True
        try:
            if (src / p.relative_to(dst)).exists():
                return True
        except ValueError:
            pass
    if p.exists():
        return not any(p == src or src in p.parents for src, _ in moves)
    return False


def plan_creates(root: Path, moves: list[tuple[Path, Path]]) -> list[tuple[Path, str]]:
    creates: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    def need(path: Path) -> bool:
        if path in seen or post_move_exists(path, moves):
            return False
        seen.add(path)
        return True

    if need(root / "CLAUDE.md"):
        creates.append((root / "CLAUDE.md", "@AGENTS.md\n"))
    if need(root / "AGENTS.md"):
        cmds = detect_commands(root) or ["TODO: add this repository's verification command"]
        creates.append((root / "AGENTS.md", (
            f"# {root.name} agent contract\n\n"
            "TODO: one paragraph on what this project is and what must never break.\n\n"
            "## Before changing code\n\n"
            "1. Read [docs/agents/README.md](docs/agents/README.md) and the guide it routes you to.\n"
            "2. Check `git status --short`; concurrent changes belong to their author.\n"
            "3. Prefer current code and tests over any prose that describes them.\n\n"
            "## Verification\n\n```bash\n" + "\n".join(cmds) + "\n```\n\n"
            "## Authority order\n\n"
            "Current code and tests > maintained guides > product docs > `docs/archive/` "
            "(historical rationale, never current behaviour).\n"
        )))
    idx = root / "docs" / "agents" / "README.md"
    if need(idx):
        cmd = (detect_commands(root) or ["TODO"])[0]
        creates.append((idx, (
            "# Agent start here\n\n"
            "Read this page, then only the guide that matches your task.\n\n"
            "| Task | Read next | Primary verification |\n| --- | --- | --- |\n"
            f"| TODO: name an area | TODO: link its guide | `{cmd}` |\n"
            f"| Agent docs, routing, or this index | [disclosure.md](disclosure.md) | "
            f"`{validate_command(root)}` |\n"
            "| Something in the docs misled you | [lessons.md](lessons.md) | append a dated entry |\n\n"
            "## Authority order\n\n"
            "1. Current code, tests, and generated contracts.\n"
            "2. This `docs/agents/` map and `docs/runbooks/`.\n"
            "3. `docs/product/` intent, read through shipped behaviour.\n"
            "4. `docs/archive/` — rationale only, never current truth.\n"
        )))
    disclosure = root / "docs" / "agents" / "disclosure.md"
    if need(disclosure):
        creates.append((disclosure, disclosure_doc(root)))

    lessons = root / "docs" / "agents" / "lessons.md"
    if need(lessons):
        creates.append((lessons, lessons_doc()))

    for d in REQUIRED_DOC_DIRS:
        readme = root / "docs" / d / "README.md"
        if need(readme):
            title, authority = DIR_PURPOSE[d]
            creates.append((readme, f"# {title}\n\n{authority}\n"))

    # The forge front page. Only ever created when absent — an existing README is someone's work,
    # and the validator's section checks are the right way to tell them what is missing.
    if need(root / "README.md"):
        creates.append((root / "README.md", readme_doc(root)))
    pr_template = root / ".github" / "pull_request_template.md"
    if need(pr_template):
        creates.append((pr_template, pr_template_doc()))
    return creates


def readme_doc(root: Path) -> str:
    """A README skeleton whose sections are the questions a reader actually arrives with."""
    cmds = detect_commands(root) or ["TODO: add this repository's verification command"]
    return f"""# {root.name}

TODO: one sentence on what this is and who it is for.

## Overview

TODO: the problem, and what this does about it.

## Current state

TODO: what ships today, and what is left. Link the plan of record.

| Milestone | State | Plan |
| --- | --- | --- |
| TODO | shipped / in progress / not started | TODO: link |

## Product requirements

| Document | Scope | Status |
| --- | --- | --- |
| TODO: link the PRD | TODO | current / superseded |

## Architecture

```mermaid
flowchart LR
    User --> App --> Data
```

TODO: two or three sentences on the shape of the system.
Detail: [docs/architecture/](docs/architecture/README.md).

## Components

| Component | Responsibility | Entry point | Detail |
| --- | --- | --- | --- |
| TODO | TODO | TODO | TODO: link its architecture page |

## Run locally

```bash
{cmds[0]}
```

## Working in this repository

Agents start at [AGENTS.md](AGENTS.md) and the route in
[docs/agents/README.md](docs/agents/README.md).

Work lands through a pull request at milestone granularity. Before merging, update this README so
its current state, components, and architecture still describe what is true.
"""


def pr_template_doc() -> str:
    """A checklist, not a workflow. No Actions minutes, nothing runs — GitHub just renders it.

    This is the only place the README question gets asked at the moment it matters: a structural
    validator can prove the sections exist, but only a human can say whether they are still true.
    """
    return """## What this changes

<!-- The milestone or slice, and why. -->

## Checks run

<!-- Paste the real command and its real outcome. A green push is not evidence. -->

- [ ] Area gate run locally, output pasted above
- [ ] README reviewed: current state, components, and architecture still true after this change
- [ ] Docs route still resolves (route validator / `make check-docs`)
- [ ] No secret, credential, or real personal data in the diff

## Remaining risk

<!-- What is still unproven, and what would catch it. -->
"""


def lessons_doc() -> str:
    """The cross-agent learning channel: the only one both harnesses can read and write."""
    return f"""<!-- progressive-disclosure standard v{STANDARD_VERSION} -->
# Route lessons

Things that misled an agent working in this repository, and the correction. Every agent reads and
appends here — it is the only learning channel all harnesses share, because a single agent's
private memory is invisible to the others.

## How to append

Add an entry when the route, a guide, or a tool sent you somewhere wrong and you had to work it
out. Newest first, two lines each.

```
### YYYY-MM-DD — short title
**Misleading:** what the docs or tooling implied.
**Actual:** what turned out to be true, with the file or command that proves it.
```

Do not log routine task notes or status. If the correction belongs in a guide, fix the guide and
skip the entry. Prune a lesson once its guide is fixed — one that no longer applies is noise.

## Lessons

_None yet._
"""


def validate_command(root: Path) -> str:
    """Name a command this repo can actually run. Never document a gate that does not exist."""
    mk = root / "Makefile"
    if mk.is_file() and re.search(r"^check-docs\s*:", mk.read_text(encoding="utf-8", errors="replace"),
                                  re.MULTILINE):
        return "make check-docs"
    return 'python3 "$HOME/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py" .'


def disclosure_doc(root: Path) -> str:
    """The per-repo copy of the disclosure rules, written against this repo's real commands."""
    return f"""<!-- progressive-disclosure standard v{STANDARD_VERSION} -->
# Agent disclosure route

How this repository routes a coding agent to the right context. Read this before editing
`AGENTS.md`, any directory-scoped guide, or this `docs/agents/` set.

## Three layers

| Layer | File | Budget | Job |
| --- | --- | --- | --- |
| Contract | root `AGENTS.md` (+ `CLAUDE.md` importing it) | ≤ 400 words | Invariants true everywhere, and where to go next |
| Index | [README.md](README.md) | ≤ 600 words | Task → one guide → one verification command |
| Scoped | `<dir>/AGENTS.md` (+ `CLAUDE.md`) | ≤ 40 words | "You are in `<dir>`; read `../docs/agents/<area>.md`" |

The scoped layer is the one that fires without an agent choosing to read anything: both harnesses
load the nearest entry file by proximity. Every source directory should carry one.

Keep both filenames per directory. `AGENTS.md` holds the text; `CLAUDE.md` is the single line
`@AGENTS.md`, so no agent reads a different contract from another.

## Rules

- **Route, don't restate.** A scoped file that explains architecture becomes another copy of the
  truth that will drift. Say where you are and what to read next.
- **One verification command per index row.** "Run the tests" is not routing.
- Historical plans, handoffs, and reports are rationale, never current behaviour.
- Adding a guide means adding its index row. An unrouted guide is invisible.

## Validate

```bash
{validate_command(root)}
```

Fails on a broken link or `@import`, a documented command that does not exist, an unrouted guide, a
source directory with no scoped entry file, or a file over budget. Run it after any edit under
`docs/agents/` or to any scoped `AGENTS.md` — a renamed guide breaks the route silently, and the
failure only shows up later as an agent that "ignored instructions".
"""


def map_path(p: Path, moves: list[tuple[Path, Path]]) -> Path | None:
    for src, dst in moves:
        if p == src:
            return dst
        if src.is_dir() or not src.suffix:
            try:
                return dst / p.relative_to(src)
            except ValueError:
                continue
    return None


def rewrite_links(root: Path, moves: list[tuple[Path, Path]], apply: bool) -> list[str]:
    """Repoint every markdown link that a move invalidated. Returns human-readable changes."""
    if not moves:
        return []
    files = tracked_files(root)
    if files is None:
        files = walk_files(root)
    changes: list[str] = []
    inverse = [(dst, src) for src, dst in moves]

    for f in sorted(files):
        if f.suffix.lower() != ".md" or not f.is_file():
            continue
        original_dir = (map_path(f, inverse) or f).parent
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        new_text = text
        targets = set(MD_IMPORT.findall(text)) | set(MD_LINK.findall(strip_code(text)))
        for t in targets:
            bare = t.split("#", 1)[0]
            if not bare or bare.startswith(("http://", "https://", "mailto:", "/")):
                continue
            old_abs = (original_dir / bare).resolve()
            mapped = map_path(old_abs, moves)
            if mapped is None:
                continue
            new_rel = os.path.relpath(mapped, f.parent)
            if new_rel == bare:
                continue
            new_text = re.sub(rf"(?<=[(\s]){re.escape(t)}(?=[)\s])",
                              t.replace(bare, new_rel), new_text)
        if new_text != text:
            changes.append(f"    relink {f.relative_to(root)}")
            if apply:
                f.write_text(new_text, encoding="utf-8")
    return changes


def backup(root: Path) -> Path:
    stamp = subprocess.run(["date", "+%Y%m%d-%H%M%S"], capture_output=True, text=True).stdout.strip()
    dest = root.parent / f".{root.name}-docs-backup-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    for rel in ("docs", "AGENTS.md", "CLAUDE.md"):
        src = root / rel
        if src.is_dir():
            shutil.copytree(src, dest / rel, dirs_exist_ok=True)
        elif src.is_file():
            shutil.copy2(src, dest / rel)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--apply", action="store_true", help="execute the plan (backs up first)")
    ap.add_argument("--force", action="store_true", help="allow --apply on a dirty git tree")
    ap.add_argument("--no-create", action="store_true", help="only move/rename; create nothing")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    moves = plan_moves(root)
    creates = [] if args.no_create else plan_creates(root, moves)
    n_dirty = dirty(root)

    print(f"migrate to standard: {root}")
    print(f"  git: {'yes' if is_git(root) else 'NO — backup is the only undo'}"
          f"   uncommitted: {n_dirty}")
    if not moves and not creates:
        print("  already conforms — nothing to do")
        return 0

    for src, dst in moves:
        print(f"    move   {src.relative_to(root)}  ->  {dst.relative_to(root)}")
    for path, _ in creates:
        print(f"    create {path.relative_to(root)}")

    if not args.apply:
        print(f"  DRY RUN — {len(moves)} move(s), {len(creates)} create(s). Nothing written.")
        print("  re-run with --apply to execute (a backup is taken first).")
        return 0

    if n_dirty and not args.force:
        print(f"  REFUSED: {n_dirty} uncommitted change(s). Commit or stash first, or pass --force.")
        return 1

    dest = backup(root)
    print(f"  backup: {dest}")

    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        moved = False
        if is_git(root):
            moved = run_git(root, "mv", str(src), str(dst)).returncode == 0
        if not moved:
            shutil.move(str(src), str(dst))
        print(f"    moved  {src.relative_to(root)} -> {dst.relative_to(root)}")

    for path, body in creates:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        print(f"    wrote  {path.relative_to(root)}")

    for line in rewrite_links(root, moves, apply=True):
        print(line)

    # A guide nothing links to is invisible. Editing someone's existing table is too fragile to
    # automate, so say plainly what to add; the validator's orphan-doc warning enforces it.
    index = root / "docs" / "agents" / "README.md"
    if index.is_file() and "disclosure.md" not in read_text(index):
        print("  ACTION: add a row to docs/agents/README.md routing to disclosure.md —")
        print("          otherwise it is an orphan and no agent will ever be sent to it.")

    print("  done. Nothing was committed — review the diff, then commit yourself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
