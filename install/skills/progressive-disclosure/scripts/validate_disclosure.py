#!/usr/bin/env python3
"""Validate a repository's progressive-disclosure route for coding agents.

Layout-agnostic: instead of assuming a directory structure, this crawls the disclosure graph
outward from the root entry files (AGENTS.md / CLAUDE.md), following markdown links and @imports,
and reports the ways that route can silently break:

  ERROR   a link or @import that does not resolve        (the route is broken today)
  ERROR   a documented command that does not exist       (an agent will run it and fail)
  WARN    an agent doc nothing links to                  (orphan: written, never routed to)
  WARN    a code directory with no scoped entry file     (proximity disclosure has a hole)
  WARN    an entry or guide over its word budget         (disclosure degrades into a dump)
  WARN    route deeper than --max-depth hops             (too many reads before real work)
  NOTE    a lessons file past its entry count             (accretion, not a rule violation)

`--readme` adds the human-facing README contract; `--standard` the repository taxonomy; `--vs REF`
warns when source changed since REF and the README did not.

EXIT CODES: 0 checked and clean (warnings and notes allowed); 1 at least one ERROR; 2 NOT checked —
a file this depends on could not be read or decoded.

REPORTED STATES: `clean`, `findings` or `partial`. `partial` means a flag-gated family (`--standard`,
`--readme`, `--vs`) did not run; `NOT RUN` lines name it and the word `clean` is unreachable. The
status and the exit code are independent: the exit code is decided by ERRORS ALONE, so a consumer
decides pass/fail from `exit`, never from `status` (`test_not_evaluated_never_changes_the_exit_code`).

All reading goes through `read_doc`, which raises `Unexaminable`; no call site catches it; `main`
catches it once and exits 2. An unreadable file once let a broken route exit 0, so there is no
swallow and no flag to turn this off. A WARN never blocks: severity is decided here, not at the
call site.

Usage:
  validate_disclosure.py [ROOT] [--json] [--max-depth N]
                         [--entry-budget N] [--guide-budget N]
                         [--readme] [--vs REF] [--hook]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import deque
from pathlib import Path

ENTRY_NAMES = ("AGENTS.md", "CLAUDE.md")

# Directories that never hold agent-facing source worth a scoped guide.
SKIP_DIRS = {
    ".git", ".github", "node_modules", "build", "dist", "target", "out", "vendor",
    ".gradle", ".venv", "__pycache__", ".next", ".cache", "coverage", "tmp", "output",
    "graphify-out", ".agents", ".codex", ".claude", ".superpowers", ".impeccable",
    ".pnpm-store", "gradle", ".idea", ".vscode",
}

CODE_SUFFIXES = {
    ".java", ".kt", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs",
    ".rb", ".php", ".cs", ".swift", ".scala", ".tf", ".sql", ".sh",
}

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

# The architecture diagram. A raster is refused: it cannot be diffed, so it goes stale in silence,
# and the identifier guard reads image bytes as mojibake. A ```mermaid fence is text the forge
# renders, git diffs and the guard reads, and `readme-diagram-drift` compares it with the prose.
MERMAID_FENCE = re.compile(r"^```mermaid\s*$(.*?)^```\s*$", re.DOTALL | re.MULTILINE)
# A quoted node label in any shape bracket. Edge labels are not matched.
MERMAID_NODE_LABEL = re.compile(r"[\[({>]{1,2}\s*\"([^\"]+)\"\s*[\])}]{1,2}")
# Only the NAME before a line break or spaced em-dash must appear in the prose.
MERMAID_LABEL_BREAK = re.compile(r"<\s*br\s*/?\s*>|\s+—\s+", re.IGNORECASE)
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".avif"}
ARCHITECTURE_IMAGE_MARKER = re.compile(
    r"<!--\s*readme-architecture-image:\s*(\{[^\r\n]*\})\s*-->", re.IGNORECASE)
ARCHITECTURE_IMAGE_MARKER_ANY = re.compile(
    r"<!--\s*readme-architecture-image:", re.IGNORECASE)
# An @import must look like a path, or a bare `@Entity` annotation line reads as a broken import.
# Matched against code-stripped text: an import inside a fence is an illustration.
MD_IMPORT = re.compile(r"^@([^\s]*[./][^\s]*)\s*$", re.MULTILINE)
CODE_FENCE = re.compile(r"(?:```.*?```|~~~.*?~~~)", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`]*`")

CMD_MAKE = re.compile(r"\bmake\s+([a-zA-Z][\w.-]*)")
CMD_PNPM = re.compile(r"\bpnpm(?:\s+run)?\s+([a-z][\w:.-]*)")
CMD_NPM = re.compile(r"\b(?:npm|yarn)\s+run\s+([a-z][\w:.-]*)")
CMD_JUST = re.compile(r"\bjust\s+([a-zA-Z][\w:.-]*)")
CMD_TASK = re.compile(r"\btask\s+([a-zA-Z][\w:.-]*)")

# A lessons file grows by accretion, so a total word budget was answered by sharding it — gaming
# the metric rather than answering it. Lessons files get no total budget. Matched tightly:
# `lessons.md`, or `lessons` plus one separator and one token; `lessons-and-onboarding-guide.md`
# is an ordinary guide and keeps its budget.
LESSONS_NAME = re.compile(r"^lessons(?:[-_][a-z0-9]+)?\.md$")


def is_lessons_file(name: str) -> bool:
    return bool(LESSONS_NAME.match(name.lower()))


# The same reasoning, one document further: a RECORD (measurements, decisions, a weekly improvement
# log, a changelog) accretes dated entries that stay true. A total word budget on it can only be
# met by evicting evidence or by sharding, which games the metric rather than answering it. A
# record keeps the entry-count note below. Keyed on the basename, so renaming one drops it.
RECORD_NAME = re.compile(
    r"^(measurements|benchmarks|decisions|adr|rulings|improvements|changelog|history)"
    r"(?:[-_][a-z0-9]+)?\.md$")


def is_record_file(name: str) -> bool:
    """A document whose entries accrete rather than being revised. No total word budget."""
    return bool(RECORD_NAME.match(name.lower()))


# Entry COUNT is the honest measure of accretion, and it is informational only: about 3x the
# largest measured lessons file, so it speaks when a file wants archiving.
LESSONS_ENTRY_NOTE_AT = 24

ENTRY_HEADING = re.compile(r"^(#{2,6})\s+\S")


def lessons_entry_count(text: str) -> int:
    """How many entries a lessons file holds: the most-used heading level, ties toward the deeper."""
    levels: dict[int, int] = {}
    for line in strip_code(text).splitlines():
        m = ENTRY_HEADING.match(line)
        if m:
            levels[len(m.group(1))] = levels.get(len(m.group(1)), 0) + 1
    if not levels:
        return 0
    return max(levels.items(), key=lambda kv: (kv[1], kv[0]))[1]

# pnpm subcommands that are not package.json scripts.
PNPM_BUILTINS = {
    "install", "add", "remove", "exec", "dlx", "up", "update", "why", "list", "ls",
    "run", "store", "prune", "audit", "publish", "pack", "link", "unlink", "create",
    "init", "config", "rebuild", "fetch", "import", "licenses", "outdated", "patch",
    "setup", "server", "start", "test", "deploy", "env", "bin", "root",
}


class Report:
    def __init__(self) -> None:
        self.errors: list[dict] = []
        self.warns: list[dict] = []
        self.notes: list[dict] = []
        self.not_run: list[dict] = []
        self.info: dict = {}

    def error(self, kind: str, where: str, detail: str) -> None:
        self.errors.append({"kind": kind, "where": where, "detail": detail})

    def warn(self, kind: str, where: str, detail: str) -> None:
        self.warns.append({"kind": kind, "where": where, "detail": detail})

    def note(self, kind: str, where: str, detail: str) -> None:
        """Informational: never affects the exit code; listed after warnings."""
        self.notes.append({"kind": kind, "where": where, "detail": detail})

    def not_evaluated(self, check: str, why: str) -> None:
        """A whole check family that did not execute. NOT a finding, and NOT nothing.

        It never changes the exit code in either direction; it denies the word `clean` to the
        summary. A `partial` run with an ERROR still exits 1.
        """
        self.not_run.append({"check": check, "why": why})

    def verdict(self) -> tuple[str, int, str]:
        """`(status, exit_code, summary)` — the ONE place this run becomes a verdict.

        There is no path from a check that did not run to the word `clean`. `code` comes from
        `self.errors` alone, so `not_run` cannot move it. `partial` outranks `findings`.
        """
        code = 1 if self.errors else 0
        counts = (f"{len(self.errors)} error(s), {len(self.warns)} warning(s), "
                  f"{len(self.notes)} note(s)")
        missed = ", ".join(item["check"] for item in self.not_run)
        if self.not_run:
            head = "no findings in what ran" if not (self.errors or self.warns or self.notes) \
                else counts
            return "partial", code, (
                f"NOT A CLEAN RESULT — {head}, but {len(self.not_run)} check "
                f"famil{'y' if len(self.not_run) == 1 else 'ies'} did NOT RUN ({missed}). "
                f"Nothing is known about "
                f"{'it' if len(self.not_run) == 1 else 'them'}.")
        if not (self.errors or self.warns or self.notes):
            return "clean", code, "clean — every route resolves, every documented command exists"
        return "findings", code, counts


class Unexaminable(Exception):
    """Something this check had to read could not be read, so no verdict was reached.

    Not a `Report` finding: "I could not look" invalidates everything else the run would print, so
    it exits 2. There is no per-call-site handling and no flag to switch it off; every read goes
    through `read_doc`, and only `main` catches this.
    """

    def __init__(self, where: str, detail: str) -> None:
        super().__init__(f"{where}: {detail}")
        self.where = where
        self.detail = detail


def _display(path: Path, root: Path | None) -> str:
    """Repository-relative when it is inside the repository, absolute when it is not."""
    if root is not None:
        try:
            return str(path.resolve().relative_to(root.resolve()))
        except (ValueError, OSError):
            pass
    return str(path)


def read_doc(path: Path, root: Path | None = None, *, binary: bool = False) -> str | bytes:
    """Read a file this check depends on. Every way of not reading it raises. No exceptions.

    Text is decoded as utf-8-sig STRICTLY: with `errors="replace"` an undecodable file matches no
    link and no command, and absence of a match would read as absence of a problem. `-sig` strips a
    BOM that would otherwise defeat `MD_IMPORT`'s `^@` anchor. Binary callers get the raw bytes.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        # `str(exc)` repeats the absolute path that `_display` just abbreviated, so only the
        # errno text is interpolated.
        why = exc.strerror or type(exc).__name__
        raise Unexaminable(
            _display(path, root),
            f"could not be read ({why}), so nothing it contains was checked — not its links, not "
            f"the documents beyond them, not the commands it documents. Fix: make it readable, "
            f"then re-run",
        ) from exc
    if binary:
        return raw
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Unexaminable(
            _display(path, root),
            f"is not valid UTF-8 ({exc.reason} at byte {exc.start}), so its links and commands "
            f"cannot be read and their absence from this report would mean nothing. Fix: re-save "
            f"it as UTF-8, then re-run",
        ) from exc


def tracked_files(root: Path) -> list[Path] | None:
    """Prefer git's view so ignored/generated files never count as source.

    Includes untracked-but-not-ignored files: a scoped guide you just added must be validated
    before it is committed, not after.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    return [root / p for p in out.split("\0") if p]


def walk_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            found.append(Path(dirpath) / f)
    return found


# Non-authoritative history. Links INTO it are checked, but the crawl does not descend: an old plan
# SHOULD cite files that have since moved.
HISTORY_PREFIXES = ("docs/archive", "docs/superpowers", ".superpowers", "docs/eval-reports")


def is_history(root: Path, p: Path) -> bool:
    try:
        rel = p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    return any(rel == h or rel.startswith(h + "/") for h in HISTORY_PREFIXES)


def strip_code(text: str) -> str:
    """Links inside fences are usually illustrative, but commands inside them are real."""
    return INLINE_CODE.sub(" ", CODE_FENCE.sub(" ", text))


def code_only(text: str) -> str:
    """The inverse: just the fenced blocks and inline spans, where commands are read from.

    Prose is never scanned for commands: "make the" is English, not a Makefile target.
    """
    return "\n".join(CODE_FENCE.findall(text) + INLINE_CODE.findall(text))


def word_count(text: str) -> int:
    return len(text.split())


def resolve(base: Path, target: str) -> Path | None:
    target = target.split("#", 1)[0].strip()
    if not target or target.startswith(("http://", "https://", "mailto:", "tel:")):
        return None
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if not target or target.startswith(("http://", "https://")):
        return None
    return (base.parent / target).resolve() if not target.startswith("/") else Path(target)


def crawl(root: Path, files: list[Path], report: Report) -> tuple[dict[Path, int], list[Path]]:
    """BFS the disclosure graph. Returns {doc: depth} and the seeds.

    Every directory-scoped AGENTS.md/CLAUDE.md is a seed, not just the root pair: harnesses load
    them by proximity rather than by link, so nothing else would ever reach them and a broken link
    inside one would go unreported.
    """
    root_seeds = [root / n for n in ENTRY_NAMES if (root / n).is_file()]
    if not root_seeds:
        report.error(
            "no-entry", str(root),
            "no AGENTS.md or CLAUDE.md at the repository root — agents have no route in",
        )
    scoped = [f for f in files if f.name in ENTRY_NAMES and f.resolve() not in
              {s.resolve() for s in root_seeds}]
    seeds = root_seeds + sorted(scoped)
    if not seeds:
        return {}, []

    depth: dict[Path, int] = {}
    queue: deque[tuple[Path, int]] = deque((s.resolve(), 0) for s in seeds)
    while queue:
        doc, d = queue.popleft()
        if doc in depth and depth[doc] <= d:
            continue
        depth[doc] = d
        stripped = strip_code(read_doc(doc, root))
        targets: list[str] = list(MD_IMPORT.findall(stripped))
        targets += MD_LINK.findall(stripped)

        for t in targets:
            dest = resolve(doc, t)
            if dest is None:
                continue
            rel_from = doc.relative_to(root) if doc.is_relative_to(root) else doc
            if not dest.exists():
                report.error("broken-link", str(rel_from), f"-> {t}")
                continue
            # A link to a *directory* named like a document resolves, so `exists()` is satisfied
            # and the old code simply declined to queue it — link-to-real-doc and link-to-directory
            # produced identical output, which is the same defect class as the swallow one branch
            # up. This one IS a finding rather than an unexaminable: the checker can see exactly
            # what is wrong, it just is not a document.
            if dest.suffix.lower() == ".md" and not dest.is_file():
                report.error("link-not-a-file", str(rel_from),
                             f"-> {t} exists but is not a file, so it routes nowhere")
                continue
            if dest.suffix.lower() == ".md" and not is_history(root, dest):
                queue.append((dest, d + 1))
    return depth, seeds


def check_commands(root: Path, docs: list[Path], report: Report) -> None:
    make_targets: set[str] = set()
    makefile = root / "Makefile"
    if makefile.is_file():
        text = read_doc(makefile, root)
        make_targets |= set(re.findall(r"^([a-zA-Z][\w.-]*)\s*:(?!=)", text, re.MULTILINE))
        for line in re.findall(r"^\.PHONY:\s*(.*)$", text, re.MULTILINE):
            make_targets |= set(line.split())

    scripts: set[str] = set()
    for pkg in [root / "package.json"] + sorted(root.glob("*/package.json")):
        if pkg.is_file():
            # A package.json that will not parse leaves `scripts` empty, and an empty `scripts`
            # switches the whole `missing-script` check off for the repository — every documented
            # `pnpm <x>` passes because nothing is known to compare it against. Silently. That is
            # the swallow again, wearing a JSONDecodeError.
            try:
                parsed = json.loads(read_doc(pkg, root))
            except json.JSONDecodeError as exc:
                raise Unexaminable(
                    _display(pkg, root),
                    f"is not valid JSON ({exc.msg}, line {exc.lineno}), so the set of runnable "
                    f"scripts is unknown and no documented `pnpm`/`npm run` command could be "
                    f"verified. Fix: repair the JSON, then re-run",
                ) from exc
            if isinstance(parsed, dict) and isinstance(parsed.get("scripts"), dict):
                scripts |= set(parsed["scripts"])

    # just recipes: `name arg1 arg2:` at column 0, excluding `name := value` assignments.
    just_recipes: set[str] = set()
    justfile = next((root / n for n in ("justfile", "Justfile", ".justfile") if (root / n).is_file()), None)
    if justfile is not None:
        jtext = read_doc(justfile, root)
        just_recipes = set(re.findall(r"^([a-zA-Z][\w-]*)[^:=\n]*:(?!=)", jtext, re.MULTILINE))

    # Taskfile tasks: keys nested one level under a top-level `tasks:` mapping.
    task_names: set[str] = set()
    taskfile = next((root / n for n in ("Taskfile.yml", "Taskfile.yaml", "taskfile.yml") if (root / n).is_file()), None)
    if taskfile is not None:
        ttext = read_doc(taskfile, root)
        block = re.split(r"^tasks:\s*$", ttext, maxsplit=1, flags=re.MULTILINE)
        if len(block) == 2:
            for line in block[1].splitlines():
                if re.match(r"^\S", line):
                    break
                m = re.match(r"^\s{1,4}([a-zA-Z][\w:.-]*):\s*$", line)
                if m:
                    task_names.add(m.group(1))

    for doc in docs:
        text = code_only(read_doc(doc, root))
        rel = doc.relative_to(root) if doc.is_relative_to(root) else doc

        if makefile.is_file():
            for target in sorted(set(CMD_MAKE.findall(text))):
                if target not in make_targets:
                    report.error("missing-make-target", str(rel),
                                 f"`make {target}` is documented but not in Makefile")
        if scripts:
            found = set(CMD_PNPM.findall(text)) | set(CMD_NPM.findall(text))
            for script in sorted(found - PNPM_BUILTINS):
                if script not in scripts:
                    report.error("missing-script", str(rel),
                                 f"`pnpm {script}` is documented but not in any package.json")
        if just_recipes:
            for recipe in sorted(set(CMD_JUST.findall(text))):
                if recipe not in just_recipes:
                    report.error("missing-just-recipe", str(rel),
                                 f"`just {recipe}` is documented but not in the justfile")
        if task_names:
            for name in sorted(set(CMD_TASK.findall(text))):
                if name not in task_names:
                    report.error("missing-task", str(rel),
                                 f"`task {name}` is documented but not in the Taskfile")


def source_dirs(root: Path, files: list[Path]) -> dict[str, int]:
    """Directories that hold real source, and how many source files each has.

    Shared by the scoped-coverage check and the README component check so "what counts as a
    component" has exactly one definition. Two answers to that question would drift.
    """
    by_dir: dict[str, int] = {}
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) < 2:
            continue
        top = rel.parts[0]
        if top in SKIP_DIRS or top.startswith("."):
            continue
        if f.suffix.lower() in CODE_SUFFIXES:
            by_dir[top] = by_dir.get(top, 0) + 1

    # In a monorepo the real source lives one level below apps/ or packages/, so a top-level-only
    # sweep reports the container and misses every project inside it.
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) < 3 or rel.parts[0] not in MONOREPO_CONTAINERS:
            continue
        if f.suffix.lower() in CODE_SUFFIXES:
            sub = f"{rel.parts[0]}/{rel.parts[1]}"
            by_dir[sub] = by_dir.get(sub, 0) + 1
            by_dir.pop(rel.parts[0], None)
    return by_dir


def check_scoped_coverage(root: Path, files: list[Path], depth: dict[Path, int],
                          report: Report) -> list[str]:
    """Every top-level directory holding source should carry its own entry file — or hold a
    reachable document strictly beneath it (so `docs/` is cleared by a routed `docs/agents/`).

    Reachability is the crawled graph, not the filesystem: a directory holding only unrouted
    documents still fires.
    """
    by_dir = source_dirs(root, files)
    reached_dirs = {doc.parent.resolve() for doc in depth}

    missing = []
    for d, n in sorted(by_dir.items()):
        dpath = (root / d).resolve()
        if any((root / d / name).is_file() for name in ENTRY_NAMES):
            continue
        if any(rd != dpath and rd.is_relative_to(dpath) for rd in reached_dirs):
            continue
        report.warn("unscoped-dir", d,
                    f"{n} source files, no {' or '.join(ENTRY_NAMES)} to route from")
        missing.append(d)
    return missing


def check_orphans(root: Path, depth: dict[Path, int], files: list[Path], report: Report) -> None:
    """A doc sitting beside routed docs but reachable from nothing is written-and-forgotten.

    Only applies to directories the index routes *into*: two or more docs reached by a link.
    """
    counts: dict[Path, int] = {}
    for doc, d in depth.items():
        if d >= 1:
            counts[doc.parent] = counts.get(doc.parent, 0) + 1
    routed_dirs = {p for p, n in counts.items() if n >= 2 and p != root}
    for f in files:
        if f.suffix.lower() != ".md" or not f.is_file():
            continue
        rf = f.resolve()
        if rf in depth or rf.parent not in routed_dirs:
            continue
        rel = f.relative_to(root) if f.is_relative_to(root) else f
        report.warn("orphan-doc", str(rel), "sits with routed docs but nothing links to it")


# ── The README contract (opt-in via --readme, implied by --standard) ─────────────────────────────
# Heading matching is deliberately loose: what is enforced is that each question is answered.
README_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("overview", r"^#{2,3}\s*(overview|why\b|what is\b|summary|about\b|the problem)",
     "what this project is"),
    ("current-state", r"^#{2,3}\s*(current state|project state|status\b|roadmap|milestones?\b|"
                      r"where (we|things) (are|stand)|progress)",
     "current state: what ships today, what is left, linked to the plan"),
    ("requirements", r"^#{2,3}\s*(product|requirements?|prds?\b|specs?\b|scope\b)",
     "product requirements, linking the PRD documents"),
    ("architecture", r"^#{2,3}\s*(architecture|high[- ]level design|hld\b|system design|"
                     r"how it works|how data (moves|flows))",
     "high-level architecture, with a diagram"),
    ("components", r"^#{2,3}\s*(components?|low[- ]level design|lld\b|component design|"
                   r"module map|repository map|codebase map|project structure)",
     "the component map, one row per component with a deep-dive link"),
    ("run", r"^#{2,3}\s*(run(ning)? locally|getting started|quick ?start|installation|"
            r"local (setup|development)|development\b|usage\b)",
     "how to run it locally"),
    ("contributing", r"^#{2,3}\s*(working in this (repo|repository)|contributing|"
                     r"development workflow|for agents|release model|how we work)",
     "how work gets done here — the agent route and the PR rules"),
)

# Only the unambiguous, high-signal shapes. A generic "long random string" rule fires on lockfile
# hashes and base64 fixtures, and a guard that cries wolf is a guard that gets bypassed.
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("AWS access key id", r"\bAKIA[0-9A-Z]{16}\b"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    ("Google API key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("Slack token", r"\bxox[baprs]-[0-9A-Za-z-]{10,}"),
    ("Stripe live key", r"\bsk_live_[0-9a-zA-Z]{20,}"),
    # Split so this file does not itself contain a matching literal.
    ("private key block", r"-----BEGIN (?:[A-Z ]+ )?PRIVATE" + r" KEY-----"),
)

PRD_HINT = re.compile(r"(?i)\bprd\b|product[-_ ]requirements?")
PLAN_HINT = re.compile(r"(?i)(^|/)(plans?|roadmap)(/|[-_.]|$)")


def readme_path(root: Path) -> Path | None:
    for name in ("README.md", "Readme.md", "readme.md"):
        if (root / name).is_file():
            return root / name
    return None


def section_body(text: str, pattern: str) -> str:
    """The lines under the first heading matching `pattern`, up to the next heading of that level."""
    lines = text.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        if start is None:
            if re.match(pattern, line, re.IGNORECASE):
                start = i + 1
                level = len(line) - len(line.lstrip("#"))
            continue
        m = re.match(r"^(#{1,6})\s", line)
        if m and len(m.group(1)) <= level:
            return "\n".join(lines[start:i])
    return "\n".join(lines[start:]) if start is not None else ""


def check_readme(root: Path, files: list[Path], report: Report) -> None:
    """Enforce the README contract: the project's front page for a human, not for the router."""
    readme = readme_path(root)
    if readme is None:
        report.error("readme-missing", "README.md",
                     "no README at the repository root — the forge front page is blank")
        return

    rel_readme = readme.name
    text = read_doc(readme, root)
    prose = strip_code(text)

    for key, pattern, what in README_SECTIONS:
        if not re.search(pattern, text, re.MULTILINE | re.IGNORECASE):
            report.error("readme-missing-section", rel_readme, f"nothing covers {what}")

    # Links are resolved here rather than by making the README a crawl seed: seeding it would mark
    # everything it mentions as "routed" and quietly disable the orphan check for the whole repo.
    linked: set[Path] = set()
    for target in MD_LINK.findall(prose) + re.findall(r"<img[^>]+src=\"([^\"]+)\"", text):
        dest = resolve(readme, target)
        if dest is None:
            continue
        if not dest.exists():
            report.error("readme-broken-link", rel_readme, f"-> {target}")
            continue
        linked.add(dest.resolve())

    # A diagram inside the architecture section specifically, and one this toolchain can read.
    arch_pattern = next(p for k, p, _ in README_SECTIONS if k == "architecture")
    arch_body = section_body(text, arch_pattern)
    if arch_body:
        fence = MERMAID_FENCE.search(arch_body)
        accepted_raster: str | None = None
        marker_text = strip_code(text)
        marker_starts = ARCHITECTURE_IMAGE_MARKER_ANY.findall(marker_text)
        markers = list(ARCHITECTURE_IMAGE_MARKER.finditer(marker_text))
        if len(marker_starts) > 1:
            report.error("readme-architecture-image", rel_readme,
                         "more than one readme-architecture-image declaration exists")
        elif len(marker_starts) == 1 and len(markers) != 1:
            report.error("readme-architecture-image", rel_readme,
                         "the readme-architecture-image declaration is malformed")
        elif len(markers) == 1:
            marker = markers[0]
            problem: str | None = None
            try:
                declaration = json.loads(marker.group(1))
            except json.JSONDecodeError:
                declaration = None
                problem = "the readme-architecture-image declaration is not valid JSON"
            if problem is None and (not isinstance(declaration, dict)
                                    or set(declaration) != {"path", "sha256", "text"}
                                    or not all(isinstance(declaration.get(key), str)
                                               and declaration[key].strip()
                                               for key in ("path", "sha256", "text"))):
                problem = "the declaration must contain only nonempty path, sha256, and text strings"
            if problem is None and marker.group(0) not in strip_code(arch_body):
                problem = "the declaration must be inside the architecture section"

            image = counterpart = None
            if problem is None:
                image_raw = declaration["path"]
                text_raw = declaration["text"]
                try:
                    image = (root / image_raw).resolve()
                    counterpart = (root / text_raw).resolve()
                    repo_root = root.resolve()
                except OSError as exc:
                    why = exc.strerror or type(exc).__name__
                    raise Unexaminable(
                        rel_readme,
                        f"declared architecture paths could not be resolved ({why}), so their "
                        "repository containment could not be checked. Fix: make the paths "
                        "resolvable, then re-run",
                    ) from exc
                except ValueError:
                    problem = "declared paths are not valid local repository paths"
                if problem is None and (Path(image_raw).is_absolute()
                                        or Path(text_raw).is_absolute()
                                        or not image.is_relative_to(repo_root)
                                        or not counterpart.is_relative_to(repo_root)):
                    problem = "declared paths must stay inside the repository, including through symlinks"
                elif problem is None and Path(image_raw).suffix.lower() not in RASTER_SUFFIXES:
                    problem = f"{image_raw} is not a supported raster image"
                elif problem is None and not image.is_file():
                    problem = f"declared image {image_raw} is missing or not a file"
                elif problem is None and not counterpart.is_file():
                    problem = f"declared text counterpart {text_raw} is missing or not a file"
                elif problem is None and not re.fullmatch(r"[0-9a-fA-F]{64}", declaration["sha256"]):
                    problem = "declared sha256 must be exactly 64 hexadecimal characters"
                elif problem is None:
                    image_bytes = read_doc(image, root, binary=True)
                    counterpart_text = read_doc(counterpart, root)
                    actual = hashlib.sha256(image_bytes).hexdigest()
                    if actual != declaration["sha256"].casefold():
                        problem = f"declared sha256 does not match {image_raw}"
                    elif not counterpart_text.strip():
                        problem = f"declared text counterpart {text_raw} has no descriptive content"
                    else:
                        embedded_targets = (re.findall(r"!\[[^\]]*\]\(([^)\s]+)", arch_body)
                                            + re.findall(r"<img[^>]+src=\"([^\"]+)\"", arch_body))
                        if image_raw not in embedded_targets:
                            problem = f"declared image {image_raw} is not embedded exactly in the architecture section"
            if problem is not None:
                report.error("readme-architecture-image", rel_readme, problem)
            else:
                accepted_raster = declaration["path"]

        if fence is None and accepted_raster is None:
            report.error("readme-no-diagram", rel_readme,
                         "the architecture section has neither a ```mermaid diagram nor a valid "
                         "declared architecture image")
        embedded = (re.findall(r"!\[[^\]]*\]\(([^)\s]+)", arch_body)
                    + re.findall(r"<img[^>]+src=\"([^\"]+)\"", arch_body))
        for target in embedded:
            clean = target.split("#")[0].split("?")[0]
            if Path(clean).suffix.lower() in RASTER_SUFFIXES and target != accepted_raster:
                report.error("readme-raster-diagram", rel_readme,
                             f"{target} draws the architecture as pixels — no diff shows it going "
                             "stale, and a private name inside it is invisible to the guard")
        # Every node's NAME must appear verbatim in the rest of the section, so the diagram cannot
        # drift from the prose beside it.
        if fence is not None:
            rest = arch_body[:fence.start()] + arch_body[fence.end():]
            for label in MERMAID_NODE_LABEL.findall(fence.group(1)):
                # `or label`: an empty name would match everything and silence the check.
                name = MERMAID_LABEL_BREAK.split(label, 1)[0].strip() or label
                if name.casefold() not in rest.casefold():
                    report.error("readme-diagram-drift", rel_readme,
                                 f"the diagram has a box named \"{name}\" that the architecture "
                                 "section never mentions — one of the two has moved on")

    # Every component a reader can see in the tree should be findable from the front page.
    for d in sorted(source_dirs(root, files)):
        if not re.search(rf"(?<![\w/-]){re.escape(d)}(?![\w-])", text):
            report.error("readme-missing-component", rel_readme,
                         f"`{d}/` holds source but is never mentioned")

    # Product intent and the plan of record. Both are things a reader asks for by name and cannot
    # find by grepping code.
    prds = sorted(f for f in files
                  if f.suffix.lower() == ".md" and PRD_HINT.search(f.name)
                  and "archive" not in f.relative_to(root).parts if f.is_relative_to(root))
    for prd in prds:
        if prd.resolve() not in linked:
            report.error("readme-unlinked-prd", rel_readme,
                         f"{prd.relative_to(root)} is a PRD but the README never links it")

    has_plan_dir = any(PLAN_HINT.search(str(f.relative_to(root))) for f in files
                       if f.is_relative_to(root) and f.suffix.lower() == ".md")
    if has_plan_dir and not any(PLAN_HINT.search(str(p.relative_to(root)))
                                for p in linked if p.is_relative_to(root)):
        report.error("readme-unlinked-plan", rel_readme,
                     "this repo has implementation plans but the README links none of them")

    arch = root / "docs" / "architecture"
    if arch.is_dir() and not any(p.is_relative_to(arch) for p in linked):
        report.error("readme-unlinked-architecture", rel_readme,
                     "docs/architecture/ exists but the README never links into it")


def _standard_repo(root: Path) -> bool:
    disclosure = root / "docs" / "agents" / "disclosure.md"
    if not disclosure.is_file():
        return False
    return "progressive-disclosure standard v" in read_doc(disclosure, root)


def check_personas(root: Path, report: Report) -> None:
    """Generated agent files must match the persona sources they came from.

    Runs for every standard repository, including one with no persona sources, because generated
    agents are committed and their drift is invisible in review. Degrades to a warning when the
    tool is absent.
    """
    overlays = root / "docs" / "agents" / "personas"
    has_sources = (overlays.is_dir()
                   and any(p.name.lower() != "readme.md" for p in overlays.glob("*.md")))
    has_outputs = any((root / harness / "agents").is_dir()
                      for harness in (".claude", ".codex"))
    if not has_sources and not has_outputs and not _standard_repo(root):
        return
    script = Path.home() / ".claude" / "skills" / "agent-personas" / "scripts" / "sync_personas.py"
    if not script.is_file():
        report.warn("persona-tool-missing", "docs/agents/personas",
                    f"overlays exist but {script} is not installed; cannot verify generated agents")
        return
    try:
        r = subprocess.run(["python3", str(script), "--repo", str(root), "--check"],
                           capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        report.warn("persona-check-failed", "docs/agents/personas", str(e))
        return
    if r.returncode == 1:
        detail = " / ".join(l.strip() for l in r.stdout.splitlines() if "STALE" in l or "/" in l)
        report.error("persona-drift", "docs/agents/personas",
                     f"generated agents do not match their source — run "
                     f"`sync_personas.py --repo .` ({detail[:160]})")
    elif r.returncode == 2:
        detail = (r.stderr or r.stdout).strip()[:160]
        report.error("persona-source-invalid", "docs/agents/personas",
                     detail or "persona source could not be parsed")
    elif r.returncode not in (0, 1):
        report.warn("persona-check-failed", "docs/agents/personas", r.stderr.strip()[:160])


def check_readme_freshness(root: Path, base: str, report: Report) -> None:
    """Warn when a branch changed source but left the README alone.

    A warning, never an error: many real changes correctly leave the front page untouched.
    """
    try:
        merge_base = subprocess.run(["git", "-C", str(root), "merge-base", base, "HEAD"],
                                    capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        changed = subprocess.run(["git", "-C", str(root), "diff", "--name-only", merge_base, "HEAD"],
                                 capture_output=True, text=True, timeout=30, check=True).stdout.split()
    except (subprocess.SubprocessError, FileNotFoundError):
        report.warn("readme-freshness-unknown", base, "could not diff against this ref")
        return
    if not changed:
        return
    if any(Path(c).name.lower() == "readme.md" for c in changed):
        return

    files = [root / c for c in changed]
    touched = sorted(source_dirs(root, files))
    if touched:
        report.warn("readme-stale", "README.md",
                    f"{len(changed)} file(s) changed under {', '.join(touched)} since {base}, "
                    "README untouched — confirm the front page is still true before merging")


# ── The shared structure standard (opt-in via --standard) ────────────────────────────────────────
# Bump when the standard's rules change. Generated per-repo copies carry this stamp so a repo
# running an older standard can be detected instead of silently drifting.
STANDARD_VERSION = "1.2"
STAMP = "<!-- progressive-disclosure standard v"

TIER1 = ("AGENTS.md", "CLAUDE.md", "docs/agents/README.md")
# Directories that hold sub-projects rather than code of their own; a monorepo puts its real
# source one level further down, so top-level-only coverage checks miss every app in them.
MONOREPO_CONTAINERS = ("apps", "packages", "services", "libs", "modules", "projects", "crates")
REQUIRED_DOC_DIRS = ("agents", "architecture", "product", "decisions", "runbooks", "archive")
# Legacy spellings → where the standard puts them. Drives both this check and the migrator.
RENAMES = {
    "docs/agent": "docs/agents",
    "docs/index.md": "docs/README.md",
    "docs/audit": "docs/archive/audit",
    "docs/audits": "docs/archive/audits",
    "docs/operations": "docs/runbooks",
    "docs/council": "docs/decisions/council",
    "docs/escalations": "docs/decisions/escalations",
    "docs/founder": "docs/product/founder",
    "docs/handoffs": "docs/archive/handoffs",
    "docs/handoff.md": "docs/agents/handoff.md",
}


def check_standard(root: Path, report: Report) -> None:
    """Enforce the cross-project structure standard. Opt-in: only runs under --standard."""
    for rel in TIER1:
        if not (root / rel).is_file():
            report.error("standard-missing", rel, "required by the standard (tier 1)")

    claude = root / "CLAUDE.md"
    if claude.is_file():
        body = [ln.strip() for ln in read_doc(claude, root).splitlines() if ln.strip()]
        if body != ["@AGENTS.md"]:
            report.warn("standard-claude-md", "CLAUDE.md",
                        "should be exactly `@AGENTS.md` so both agents read one contract")

    docs = root / "docs"
    if docs.is_dir():
        for d in REQUIRED_DOC_DIRS:
            if not (docs / d).is_dir():
                report.error("standard-missing-dir", f"docs/{d}", "required by the standard")
            elif not (docs / d / "README.md").is_file():
                report.warn("standard-dir-readme", f"docs/{d}",
                            "needs a README.md stating its purpose and authority level")

    for legacy, target in RENAMES.items():
        if (root / legacy).exists():
            report.error("standard-legacy-name", legacy, f"the standard calls this `{target}`")

    # The standard sets tighter budgets than the generic defaults: 400 words for the root
    # contract, 40 for a scoped file that should do nothing but route.
    for entry in sorted(root.glob("*/AGENTS.md")) + [root / "AGENTS.md"]:
        if not entry.is_file():
            continue
        words = word_count(read_doc(entry, root))
        rel = entry.relative_to(root)
        limit = 400 if entry.parent == root else 40
        if words > limit:
            report.warn("standard-over-budget", str(rel),
                        f"{words} words > {limit} for {'the contract' if limit == 400 else 'a scoped router'}")

    agents_dir = root / "docs" / "agents"
    if agents_dir.is_dir():
        for f in sorted(agents_dir.glob("*.md")):
            if f.name != "README.md" and f.name != f.name.lower():
                report.warn("standard-filename-case", f"docs/agents/{f.name}",
                            "use lowercase-kebab filenames")

    # Scaffolding that was generated but never finished still passes every structural check, so
    # a bootstrapped repo can sit for months with a placeholder contract nobody notices. The README
    # is included because a skeleton front page is worse than none: it looks answered.
    for rel in TIER1 + ("docs/agents/disclosure.md", "README.md"):
        f = root / rel
        if not f.is_file():
            continue
        hits = [ln.strip() for ln in read_doc(f, root).splitlines() if "TODO" in ln]
        if hits:
            report.error("standard-placeholder", rel,
                         f"{len(hits)} unfinished placeholder(s), first: {hits[0][:60]}")

    # A per-repo copy generated from an older standard drifts silently otherwise.
    disc = root / "docs" / "agents" / "disclosure.md"
    if disc.is_file():
        text = read_doc(disc, root)
        if STAMP in text:
            found = text.split(STAMP, 1)[1].split(" ", 1)[0].strip().rstrip("-->").strip()
            if found != STANDARD_VERSION:
                report.warn("standard-version-drift", "docs/agents/disclosure.md",
                            f"generated from standard v{found}; current is v{STANDARD_VERSION}")
        else:
            report.warn("standard-version-drift", "docs/agents/disclosure.md",
                        f"no version stamp; regenerate to track standard v{STANDARD_VERSION}")


def check_stale_paths(root: Path, depth: dict[Path, int], files: list[Path], report: Report) -> None:
    """Flag code paths a routed guide cites that no longer exist anywhere plausible.

    Guides cite paths relative to the area they describe (`components/AppShell.tsx` in web.md means
    `web/src/components/...`), so resolution tries every plausible base. When in doubt this stays
    quiet: a false positive here trains readers to ignore the whole report.
    """
    bases = [root]
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."):
            bases += [d, d / "src"]

    # A citation that names a file which exists *somewhere* is imprecise, not stale. `compare.py`
    # living at `ai/eval/compare.py` is exactly the case the base list cannot guess, and warning on
    # it is the false positive this check promised not to produce.
    known_names = {f.name for f in files}

    cited = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:java|kt|ts|tsx|js|jsx|mjs|py|go|rs|sql|tf))`")
    for doc, _ in sorted(depth.items()):
        if not doc.is_file() or doc.suffix != ".md":
            continue
        rel = doc.relative_to(root) if doc.is_relative_to(root) else doc
        stem_bases = bases + [root / doc.stem, root / doc.stem / "src"]
        text = read_doc(doc, root)
        for path in sorted(set(cited.findall(text))):
            if any((b / path).exists() for b in stem_bases):
                continue
            if Path(path).name in known_names:
                continue
            report.warn("stale-path", str(rel), f"cites `{path}`, which resolves nowhere")


def check_stale_guides(root: Path, seeds: list[Path], report: Report) -> None:
    """Warn when a folder's area guide predates commits to the folder's non-doc files.

    Only scoped entry files count (`D` is their folder), and only guides they link under `D`.
    A guide never committed, or any git failure, is skipped. A WARN, never an ERROR.
    """
    base, seen = root.resolve(), set()

    def git(*args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(base), *args], capture_output=True, text=True,
                               timeout=30)
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""
        return r.stdout.strip() if r.returncode == 0 else ""

    for entry in seeds:
        d = entry.resolve().parent
        if d == base or not entry.is_file():
            continue
        stripped = strip_code(read_doc(entry, root))
        for t in MD_IMPORT.findall(stripped) + MD_LINK.findall(stripped):
            guide = resolve(entry, t)
            if (guide is None or guide.suffix.lower() != ".md" or not guide.is_file()
                    or guide == entry.resolve() or not guide.is_relative_to(d)
                    or (guide, d) in seen):
                continue
            seen.add((guide, d))
            g = git("log", "-1", "--format=%H", "--", str(guide))
            rel = d.relative_to(base).as_posix()
            n = g and git("rev-list", "--count", f"{g}..HEAD", "--", f":(literal){rel}",
                          ":(exclude,glob)**/*.md")
            if n.isdigit() and int(n) > 0:
                report.warn("stale-guide", str(guide.relative_to(base)),
                            f"{n} commit(s) to {rel} since the guide last changed")


def collect(args: argparse.Namespace, root: Path) -> tuple[Report, list[Path]]:
    """Run every check and return what was found. Raises `Unexaminable` and does not catch it.

    Split out of `main` so that the one and only handler for "the check could not run" lives at the
    top level, above all of it. Nothing in here is allowed to know about that exception.
    """
    report = Report()
    files = tracked_files(root)
    if files is None:
        files = walk_files(root)
    files = [f for f in files if f.exists()]
    depth, seeds = crawl(root, files, report)

    # Budgets and depth describe the *route*, not reference material it links: a long PRD is a PRD.
    index_dir = (root / "docs" / "agents") if (root / "docs" / "agents" / "README.md").is_file() else None
    for doc, d in sorted(depth.items(), key=lambda kv: kv[1]):
        rel = doc.relative_to(root) if doc.is_relative_to(root) else doc
        on_route = (d == 0 or doc.name in ENTRY_NAMES
                    or index_dir is None or doc.parent.resolve() == index_dir.resolve())
        if not on_route:
            continue
        text = read_doc(doc, root)
        words = word_count(text)
        if is_lessons_file(doc.name) or is_record_file(doc.name):
            # No word budget in any form — see LESSONS_ENTRY_NOTE_AT. Entry count instead, and
            # only as an observation.
            kind = "lessons" if is_lessons_file(doc.name) else "record"
            entries = lessons_entry_count(text)
            if entries > LESSONS_ENTRY_NOTE_AT:
                report.note(f"{kind}-entries", str(rel),
                            f"{entries} entries ({words} words) — past {LESSONS_ENTRY_NOTE_AT} a "
                            f"{kind} file stops being readable in one sitting; consider archiving "
                            "the entries that no longer change what anyone does")
        else:
            budget = args.entry_budget if d == 0 else args.guide_budget
            if words > budget:
                report.warn("over-budget", str(rel),
                            f"{words} words > {budget} budget at depth {d}")
        if d > args.max_depth:
            report.warn("too-deep", str(rel), f"{d} hops from the entry point")

    check_commands(root, list(depth), report)
    check_orphans(root, depth, files, report)
    check_scoped_coverage(root, files, depth, report)
    check_stale_guides(root, seeds, report)
    check_stale_paths(root, depth, files, report)
    check_personas(root, report)
    # THE OPT-IN FAMILIES, and the one place their absence is recorded. Each flag-gated `check_*`
    # declares its absence in its else (`test_every_flag_gated_check_declares_its_absence`).
    # `--readme` is not on by default: that would turn a repository's deliberate omission of a
    # section into a commit-blocking ERROR everywhere at once.
    if args.standard:
        check_standard(root, report)
    else:
        report.not_evaluated("cross-project structure standard",
                             "not requested — pass --standard to evaluate it")
    if args.readme or args.standard:
        check_readme(root, files, report)
    else:
        report.not_evaluated("README contract",
                             "not requested — pass --readme (or --standard) to evaluate it")
    if args.vs:
        check_readme_freshness(root, args.vs, report)
    else:
        report.not_evaluated("README freshness against a git ref",
                             "not requested — pass --vs REF to evaluate it")

    report.info = {
        "root": str(root),
        "entry_files": [str(s.relative_to(root)) for s in seeds],
        "routed_docs": len(depth),
        "max_depth": max(depth.values()) if depth else 0,
    }
    return report, seeds


def report_could_not_run(args: argparse.Namespace, root: Path, exc: Unexaminable) -> int:
    """Say that no verdict was reached, with no count, because none was established. Exit 2."""
    detail = f"{exc.where}: {exc.detail}"
    if args.as_json:
        # No `errors`/`warnings`/`notes` keys: empty ones would read as a clean route. `exit` is
        # present on every payload this script emits.
        print(json.dumps({
            "status": "could-not-run",
            "exit": 2,
            "could_not_run": {"where": exc.where, "detail": exc.detail},
            "info": {"root": str(root)},
        }, indent=2))
    elif args.hook:
        print(f"CHECK COULD NOT RUN [unexaminable] {detail}. The route was NOT checked; "
              f"no error count exists and this is not a clean result.")
    else:
        print(f"progressive disclosure: {root}")
        print(f"  CHECK COULD NOT RUN  [unexaminable] {detail}")
        print("  no verdict — this route was not checked, so there is no error count to report "
              "and this is not a clean result")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--standard", action="store_true",
                    help="also enforce the shared cross-project structure standard")
    ap.add_argument("--readme", action="store_true",
                    help="also enforce the README contract (implied by --standard)")
    ap.add_argument("--vs", metavar="REF", default=None,
                    help="warn when source changed since REF but the README did not")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--hook", action="store_true",
                    help="print findings only; stay silent when the route is healthy")
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--entry-budget", type=int, default=600, help="max words in a root entry file")
    ap.add_argument("--guide-budget", type=int, default=1200, help="max words in any routed guide")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    try:
        report, seeds = collect(args, root)
    except Unexaminable as exc:
        return report_could_not_run(args, root, exc)

    status, code, summary = report.verdict()

    if args.as_json:
        print(json.dumps({"status": status, "exit": code, "info": report.info,
                          "errors": report.errors, "warnings": report.warns,
                          "notes": report.notes, "not_run": report.not_run,
                          "summary": summary}, indent=2))
    elif args.hook:
        for item in report.errors:
            print(f"ERROR [{item['kind']}] {item['where']}: {item['detail']}")
        for item in report.warns:
            print(f"WARN [{item['kind']}] {item['where']}: {item['detail']}")
        for item in report.notes:
            print(f"NOTE [{item['kind']}] {item['where']}: {item['detail']}")
        # Scope, but only when this mode is already speaking: `--hook` is silent on a healthy route.
        if report.errors or report.warns or report.notes:
            for item in report.not_run:
                print(f"NOT RUN [{item['check']}] {item['why']}")
    else:
        print(f"progressive disclosure: {root}")
        if seeds:
            names = report.info["entry_files"]
            shown = names if len(names) <= 4 else names[:3] + [f"+{len(names) - 3} more scoped"]
            print(f"  entry: {', '.join(shown)}")
        print(f"  routed docs: {report.info['routed_docs']}  max depth: {report.info['max_depth']}")
        for item in report.errors:
            print(f"  ERROR  [{item['kind']}] {item['where']}: {item['detail']}")
        for item in report.warns:
            print(f"  WARN   [{item['kind']}] {item['where']}: {item['detail']}")
        for item in report.notes:
            print(f"  NOTE   [{item['kind']}] {item['where']}: {item['detail']}")
        for item in report.not_run:
            print(f"  NOT RUN  {item['check']}: {item['why']}")
        # One line, composed from what ran; never a literal.
        print(f"  {summary}")

    return code


if __name__ == "__main__":
    raise SystemExit(main())
