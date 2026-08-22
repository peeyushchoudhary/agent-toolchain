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
        runbooks = sorted({
            *docs.glob("RUNBOOK*.md"),
            *docs.glob("*RUNBOOK*.md"),
        })
        for f in runbooks:
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
            "<!-- agent-personas: TODO choose project specialists or base-only with a reason -->\n\n"
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
- Every project records a persona decision in the index: routed project persona sources, or an
  exact `base-only` marker with a non-empty reason. Silence is not a decision.

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
        # Non-None exactly when THIS FILE moved. Both directions matter and only one was handled:
        # a link breaks when its target moves, and equally when its *source* moves to another
        # directory and the relative path it was written as stops meaning the same thing.
        origin = map_path(f, inverse)
        original_dir = (origin or f).parent
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
                # The target stayed put. That is still a rewrite when the FILE moved: a runbook
                # rising from `docs/` to `docs/runbooks/` carries `architecture/design.md`, which
                # after the move points at `docs/runbooks/architecture/design.md` — a path that
                # does not exist. Measured on the migrator's own shipped runbook move.
                if origin is None:
                    continue
                mapped = old_abs
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


# --- docs/product/ mode ---------------------------------------------------------------------
# The schema in `spec_check.py` binds feature specs by ONE path glob, `docs/product/specs/F-*.md`.
# A repository that writes `docs/product/specs/<slug>/spec.md` — a real and reasonable layout — has
# every one of its specs walked, matched by no rule, and reported as a clean exit 0. Measured on one
# real corpus: 233 documents under `docs/product/specs/`, 0 bound, 0 findings, three times mistaken
# for clean. This mode closes that silence with a RENAME PLUS A HEADER and nothing else.
#
# IT NEVER EDITS A BODY. The transform is exactly: move the file to a bound name, prepend a front
# matter block, repoint the links the move invalidated. If a diff of the body is non-empty the mode
# is wrong, and `--product` prints the body word count before and after so that claim is checkable
# rather than asserted.

# `FED-C1`, `TRS-C11`, `NBY-C9`: an AREA prefix and an ordinal. The area prefix is the identifier a
# real repository actually uses — one corpus cites these 2,056 times across 239 files, including SQL
# migrations, a Java source file and CI config. IT MUST SURVIVE THE MIGRATION, so it is kept verbatim
# in the title and lowercased into the filename slug. The `id:` value is `F-<n>` for one reason only:
# `spec_check.ID_RE` is `^F-\d+[A-Z]?$` and refuses everything else.
AREA_ID_RE = re.compile(r"^(?P<id>[A-Z][A-Z0-9]{1,7}-[A-Z]{0,3}\d+[A-Z]?)\s*[—–:-]\s*(?P<title>.+?)\s*$")
H1_RE = re.compile(r"^#\s+(?P<text>.+?)\s*$", re.MULTILINE)
# The document's own statement of its parent. Read, never invented.
PARENT_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:Product spec|Product doc|Product|PRD|Parent)(?:\*\*)?\s*:\s*(?P<rest>.*)$",
    re.MULTILINE | re.IGNORECASE)
STATUS_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?Status(?:\*\*)?\s*:\s*(?P<rest>.*)$",
                            re.MULTILINE | re.IGNORECASE)
BOUND_GLOB = "docs/product/specs/F-*.md"
BOUND_ID_RE = re.compile(r"^F-(?P<n>\d+)")
# Index and routing files are not specs however they are named, and a plan is not its spec.
NOT_A_SPEC = {"readme.md", "agents.md", "claude.md", "index.md", "plan.md"}
SPEC_STATUSES = ("draft", "approved", "building", "shipped", "dropped")
# Written when a field cannot be derived. NOT a guess and deliberately not an empty value: an empty
# `status:`/`prd:` passes `check_keys` and `if target and ...` in silence, which is the same failure
# this whole mode exists to end. `TODO` fires B4/D3 on the next run and puts the gap in front of a
# human who can answer it.
UNDERIVED = "TODO"


class SpecMove:
    """One proposed rename-plus-header, and every field it could not derive."""

    def __init__(self, src: Path, root: Path) -> None:
        self.src, self.root = src, root
        self.rel = src.relative_to(root).as_posix()
        self.text = read_text(src)
        self.dst: Path | None = None
        self.identifier = ""
        self.area_id = ""
        self.title = ""
        self.prd = UNDERIVED
        self.status = UNDERIVED
        self.updated = UNDERIVED
        self.refusals: list[str] = []
        self.skipped = ""

    def front_matter(self) -> str:
        return ("---\n"
                f"id: {self.identifier}\n"
                f"title: {yaml_scalar(self.title)}\n"
                f"prd: {self.prd}\n"
                f"status: {self.status}\n"
                f"updated: {self.updated}\n"
                "---\n\n")

    def new_text(self) -> str:
        return self.front_matter() + self.text


def yaml_scalar(value: str) -> str:
    """Quote a title so an em dash, a colon or a `#` cannot change what the parser reads."""
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    return f'"{value.replace(chr(34), chr(39))}"'


def h1(text: str) -> str:
    m = H1_RE.search(text)
    return m.group("text").strip() if m else ""


def body_words(text: str) -> int:
    """Words below the front matter block. The measurement the hand migration was checked by."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                start = index + 1
                break
    return len("\n".join(lines[start:]).split())


def slugify(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return out or "spec"


def spec_shaped(path: Path, root: Path) -> bool:
    """Under `docs/product/specs/`, bound by nothing, and shaped like a spec rather than an index.

    The `spec.md` basename is the layout this mode exists for. The H1 test catches the flat
    `<AREA-ID> — <title>.md` variant. Both are checked against the real corpus: of 233 documents
    under one repository's `docs/product/specs/`, these two rules select the 65 specs and reject
    all 80 READMEs, all 65 plans and every area page — the plans because their H1 reads
    `Plan — FED-C1 …`, so the id is not first and `AREA_ID_RE` does not anchor.
    """
    if path.suffix.lower() != ".md" or not path.is_file():
        return False
    rel = path.relative_to(root).as_posix()
    if not rel.startswith("docs/product/specs/"):
        return False
    if path.match(BOUND_GLOB):
        return False
    if path.name.lower() in NOT_A_SPEC:
        return False
    return path.name.lower() == "spec.md" or bool(AREA_ID_RE.match(h1(read_text(path))))


def next_free_id(root: Path) -> int:
    """Continue the corpus's own numbering. Ids are never reused — `spec_check` rule B3 says so."""
    highest = 0
    specs = root / "docs" / "product" / "specs"
    for path in sorted(specs.glob("F-*.md")) if specs.is_dir() else []:
        m = BOUND_ID_RE.match(path.name)
        if m:
            highest = max(highest, int(m.group("n")))
    return highest + 1


def derive_prd(move: SpecMove, root: Path) -> None:
    """`prd:` must RESOLVE. Where nothing resolves, report it — never guess a path into existence.

    Order: the standard `docs/product/prd.md`, then the parent the document itself names on its own
    `Product spec:` / `PRD:` / `Parent:` line. One real repository's top-level product document is a
    `.docx`, which is not a markdown parent and is not treated as one; there the per-document line is
    the only true answer, and where a document states no parent this refuses and says so.
    """
    standard = root / "docs" / "product" / "prd.md"
    if standard.is_file():
        move.prd = "docs/product/prd.md"
        return
    for m in PARENT_LINE_RE.finditer(move.text):
        for target in MD_LINK.findall(m.group("rest")):
            resolved = (move.src.parent / target.split("#", 1)[0]).resolve()
            if resolved.is_file() and resolved.suffix.lower() == ".md":
                move.prd = resolved.relative_to(root).as_posix()
                return
    move.refusals.append(
        "prd: no `docs/product/prd.md` and the document names no parent that resolves to a "
        "markdown file — left as TODO for a human to point at the real parent")


def derive_status(move: SpecMove) -> None:
    m = STATUS_LINE_RE.search(move.text)
    if m:
        first = re.split(r"[^A-Za-z]+", m.group("rest").strip())[0].lower()
        if first in SPEC_STATUSES:
            move.status = first
            return
    move.refusals.append(
        f"status: the document states none of {' | '.join(SPEC_STATUSES)} — left as TODO rather "
        "than defaulted to `draft`, because guessing a status is how an undecided document becomes "
        "an approved one")


def derive_updated(move: SpecMove, root: Path) -> None:
    out = run_git(root, "log", "-1", "--format=%ad", "--date=short", "--", move.rel)
    date = out.stdout.strip() if out.returncode == 0 else ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        move.updated = date
        return
    move.refusals.append("updated: the file has no commit in this repository, so it has no date "
                         "to state — left as TODO")


def plan_product(root: Path) -> tuple[list[SpecMove], list[SpecMove]]:
    """Every spec-shaped document no rule binds. Returns (migratable, skipped)."""
    specs = root / "docs" / "product" / "specs"
    if not specs.is_dir():
        return [], []
    candidates = [p for p in sorted(specs.rglob("*.md")) if spec_shaped(p, root)]
    number = next_free_id(root)
    moves: list[SpecMove] = []
    skipped: list[SpecMove] = []
    taken: set[Path] = set()
    for path in candidates:
        move = SpecMove(path, root)
        heading = h1(move.text)
        m = AREA_ID_RE.match(heading)
        if not m:
            # NO ID MEANS NO LEGAL FILENAME, so there is nothing partial to do here. Renaming it to
            # an invented `F-<n>` would put a number nothing in the repository cites into a filename
            # 2,056 citations have to keep matching. Hand it back whole.
            move.skipped = (f"no feature id in the H1 {heading!r}" if heading
                            else "the document has no H1 to read a feature id or title from")
            skipped.append(move)
            continue
        move.area_id = m.group("id")
        move.title = heading
        move.identifier = f"F-{number}"
        number += 1
        slug = slugify(path.parent.name if path.name.lower() == "spec.md" else path.stem)
        if move.area_id.lower() not in slug:
            slug = f"{slugify(move.area_id)}-{slug}"
        move.dst = specs / f"{move.identifier}-{slug}.md"
        if move.dst.exists() or move.dst in taken:
            move.skipped = f"{move.dst.relative_to(root).as_posix()} already exists"
            skipped.append(move)
            continue
        taken.add(move.dst)
        derive_prd(move, root)
        derive_status(move)
        derive_updated(move, root)
        moves.append(move)
    return moves, skipped


def link_report(root: Path) -> tuple[int, list[str]]:
    """Every relative markdown link in the repository, and the ones that do not resolve.

    The second half of the hand migration's check: identical body words proves no prose moved,
    zero broken links proves the rename did not orphan a reference.
    """
    files = tracked_files(root)
    if files is None:
        files = walk_files(root)
    checked, broken = 0, []
    for f in sorted(files):
        if f.suffix.lower() != ".md" or not f.is_file():
            continue
        text = read_text(f)
        for target in set(MD_IMPORT.findall(text)) | set(MD_LINK.findall(strip_code(text))):
            bare = target.split("#", 1)[0].strip()
            if not bare or bare.startswith(("http://", "https://", "mailto:", "tel:", "/", "#")):
                continue
            checked += 1
            if not (f.parent / bare).resolve().exists():
                broken.append(f"{f.relative_to(root).as_posix()} -> {target}")
    return checked, broken


def print_product_plan(root: Path, moves: list[SpecMove], skipped: list[SpecMove],
                       checked: int, broken: list[str]) -> None:
    bound = len(list((root / "docs" / "product" / "specs").glob("F-*.md"))) \
        if (root / "docs" / "product" / "specs").is_dir() else 0
    print(f"migrate docs/product/ to the bound schema: {root}")
    print(f"  git: {'yes' if is_git(root) else 'NO — backup is the only undo'}"
          f"   uncommitted: {dirty(root)}")
    print(f"  bound today: {bound} document(s) match {BOUND_GLOB}")
    print(f"  spec-shaped and bound by nothing: {len(moves) + len(skipped)}")
    for move in moves:
        print(f"    move   {move.rel}")
        print(f"           ->  {move.dst.relative_to(root).as_posix()}")
        print(f"           + id: {move.identifier}   title: {yaml_scalar(move.title)}")
        print(f"             prd: {move.prd}   status: {move.status}   updated: {move.updated}")
        for refusal in move.refusals:
            print(f"           REFUSED TO DERIVE — {refusal}")
    if skipped:
        print(f"  NOT MIGRATED — {len(skipped)} document(s) a human has to decide:")
        for move in skipped:
            print(f"    skip   {move.rel}")
            print(f"           {move.skipped}; migrating it half way would be worse than "
                  "leaving it, so nothing is proposed")
    before = sum(body_words(move.text) for move in moves)
    after = sum(body_words(move.new_text()) for move in moves)
    print("  verification:")
    print(f"    body words   before {before}   after {after}   "
          f"{'IDENTICAL' if before == after else 'DIFFER — THE PLAN IS WRONG, IT TOUCHES PROSE'}")
    print(f"    links        checked {checked}   broken {len(broken)}")
    for item in broken[:10]:
        print(f"      broken   {item}")
    if len(broken) > 10:
        print(f"      ... and {len(broken) - 10} more")
    refused = sum(len(move.refusals) for move in moves)
    if refused or skipped:
        print(f"  {refused} field(s) left as `{UNDERIVED}` and {len(skipped)} document(s) skipped. "
              "Nothing was invented to fill them.")
    if moves:
        print("  NOTE: `updated:` is each file's OWN last commit date, as the document's history "
              "states it. Once you COMMIT this migration, `spec_check` rule A4 compares that value "
              "against the migration commit and will disagree. Either re-date the header in the "
              "same commit or expect A4 to name every file once.")


def run_product(root: Path, args: argparse.Namespace) -> int:
    moves, skipped = plan_product(root)
    checked, broken = link_report(root)
    print_product_plan(root, moves, skipped, checked, broken)
    if not moves:
        print("  nothing to migrate.")
        return 0
    if not args.apply:
        print(f"  DRY RUN — {len(moves)} rename(s) plus header. Nothing written.")
        print("  re-run with --product --apply to execute (a backup is taken first).")
        return 0
    n_dirty = dirty(root)
    if n_dirty and not args.force:
        print(f"  REFUSED: {n_dirty} uncommitted change(s). Commit or stash first, or pass --force.")
        return 1
    print(f"  backup: {backup(root)}")
    pairs = [(move.src, move.dst) for move in moves]
    for move in moves:
        move.dst.parent.mkdir(parents=True, exist_ok=True)
        moved = run_git(root, "mv", str(move.src), str(move.dst)).returncode == 0 if is_git(root) \
            else False
        if not moved:
            shutil.move(str(move.src), str(move.dst))
        # PREPEND ONLY. The body is written back byte for byte; there is no other write in this mode.
        move.dst.write_text(move.front_matter() + read_text(move.dst), encoding="utf-8")
        print(f"    moved  {move.rel} -> {move.dst.relative_to(root).as_posix()}")
    for line in rewrite_links(root, pairs, apply=True):
        print(line)
    after_words = sum(body_words(read_text(move.dst)) for move in moves)
    before_words = sum(body_words(move.text) for move in moves)
    checked, broken = link_report(root)
    print("  after --apply:")
    print(f"    body words   before {before_words}   after {after_words}   "
          f"{'IDENTICAL' if before_words == after_words else 'DIFFER — A BODY WAS EDITED'}")
    print(f"    links        checked {checked}   broken {len(broken)}")
    for item in broken[:10]:
        print(f"      broken   {item}")
    print("  done. Nothing was committed — review the diff, then commit yourself.")
    return 0 if before_words == after_words and not broken else 1


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
    ap.add_argument("--product", action="store_true",
                    help="migrate docs/product/specs/ documents no schema rule binds")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    # A separate mode, not an extra move table. The structure migration and the product migration
    # answer to different validators and are reviewed by different people; running them in one
    # commit makes each one's diff unreadable inside the other's.
    if args.product:
        return run_product(root, args)

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
