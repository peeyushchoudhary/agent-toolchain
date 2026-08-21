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
  WARN    no rendered execution methodology                (docs/agents/execution/, or minor drift)
  ERROR   an execution methodology a MAJOR version behind  (the repo documents withdrawn rules)
  NOTE    a lessons file past its entry count             (accretion, not a rule violation)

`--readme` adds the human-facing README contract: the front page a person meets on the forge, and
the one document that must answer "what is this, where is it, what is left" without a repo tour.

EXIT CODES — three states, because two were not enough:

  0  the route was checked and is clean (or has only warnings and notes)
  1  the route was checked and something is wrong: at least one ERROR
  2  the route was NOT checked — a file this depends on could not be read or decoded

REPORTED STATES — also three, and NOT the same three. A run reports `clean`, `findings` or
`partial`, and `partial` is the state this script used to have no way to say. `--standard`,
`--readme` and `--vs` each gate a whole family of ERROR-producing checks at the CALL SITE, and a
run that skipped them printed, verbatim, `clean — every route resolves, every documented command
exists`. Measured: one repository, no flags, exit 0, that line; the same repository with `--readme`,
exit 1, five `readme-missing-section` ERRORs. Nothing about the tree changed between the two runs.

THE STATUS AND THE EXIT CODE ARE INDEPENDENT, and a consumer must not infer either from the other.
The rule, stated once and asserted by `test_not_evaluated_never_changes_the_exit_code`:

    the exit code is decided by ERRORS ALONE. A family that did not run never raises it and never
    lowers it. `partial` therefore exits 1 whenever the checks that DID run found an ERROR, which
    on the current fleet is most of the time.

An earlier version of this paragraph said "a `partial` run still exits 0". That was true of the
mechanism it originally described — nothing about a not-run family touches the code — and it became
false the moment the exit computation moved into `verdict()`, because the same sentence then read as
a claim about the whole status. It is called out here rather than quietly corrected because a
maintainer who believed it and mapped `status == "partial"` to non-blocking would swallow every
ERROR in every default-flag invocation on the fleet: this file's own defect class, one consumer
downstream, installed by its documentation.

FOR A CONSUMER, therefore: decide pass/fail from `exit` (or `len(errors)`), NEVER from `status`.
`status` describes the SCOPE of the run, not its outcome. Note also that `partial` outranks
`findings` in `verdict()`, so a run that skipped any family reports `partial` however many errors it
found — and since `disclosure-check.sh` passes only `--readme`, and nothing on the fleet passes both
`--standard` and `--vs`, `findings` is in practice unreachable and a switch on
{clean, findings, partial} will only ever see `partial`.

What a not-run family DOES change is the summary, which is what was actually false: `NOT RUN` lines
name every family that did not execute, and the word `clean` is unreachable when any did not.
See `Report.verdict`.

The third state is the one this script lacked, and its absence was a fail-open. Every read used to
end in `except OSError: continue`, `except (JSONDecodeError, OSError): pass`, or nothing at all, so
an unreadable file was skipped and the run then declared the route clean. Measured: a root AGENTS.md
holding two broken links exits 1 and names them; the same file at `chmod 000` exits 0 and prints
`0 error(s), 1 warning(s)`. A failing route could be made to pass by making a file unreadable, and
the report said nothing about it.

The remedy is the ABSENCE of the swallow, not a longer list of cases it handles. All reading goes
through `read_doc`, which raises `Unexaminable`; no call site catches it; `main` catches it once and
exits 2 without printing a count it never established. See `Unexaminable` for why this is exit 2
rather than one more entry in the findings list, and why there is no flag to turn it off.

A WARN never blocks a commit — severity is a property of the finding, decided here, not a flag
chosen at the call site.

Usage:
  validate_disclosure.py [ROOT] [--json] [--max-depth N]
                         [--entry-budget N] [--guide-budget N]
                         [--readme] [--vs REF] [--hook]
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
CODE_FENCE = re.compile(r"(?:```.*?```|~~~.*?~~~)", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`]*`")

CMD_MAKE = re.compile(r"\bmake\s+([a-zA-Z][\w.-]*)")
CMD_PNPM = re.compile(r"\bpnpm(?:\s+run)?\s+([a-z][\w:.-]*)")
CMD_NPM = re.compile(r"\b(?:npm|yarn)\s+run\s+([a-z][\w:.-]*)")
CMD_JUST = re.compile(r"\bjust\s+([a-zA-Z][\w:.-]*)")
CMD_TASK = re.compile(r"\btask\s+([a-zA-Z][\w:.-]*)")
PERSONA_MARKER = re.compile(r"<!--\s*agent-personas:\s*(\{[^\r\n]*\})\s*-->", re.IGNORECASE)
PERSONA_MARKER_ANY = re.compile(r"<!--\s*agent-personas:", re.IGNORECASE)
# Same single-line JSON comment spelling, for the rendered execution methodology.
EXECUTION_MARKER = re.compile(r"<!--\s*execution-methodology:\s*(\{[^\r\n]*\})\s*-->", re.IGNORECASE)
EXECUTION_MARKER_ANY = re.compile(r"<!--\s*execution-methodology:", re.IGNORECASE)
SEMVER2 = re.compile(r"^(\d{1,4})\.(\d{1,4})$")

# A lessons file grows by accretion — entries get added, rarely removed — so a total word budget
# is a budget on entry *count*, not entry length. It was answered by sharding lessons.md into two
# compliant files with more total text, not shorter text: the split gamed the metric instead of
# answering it. Lessons files get no total budget; the per-append convention in every project's
# "How to append" section is what actually keeps an entry short, not this validator.
#
# Matched tightly on purpose. A bare `startswith("lessons-")` exempts
# `lessons-and-onboarding-guide.md` — an ordinary guide that then escapes its budget entirely — and
# the two failure directions are not symmetric: a shard this does not recognise merely gets the
# warning it would have got anyway, while a guide this wrongly recognises gets no budget at all.
# So: `lessons.md`, or `lessons` plus one separator plus a single unbroken token
# (`lessons-archive.md`, `lessons_2026.md`). A multi-word tail is a different document.
LESSONS_NAME = re.compile(r"^lessons(?:[-_][a-z0-9]+)?\.md$")


def is_lessons_file(name: str) -> bool:
    return bool(LESSONS_NAME.match(name.lower()))


# The same reasoning, one document further. A measurements file is a RECORD: each entry is a dated
# fact that stays true, so the file grows by accretion exactly as a lessons file does, and a total
# word budget on it has the same two exits — evict evidence, or shard the file and game the metric.
# It reached 1194 of 1200 words with every routed guide in the fleet at 1178-1199, so the next
# measurement could not land at all while AGENTS.md still routed measurements there. The budget and
# the address were in direct conflict, and the budget was the wrong half.
#
# A record is not exempt from being readable. It gets the same entry-count observation, set from
# the same measured basis: this file holds 8 sections today, so the threshold speaks only when the
# document has grown into something that wants archiving.
RECORD_NAME = re.compile(r"^(measurements|benchmarks)(?:[-_][a-z0-9]+)?\.md$")


def is_record_file(name: str) -> bool:
    """A document whose entries accrete rather than being revised. No total word budget."""
    return bool(RECORD_NAME.match(name.lower()))


# The one constraint that survives. Not a word budget in any form — the total budget was gamed by
# sharding, and a per-entry word rule fires on compliant content today (real entries across the
# fleet run ~120-200 words, well past the ~150 that was proposed as a limit).
#
# Entry COUNT is the honest measure of accretion, and it is informational: it names the moment a
# lessons file stopped being readable in one sitting, and never blocks anything. The threshold is
# set from measured data — the largest routed lessons file in the fleet holds 8 entries — with
# roughly 3x headroom, so it fires on nothing that exists today and only speaks when a file has
# grown into something that wants archiving. At the observed ~150 words/entry, 24 entries is
# already ~3,600 words.
LESSONS_ENTRY_NOTE_AT = 24

ENTRY_HEADING = re.compile(r"^(#{2,6})\s+\S")


def lessons_entry_count(text: str) -> int:
    """How many entries a lessons file holds.

    There is no cross-project convention for the heading level of an entry: some projects use `##`
    per entry, others nest `###` entries under a `## Lessons` wrapper. So rather than fixing a
    level, take the level used most often and count that — ties broken toward the deeper level,
    since the wrapper is always shallower and rarer than the entries it wraps. Headings inside code
    fences are not entries.
    """
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
        """Informational: worth saying, never worth blocking or nagging about.

        A third level exists because the alternative to "warn" was "nothing at all", and a rule
        with no observation behind it stops being a rule. Notes never affect the exit code and are
        listed after warnings everywhere.
        """
        self.notes.append({"kind": kind, "where": where, "detail": detail})

    def not_evaluated(self, check: str, why: str) -> None:
        """A whole check family that did not execute. NOT a finding, and NOT nothing.

        The third state. `Unexaminable` covers "I started and could not finish"; this covers "I was
        never asked to start", which the previous code expressed by producing no output at all — so
        a run that skipped seven ERROR-producing README checks printed the same
        `clean — every route resolves, every documented command exists` as a run that ran them.
        Measured on a real repository the day this was written: no flags, exit 0, that exact line;
        `--readme`, exit 1, five `readme-missing-section` ERRORs against the same unchanged tree.

        Calling this NEVER changes the exit code, in either direction: a check the caller did not
        request is a scope decision, not a defect in the repository. What it does is deny the word
        `clean` to the summary, which is the claim that was actually false.

        Note what that does NOT say. It does not say the run exits 0 — the errors found by the
        checks that DID run still decide that, so a `partial` run with an ERROR exits 1. The
        difference between "this never raises the code" and "a partial run exits 0" is the whole of
        finding R1; see the module docstring.
        """
        self.not_run.append({"check": check, "why": why})

    def verdict(self) -> tuple[str, int, str]:
        """`(status, exit_code, summary)` — the ONE place this run becomes a verdict.

        Three states, never two: `clean`, `findings`, `partial`. There is no path from a check that
        did not run to the word `clean`.

        THE EXIT CODE COMES FROM HERE, not from a second computation at the bottom of `main`. It
        used to, and two independent decision sites with nothing holding them consistent is exactly
        how a summary and an exit code come to disagree — the defect class of this card, one level
        up. One function decides; `main` reports what it decided.

        THE STATUS DOES NOT DETERMINE THE EXIT CODE. `code` is computed from `self.errors` alone,
        above and independent of the status branches below, so that `not_run` cannot move it in
        either direction — a family nobody requested must not fail a pre-commit hook, and must not
        rescue one either. Consequently `partial` exits 1 whenever the checks that ran found an
        ERROR. Read `exit`, never `status`, to decide pass/fail.

        PRECEDENCE, stated because a consumer will switch on this: `partial` is tested FIRST, so it
        outranks `findings`. A run that skipped any family reports `partial` no matter how many
        errors it found, which makes `findings` reachable only when both `--standard` and `--vs`
        are passed. Nothing on the fleet does that today.
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

    Deliberately NOT a `Report` finding, and deliberately not catchable per call site.

    A finding says "I looked, and this is wrong." This says "I could not look." Those are different
    claims and they need different exit codes, because the second one invalidates everything else
    the run would otherwise print. An unread entry file is not one missing observation: its links
    were never followed, so every document beyond it went unvisited, its documented commands were
    never checked, its budget was never counted — and the documents it would have routed to now
    look like orphans while the broken links it holds vanish from the report. The measured shape of
    that was a route with two broken links reporting `0 error(s), 1 warning(s)` and exiting 0 the
    moment its AGENTS.md was made unreadable. Making a file unreadable must never be a way to make
    a failing route pass.

    THERE IS NO PER-CALL-SITE HANDLING OF THIS, AND THAT IS THE POINT. Every read goes through
    `read_doc`, which raises; nothing between there and `main` catches it. The previous shape was
    four separate `except OSError: continue` clauses, one `except (JSONDecodeError, OSError): pass`,
    and nine reads with no guard at all that would have exited 1 with a traceback — nine reads that
    nobody had thought about, which is what a per-site convention always decays into. A rule
    enforced by the absence of a swallow cannot regress. A rule enforced by remembering to handle
    each new read can, and did.

    There is no flag to switch this off. "Ignore files I cannot read" is a request to be told the
    route is fine when nobody knows whether it is.
    """

    def __init__(self, where: str, detail: str) -> None:
        super().__init__(f"{where}: {detail}")
        self.where = where
        self.detail = detail


def _display(path: Path, root: Path | None) -> str:
    """Repository-relative when it is inside the repository, absolute when it is not.

    A machine-global path — an optional skill under the home directory — is genuinely not part of
    the repository, and abbreviating it to something repo-shaped would send the reader looking in
    the wrong tree.
    """
    if root is not None:
        try:
            return str(path.resolve().relative_to(root.resolve()))
        except (ValueError, OSError):
            pass
    return str(path)


def read_doc(path: Path, root: Path | None = None) -> str:
    """Read a file this check depends on. Every way of not reading it raises. No exceptions.

    Decoded as utf-8-sig, and STRICTLY, which is the second half of the same defect and was the
    quieter half. `errors="replace"` never raises, so a UTF-16 or latin-1 entry file was read as a
    wall of replacement characters in which no markdown link matches, no `@import` matches, and no
    documented command matches — a clean report over a file the checker never actually understood.
    That is the same fail-open as the swallow, arrived at by a different road, and it is worse
    because it leaves no trace at all. `-sig` because editors on this platform write a BOM without
    being asked, and an unstripped BOM is glued to the first character of the first line, which is
    exactly where `MD_IMPORT`'s `^@` anchor lives.

    The counter-argument for `errors="replace"` — that mangling costs at most a garbled character —
    holds when you are scanning text for a pattern that must be present. It does not hold here,
    where absence of a match is read as absence of a problem. Same asymmetry `identifier_guard.py`
    reasons about between `_decode` and `read_denylist`, resolved the same way and for the same
    reason: the direction of the risk, not the likelihood of the failure.
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
    reachable document somewhere beneath it.

    `docs/` in a repo where `docs/agents/` is the routed index is the case this exists for: a
    reader landing in `docs/` finds the route one hop down, so the top-level bucket does not also
    need its own AGENTS.md/CLAUDE.md.

    Be precise about the clearing predicate, because it is broader than "has a route into it" and
    the difference is the whole judgement call. `reached_dirs` below is the parent directory of
    *every* document in the crawled graph, so the test a directory has to pass is: **some markdown
    file strictly beneath me is reachable from the entry point.** Any linked document one level
    down clears the directory — not only an entry file, and not only an index. That is deliberate.
    The signal being protected is "a reader landing here finds their way out", and a reachable doc
    provides that; demanding an AGENTS.md/CLAUDE.md specifically would re-fire on `docs/` in every
    repo whose route lives in `docs/agents/README.md`, which is the exact false positive this
    narrowing exists to remove.

    What still fires, and must: a directory holding only documents nobody links to. Reachability is
    the crawled graph, not the filesystem, so an unrouted doc sitting in an unrouted directory
    clears nothing.

    Name collision, since one file now spells it twice: `check_orphans` also binds `routed_dirs`,
    and it means something else there — directories the index routes *into*, requiring two or more
    linked docs. This function's set is deliberately named `reached_dirs` to keep the two apart.
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


def _standard_repo(root: Path) -> bool:
    disclosure = root / "docs" / "agents" / "disclosure.md"
    if not disclosure.is_file():
        return False
    return "progressive-disclosure standard v" in read_doc(disclosure, root)


def check_persona_decision(root: Path, depth: dict[Path, int], report: Report) -> None:
    """Require a deliberate project-persona decision in every routed repository.

    Persona sources are the positive decision. A project that needs only the shared base pool
    records one exact JSON marker in the routed index. Missing decisions are warnings during the
    fleet migration; contradictory or unreachable specialist sources are structural errors.
    """
    index = root / "docs" / "agents" / "README.md"
    overlays = root / "docs" / "agents" / "personas"
    sources = (sorted(p for p in overlays.glob("*.md")
                      if p.is_file() and p.name.lower() != "readme.md")
               if overlays.is_dir() else [])
    text = read_doc(index, root) if index.is_file() else ""
    marker_text = strip_code(text)
    raw_markers = PERSONA_MARKER.findall(marker_text)
    marker_count = len(PERSONA_MARKER_ANY.findall(marker_text))
    any_marker = marker_count > 0
    decision: dict | None = None

    if marker_count > 1:
        report.error("persona-decision-invalid", "docs/agents/README.md",
                     "contains more than one `agent-personas` decision marker; keep exactly one")
    elif marker_count == 1 and len(raw_markers) == 1:
        try:
            parsed = json.loads(raw_markers[0])
        except json.JSONDecodeError as exc:
            report.error("persona-decision-invalid", "docs/agents/README.md",
                         f"`agent-personas` marker is not valid JSON: {exc.msg}")
        else:
            if not isinstance(parsed, dict) or parsed.get("mode") != "base-only":
                report.error("persona-decision-invalid", "docs/agents/README.md",
                             "`agent-personas` marker mode must be `base-only`")
            elif not isinstance(parsed.get("reason"), str) or not parsed["reason"].strip():
                report.error("persona-decision-invalid", "docs/agents/README.md",
                             "`agent-personas` base-only decision needs a non-empty reason")
            else:
                decision = parsed
    elif marker_count == 1:
        report.error("persona-decision-invalid", "docs/agents/README.md",
                     "`agent-personas` marker must contain one single-line JSON object")

    if sources:
        if decision is not None:
            report.error("persona-decision-conflict", "docs/agents/README.md",
                         "declares `base-only` but docs/agents/personas/ contains persona sources")
        guide = root / "docs" / "agents" / "personas.md"
        direct_links = set()
        if index.is_file():
            for target in MD_LINK.findall(strip_code(text)):
                path = target.split("#", 1)[0]
                if not path or "://" in path:
                    continue
                direct_links.add((index.parent / path).resolve())
        if not guide.is_file() or guide.resolve() not in direct_links or guide.resolve() not in depth:
            report.error("persona-route-missing", "docs/agents/personas.md",
                         "persona sources exist but docs/agents/README.md does not directly route "
                         "to the maintained personas guide")
        return

    if not index.is_file():
        return
    if decision is None and not any(item["kind"] == "persona-decision-invalid"
                                    for item in report.errors):
        report.warn("persona-decision-missing", "docs/agents/README.md",
                    "record either project persona sources or "
                    '`<!-- agent-personas: {"mode":"base-only","reason":"..."} -->`')


def check_personas(root: Path, report: Report) -> None:
    """Generated agent files must match the persona sources they came from.

    Runs for every standard repository, including a base-only decision: deleting the last source
    must not leave a generated project agent dispatchable. The generated `.claude/agents/` and
    `.codex/agents/` files are committed, so drift is invisible in review — the diff looks
    intentional. Same reason a generated API client gets a drift check.

    Degrades quietly when the tool is absent, like every other machine-local check here.
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


def installed_methodology_version() -> str | None:
    """The methodology version this machine has installed, or None if it cannot be determined.

    Read from the renderer's own constant rather than duplicated here. Two copies of a version
    number drift, and the copy inside a validator is the one nobody remembers to bump.

    ABSENCE stays soft, and only absence. The methodology skill is an optional machine-global
    install; a machine that does not have it is not a repository with a problem, and turning a
    missing optional skill into a blocked commit would be the opposite mistake. So
    `FileNotFoundError` returns None and the version comparison is skipped.

    PRESENT-BUT-UNREADABLE does not stay soft, because it used to return the same None down the
    same path — the two states were indistinguishable in the output, which is the whole pattern
    this file was audited for. An installed skill this process cannot read is a broken machine, not
    an absent feature, and `read_doc` says so.
    """
    script = (Path.home() / ".claude" / "skills" / "execution-methodology"
              / "scripts" / "sync_methodology.py")
    if not script.exists():
        return None
    text = read_doc(script)
    m = re.search(r'^METHODOLOGY_VERSION\s*=\s*"(\d{1,4}\.\d{1,4})"', text, re.MULTILINE)
    return m.group(1) if m else None


def check_execution_methodology(root: Path, report: Report) -> None:
    """Check the rendered execution methodology at docs/agents/execution/methodology.md.

    Codex has no Skill tool, so the methodology only reaches both harnesses as in-repo markdown. A
    repo carrying a copy from a MAJOR-older methodology is following rules that have since been
    withdrawn, which is an error.

    This checks a rendered copy and says nothing about a repository that has none. Whether a repo
    *should* have adopted the methodology is not this script's question: adoption is staggered, a
    repo may have deliberately deferred it with a recorded reason, and only
    `sync_methodology.py --adoption-check` can tell the four states apart. Two scripts reporting the
    same fact is how a deferred repo ends up being told off for a decision it recorded on purpose.

    Fail-soft about JUDGEMENT, not about COVERAGE. An unparseable or missing marker is still a
    finding rather than a crash, and a repo with no rendered copy is still left alone. But the
    rendered file being unreadable was previously a `warn`, and a warn exits 0 — so chmod-ing the
    rendered methodology made a major-version-behind repository pass. Unreadable is now
    `read_doc`'s business, like every other read in this file.
    """
    if not (root / "docs" / "agents" / "README.md").is_file():
        return                      # not a routed repository; nothing to be behind on
    installed = installed_methodology_version()
    rel = "docs/agents/execution/methodology.md"
    rendered = root / "docs" / "agents" / "execution" / "methodology.md"

    if not rendered.is_file():
        return                      # not adopted — the adoption check owns that report

    text = strip_code(read_doc(rendered, root))

    count = len(EXECUTION_MARKER_ANY.findall(text))
    raw = EXECUTION_MARKER.findall(text)
    if count == 0:
        report.warn("execution-marker-missing", rel,
                    "carries no `execution-methodology` version marker; re-render it with "
                    "`sync_methodology.py --repo .`")
        return
    if count > 1:
        report.error("execution-marker-invalid", rel,
                     "contains more than one `execution-methodology` marker; keep exactly one")
        return
    if len(raw) != 1:
        report.error("execution-marker-invalid", rel,
                     "`execution-methodology` marker must contain one single-line JSON object")
        return
    try:
        parsed = json.loads(raw[0])
    except json.JSONDecodeError as exc:
        report.error("execution-marker-invalid", rel,
                     f"`execution-methodology` marker is not valid JSON: {exc.msg}")
        return
    if not isinstance(parsed, dict):
        report.error("execution-marker-invalid", rel,
                     "`execution-methodology` marker must be a JSON object")
        return

    found = parsed.get("v")
    m = SEMVER2.match(found.strip()) if isinstance(found, str) else None
    if m is None:
        report.error("execution-marker-invalid", rel,
                     f"`execution-methodology` marker version {found!r} is not MAJOR.MINOR")
        return
    if installed is None:
        return
    cur = SEMVER2.match(installed)
    if cur is None:
        return
    if int(m.group(1)) < int(cur.group(1)):
        report.error("execution-version-drift", rel,
                     f"rendered from methodology v{found}; current is v{installed} — a major "
                     "version behind, so this repo documents withdrawn rules. Re-render it.")
    elif int(m.group(1)) == int(cur.group(1)) and int(m.group(2)) < int(cur.group(2)):
        report.warn("execution-version-drift", rel,
                    f"rendered from methodology v{found}; current is v{installed}")


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
    check_stale_paths(root, depth, files, report)
    check_persona_decision(root, depth, report)
    check_personas(root, report)
    check_execution_methodology(root, report)
    # THE OPT-IN FAMILIES, and the one place their absence is recorded.
    #
    # Each of these is a whole family of ERROR-producing checks selected at the CALL SITE, which
    # the module docstring's "severity is a property of the finding, decided here, not a flag
    # chosen at the call site" flatly contradicts. That contradiction is not fixed by flipping the
    # defaults — see below — it is fixed by never again letting a run that skipped them describe
    # itself as clean. Three hand-written if/else pairs, NOT a table — the sibling file has a table
    # (`DEFAULT_CHECKS` in check_toolchain.py) and this comment once claimed one here, which was
    # simply untrue of the code beneath it. What actually stops a fourth opt-in family being added
    # without declaring its absence is a structural test,
    # `test_every_flag_gated_check_declares_its_absence`, which walks this function and fails on any
    # `args.<flag>`-gated call to a `check_*` with no `report.not_evaluated(...)` in its else.
    #
    # WHY THE DEFAULTS ARE NOT FLIPPED. Turning `--readme` on by default was the alternative
    # remedy and it was rejected on evidence: the README contract is seven required sections, and
    # the public repository this was measured against deliberately omits two of them — it says so
    # in a section of its own README titled "Two sections a software project would have, and this
    # does not". Defaulting the flag on would convert a documented, intentional editorial choice
    # into a commit-blocking ERROR in every repository at once, and the pre-commit hook text that
    # would start failing is generated by install_hooks.py, which is outside this change. A checker
    # that must be silenced on day one teaches the reader to silence it.
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
    """Say that no verdict was reached, in the same sentence as the verdict would have been.

    The count and the caveat must not be two lines. The measured failure mode of this whole class
    is a reader skimming to the bottom line — `0 error(s), 1 warning(s)` — and taking it at face
    value, so a reassuring summary with an honest note above it is still a lie by layout. Here
    there is no count at all, because none was established: the run stopped at the first thing it
    could not read, and everything downstream of that file went unvisited.

    Exit 2, not 1. See the module docstring.
    """
    detail = f"{exc.where}: {exc.detail}"
    if args.as_json:
        # No `errors`/`warnings`/`notes` keys, deliberately. Emitting them empty would let a
        # consumer read `len(errors) == 0` as a clean route, which is the defect one layer up.
        # Their absence makes a naive consumer raise instead of concluding.
        print(json.dumps({
            "status": "could-not-run",
            # `exit` is present on EVERY payload this script emits, including this one. A consumer
            # doing `payload["exit"]` must not have to special-case the path where the answer
            # matters most; omitting it here would have raised KeyError at the moment the run was
            # least trustworthy.
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
        # `status` is no longer the constant "ok": a consumer must be able to tell a run that
        # checked everything from one that checked part of it, and "ok" said the first about both.
        # `errors`/`warnings`/`notes` keep their shape; `not_run` is additive.
        # `exit` mirrors check_toolchain.py's payload deliberately. TC-37 consumes both, and an
        # asymmetry there is a special case in the caller for no reason on this side.
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
        # Scope, but only when this mode is already speaking. `--hook` is contractually silent on a
        # healthy project — it fires at every session start in every directory — so printing "the
        # README contract was not requested" unconditionally would put two permanent lines into
        # every session in every repository on the fleet and train the reader to skip the block.
        # Whenever it does speak, though, the reader is entitled to know what the run did not look
        # at, because that is the sentence that changes what they do next.
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
        # One line, composed from what ran. Never a literal, because a literal is how
        # `clean — every route resolves, every documented command exists` came to be printed over
        # a README contract the run had not looked at.
        print(f"  {summary}")

    return code


if __name__ == "__main__":
    raise SystemExit(main())
