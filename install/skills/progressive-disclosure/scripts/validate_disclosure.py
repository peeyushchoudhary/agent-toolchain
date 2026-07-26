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

`--readme` adds the human-facing README contract: the front page a person meets on the forge, and
the one document that must answer "what is this, where is it, what is left" without a repo tour.

Exit code 1 on any ERROR, or on any WARN when --strict is passed.

Usage:
  validate_disclosure.py [ROOT] [--strict] [--json] [--max-depth N]
                         [--entry-budget N] [--guide-budget N]
                         [--readme] [--vs REF]
"""

from __future__ import annotations

import argparse
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
# An @import must look like a path. Without the dot-or-slash requirement this matches a bare Java
# annotation sitting on its own line — `@Entity`, `@RestController` — and every design document that
# quotes Spring code reports dozens of broken "imports". Matching is also done against code-stripped
# text, because an import inside a fence is an illustration, not a directive.
MD_IMPORT = re.compile(r"^@([^\s]*[./][^\s]*)\s*$", re.MULTILINE)
CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`]*`")

CMD_MAKE = re.compile(r"\bmake\s+([a-zA-Z][\w.-]*)")
CMD_PNPM = re.compile(r"\bpnpm(?:\s+run)?\s+([a-z][\w:.-]*)")
CMD_NPM = re.compile(r"\b(?:npm|yarn)\s+run\s+([a-z][\w:.-]*)")
CMD_JUST = re.compile(r"\bjust\s+([a-zA-Z][\w:.-]*)")
CMD_TASK = re.compile(r"\btask\s+([a-zA-Z][\w:.-]*)")

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
        self.info: dict = {}

    def error(self, kind: str, where: str, detail: str) -> None:
        self.errors.append({"kind": kind, "where": where, "detail": detail})

    def warn(self, kind: str, where: str, detail: str) -> None:
        self.warns.append({"kind": kind, "where": where, "detail": detail})


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


# Material the standard declares non-authoritative: superseded documents, tool output, dated plans
# and handoffs. Links *into* it are still checked — a dead link is a dead link — but the crawl does
# not descend, and its contents are exempt from freshness checks.
#
# Following it would be actively wrong. A plan written months ago SHOULD cite files that have since
# moved; that is what makes it history. Crawling it turns every correct archival document into a
# pile of stale-path warnings and buries the one real breakage in the live route.
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
    """The inverse: just the fenced blocks and inline spans.

    Commands are read from here and nowhere else. A documented command is always written in code
    formatting, while running the patterns over prose matches ordinary English — "make the", "make
    you", "make active" were all reported as missing Makefile targets before this existed.
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
        try:
            raw = doc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        stripped = strip_code(raw)
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
            if dest.suffix.lower() == ".md" and dest.is_file() and not is_history(root, dest):
                queue.append((dest, d + 1))
    return depth, seeds


def check_commands(root: Path, docs: list[Path], report: Report) -> None:
    make_targets: set[str] = set()
    makefile = root / "Makefile"
    if makefile.is_file():
        text = makefile.read_text(encoding="utf-8", errors="replace")
        make_targets |= set(re.findall(r"^([a-zA-Z][\w.-]*)\s*:(?!=)", text, re.MULTILINE))
        for line in re.findall(r"^\.PHONY:\s*(.*)$", text, re.MULTILINE):
            make_targets |= set(line.split())

    scripts: set[str] = set()
    for pkg in [root / "package.json"] + sorted(root.glob("*/package.json")):
        if pkg.is_file():
            try:
                scripts |= set(json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {}))
            except (json.JSONDecodeError, OSError):
                pass

    # just recipes: `name arg1 arg2:` at column 0, excluding `name := value` assignments.
    just_recipes: set[str] = set()
    justfile = next((root / n for n in ("justfile", "Justfile", ".justfile") if (root / n).is_file()), None)
    if justfile is not None:
        jtext = justfile.read_text(encoding="utf-8", errors="replace")
        just_recipes = set(re.findall(r"^([a-zA-Z][\w-]*)[^:=\n]*:(?!=)", jtext, re.MULTILINE))

    # Taskfile tasks: keys nested one level under a top-level `tasks:` mapping.
    task_names: set[str] = set()
    taskfile = next((root / n for n in ("Taskfile.yml", "Taskfile.yaml", "taskfile.yml") if (root / n).is_file()), None)
    if taskfile is not None:
        ttext = taskfile.read_text(encoding="utf-8", errors="replace")
        block = re.split(r"^tasks:\s*$", ttext, maxsplit=1, flags=re.MULTILINE)
        if len(block) == 2:
            for line in block[1].splitlines():
                if re.match(r"^\S", line):
                    break
                m = re.match(r"^\s{1,4}([a-zA-Z][\w:.-]*):\s*$", line)
                if m:
                    task_names.add(m.group(1))

    for doc in docs:
        try:
            text = code_only(doc.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
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


def check_scoped_coverage(root: Path, files: list[Path], report: Report) -> list[str]:
    """Every top-level directory holding source should carry its own entry file."""
    by_dir = source_dirs(root, files)

    missing = []
    for d, n in sorted(by_dir.items()):
        if not any((root / d / name).is_file() for name in ENTRY_NAMES):
            report.warn("unscoped-dir", d,
                        f"{n} source files, no {' or '.join(ENTRY_NAMES)} to route from")
            missing.append(d)
    return missing


def check_orphans(root: Path, depth: dict[Path, int], files: list[Path], report: Report) -> None:
    """A doc sitting beside routed docs but reachable from nothing is written-and-forgotten.

    Only applies to directories the index actually routes *into* — two or more docs reached by a
    link, not by proximity. Counting the scoped AGENTS.md/CLAUDE.md pair would make every source
    directory look like an agent-docs directory and flag its README, training readers to ignore
    this check.
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
# The README is the only document a human meets before deciding whether the project is real. It has
# to answer four questions without a repo tour: what is this, what is its state, how is it built,
# and where is the detail. Each section below is one of those questions.
#
# Heading matching is deliberately loose. A repo that already says "Getting started" instead of
# "Run locally" is not wrong, and renaming everyone's headings to satisfy a linter would be the
# tail wagging the dog. What is enforced is that the *question* is answered somewhere.
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
    # Split so this file does not itself contain a matching literal. Without the split, any
    # repository carrying this scanner — or documentation quoting a PEM header — trips its own
    # guard, and the only way past is the --no-verify habit this is meant to prevent.
    # The [A-Z ]+ alternative already covers OPENSSH, RSA, EC and the rest.
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
    """The lines under the first heading matching `pattern`, up to the next heading of that level.

    Needed because a document-wide search for a diagram is satisfied by the logo at the top. The
    question is not "does this README contain an image" but "does the architecture section show
    the architecture".
    """
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
    text = readme.read_text(encoding="utf-8", errors="replace")
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

    # A diagram, in any form the forge renders, inside the architecture section specifically.
    # Mermaid is preferred — it diffs, and an agent can edit it — but an exported image is a
    # legitimate choice and not worth failing over.
    arch_pattern = next(p for k, p, _ in README_SECTIONS if k == "architecture")
    arch_body = section_body(text, arch_pattern)
    if arch_body and "```mermaid" not in arch_body and not re.search(r"!\[[^\]]*\]\(|<img\s", arch_body):
        report.error("readme-no-diagram", rel_readme,
                     "the architecture section has no diagram (```mermaid fence or an image)")

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


def check_personas(root: Path, report: Report) -> None:
    """Generated agent files must match the persona sources they came from.

    Only runs for a repo that specialises personas. The generated `.claude/agents/` and
    `.codex/agents/` files are committed, so drift is invisible in review — the diff looks
    intentional. Same reason a generated API client gets a drift check.

    Degrades quietly when the tool is absent, like every other machine-local check here.
    """
    overlays = root / "docs" / "agents" / "personas"
    if not overlays.is_dir() or not any(overlays.glob("*.md")):
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
    elif r.returncode not in (0, 1):
        report.warn("persona-check-failed", "docs/agents/personas", r.stderr.strip()[:160])


def check_readme_freshness(root: Path, base: str, report: Report) -> None:
    """Warn when a branch changed source but left the README alone.

    A warning, never an error. Plenty of real changes — a refactor, a test fix, a dependency bump —
    correctly leave the front page untouched, and a gate that fires on those gets muted within a
    week. The judgement stays with the author; this only makes sure the question is asked.
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
STANDARD_VERSION = "1.1"
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
        body = [ln.strip() for ln in claude.read_text(encoding="utf-8", errors="replace").splitlines()
                if ln.strip()]
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
        words = word_count(entry.read_text(encoding="utf-8", errors="replace"))
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
        hits = [ln.strip() for ln in f.read_text(encoding="utf-8", errors="replace").splitlines()
                if "TODO" in ln]
        if hits:
            report.error("standard-placeholder", rel,
                         f"{len(hits)} unfinished placeholder(s), first: {hits[0][:60]}")

    # A per-repo copy generated from an older standard drifts silently otherwise.
    disc = root / "docs" / "agents" / "disclosure.md"
    if disc.is_file():
        text = disc.read_text(encoding="utf-8", errors="replace")
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
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for path in sorted(set(cited.findall(text))):
            if any((b / path).exists() for b in stem_bases):
                continue
            if Path(path).name in known_names:
                continue
            report.warn("stale-path", str(rel), f"cites `{path}`, which resolves nowhere")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--standard", action="store_true",
                    help="also enforce the shared cross-project structure standard")
    ap.add_argument("--readme", action="store_true",
                    help="also enforce the README contract (implied by --standard)")
    ap.add_argument("--vs", metavar="REF", default=None,
                    help="warn when source changed since REF but the README did not")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--entry-budget", type=int, default=600, help="max words in a root entry file")
    ap.add_argument("--guide-budget", type=int, default=1200, help="max words in any routed guide")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    report = Report()
    files = tracked_files(root)
    if files is None:
        files = walk_files(root)
    files = [f for f in files if f.exists()]
    depth, seeds = crawl(root, files, report)

    # Budgets and depth describe the *route* — the files an agent reads on the way to a task. They
    # are not a judgement on reference material the route happens to link. A 2,800-word PRD is not
    # a disclosure failure; it is a PRD. Applying the guide budget to it produces warnings that are
    # correct by the letter and wrong by the purpose, which is how a report gets ignored.
    index_dir = (root / "docs" / "agents") if (root / "docs" / "agents" / "README.md").is_file() else None
    for doc, d in sorted(depth.items(), key=lambda kv: kv[1]):
        rel = doc.relative_to(root) if doc.is_relative_to(root) else doc
        on_route = (d == 0 or doc.name in ENTRY_NAMES
                    or index_dir is None or doc.parent.resolve() == index_dir.resolve())
        if not on_route:
            continue
        try:
            words = word_count(doc.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        budget = args.entry_budget if d == 0 else args.guide_budget
        if words > budget:
            report.warn("over-budget", str(rel),
                        f"{words} words > {budget} budget at depth {d}")
        if d > args.max_depth:
            report.warn("too-deep", str(rel), f"{d} hops from the entry point")

    check_commands(root, list(depth), report)
    check_orphans(root, depth, files, report)
    check_scoped_coverage(root, files, report)
    check_stale_paths(root, depth, files, report)
    check_personas(root, report)
    if args.standard:
        check_standard(root, report)
    if args.readme or args.standard:
        check_readme(root, files, report)
    if args.vs:
        check_readme_freshness(root, args.vs, report)

    report.info = {
        "root": str(root),
        "entry_files": [str(s.relative_to(root)) for s in seeds],
        "routed_docs": len(depth),
        "max_depth": max(depth.values()) if depth else 0,
    }

    if args.as_json:
        print(json.dumps({"info": report.info, "errors": report.errors, "warnings": report.warns}, indent=2))
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
        if not report.errors and not report.warns:
            print("  clean — every route resolves, every documented command exists")
        else:
            print(f"  {len(report.errors)} error(s), {len(report.warns)} warning(s)")

    if report.errors:
        return 1
    return 1 if (args.strict and report.warns) else 0


if __name__ == "__main__":
    raise SystemExit(main())
