#!/usr/bin/env python3
"""Check the agent toolchain for drift.

Everything else here is scoped to a repository. The first three things below are not — they live in
`~/.claude` and `~/.codex`, are shared by every project, and no per-repo check owns them. That is
exactly why they rot silently:

  1. The persona pool vs the agents generated from it. A per-repo drift check only fires in a
     repository that has overlays — one project in thirteen — so an unsynced edit to the pool runs
     stale in every other project and nothing says so.
  2. The shared sections of ~/.claude/CLAUDE.md and ~/.codex/AGENTS.md. Mirrored by hand; drift
     means the two harnesses are following different rules and neither announces it.
  3. The skills mirrored into ~/.codex/skills. Refreshed only when install_hooks.py runs, so a
     newly added skill is missing there until someone happens to run it in some repository.

Each failure is invisible from inside a project and silent at the point of use: Codex simply
follows an older contract. Reports; fixes nothing.

A fourth machine-global concern was added by TC-41, and it sits one floor BELOW the other three:

  4. The PLUGIN SURFACE in both harnesses. Everything else this toolchain governs decides what a
     PERSONA holds — an allow-list, a derived deny-list, a roster floor. A plugin adds capability
     underneath all of that: its hooks execute for every persona including the judging ones, and an
     `agents/<name>.md` it ships can shadow a base persona from a directory neither the roster, nor
     the allow-list, nor `sync_personas.py --check` looks at. There are three sources of that same
     shadowing door and only the first is governed by anything:

         ~/.claude/agents/<name>.md        `sync_personas.py --check` compares it
         <repo>/.claude/agents/<name>.md   overrides globally; nothing automatic compares it
         <plugin>/agents/<name>.md         seen by nothing at all — this is what is closed here

     `check_plugins` ENUMERATES and CLASSIFIES. It does not approve. There is no conforming set of
     plugins and inventing one would be wrong on the first new plugin and would train the reader to
     ignore the report. See `check_plugins` for the classification and the severity table.

A fifth machine-global concern was added by TC-47, and it sits one floor BELOW even the plugins:

  5. WHETHER GIT WOULD COMMIT ANY OF THIS AT ALL. Three times in one milestone authored content was
     invisible to version control and nothing noticed — a decision record the renderer read at
     startup, a lessons file invisible for two days while `git status` reported clean, and an entire
     new skill directory a commit would have silently dropped. Each was found by a person and fixed
     by a person adding one line to an allow-list. `check_tracking` asks git the question instead,
     once per skill directory, with `git add --dry-run` and emphatically NOT `git check-ignore` —
     see the block comment on GIT_ENV for the measurement that rules the second one out. The Codex
     side is a derived mirror and is declared out of scope rather than swept; see
     CODEX_TRACKING_ASYMMETRY.

`--vendored` and `--reviews` add two REPOSITORY-SCOPED concerns; neither ever runs implicitly:

  6. `--reviews <workspace>`: for every card that produced a report, an independent review artifact
     must exist. Same defect class as (5) one floor over — authored work that no gate can see —
     added after a live near-miss in which a card skipped its review stage entirely, was verified,
     and moved toward a commit carrying two criticals. See `check_reviews`.

  7. `--vendored <repo>`: a repository that publishes a vendored copy of the installed shared layer
     — `install/skills` mirroring `~/.claude/skills`. That copy is refreshed by hand, so it drifts
     in both directions: a skill edited or added in `~/.claude` and never re-vendored publishes
     stale instructions, and a skill deleted or renamed in `~/.claude` but left in the repository
     publishes a dead one forever. Neither side of that drift is visible from either side alone. It
     is a concern of its own rather than a mode of the machine-global ones because the comparison is
     between a machine and a *specific* repository, named on the command line.

The two repository-scoped modes are MUTUALLY EXCLUSIVE at the argument parser: they are verdicts
about different trees, and a run that silently executed one of them would print a status for a
question the caller did not ask.

THREE STATES, NEVER TWO. Every run resolves to exactly one of `clean`, `findings`, or `not-run`,
and a check that did not execute is reported as not-run in those words. It is never absorbed into a
pass and never contributes its name to the success line. The defect this closes is the one where
the failure path and the success path produce the same output: `check_skills` used to `continue`
past a mirrored skill that was not installed, and `check_personas` called a missing sync tool a
`warn`, so a run that compared nothing printed the same "clean — personas in sync, instructions
mirrored, Codex skills current" as a run that compared everything.

Exit codes: 0 clean, 1 finding, 2 the check could not run (usage, environment, or a `not-run`
finding). 2 outranks 1 for the reason `check_github.exit_code` gives: the exit code answers "can
you trust this report" before it answers "did it find anything".

Which severities gate the exit differs by mode — see EXIT SEMANTICS in `main()`. The exit code is
NOT the whole result in default mode, deliberately (see the TC-06 ruling on SEVERITY_RANK), so a
caller that reads only the exit status will miss real Codex-mirror drift. Callers must read `--json`
or the summary line; `verify.sh` reading `>/dev/null 2>&1` and the exit code alone is that bug.

Usage:
  check_toolchain.py           # human report
  check_toolchain.py --hook    # compact agent context, silent when healthy
  check_toolchain.py --json
  check_toolchain.py --vendored <repo>   # diff ~/.claude/skills against <repo>/install/skills
  check_toolchain.py --reviews <dir>     # every card with a report in <dir> must carry a review

`--json` emits an OBJECT, not a bare findings array: an array cannot carry the difference between
"nothing was wrong" and "nothing was looked at". Stable keys for a caller:

  {"mode", "status", "exit", "counts": {<severity>: n, "total": n},
   "evaluated": [...], "not_evaluated": [{"check", "why"}], "excluded": [{"name", "why"}],
   "findings": [{"severity", "detail"}], "plugins": {...} | null,
   "tracking": {...} | null, "reviews": {...} | null, "summary": "..."}

`counts` is keyed by severity so a caller counts by severity without parsing prose, and always
carries a key for every severity in SEVERITY_RANK even when it is zero.

`plugins` is the TC-41 enumeration, structured so `project-conformance` can act on it without
parsing prose. It is `null` in `--vendored` mode — that mode enumerates no plugins, and `null` says
so where `{}` would read as "there are none". Its shape is fixed by `plugin_surface()`; the field a
caller most likely wants is `plugins["claude"]["enumerated"]`, which is `false` whenever any part of
the Claude-side enumeration could not be completed, so an incomplete list can never be mistaken for
a short one.

`tracking` and `reviews` are TC-47's two sweeps, on the same terms and `null` in the modes that do
not run them — `tracking` in `--vendored` and `--reviews`, `reviews` everywhere but `--reviews`.

  tracking.claude.asked        false whenever git could not be asked. THE FIELD TO CHECK FIRST: an
                               unasked question is not a satisfied one, and `results` is empty in
                               both cases.
  tracking.claude.results      skill directory -> "trackable" | "ignored" | "unknown", keyed by what
                               the WORKING TREE holds, not by what HEAD carries. Do not reconcile
                               its length against `git ls-files`; they count different trees.
  tracking.claude.declared_vendor   name -> why. The exclusion list, quoted so it is visible.
  tracking.codex.in_scope      always false, with `why_not_asked` carrying the reason.
  reviews.cards                card id -> {"reports", "reviews"}. The per-card counts; the zero
                               that is invisible in the aggregate is obvious here.
  reviews.totals               {"cards", "with_reports", "unreviewed"}.

WHAT A `--json` CONSUMER MUST HANDLE, stated because it is NOT symmetrical with
`validate_disclosure.py` and a caller told otherwise will crash on the path that matters most.
The five usage-and-environment failures in `main` — an empty `--vendored` value, either root
missing, either root a symlink, both roots resolving to the same directory, and an OSError while
reading — print a message to **stderr** and return 2 **without emitting any JSON at all**, even
under `--json`. Stdout is empty. That is deliberate: the empty stdout is itself pinned by
`test_empty_and_whitespace_vendored_argument_exit_two`, because those paths never established a
result to report and an empty findings array would read as "nothing was wrong".

So: check the exit status BEFORE parsing. `0/1` ⇒ stdout is one JSON object; `2` ⇒ stdout may be
empty and the reason is on stderr. `validate_disclosure.py` differs here — its could-not-run path
DOES emit an object, carrying `"status": "could-not-run"` and `"exit": 2`.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
CODEX_MD = HOME / ".codex" / "AGENTS.md"
CODEX_SKILLS = HOME / ".codex" / "skills"
CLAUDE_SKILLS = HOME / ".claude" / "skills"
SYNC = CLAUDE_SKILLS / "agent-personas" / "scripts" / "sync_personas.py"

# The plugin surface, both harnesses. Module-level and derived from HOME for the same reason
# everything above is: the tests drive this file under a synthetic HOME.
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"
CLAUDE_PLUGINS = HOME / ".claude" / "plugins"
INSTALLED_PLUGINS = CLAUDE_PLUGINS / "installed_plugins.json"
CODEX_CONFIG = HOME / ".codex" / "config.toml"

# What makes a directory a plugin, and it is a MANIFEST rather than a naming convention. Measured
# on this machine: a naive `find ~/.claude/plugins -path '*/agents/*.md'` returns 34 files, three of
# which live at `<plugin>/skills/skill-creator/agents/*.md` — inside a skill's own body, not in the
# plugin's agent directory. Those three are not plugin-supplied agents and the harness does not load
# them as such. Anchoring on the manifest and then on `<root>/agents/*.md` gives 31 files / 29 names,
# and that is the number this check reports.
PLUGIN_MANIFEST = (".claude-plugin", "plugin.json")

# Pruned from the plugin walk. Neither can contain a plugin root that the harness would load, and
# `node_modules` in particular can be enormous — a vendored dependency tree that happens to contain
# a `.claude-plugin/plugin.json` is not an installed plugin.
PLUGIN_WALK_PRUNE = frozenset({"node_modules", ".git", "__pycache__"})

# Said in every plugin finding, because it is the fact most likely to be acted on wrongly. This tool
# runs per-repository at every session start; the plugin surface it reports is per-MACHINE. Without
# this sentence someone fixes it in one repository and expects the others to change.
MACHINE_GLOBAL = ("This is MACHINE-GLOBAL, not a property of this repository: it comes from "
                  "~/.claude and ~/.codex and is identical in every project on this machine.")

# Blocks that must be byte-identical in both harnesses' global instructions, as (start, end) text
# markers present in both files. The end marker is excluded from the comparison.
#
# Deliberately NOT listed: `# Operating model` and the surrounding `# Cross-project implementation
# strategy` prose. Those differ on purpose — first person for Claude, third for Codex, and each
# points at its own skills directory. Comparing them byte-for-byte would report a permanent failure
# and train the reader to ignore this check. Only blocks that carry rules, rather than voice, are
# required to match.
MIRRORED = [
    ("# GitHub", "# Cross-project implementation strategy"),
    ("**The personas are defined, not improvised.**", "system-prompt floor every call."),
]

# Skills both harnesses need. `graphify` is deliberately excluded: it is a vendor skill hidden from
# model-initiated use on the Claude side, and its presence in Codex is not something we manage.
#
# Scope: this list governs the ~/.codex mirror ONLY (`check_skills`). It is deliberately NOT reused
# by `check_vendored`, which has no allow-list at all and compares every non-symlinked directory
# under ~/.claude/skills — a symlinked one is reported as uncompared rather than descended into. Those are different questions — "which skills must Codex be able to run" is not
# "which skills may be published in a public repository" — and answering the second one needs a
# published-skills manifest this file does not have. Until it does, `check_vendored` reports the
# raw fact that a directory exists on one side and not the other, and the operator decides what to
# do about it; it must not be read as an instruction to publish anything. See the TC-03 review, F5.
MIRRORED_SKILLS = ("progressive-disclosure", "agent-personas", "agent-persona-factory",
                   "graph-navigation", "project-onboarding", "execution-methodology")

# The third state. A `not-run` is not a severity of finding in the ordinary sense — it is the
# absence of a finding *and* the absence of a clean result, which is precisely the thing two-state
# reporting cannot express. Spelled the way it is printed, so a grep for the word finds both.
NOT_RUN = "not-run"

# TC-06's ruling, implemented here rather than restated: RANK GOVERNS VISIBILITY, `BLOCKING`
# GOVERNS THE EXIT CODE, and the two are deliberately different objects. An unknown severity —
# whatever someone adds next — sorts to the TOP of the report (rank -1, louder than not-run) and is
# NOT in any blocking set. Loud but not fatal. The alternative, treating an unrecognised severity
# as blocking, would make every session start fail the day an advisory level is introduced.
SEVERITY_RANK: dict[str, int] = {NOT_RUN: 0, "critical": 1, "warn": 2, "info": 3}

# Default / --hook / --json. `warn` here means "a mirror this tool cannot fix from here has
# drifted"; it is real and must be visible, but it has always exited 0 and raising it would turn
# every session start into a failure. Visibility is the summary line and `--json`, not the code.
BLOCKING_DEFAULT = frozenset({"critical"})

# `--vendored`. A sentinel, not a set, so that adding a new severity later cannot quietly restore
# the false GREEN this mode was built to kill. See EXIT SEMANTICS in `main()`.
BLOCKING_ANY = "any-finding"


def severity_sort_key(severity: str) -> tuple[int, str]:
    """Report order. Unknown severities sort first — loud, per the TC-06 ruling."""
    return (SEVERITY_RANK.get(severity, -1), severity)


class Run:
    """One execution of the checker: what it evaluated, what it did not, and what it found.

    Exists so that "what may the summary claim" is answered by recorded fact rather than by a
    hard-coded sentence. The old success line named three checks unconditionally; a run in which
    none of the three could execute printed it verbatim.

    `evaluated` is what actually ran to completion — and ONLY `evaluated` may appear in the clean
    line. `not_evaluated` is what did not, and its presence alone is enough to deny a clean verdict
    even when there is not a single finding. `excluded` is scope that was declared out of the
    comparison on purpose: reported, never silent, never a finding.
    """

    def __init__(self, mode: str, blocking) -> None:
        self.mode = mode
        self.blocking = blocking
        self.findings: list[tuple[str, str]] = []
        self.evaluated: list[str] = []
        self.clean_phrases: list[str] = []
        self.not_evaluated: list[tuple[str, str]] = []
        self.excluded: list[tuple[str, str]] = []
        # The TC-41 enumeration, or None in a mode that does not enumerate plugins. NOT `{}`:
        # an empty mapping is the correct value for "a machine with no plugins", so using it for
        # "not enumerated here" would collapse the same two states this class exists to keep apart.
        self.plugins: dict | None = None
        # The TC-47 sweeps, on the same terms and for the same reason: `{}` is the right value for
        # "a workspace with no cards", so it cannot also mean "this mode does not sweep".
        self.tracking: dict | None = None
        self.reviews: dict | None = None

    def add(self, findings: list[tuple[str, str]], label: str | None = None,
            clean_phrase: str | None = None) -> None:
        """Record one check's findings and, from them alone, whether it may claim coverage.

        THE CHOKEPOINT for coverage. A check earns its phrase only when it produced no `not-run`
        finding, so it is structurally impossible for a check that skipped its work to contribute
        the phrase that says it did the work. No caller decides this; the findings do.

        TWO VOCABULARIES, kept apart on purpose. `label` NAMES the check ("Codex skill mirror") and
        is what "checked: ..." lists — a statement that it ran, which stays true when it found
        something. `clean_phrase` ASSERTS a result ("Codex skills current") and may only ever reach
        the success line. Folding them into one list put "Codex skills current" in the summary of a
        run that had just printed two Codex-mirror differences, which is the same false-reassurance
        defect one layer in.
        """
        self.findings += findings
        if label is None:
            return
        why = [d for s, d in findings if s == NOT_RUN]
        if why:
            self.not_evaluated.append((label, why[0]))
        else:
            self.evaluated.append(label)
            self.clean_phrases.append(clean_phrase or label)

    def counts(self) -> dict[str, int]:
        tally = {s: 0 for s in SEVERITY_RANK}
        for severity, _ in self.findings:
            tally[severity] = tally.get(severity, 0) + 1
        tally["total"] = len(self.findings)
        return tally

    def verdict(self) -> tuple[str, int]:
        """The ONE place a run becomes a status and an exit code. Three states, never two.

        `not-run` outranks everything: a report you cannot trust is worse news than a report with a
        finding in it, and it must never resolve to 0. Only after that does severity gate the code,
        and which severities do is the mode's business, not this function's.
        """
        if any(s == NOT_RUN for s, _ in self.findings) or self.not_evaluated:
            return NOT_RUN, 2
        if not self.findings:
            return "clean", 0
        blocked = (self.blocking is BLOCKING_ANY
                   or any(s in self.blocking for s, _ in self.findings))
        return "findings", (1 if blocked else 0)

    def summary(self, status: str) -> str:
        """The one sentence allowed to characterise the run. Derived, never asserted.

        A clean line may name only `evaluated`. Anything else in it would be the original defect
        wearing a new sentence.
        """
        scope = ""
        if self.excluded:
            # "excluded from findings", not "excluded and NOT compared". The header used to assert
            # the stronger thing, which was true of every exclusion until TC-47 added one that was
            # ASKED and ANSWERED and merely exempt from producing a finding — a declared vendor,
            # whose state is recorded in `tracking.claude.results`. A header that contradicts the
            # data two keys away is the same false-reassurance defect at label size. Each entry's
            # own `why` still says which of the two it is.
            scope = ("; " + f"{len(self.excluded)} excluded from findings: "
                     + ", ".join(f"{n} ({w})" for n, w in self.excluded))
        if status == "clean":
            return "clean — " + ("; ".join(self.clean_phrases) or "nothing to check") + scope
        tally = self.counts()
        parts = ", ".join(f"{tally[s]} {s}" for s in sorted(tally, key=severity_sort_key)
                          if s != "total" and tally[s])
        head = f"{tally['total']} finding(s): {parts}" if tally["total"] else "no findings"
        ran = "; checked: " + (", ".join(self.evaluated) or "nothing")
        if status == NOT_RUN:
            missed = ", ".join(label for label, _ in self.not_evaluated)
            return (f"NOT A CLEAN RESULT — {head}{ran}{scope}. "
                    f"NOT RUN: {missed or 'see the not-run finding(s) above'}. "
                    f"No verdict is available for what did not run.")
        return f"NOT A CLEAN RESULT — {head}{ran}{scope}."


def section(text: str, start: str, end: str) -> str | None:
    try:
        return text[text.index(start):text.index(end)]
    except ValueError:
        return None


def check_personas() -> list[tuple[str, str]]:
    """Every early return here used to be a `warn`, which is the wrong claim three times over.

    "The sync tool is missing", "the tool would not start" and "the tool failed" are not findings
    about the persona pool — they are the absence of any finding about it, and calling them `warn`
    let a run that never compared a single persona exit 0 under a line saying personas were in sync.
    """
    if not SYNC.is_file():
        return [(NOT_RUN, f"persona sync was NOT RUN: the sync tool is missing at {SYNC}, so no "
                          f"generated agent file was compared against the pool")]
    try:
        r = subprocess.run(["python3", str(SYNC), "--check"],
                           capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return [(NOT_RUN, f"persona sync was NOT RUN: the sync check could not be started ({e})")]
    if r.returncode == 1:
        n = sum(1 for line in r.stdout.splitlines() if line.strip().startswith("/"))
        return [("critical", f"{n} generated agent file(s) do not match the persona pool. Both "
                             f"harnesses are running a stale persona. Fix: python3 {SYNC}")]
    if r.returncode not in (0, 1):
        return [(NOT_RUN, f"persona sync was NOT RUN: the sync check exited {r.returncode} without "
                          f"reaching a verdict ({r.stderr.strip()[:120]})")]
    return []


def check_instructions() -> list[tuple[str, str]]:
    """A section that is absent from one side was never compared, and says so in those words.

    The previous `warn` conflated "I compared these and they differ" with "one of them is not there
    to compare", and only the first of those is a finding about the mirror.
    """
    if not CLAUDE_MD.is_file() or not CODEX_MD.is_file():
        return [(NOT_RUN, "the instruction mirror was NOT RUN: one of ~/.claude/CLAUDE.md or "
                          "~/.codex/AGENTS.md is missing, so no shared block was compared")]
    # `is_file()` is True for a mode-000 file and for a UTF-16 one, so the existence probe above
    # does not make the read safe. Unguarded, this raised out of `main` and Python exited 1 with a
    # traceback — which is the two-state world returning: a run that could not look reported the
    # code for "I looked and found something". Same shape as the guard in `read_declaration`.
    try:
        a, b = (CLAUDE_MD.read_text(encoding="utf-8", errors="strict"),
                CODEX_MD.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError) as e:
        return [(NOT_RUN, f"the instruction mirror was NOT RUN: ~/.claude/CLAUDE.md or "
                          f"~/.codex/AGENTS.md could not be read ({e}), so no shared block was "
                          f"compared")]
    out = []
    for start, end in MIRRORED:
        sa, sb = section(a, start, end), section(b, start, end)
        if sa is None or sb is None:
            out.append((NOT_RUN,
                        f"section `{start}` was NOT COMPARED: it is missing from "
                        f"{'~/.claude/CLAUDE.md' if sa is None else '~/.codex/AGENTS.md'}, so "
                        f"whether the two harnesses agree on it is unknown"))
        elif sa != sb:
            out.append(("critical", f"section `{start}` differs between ~/.claude/CLAUDE.md and "
                                    f"~/.codex/AGENTS.md — the two harnesses are following "
                                    f"different rules"))
    return out


def tree(root: Path, pattern: str = "**/*") -> tuple[dict[str, bytes], list[tuple[str, str]]]:
    """Every readable file under `root`, keyed by relative path, plus everything it could not read.

    Returns `(files, problems)`. `files` maps relative path -> bytes. `problems` is a list of
    `(relative_path, reason)` for entries this walk could not turn into a trustworthy value.

    Not `filecmp.dircmp`: its `diff_files` covers only the top level, and every skill keeps its
    logic in `scripts/`. A stale mirrored validator sat undetected behind exactly that blind spot.
    Bytes rather than the default stat-signature compare, because a copy preserves mtime and an
    edit that keeps the file the same size would otherwise read as identical.

    Nothing unreadable is ever given a placeholder value. An earlier version substituted
    `b"<unreadable>"`, which made two files that could not be read compare EQUAL and report as in
    sync — a fail-open in the comparison primitive itself. An unreadable *file* is now absent from
    `files` (so it cannot compare equal to anything) and present in `problems` (so it is a finding
    in its own right). Callers must report `problems` and must exclude those paths from their
    present/absent diff, or an unreadable file would also be miscounted as missing.

    KNOWN GAP, deliberately not closed here. That guarantee covers files, not directories. The only
    thing that appends to `problems` is the `read_bytes()` handler below, and `Path.glob` swallows
    the error for a directory it cannot descend into — it yields nothing from inside and raises
    nothing. So an unreadable *directory* is silently absent from BOTH sides' `files` and absent
    from `problems` too, and its whole region reads as in sync. Closing it means walking with
    `os.walk(..., onerror=...)` so the descent error becomes a problem entry; that is a larger
    change than this card carries and is carded separately as TC-08. Until that card lands, do not
    read "clean" as covering a subtree this process lacks execute permission on.

    Symlinks are problems, not entries. `Path.rglob` does not descend into a symlinked directory
    while `Path.is_dir()` follows it, so a symlinked subdirectory silently contributes zero files
    and its whole region reads as in sync on both sides. Verified on CPython 3.14.6: for a tree
    whose only child is a symlink to a populated directory, `rglob("*")` yields just the link.

    `pattern` selects what is walked, so the same primitive serves both the recursive whole-skill
    comparison (`"**/*"`, the default) and the non-recursive top-level-file sweep (`"*"`). Callers
    get one walker with one set of rules, not two that can drift apart.
    """
    files: dict[str, bytes] = {}
    problems: list[tuple[str, str]] = []
    for p in root.glob(pattern):
        if "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        rel = str(p.relative_to(root))
        if p.is_symlink():
            problems.append((rel, "symlink, not compared"))
            continue
        if not p.is_file():
            continue
        try:
            files[rel] = p.read_bytes()
        except OSError as e:
            problems.append((rel, f"unreadable: {e.strerror or e}"))
    return files, problems


def check_skills() -> list[tuple[str, str]]:
    if not CODEX_SKILLS.is_dir():
        return [(NOT_RUN, "the Codex skill mirror was NOT RUN: ~/.codex/skills does not exist, so "
                          "none of the shared skills was compared — Codex has none of them and no "
                          "statement about their currency is available")]
    out = []
    for name in MIRRORED_SKILLS:
        src, dst = CLAUDE_SKILLS / name, CODEX_SKILLS / name
        if not src.is_dir():
            # The original silent swallow of this file: a bare `continue`. A mirrored skill that is
            # not installed produced no output at all, so the failure path and the success path
            # were byte-identical and the run still claimed "Codex skills current".
            out.append((NOT_RUN, f"skill `{name}` was NOT COMPARED: it is named in MIRRORED_SKILLS "
                                 f"but is not installed at {src}, so there was nothing to compare "
                                 f"the Codex copy against"))
            continue
        if not dst.is_dir():
            out.append(("critical", f"skill `{name}` is missing from ~/.codex/skills — Codex "
                                    f"cannot use it. Fix: install_hooks.py <any-repo>"))
            continue
        a, a_bad = tree(src)
        b, b_bad = tree(dst)
        # A path this walk could not read is neither present nor absent — exclude it from the
        # present/absent diff and name it directly, rather than reporting it as missing.
        unread = {rel for rel, _ in a_bad} | {rel for rel, _ in b_bad}

        # Symlinks get their own finding, because they get their own remedy. Folded into `bad`
        # below they inherited "Fix: install_hooks.py <any-repo>", which cannot clear them under
        # either `copytree` symlink setting: it either copies the link again or copies the target's
        # contents, and in neither case does the reported path stop being a link. This line prints
        # at every session start in every directory, so an untrue remedy here is expensive — the
        # reader runs the suggested command, sees the finding survive, and learns to ignore both.
        links = sorted({rel for rel, why in a_bad if why == "symlink, not compared"}
                       | {rel for rel, why in b_bad if why == "symlink, not compared"})
        if links:
            # `not-run`, not `warn`. "This skill is only partly checked" was already the honest
            # sentence; the severity beside it said otherwise and let the run exit 0 under a line
            # claiming the Codex skills are current. A region that was not compared is not-run for
            # that region however much of the rest succeeded.
            detail = ", ".join(links[:3]) + (f", +{len(links) - 3} more" if len(links) > 3 else "")
            out.append((NOT_RUN, f"skill `{name}` contains a symlink that was NOT COMPARED "
                                 f"({detail}), so this skill is only partly checked. Fix: replace "
                                 f"the symlink with a real directory — install_hooks.py will not "
                                 f"remove it."))

        bad = (sorted((set(a) ^ set(b)) - unread)
               + sorted(k for k in set(a) & set(b) if a[k] != b[k])
               + [f"{rel} ({why})" for rel, why in sorted(set(a_bad) | set(b_bad))
                  if why != "symlink, not compared"])
        if bad:
            detail = ", ".join(bad[:3]) + (f", +{len(bad) - 3} more" if len(bad) > 3 else "")
            out.append(("warn", f"skill `{name}` differs from the Codex copy ({detail}). "
                                f"Fix: install_hooks.py <any-repo>"))
    return out


def _gitignore_rules(text: str) -> list[tuple[str, bool, bool]]:
    """Parse a .gitignore into `(pattern, negated, anchored)` rules matching one path component.

    Deliberately narrow. This answers exactly one question — "does this repository declare that it
    does not publish this path" — so it handles only the constructs that can bear on a single path
    component: comments, blanks, `!` negation, a leading or trailing `/`, and shell globs. A rule
    containing an interior `/` addresses a specific nested path; it is skipped rather than
    half-applied, and skipping is the fail-CLOSED direction because it produces a finding rather
    than a silent exclusion.

    ANCHORING IS NOT COSMETIC, and dropping it is how this function nearly became a catastrophe.
    `/*` and `.DS_Store` are both in the real declaration and they mean opposite-scoped things:
    `/*` ignores every entry at the TOP of this directory, while `.DS_Store` ignores that name
    ANYWHERE beneath it. An earlier draft stripped the leading `/` and returned both as bare
    patterns, which was harmless only for as long as the rules were applied to top-level names
    alone. Applied to nested paths — which F1 requires — an unanchored `*` matches every component
    at every depth and excludes the entire tree, turning the whole comparison into a silent pass:
    the exact defect class this card exists to remove, introduced by the fix for it.
    """
    rules: list[tuple[str, bool, bool]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        anchored = line.startswith("/")
        line = line.strip("/")
        if not line or "/" in line:
            continue
        rules.append((line, negated, anchored))
    return rules


def excluded_by(rules: list[tuple[str, bool, bool]], rel: str) -> bool:
    """Does the declaration cover `rel`, a path relative to the skills root?

    THE ONE PLACE the declaration is applied. Every comparison site routes through here, because
    F1 was precisely a comparison site that did not: exclusion reached the two directory sets and
    not the top-level file sweep, so a `.DS_Store` — named in the real declaration, created by
    opening the folder in Finder once, and unpublishable by git forever — became a permanent
    CRITICAL. A permanent finding no remedy can clear is the thing that teaches a reader to ignore
    the whole report, which is the pathology this card was written about.

    Git's rules, narrowed to what the parser above produces:
      * an anchored rule (`/x`) may match only the FIRST component;
      * an unanchored rule (`x`) may match a component at any depth — that is what makes
        `.DS_Store` and `*.pyo` "never, anywhere" in the real file;
      * an ignored directory takes its contents with it, so a match on ANY component excludes the
        whole path;
      * last matching rule wins, which is what makes the allowlist form (`/*` then `!/name`) work.
    """
    for index, part in enumerate(Path(rel).parts):
        ignored = False
        for pattern, negated, anchored in rules:
            if anchored and index > 0:
                continue
            if fnmatch.fnmatchcase(part, pattern):
                ignored = not negated
        if ignored:
            return True
    return False


def read_declaration(vendored_skills: Path) -> tuple[list[tuple[str, bool, bool]],
                                                     list[tuple[str, str]]]:
    """Load `<repo>/install/skills/.gitignore`. Returns `(rules, findings)`.

    THE DECLARATION ALREADY EXISTS. That file is the one git itself consults to decide what this
    directory publishes, it is tracked, and it is written as an allowlist: ignore everything at the
    top level, then name the skills the repository owns, then a short "never, anywhere" tail. A
    vendor skill that installs itself into `~/.claude/skills` on its own schedule — graphify does
    exactly this — is therefore already declared unpublished, by the only mechanism that actually
    governs publication. Reading it is the whole fix.

    There is no second exception list and no name is special-cased in this file. Delete the
    declaration and every path it covered becomes a finding again, which is what the test asserts.

    A missing .gitignore excludes nothing: the correct reading of "no declaration" is "everything is
    published", and inventing exclusions from its absence would be the fail-open being remediated.
    An UNREADABLE one is a `not-run`, because then what is excluded is unknown and every presence
    finding below it would be a guess.
    """
    declaration = vendored_skills / ".gitignore"
    if not declaration.is_file():
        return [], []
    try:
        return _gitignore_rules(declaration.read_text(encoding="utf-8", errors="strict")), []
    except (OSError, UnicodeDecodeError) as e:
        return [], [(NOT_RUN, f"vendored drift was NOT RUN: {declaration} could not be read ({e}), "
                              f"so what this repository declares unpublished is unknown and no "
                              f"presence finding below would be trustworthy")]


def declared_unpublished(vendored_skills: Path, rules) -> dict[str, str]:
    """The top-level skill DIRECTORIES the declaration covers, on either side.

    Directories only, and that is the whole of its job: these are the names subtracted from the two
    directory sets in `check_vendored`, which is a set operation over directory names. Excluded
    FILES are not its business and must not be inferred from its absence — they are dropped inside
    `_compare`, and `_compare` reports what it dropped. This function used to be the sole source of
    the `excluded` report too, which is exactly how excluded files came to be reported nowhere.

    Both sides, not just the installed one. A name present only in the vendored copy and covered by
    the declaration is untracked litter that git will never publish — uninstall graphify while a
    stale `install/skills/graphify/` remains and the installed-only view would report it as "stale
    published content" forever, another permanent finding no action can clear. The categories in
    `check_vendored` must describe genuine publication, so the exclusion has to be symmetric.
    """
    names = {p.name for p in CLAUDE_SKILLS.iterdir() if p.is_dir() and not p.is_symlink()}
    names |= {p.name for p in vendored_skills.iterdir() if p.is_dir() and not p.is_symlink()}
    return {name: "declared unpublished by install/skills/.gitignore"
            for name in sorted(names) if excluded_by(rules, name)}


def _describe_vendored(skill: str, rel_path: str) -> str:
    """Name what a relative path inside `skill` is, for a --vendored finding.

    Persona files get named by persona, since that is the unit a human recognizes — not the raw
    path `personas/chief-of-staff.md`.

    Exactly two parts, not a prefix match: `personas/README.md` is an index and not a persona, and
    `personas/archive/scout.md` is a retired copy that must not render identically to the live
    `personas/scout.md`. Both fall through to the raw-path form.
    """
    parts = Path(rel_path).parts
    stem = Path(rel_path).stem
    if skill == "agent-personas" and len(parts) == 2 and parts[0] == "personas" \
            and rel_path.endswith(".md") and stem.lower() != "readme":
        return f"persona `{stem}`"
    return f"skill `{skill}` file `{rel_path}`"


def check_vendored(vendored_skills: Path, rules=()) -> list[tuple[str, str]]:
    """Diff ~/.claude/skills (the installed shared layer) against a repository's vendored copy.

    Reuses `tree()` — once per side for the top-level regular files, once per shared skill for the
    recursive comparison — rather than a second walker. Reports drift; does not fix it.
    Missing/extra/differs are kept as separate findings so the categories in the invariant survive
    into the output rather than collapsing into "something is different".

    Findings are FACTS about what is on each side, never instructions. In particular "present
    installed, absent from vendored" does not mean "publish this": there is no published-skills
    manifest here, so a personal or client-specific skill under ~/.claude/skills produces that
    finding too, and publishing it into a public repository would be the wrong response. See the
    MIRRORED_SKILLS note above.

    Every finding this returns gates the exit code in `--vendored` mode regardless of severity;
    the severity label orders the report, it does not decide pass/fail. See EXIT SEMANTICS.

    Returns `(findings, excluded)`. `excluded` is `(path, why)` for everything the declaration
    removed from this comparison, collected FROM THE COMPARISONS THEMSELVES rather than from a
    separate enumeration — see the note on silence below.

    `rules` are the repository's own `install/skills/.gitignore` (see `read_declaration`), and they
    reach every comparison this function performs — the two directory sets, the top-level entry
    sweep, and each skill's recursive sweep — through the single `excluded_by` predicate. An earlier
    version applied them to the directory sets only, so a `.DS_Store` at the top level (named in the
    real declaration, and unpublishable by git forever) was a permanent CRITICAL. That completeness
    is enforced two ways: `_compare` has no default for `is_excluded`, so a new call site that omits
    it raises TypeError, and `test_every_comparison_applies_the_declaration` walks this function's
    AST and fails if any `_compare` call lacks the argument.

    What exclusion means, in all three directions: a path git will never publish is not missing
    from the vendored copy, is not stale published content if it happens to sit there untracked,
    and has no published bytes to compare.

    NOTHING IS DROPPED SILENTLY, and getting that right required deriving the report from the drop.
    An earlier version re-enumerated the excluded set by listing top-level DIRECTORIES, so an
    excluded top-level FILE — which the real anchored `/*` produces for every un-negated entry —
    was removed from the comparison and appeared in no output at all. `touch NOTES.md` and it
    vanished; if NOTES.md were something the repository should publish and someone had forgotten
    the negation, the failure path and the success path produced identical output. The exclusions
    reported are now exactly the exclusions applied.
    """
    out: list[tuple[str, str]] = []
    why = "declared unpublished by install/skills/.gitignore"
    excluded_names = declared_unpublished(vendored_skills, rules)
    excluded = set(excluded_names)
    dropped: dict[str, str] = dict(excluded_names)

    # Symlinked top-level entries are excluded from the directory sets and reported by the
    # top-level `tree()` sweep below: a symlinked skill directory is walked as empty (see tree()),
    # so treating it as a real skill would compare two empty trees and call the region clean.
    installed = {p.name for p in CLAUDE_SKILLS.iterdir()
                 if p.is_dir() and not p.is_symlink()} - set(excluded)
    vendored = {p.name for p in vendored_skills.iterdir()
                if p.is_dir() and not p.is_symlink()} - set(excluded)

    # ...but excluding them from those sets is not enough on its own. A skill that is a real
    # directory on one side and a SYMLINK on the other is absent from exactly one set, and so was
    # reported as a presence difference — most wrongly as "stale published content" for a skill
    # that is installed, merely installed as a link. It is not stale and it is not unpublished; it
    # is uncompared, which the top-level sweep below already says accurately. Subtract those names
    # so the presence categories only ever describe genuine presence.
    linked = ({p.name for p in CLAUDE_SKILLS.iterdir() if p.is_symlink()}
              | {p.name for p in vendored_skills.iterdir() if p.is_symlink()})

    for name in sorted((installed - vendored) - linked):
        out.append(("critical", f"skill `{name}` present in ~/.claude/skills, "
                                f"absent from the vendored copy"))
    for name in sorted((vendored - installed) - linked):
        out.append(("critical", f"skill `{name}` present in the vendored copy, "
                                f"absent from ~/.claude/skills — stale published content"))

    # F7: regular files at the top level of either skills root — a README, an index, a manifest —
    # were previously invisible in both directions because only directories were enumerated.
    # "entry", not "file": this sweep is also what reports a symlinked skill DIRECTORY, and calling
    # that a file is the same class of inaccuracy as calling it stale.
    found, skipped = _compare(CLAUDE_SKILLS, vendored_skills, "*",
                              lambda rel: f"top-level entry `{rel}`",
                              lambda rel: excluded_by(rules, rel))
    out += found
    dropped.update({rel: why for rel in skipped})

    for name in sorted(installed & vendored):
        found, skipped = _compare(
            CLAUDE_SKILLS / name, vendored_skills / name, "**/*",
            lambda rel, _n=name: _describe_vendored(_n, rel),
            # The rule set is relative to the SKILLS ROOT, so a path inside a skill has to be
            # re-rooted before it is matched. Passing the skill-relative path would test
            # `scripts/x.py` against rules written for `<skill>/scripts/…` and quietly
            # under-exclude.
            lambda rel, _n=name: excluded_by(rules, f"{_n}/{rel}"))
        out += found
        dropped.update({f"{name}/{rel}": why for rel in skipped})

    return out, sorted(dropped.items())


def _compare(installed_root: Path, vendored_root: Path, pattern: str,
             describe, is_excluded) -> tuple[list[tuple[str, str]], list[str]]:
    """One `tree()` per side, rendered as the three drift categories plus unreadable entries.

    Returns `(findings, skipped)`. `skipped` is every path the declaration removed here, so that
    what gets REPORTED as out of scope is derived from what was actually skipped rather than from a
    second enumeration free to disagree with it.

    `is_excluded` HAS NO DEFAULT, deliberately. It was `lambda rel: False`, which meant a call site
    added later would compare unexcluded, reintroduce the permanent CRITICAL this parameter exists
    to prevent, and leave every test green. Omission is now a TypeError at the call site — the
    cheapest enforcement there is — and `test_every_comparison_applies_the_declaration` asserts the
    same rule against this module's AST, so the guarantee survives a default being restored.

    Applied to BOTH sides before any category is computed, so a declared-unpublished path is absent
    from the present/absent diff, the content diff, and the unreadable list alike. Filtering one
    side only would convert an exclusion into a presence finding, which is the bug rather than a fix.
    """
    a, a_bad = tree(installed_root, pattern)
    b, b_bad = tree(vendored_root, pattern)
    skipped = sorted({rel for rel in set(a) | set(b) if is_excluded(rel)}
                     | {rel for rel, _ in a_bad + b_bad if is_excluded(rel)})
    a = {rel: data for rel, data in a.items() if not is_excluded(rel)}
    b = {rel: data for rel, data in b.items() if not is_excluded(rel)}
    a_bad = [(rel, why) for rel, why in a_bad if not is_excluded(rel)]
    b_bad = [(rel, why) for rel, why in b_bad if not is_excluded(rel)]
    out: list[tuple[str, str]] = []

    # An entry that could not be read is neither present nor absent. Report it as its own finding
    # and keep it out of the present/absent diff, so it is never silently counted as missing — and
    # never, as it once was, given a placeholder value that compares equal to the other side's.
    unread = {rel for rel, _ in a_bad} | {rel for rel, _ in b_bad}
    for rel, why in sorted(set(a_bad)):
        out.append(("critical", f"{describe(rel)} could not be compared "
                                f"in ~/.claude/skills ({why})"))
    for rel, why in sorted(set(b_bad)):
        out.append(("critical", f"{describe(rel)} could not be compared "
                                f"in the vendored copy ({why})"))

    for rel in sorted((set(a) - set(b)) - unread):
        out.append(("critical", f"{describe(rel)} present installed, absent from vendored"))
    for rel in sorted((set(b) - set(a)) - unread):
        out.append(("critical", f"{describe(rel)} present in vendored, not installed"))
    for rel in sorted(k for k in (set(a) & set(b)) - unread if a[k] != b[k]):
        out.append(("critical", f"{describe(rel)} content differs from vendored"))
    return out, skipped


def _read_json(path: Path) -> tuple[dict | None, str | None]:
    """`(parsed, why_not)`. Absent, unreadable and unparseable are three distinguishable answers.

    Returns `(None, reason)` for unreadable or unparseable, and `({}, None)` for absent — because
    "this optional file is not there" is a real answer for `installed_plugins.json` on a machine
    that has never installed a plugin, while "it is there and I could not read it" is not.
    """
    if not path.is_file():
        return {}, None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        return None, f"{path} could not be read as JSON ({e})"
    if not isinstance(loaded, dict):
        return None, f"{path} is valid JSON but not an object (got {type(loaded).__name__})"
    return loaded, None


def persona_names() -> tuple[frozenset[str], frozenset[str], str | None]:
    """`(base, judging, why_not)` — the two name sets, READ FROM sync_personas.py.

    NOT a copy. `BASE_PERSONA_NAMES` and `JUDGING_PERSONA_NAMES` live in
    `agent-personas/scripts/sync_personas.py`, which is the module the renderer itself consults; a
    second literal list here is precisely the drift this programme has spent itself removing, and it
    would fail SILENTLY — a persona added to the pool and not to the copy would be a name this check
    then declined to protect.

    Imported rather than shelled out to, because the values wanted are objects rather than a verdict
    and `sync_personas.py` has no flag that prints them as data. The import is safe by inspection at
    the only property that matters here: the module guards its entry point behind
    `if __name__ == "__main__"`, so importing it defines constants and functions and runs no sync.
    That is a claim about a file outside this card's write set, so it is stated as the reason for a
    choice and NOT asserted by a test here — the assertion that belongs with it belongs to the
    agent-personas write set. What IS asserted here is the consequence that matters: that this
    function returns the same sets the module holds, and that a failed import is a not-run.

    A failure to import is `(frozenset(), frozenset(), reason)`. The caller must turn that into a
    not-run: without the names there is no cross-check, and an enumeration that silently skipped the
    cross-check would report "no plugin shadows a persona" having compared against nothing.
    """
    if not SYNC.is_file():
        return frozenset(), frozenset(), (f"the persona name sets could not be read: {SYNC} is "
                                          f"missing, so no plugin agent name was cross-checked")
    try:
        spec = importlib.util.spec_from_file_location("_toolchain_persona_names", SYNC)
        if spec is None or spec.loader is None:
            raise ImportError(f"no loader for {SYNC}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        base = frozenset(module.BASE_PERSONA_NAMES)
        judging = frozenset(module.JUDGING_PERSONA_NAMES)
    # BaseException, not Exception, and this is not defensive padding — it is the observed
    # behaviour. `exec_module` runs the target's module body, and a body that calls `sys.exit()`
    # raises SystemExit, which is a BaseException: uncaught, it terminates check_toolchain.py with
    # an empty stdout, so a `--json` caller gets no object at all and the three-state contract is
    # gone. Reproduced against a one-line stub during TC-41. Any failure to obtain the names is the
    # same not-run whatever its base class.
    except BaseException as e:  # noqa: BLE001
        return frozenset(), frozenset(), (f"the persona name sets could not be read from {SYNC} "
                                          f"({type(e).__name__}: {e}), so no plugin agent name was "
                                          f"cross-checked")
    if not base or not judging:
        return frozenset(), frozenset(), (f"{SYNC} exposes an EMPTY persona or judging name set. "
                                          f"An empty set collides with nothing, so cross-checking "
                                          f"against it would report a clear result having compared "
                                          f"against no names at all")
    return base, judging, None


def plugin_roots(base: Path) -> tuple[list[Path], list[str]]:
    """Every directory under `base` holding `.claude-plugin/plugin.json`, plus what could not be read.

    `os.walk(..., onerror=...)` rather than `Path.rglob`, and that is the whole reason this does not
    reuse `tree()`. `rglob` swallows a descent failure — it yields nothing from inside an
    unreadable directory and raises nothing — which is the KNOWN GAP documented on `tree()`. Here
    that gap would be a fail-open in the enumeration itself: a plugins directory this process cannot
    descend into would contribute zero plugins and the surface would read as smaller than it is.
    `onerror` turns the descent failure into a reported problem, which the caller makes a not-run.
    """
    roots: list[Path] = []
    problems: list[str] = []
    if not base.exists():
        return roots, problems
    if not base.is_dir():
        return roots, [f"{base} exists but is not a directory, so no plugin was enumerated"]

    def on_error(e: OSError) -> None:
        problems.append(f"{e.filename or base} could not be walked ({e.strerror or e})")

    for dirpath, dirnames, _ in os.walk(base, onerror=on_error, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in PLUGIN_WALK_PRUNE]
        here = Path(dirpath)
        if (here / PLUGIN_MANIFEST[0] / PLUGIN_MANIFEST[1]).is_file():
            roots.append(here)
    return sorted(roots), problems


def plugin_relative(root: Path, declared: str) -> Path:
    """Resolve a path a manifest declares, without letting it escape the plugin root.

    Manifests write these as `"./hooks/hooks-cursor.json"`, and the harness also expands
    `${CLAUDE_PLUGIN_ROOT}`. Both forms are normalised to a path under `root`, and a declaration
    that resolves outside the plugin is refused rather than followed: this check reads files
    BECAUSE a third party named them, and `"../../../etc/passwd"` is a file the third party would
    then have chosen for us to read. Refusing is the fail-closed direction — the caller turns it
    into a problem, which is a not-run, not a silent skip.
    """
    text = declared.replace("${CLAUDE_PLUGIN_ROOT}", "").replace("$CLAUDE_PLUGIN_ROOT", "")
    return (root / text.lstrip("/")).resolve()


def _events_from(obj, where: str) -> tuple[list[str], str | None]:
    """Event names out of a hooks declaration, whether it nests under `hooks` or is the map itself.

    Both shapes are real and both were observed on this machine: `hooks/hooks.json` files here nest
    under a `"hooks"` key, while a manifest's inline `"hooks": {}` is the map directly.
    """
    events = obj.get("hooks", obj) if isinstance(obj, dict) else obj
    if not isinstance(events, dict):
        return [], (f"{where} declares hooks in a shape this check does not recognise "
                    f"({type(events).__name__}), so which events it binds is unknown")
    return sorted(str(k) for k in events), None


def hook_events(root: Path, manifest_hooks=None) -> tuple[list[str], str | None]:
    """Which lifecycle events a plugin binds. NEVER what the hook does.

    Enumerating THAT a plugin binds `PreToolUse` is a fact this file can assert from a manifest.
    Reading intent out of the third-party script the binding points at is out of scope and would be
    a false assurance — a hook reported as harmless is worse than a hook reported as present. So the
    command strings are read past and only the event names are returned. Nothing here executes.

    TWO SOURCES, UNIONED — NOT a precedence rule, and the difference matters. The convention is
    `<root>/hooks/hooks.json`; the manifest may also declare `"hooks"` itself, as a PATH or as an
    inline MAP. Reading only the first was a fail-open in the loudest tier: a plugin declaring hooks
    by manifest was classified `inert`, emitted no warning, and was counted in the skills-only
    census.

    The first fix said the manifest WINS where both exist. THAT CLAIM HAD NO SOURCE. The evidence
    cited for it was two sibling manifests — `.cursor-plugin/plugin.json` and
    `.codex-plugin/plugin.json` — which THIS CODE NEVER READS; they establish that the declaration
    forms exist in the wild, and nothing about how Claude's own loader resolves a conflict. Neither
    manifest branch is exercised by any real plugin on this machine: superpowers' actual
    `.claude-plugin/plugin.json` carries no `hooks` key at all. And the rule was actively wrong in a
    shape that exists one directory over — `"hooks": {}` beside a populated `hooks/hooks.json`
    yielded NO events, no problem, and tier `inert`.

    So both sources are read and their event names unioned. Where the harness's real precedence is
    unknown, reporting the union is the fail-closed direction: it can over-report an event the
    harness would have ignored, and it cannot miss one the harness binds. Over-reporting a hook is
    recoverable; missing one is the defect this function exists to prevent.
    """
    events: set[str] = set()
    problems: list[str] = []

    if isinstance(manifest_hooks, dict):
        found, why = _events_from(manifest_hooks, f"{root} manifest `hooks`")
        events |= set(found)
        if why:
            problems.append(why)
    elif isinstance(manifest_hooks, str) and manifest_hooks.strip():
        target = plugin_relative(root, manifest_hooks)
        try:
            inside = target.is_relative_to(root.resolve())
        except AttributeError:  # pragma: no cover - Path.is_relative_to is 3.9+
            inside = str(target).startswith(str(root.resolve()))
        if not inside:
            problems.append(f"{root} manifest declares `hooks: {manifest_hooks}`, which resolves "
                            f"OUTSIDE the plugin root to {target}. It was NOT read, so which events "
                            f"this plugin binds is unknown")
        elif not target.is_file():
            problems.append(f"{root} manifest declares `hooks: {manifest_hooks}` but {target} is "
                            f"not a file, so which events this plugin binds is unknown")
        else:
            parsed, why = _read_json(target)
            if parsed is None:
                problems.append(why)
            else:
                found, why = _events_from(parsed, str(target))
                events |= set(found)
                if why:
                    problems.append(why)
    elif manifest_hooks is not None:
        problems.append(f"{root} manifest declares `hooks` as {type(manifest_hooks).__name__}, a "
                        f"shape this check does not recognise, so which events it binds is unknown")

    conventional = root / "hooks" / "hooks.json"
    if conventional.is_file():
        parsed, why = _read_json(conventional)
        if parsed is None:
            problems.append(why)
        else:
            found, why = _events_from(parsed, str(conventional))
            events |= set(found)
            if why:
                problems.append(why)
    return sorted(events), problems


def registered_agent_name(path: Path) -> tuple[str, str | None]:
    """The name the HARNESS will resolve this subagent by. `(name, problem)`.

    NOT the filename stem, and the difference is the card's own defect one field over. A subagent
    file declares `name:` in its YAML frontmatter and that is what the harness registers; the stem
    is merely where it usually agrees. Verified on this machine: all 31 plugin-supplied agent files
    carry `name:` and all 31 happen to match their stem — a CONVENTION, not a guarantee. A plugin
    shipping `agents/helper.md` whose frontmatter says `name: reviewer` registers as `reviewer`,
    and a stem-based check would report `helper`, find no collision, and exit 0.

    Frontmatter only, and only its `name:` line — this is not a YAML parser and does not need to be.

    A file with no frontmatter, or frontmatter with no `name:`, falls back to the stem. THAT IS THIS
    CHECK'S CHOICE IN THE ABSENCE OF A DECLARED NAME, not a documented harness behaviour: whether
    the harness registers such a file by stem or declines to load it at all is NOT established here,
    and there is no access to its subagent loader from this file. An earlier version of this
    sentence called it "the harness's own fallback", which is the same unsourced assertion about
    another system that `hook_events` was rewritten to stop making — stated in the same declarative
    register as the measured claim above it, where a reader could not tell the two apart.

    The direction is the safe one: if the harness in fact declines such files, this OVER-reports and
    could raise a shadow finding for a file that never loads. Over-reporting a shadow is recoverable;
    missing one is what this function exists to prevent.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return path.stem, (f"{path} could not be read ({e.strerror or e}), so the name this "
                           f"subagent registers under is unknown and the stem was used instead")
    if not lines or lines[0].strip() != "---":
        return path.stem, None
    for line in lines[1:60]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            value = line[len("name:"):].strip().strip("\"'").strip()
            if value:
                return value, None
            break
    return path.stem, None


def classify(root: Path) -> tuple[dict, list[str]]:
    """One plugin, described by WHAT IT BRINGS. `(description, problems)`.

    THREE TIERS, and the ordering is by what the plugin can do without being asked:

      `hook`   it binds a lifecycle event, so its code runs every session or every prompt for every
               persona INCLUDING the judging ones, which hold no Bash and no write tools precisely
               so that they cannot make things happen. A hook is underneath that guarantee.
      `agent`  it adds a subagent definition, which either introduces a new name or SHADOWS one of
               ours from a directory no other check looks at.
      `inert`  skills and commands only. Real capability, but nothing happens until someone invokes
               it by name, so it is enumerated and not reported on its own.

    Tiers are assigned by precedence, not accumulated: a plugin that ships hooks AND agents is a
    `hook`, because that is the loudest true thing about it. The `agents`, `skills` and `commands`
    fields are still populated, so nothing is lost to the tier label.

    `agents` holds the names the HARNESS REGISTERS — frontmatter `name:`, falling back to the stem.
    `agent_files` maps each of those back to the file it came from, so a report can name the file
    while the collision check works on the name that actually resolves. See `registered_agent_name`.
    """
    manifest = root / PLUGIN_MANIFEST[0] / PLUGIN_MANIFEST[1]
    parsed, why = _read_json(manifest)
    problems = [why] if why else []
    declared = parsed.get("name") if isinstance(parsed, dict) else None

    events, hook_problems = hook_events(root,
                                        parsed.get("hooks") if isinstance(parsed, dict) else None)
    problems += hook_problems

    # `name -> [file, ...]`, NOT `name -> file`. A dict keyed by registered name silently dropped
    # every file but the last when two files in ONE plugin declared the same `name:` — say
    # `agents/helper.md` with `name: reviewer` beside `agents/reviewer.md`. The loser was named
    # nowhere in the output, `agents` was one short, the "adds N agent(s)" line undercounted, and no
    # duplicate finding fired because the cross-plugin check collects plugin ITEMS, not files. The
    # enumeration was silently short in the one directory this whole check exists because nothing
    # else looks at it.
    agent_files: dict[str, list[str]] = {}
    agent_dir = root / "agents"
    if agent_dir.is_dir():
        try:
            found = sorted(p for p in agent_dir.glob("*.md") if p.is_file())
        except OSError as e:
            found = []
            problems.append(f"{agent_dir} could not be listed ({e.strerror or e}), so whether this "
                            f"plugin ships an agent that shadows a persona is unknown")
        for path in found:
            name, agent_why = registered_agent_name(path)
            if agent_why:
                problems.append(agent_why)
            agent_files.setdefault(name, []).append(path.name)

    agents = sorted(agent_files)
    tier = "hook" if events else "agent" if agents else "inert"
    return {
        "name": str(declared) if declared else root.name,
        "root": str(root),
        "tier": tier,
        "hook_events": events,
        "agents": agents,
        "agent_files": agent_files,
        "skills": (root / "skills").is_dir(),
        "commands": (root / "commands").is_dir(),
    }, problems


def enabled_claude_plugins() -> tuple[dict[str, str | None], list[str]]:
    """`({key: installPath or None}, problems)` for the plugins Claude actually loads.

    ENABLEMENT IS THE DIFFERENCE BETWEEN A CATALOGUE AND A SURFACE, and it is why this is read at
    all rather than treating every manifest on disk as live. `~/.claude/plugins/marketplaces` is a
    downloaded catalogue: on this machine it holds 42 plugin roots of which ONE is enabled. Ranking
    the other 41 as loudly as the enabled one would put eight permanent hook warnings in front of a
    reader at every session start in every directory, and this file's own docstring is about what
    that does to a reader.

    Only ~/.claude/settings.json is consulted. A project's `.claude/settings.json` can also enable a
    plugin; that is deliberately NOT read here, because this check reports a machine-global fact and
    a per-project enablement is not one. It is a real gap and it is stated rather than papered over:
    a plugin enabled only by the current repository is enumerated here as present-not-enabled.
    """
    settings, why = _read_json(CLAUDE_SETTINGS)
    if settings is None:
        return {}, [f"{why}, so which plugins Claude has ENABLED is unknown"]
    raw = settings.get("enabledPlugins") or {}
    if not isinstance(raw, dict):
        return {}, [f"{CLAUDE_SETTINGS} has an `enabledPlugins` that is not an object "
                    f"({type(raw).__name__}), so which plugins Claude has enabled is unknown"]
    keys = sorted(k for k, v in raw.items() if v)
    if not keys:
        return {}, []

    installed, why = _read_json(INSTALLED_PLUGINS)
    if installed is None:
        return {k: None for k in keys}, [f"{why}, so the install path of {len(keys)} enabled "
                                         f"plugin(s) is unknown and what they bring was not read"]
    records = installed.get("plugins") or {}
    out: dict[str, str | None] = {}
    problems: list[str] = []
    for key in keys:
        entries = records.get(key) if isinstance(records, dict) else None
        paths = [e.get("installPath") for e in entries or [] if isinstance(e, dict)]
        paths = [p for p in paths if p and Path(p).is_dir()]
        out[key] = paths[-1] if paths else None
        if not paths:
            problems.append(f"plugin `{key}` is ENABLED in {CLAUDE_SETTINGS} but its install path "
                            f"could not be resolved from {INSTALLED_PLUGINS}, so what it brings — "
                            f"hooks, agents or neither — was NOT determined")
    return out, problems


def codex_plugin_keys() -> tuple[list[str], list[str]]:
    """`(keys, problems)` from ~/.codex/config.toml `[plugins."name@marketplace"]` sections.

    A LINE SCAN, NOT A TOML PARSE, and the narrowing is deliberate twice over. `tomllib` arrived in
    Python 3.11 and this file is run by whatever `python3` the session hook resolves — 3.9.6 at
    /usr/bin/python3 on this machine — so a `tomllib` import would make the check crash on the
    interpreter most likely to run it. And the question asked is narrow enough not to need a parser:
    which `[plugins."..."]` sections exist and is `enabled` true in each. Nothing here interprets a
    value type, an array, or a multi-line string.

    THE FAILURE DIRECTION IS BOTH WAYS. An early version of this docstring said it could only
    over-report; that was wrong, and the file it reads is hand-edited and already carries `#`
    markers, so the under-reporting cases were live.

    WHAT IS HANDLED — three detectors, and this list is the contract:

      READ, and a plugin is enumerated from it:
        `[plugins."x@mp"]` … `enabled = true`, with a trailing `#` comment on either line.
      DETECTED as unparseable, raising a problem rather than dropping a plugin:
        `is_plugins_table`    — a `[plugins]` or `[plugins.…]` header whose members this scanner
                                does not read. Parses the header interior, so `[plugins_cache]`
                                is correctly NOT treated as a plugin section; prefix-matching it
                                produced a permanent exit 2 no action could clear.
        `assigns_plugins_key` — any statement whose first key segment is `plugins`, which covers
                                `plugins = { … }` (header-less inline table), `plugins."x".enabled`
                                and `"plugins"."x".enabled`. Segment equality rather than a prefix,
                                so `plugins_cache = 30` is not caught.

    ANYTHING ELSE IS BEST-EFFORT, and this paragraph does not claim to enumerate it. Two known
    examples, in both directions: a `[plugins."x"]` header inside a multi-line string literal is
    counted as a section (over-reports), and a `plugins.foo = 1` line inside a `\"\"\"…\"\"\"` block
    raises a problem for text that is not configuration (over-reports, and unclearable until the
    file changes). Neither exists in a Codex config today. A form not listed above may be read
    wrongly in either direction; the detectors are a floor, not a parser.
    """
    if not CODEX_CONFIG.is_file():
        return [], [f"{CODEX_CONFIG} is absent, so no Codex plugin was enumerated and the Codex "
                    f"plugin surface is unknown rather than empty"]
    try:
        text = CODEX_CONFIG.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as e:
        return [], [f"{CODEX_CONFIG} could not be read ({e}), so no Codex plugin was enumerated"]
    keys: list[str] = []
    problems: list[str] = []
    current: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if line.startswith("["):
            # Everything after the closing `"]` is a trailing comment or trailing whitespace. Taking
            # the header up to that bracket is what makes `[plugins."x@mp"]  # note` readable.
            current = None
            end = line.find('"]')
            if line.startswith('[plugins."') and end > 0:
                current = line[len('[plugins."'):end]
            elif is_plugins_table(line):
                # `[plugins]` on its own, whose members are inline `"x@mp" = { enabled = true }`
                # entries this scanner does not read. NOT `startswith("[plugins")`, which also
                # matched `[plugins_cache]` — an unrelated table that would have produced a
                # permanent, unclearable exit 2 that no action could resolve.
                problems.append(f"{CODEX_CONFIG}:{number} is a `plugins` section in a form this "
                                f"scanner does not parse ({line[:60]!r}), so the Codex plugin list "
                                f"may be incomplete and cannot be trusted")
            continue
        # A bare `key = value` line. Strip a trailing comment.
        #
        # NOT "every value this scanner reads is a bare boolean, so there is no quoted `#` to
        # protect" — that was the previous sentence and it is not true of this code, which splits
        # EVERY non-header line, including ones whose values it never reads. A `#` inside a quoted
        # string on such a line is truncated here. The consequence is nil today: the truncated
        # remainder only ever reaches the two `startswith` probes below, and a key segment cannot
        # contain an unquoted `#`. Recorded because the old sentence licensed an assumption a later
        # edit would have relied on.
        statement = line.split("#", 1)[0].strip()
        if not statement:
            continue
        squashed = statement.replace(" ", "")
        if current and squashed.startswith("enabled="):
            if statement.split("=", 1)[1].strip().lower() == "true":
                keys.append(current)
            current = None
        elif assigns_plugins_key(statement):
            problems.append(f"{CODEX_CONFIG}:{number} declares plugins with a key this scanner "
                            f"does not parse ({statement[:60]!r}), so the Codex plugin list may be "
                            f"incomplete and cannot be trusted")
    return sorted(keys), problems


def assigns_plugins_key(statement: str) -> bool:
    """Does this `key = value` line assign to the `plugins` table by any key form?

    Compares the FIRST key segment rather than matching prefixes, which is what closes the gap the
    mislabelled test was hiding. The three forms, all of which silently dropped a plugin before:

        plugins = { "x@mp" = { enabled = true } }     top-level inline table
        plugins."x@mp".enabled = true                 dotted key
        "plugins"."x@mp".enabled = true               quoted dotted key

    A prefix match would also have caught `plugins_cache = 30`, which is the `[plugins_cache]`
    mistake in the other syntactic position; segment equality does not.
    """
    key = statement.split("=", 1)[0].strip()
    head = key.split(".", 1)[0].strip().strip('"').strip("'").strip()
    return head == "plugins"


def is_plugins_table(line: str) -> bool:
    """Is this header the `plugins` table itself, rather than a table whose name merely starts so?

    `[plugins]`, `[plugins.x]` and `["plugins"...]` are the plugin table; `[plugins_cache]` and
    `[plugins-old]` are unrelated tables that happen to share a prefix, and treating them as
    unparseable plugin sections produced a permanent exit 2 with no action that could clear it.
    """
    inside = line[1:].split("]", 1)[0].strip()
    if inside.startswith('"plugins"'):
        return True
    return inside == "plugins" or inside.startswith("plugins.")


# What the Codex harness's manifest cannot say, stated ONCE and reported rather than worked around.
# `[plugins."name@marketplace"] enabled = true` carries a name and a boolean and nothing else: there
# is no key for hooks, none for agents, and none for skills. `~/.codex/plugins/cache` does hold
# plugin bodies, but in a layout with no `.claude-plugin/plugin.json` and no documented contract this
# file can read, so classifying from it would mean inferring semantics from directory names — which
# is exactly the invention TC-41 forbids. The asymmetry is therefore REPORTED as scope that was
# deliberately not covered, and the Codex enumeration carries `"classified": false` so a consumer
# cannot mistake an unclassified list for a list of inert plugins.
CODEX_ASYMMETRY = ("~/.codex/config.toml expresses only `[plugins.\"name@marketplace\"] enabled`, "
                   "with no key for hooks, agents or skills, so Codex plugins are enumerated by "
                   "NAME ONLY. Whether a Codex plugin ships an agent that shadows a persona is "
                   "UNKNOWN, not known to be false.")

# ------------------------------------------------------------------------------------------------
# TC-47. Authored content that git would not commit, and nothing noticed.
#
# THREE MEASURED INSTANCES IN ONE MILESTONE, all the same mechanism and all found by a person rather
# than a gate: `docs/decisions.md` untracked while the renderer READ it at startup — an untracked
# record is a broken install, not a documentation gap; `docs/fleet-lessons.md` invisible to git for
# two DAYS while `git status` reported clean; and an entire new skill directory for which
# `git status --porcelain` returned NOTHING, so a commit would have silently dropped it. Each was
# fixed by a human adding one line to an allow-list. The remedy is right and the discovery mechanism
# is not: nothing ever asked.
#
# THE QUESTION IS `git add --dry-run`, NOT `git check-ignore`, AND THAT DISTINCTION IS THE WHOLE
# CHECK. `check-ignore` exits 0 both when a path is excluded AND when a NEGATION matched it, and only
# the second is the wanted answer. Verified here on git 2.50.1 against `/*` + `!/kept`:
#
#     git check-ignore -v -- kept          -> exit 0, prints `.gitignore:2:!/kept  kept`
#     git check-ignore -v -- ignored       -> exit 0, prints `.gitignore:1:/*      ignored`
#
# Two opposite states, one exit code. `skills/.gitignore` is an ALLOW-LIST — `/*` then a negation per
# owned skill — so under that shape EVERY published skill is a negation match and a check built on
# check-ignore's exit code cannot tell the published ones from the dropped one. It would report the
# same answer for the whole directory on exactly the state it exists to catch. The programme's ledger
# already records that trap being hit once; this is it not being inherited in a new form.
#
# `git add --dry-run` answers the question that was actually asked — WOULD THIS BE COMMITTED — and
# separates the two states by exit code: 0 for the negated path, 1 for the excluded one.
#
# IT DOES NOT STAGE, re-derived rather than taken on trust, because a check that mutated the index at
# every session start would be far worse than the gap it closes. On the case that carries the risk —
# an untracked, NON-ignored path, where the add path really runs and really printed `add
# 'newskill/SKILL.md'` — `git ls-files -s`, the raw bytes of `.git/index`, and `git status
# --porcelain` were all byte-identical before and after. Proving the guarded operation was ATTEMPTED
# is half of that: a probe on an ignored path leaves the index alone for the uninteresting reason
# that it did nothing at all, and "no mutation" measured there would be a control broken in the
# exonerating direction.
#
# THERE IS NO SECOND BELT, and an earlier version of this comment claimed there was. It set
# `GIT_OPTIONAL_LOCKS=0` and told the reader the no-mutation property therefore did not rest solely
# on `--dry-run`. MEASURED, and the claim was false: that variable suppresses only lock-taking git
# considers OPTIONAL, and `git add`'s index lock is not. With `.git/index.lock` already held,
# `git add --dry-run` fails identically with and without it —
#
#     touch .git/index.lock
#     GIT_OPTIONAL_LOCKS=0 git add --dry-run -- agents   -> exit 128, "Unable to create index.lock"
#                          git add --dry-run -- agents   -> exit 128, "Unable to create index.lock"
#
# — and polling the work tree during forty probes observes `.git/index.lock` being created. So the
# variable was inert here and has been REMOVED rather than left in place with a corrected comment:
# an inert setting whose comment claims a safety property is worse than no setting, because it
# answers the question a reader would otherwise go and measure.
#
# The no-mutation property therefore rests SOLELY on `--dry-run`, which is exactly what stop
# condition 1 asked to be verified. It is verified twice — by the measurement above, and now by
# `test_a_tracking_run_does_not_touch_the_index`, which hashes `.git/index` and `git ls-files -s`
# across a real run on a home carrying an untracked NON-ignored skill, so the add path runs.
#
# THE SECOND CONSEQUENCE IS OPERATIONAL AND IT IS WHY `git_probe` RETRIES. Taking the lock means one
# probe per skill directory contends with any other git process in the same repository — and
# `~/.claude` is a repository several agent sessions write to at once.
#
# MEASURED, WITH ITS TREE NAMED, because the first version of this comment said "six on a completely
# healthy machine" and six was the six-skill TEST FIXTURE, not this machine, which has eight skill
# directories. Two measured numbers in one file disagreeing is a provenance defect whatever the
# conclusion. Re-run on a faithful eight-directory replica of ~/.claude carrying BOTH .gitignore
# files — not on the live repository, deliberately: creating `.git/index.lock` there would inflict
# on concurrent sessions exactly the failure being measured.
#
#   held lock, retries disabled  -> 8 unknown, 8 not-run findings   (the original defect, at 8)
#   held lock, retries on, never clears -> 8 unknown, 8 not-run     (correctly still not-run)
#   transient lock ~60ms, retries on    -> 0 findings, all resolved (the flake, removed)
#
# A session-start gate that flakes to "cannot be trusted" because another session held a lock for
# three milliseconds teaches the reader to ignore exit 2, which is the same cry-wolf failure the
# severity ruling in `check_tracking` exists to avoid.
GIT_ENV = {
    # git's ignored-path message is prose, and the classification below reads it to tell "excluded"
    # apart from any other reason `add` could fail. Pin the language so a localised machine does not
    # silently reclassify — and note the failure direction if git ever rewords it: the marker stops
    # matching, the path resolves to `unknown`, and `unknown` is a not-run. Fail-closed.
    "LC_ALL": "C",
}

# What `git` says when another process holds the index lock, and how many times to wait it out.
# Bounded and short: this is contention with a sibling process that is about to finish, not a
# recovery mechanism. When the retries are exhausted the answer is still UNKNOWN — the three-state
# contract is not weakened, only stopped from firing on a transient.
GIT_LOCK_MARKER = "unable to create"
GIT_LOCK_RETRIES = 3
GIT_LOCK_BACKOFF = 0.05

# The sentence `git add` prints when it refuses an excluded path, under LC_ALL=C.
GIT_IGNORED_MARKER = "ignored by one of your"

# The three answers a probe may return. `unknown` is not a third kind of "fine" — it is the
# unanswerable question, and it becomes a not-run finding, for the same reason `Run.verdict` ranks
# not-run above every severity.
TRACKABLE, IGNORED, UNKNOWN = "trackable", "ignored", "unknown"

# THE DECLARED-VENDOR LIST. Short, in code, and quoted into the output so an exclusion is visible
# rather than tacit.
#
# WHY IT IS IN CODE, and WHAT THE RULE IT IS EXEMPTED FROM ACTUALLY SAYS — stated precisely,
# because an earlier version of this comment overstated it and thereby overstated the cost of the
# exemption. `test_no_skill_is_special_cased_by_name` does NOT forbid "any skill name": it matches
# ONE literal, `"graphify" in n.value.lower()`. Proof inside this same file — `MIRRORED_SKILLS`
# holds six skill names as module-level constants and has always passed it. So the exemption below
# widens a one-name rule by one assignment, which is a smaller trade than "a rule against naming
# skills" implies.
#
# The rule so scoped protects `check_vendored`, whose exclusions are READ from the repository's own
# `install/skills/.gitignore`, so deleting a line there restores the finding. There is no equivalent
# declaration to read here. `~/.claude/skills/.gitignore` is an allow-list of what this repository
# OWNS; a vendor skill is not in it, and being absent from an allow-list is precisely the state
# under test — it carries no statement that the absence was deliberate. Reading it as one would make
# every dropped skill self-exonerating.
#
# So the exemption is deliberate and it is paid for: the list may hold at most two entries, every
# entry must carry an argument a reader can weigh, and emptying it must restore the finding. All
# three are asserted by `TrackedContentTest`, which is what keeps this from being an allow-list
# growing in the dark.
DECLARED_VENDOR_SKILLS: dict[str, str] = {
    "graphify": "third-party; it installs itself into both harnesses via `uv tool` and updates on "
                "its own schedule. TC-04 ruled the vendor is the recovery path, so a pinned stale "
                "copy tracked here would be worse than none.",
}

# STOP CONDITION 4, answered rather than worked around: `~/.codex/skills` CANNOT be asked this
# question the same way, and a sweep that pretended otherwise would be permanently and unfixably red.
#
# Measured: `~/.codex` IS a work tree, and all seven skill directories in it come back ignored,
# because `~/.codex/.gitignore` excludes `skills/` wholesale and says why — the tree is RENDERED from
# ~/.claude by install_hooks.py, and backing up a derived copy costs space and creates a second
# source of truth. Treated as authored content it would produce seven findings with no remedy, on
# every machine, at every session start; that is the cry-wolf pathology this milestone exists to
# remove, and a finding the reader learns to skip is worse than the gap.
#
# The compensating control is real but NARROWER THAN IT FIRST APPEARS, and the earlier version of
# this comment overclaimed it. `check_skills` fires `critical` when a mirrored skill is missing from
# ~/.codex/skills — but it iterates MIRRORED_SKILLS, which is SIX names, so it covers exactly those
# six. `project-conformance` is not among them, which means the skill from measured incident 3 is
# gated by this sweep on the Claude side and by NOTHING on the Codex side. That is a real edge and
# it is stated rather than smoothed over.
#
# What the exclusion does rest on is that nothing AUTHORED lives in ~/.codex/skills: the tree is
# generated, so the recovery path is regeneration rather than restoration from a commit. Same shape
# as the TC-04 ruling on vendor content. That argument holds for all seven directories there
# regardless of how many of them `check_skills` happens to compare.
#
# DECLARED is the operative word. The Codex side is reported as scope deliberately not covered, never
# silently dropped, and `tracking.codex.asked` is false so a consumer cannot read an unasked question
# as a satisfied one.
CODEX_TRACKING_ASYMMETRY = (
    "~/.codex/skills is a DERIVED mirror rendered from ~/.claude by install_hooks.py, and "
    "~/.codex/.gitignore excludes it wholesale so as not to create a second source of truth. Asked "
    "the same question every one of its skill directories answers `ignored`, which is a policy "
    "rather than drift. Its currency is gated instead by the Codex skill mirror check, which fires "
    "critical when a mirrored skill is missing there. Whether the Codex tree would be committed is "
    "therefore NOT ASKED, not known to be fine.")

# Module-level DATA for the same reason `PLUGIN_EXCLUSIONS` is — see the note there. Short, because
# `Run.summary` renders every exclusion inline on every line this tool prints.
TRACKING_EXCLUSIONS = [("Codex skill tracking",
                        "derived mirror, not authored; see tracking.codex in --json")]

# ------------------------------------------------------------------------------------------------
# TC-47, sweep two. Same class one floor over: authored work that no gate can see.
#
# A LIVE NEAR-MISS, not a hypothetical. Card TC-40 skipped its review stage entirely, was verified,
# and moved toward a commit; the first review it ever received returned two CRITICALs, one of them a
# `--fix` that deleted machine-global agent files while printing "nothing changed". At that moment
# the workspace held, per card: TC-35 2 review artifacts, TC-36 2, TC-37 2, TC-39 5, TC-41 3,
# TC-42 2, TC-45 2 — and TC-40 zero. Seventeen artifacts across eight cards looks healthy in
# aggregate and the zero is obvious the instant it is counted PER CARD. So the question this asks is
# not "is a review file missing" but "did anything act on a paraphrase", once per card.
#
# REPOSITORY-SCOPED, like `--vendored` and unlike everything above it: the subject is one named
# directory on the command line, never the machine, and it never runs implicitly at session start.
CARD_PATTERN = "TC-*.yaml"
REPORTS_DIRNAME = "reports"

# What an artifact's name after `TC-<id>-` must contain to count. Two markers, not one: a
# security-validator's verdict is an independent judging artifact by a persona that holds no write
# tool, and refusing to count it would report a card as unreviewed because of who reviewed it.
#
# NOTE FOR ANYONE RECONCILING THIS WITH THE COUNTS ABOVE: those were taken with `review` alone, so
# `--reviews` reports TC-39 as 6 rather than 5, and TC-34 and TC-38 as reviewed on the strength of a
# `-security.md`. Two of the eight measured counts have moved on their own since (TC-40 acquired the
# review that found the criticals; TC-41 a fourth round), which is why no count is pinned anywhere.
REVIEW_MARKERS = ("review", "security")
REPORT_MARKER = "report"

# Module-level DATA, exactly like `MIRRORED`, and for a reason worth stating: an `excluded` entry is
# a `(name, why)` pair with the same shape as a `(severity, detail)` finding, so built inline it
# would be indistinguishable from an emission to the AST rule in
# `test_every_severity_emitted_is_ranked` — which would then report "Codex plugin classification" as
# an unranked severity. Hoisting it here is what that test's module-data subtraction is for.
#
# SHORT, and that is a fix rather than a style choice. `Run.summary` renders every exclusion inline
# as `name (why)`, so the full 250-character asymmetry paragraph rode on EVERY summary line this
# tool printed — including the clean one, at every session start in every directory, with no action
# that could ever clear it. The reason a reader may need is one clause; the paragraph stays in
# `--json` under `plugins.codex.why_not_classified`, where a consumer reads it deliberately.
PLUGIN_EXCLUSIONS = [("Codex plugin classification",
                      "config.toml carries names only; see plugins.codex in --json")]


def plugin_surface() -> tuple[dict, list[str], list[str]]:
    """Enumerate and classify both harnesses. `(surface, claude_problems, codex_problems)`.

    One code path per harness because the data differs, and where it differs the surface says so in
    a field rather than emitting a silently thinner Codex result — see CODEX_ASYMMETRY.

    THE TWO PROBLEM LISTS ARE SEPARATE AND THAT IS THE POINT. They were one list, and one list means
    one blast radius: the absence of `~/.codex/config.toml` — an ordinary state on a Claude-only
    machine — made `plugins.claude.enumerated` false and suppressed every Claude-side conclusion,
    including a critical shadow finding about an enabled plugin. A failure in one harness must not
    be able to silence an observation made in the other. A caller that wants the old behaviour can
    concatenate them; a caller that wants the truth per harness now can have it.
    """
    problems: list[str] = []
    enabled, enabled_problems = enabled_claude_plugins()
    problems += enabled_problems
    enabled_roots = {str(Path(p).resolve()) for p in enabled.values() if p}

    # THE THIRD VALUE, and the whole of H-1 in three lines. `enabled_claude_plugins` returns None as
    # the path for a key that settings.json says IS enabled but whose install root could not be
    # located — a malformed installed_plugins.json, or an installPath that no longer exists after an
    # uninstall/reinstall. With a two-valued flag every plugin on disk then read `enabled: False`,
    # which is not "not enabled": it is "I could not tell". A rogue shipping `agents/reviewer.md`
    # came out as a `warn` saying "Not enabled today" about a plugin whose enablement had been read
    # successfully from settings.json one function earlier, and `enabled_keys` contradicted
    # `enabled_count` in the same object.
    #
    # Which root each unresolved key refers to is exactly what could not be determined, so the
    # uncertainty is not attributable to one plugin: any root that is not POSITIVELY matched to a
    # resolved enabled key becomes `unknown` rather than `not-enabled`. Fail-closed, and it collapses
    # back to the old answer the moment every enabled key resolves.
    # `or enabled_problems`, and leaving it off was the same conflation one function further OUT.
    # Two of `enabled_claude_plugins`'s four exits — settings.json unreadable, and `enabledPlugins`
    # present but not an object — return an EMPTY dict beside a problem. `unresolved` is then `[]`,
    # so a run that could not read which plugins are enabled AT ALL took the `not-enabled` branch
    # and reported every plugin on disk as determined-not-enabled. Enablement was made three-valued
    # at the source and then consumed two-valued here. ANY problem from that function means the
    # enablement picture is incomplete, whether or not it produced a key to point at.
    unresolved = sorted(k for k, p in enabled.items() if not p)
    unmatched = "unknown" if unresolved or enabled_problems else "not-enabled"

    roots, walk_problems = plugin_roots(CLAUDE_PLUGINS)
    problems += walk_problems

    items: list[dict] = []
    for root in roots:
        described, root_problems = classify(root)
        problems += root_problems
        matched = str(root.resolve()) in enabled_roots
        described["enablement"] = "enabled" if matched else unmatched
        described["key"] = next((k for k, p in enabled.items()
                                 if p and Path(p).resolve() == root.resolve()), None)
        items.append(described)

    # An enabled plugin whose root is not under ~/.claude/plugins is still part of the surface, and
    # `enabled_claude_plugins` already reported the unresolvable ones. This catches the resolvable
    # ones the walk did not reach — a plugin installed from a path outside the plugins directory.
    seen = {str(Path(i["root"]).resolve()) for i in items}
    for key, path in sorted(enabled.items()):
        if path and str(Path(path).resolve()) not in seen:
            described, root_problems = classify(Path(path))
            problems += root_problems
            described["enablement"] = "enabled"
            described["key"] = key
            items.append(described)

    codex_keys, codex_problems = codex_plugin_keys()

    tiers = {t: sum(1 for i in items if i["tier"] == t) for t in ("hook", "agent", "inert")}
    enablement = {state: sum(1 for i in items if i["enablement"] == state)
                  for state in ("enabled", "not-enabled", "unknown")}
    return {
        "claude": {
            # False whenever any part of the CLAUDE enumeration failed — and only then. A consumer
            # that reads only this field can never mistake a truncated list for a short one, which
            # is the empty-versus-failed distinction expressed in the data. It used to be false when
            # the CODEX config was merely absent, which told `project-conformance` that 42 perfectly
            # enumerated Claude plugins could not be trusted.
            "enumerated": not problems,
            "classified": True,
            "root": str(CLAUDE_PLUGINS),
            "count": len(items),
            "enablement": enablement,
            "enabled_count": enablement["enabled"],
            "enabled_keys": sorted(enabled),
            # The keys settings.json enables and this run could NOT locate. Present so that
            # `enabled_keys` non-empty beside `enabled_count: 0` is explained by the data rather
            # than reading as a self-contradiction.
            "unresolved_enabled_keys": unresolved,
            "tiers": tiers,
            "items": sorted(items, key=lambda i: (i["enablement"] != "enabled", i["name"],
                                                  i["root"])),
        },
        "codex": {
            "enumerated": not codex_problems,
            "classified": False,
            "why_not_classified": CODEX_ASYMMETRY,
            "config": str(CODEX_CONFIG),
            "count": len(codex_keys),
            "enabled_keys": codex_keys,
        },
    }, problems, codex_problems


# The three states an item's `enablement` may hold, ordered MOST ALARMING FIRST. `unknown` outranks
# `not-enabled` for the same reason `not-run` outranks `clean` in `Run.verdict`: a thing you could
# not determine is worse news than a thing you determined to be absent, and collapsing the two is
# the two-valued-flag defect this ordering exists to prevent recurring.
ENABLEMENT_ORDER = ("enabled", "unknown", "not-enabled")


def worst_enablement(owners: list[dict]) -> str:
    """The most alarming enablement state among the plugins shipping one agent name.

    One place, so a caller cannot accidentally write `any(o["enablement"] == "enabled" ...)` and
    silently treat `unknown` as `not-enabled` — which is precisely the bug, one boolean over.
    """
    states = {o["enablement"] for o in owners}
    return next(state for state in ENABLEMENT_ORDER if state in states)


def from_file(item: dict, agent: str) -> str:
    """` (agents/x.md)` when the files disagree with the name they register, else empty.

    Naming the file unconditionally made the ordinary duplicate finding — two plugins shipping
    `code-reviewer.md` as `code-reviewer` — three lines of repeated path for no information. The
    disagreement is the only case where the filename tells the reader something the name does not,
    and it is exactly the M3 case, so it is the only case that prints it.

    ALL the files, not the first: a plugin registering one name from two files is the L-5 case, and
    printing one of them is how that case stayed invisible.
    """
    filenames = item["agent_files"].get(agent, [])
    if filenames == [f"{agent}.md"]:
        return ""
    return " (" + ", ".join(f"agents/{f}" for f in filenames) + ")"


def check_plugins() -> tuple[dict, list[tuple[str, str]], list[tuple[str, str]]]:
    """`(surface, findings, excluded)`. ENUMERATES AND CLASSIFIES; NEVER APPROVES.

    THERE IS NO CONFORMING SET OF PLUGINS and this function must never grow one. No name is
    allow-listed, no name is deny-listed, and no plugin is called acceptable or unacceptable
    anywhere below. What a plugin is permitted to be is the operator's decision; what it BRINGS is
    a fact, and facts are all this reports. A check that decided would be wrong on the first new
    plugin and would train its reader to skip the whole report.

    THE SEVERITY TABLE, and every row of it turns on whether the plugin is ENABLED, because only an
    enabled plugin executes:

      critical  an ENABLED plugin ships `agents/<name>.md` matching a base persona. It is live, it
                shadows from a directory `sync_personas.py --check` does not look at, and if the
                name is on the judging roster the no-edit guarantee is void without any file the
                roster governs having changed.
      warn      a plugin that is PRESENT BUT NOT ENABLED ships such a name. One `/plugin install`
                from being the row above, with precedence undefined by anything this toolchain owns.
      warn      an ENABLED plugin binds a lifecycle hook. The loud tier: its code runs for every
                persona, including the judges that hold no Bash and no write tool.
      warn      one agent name shipped by two or more plugins where at least one is enabled.
      info      one agent name shipped by two or more plugins, none enabled. TRUE ON THIS MACHINE
                TODAY: `code-reviewer` (feature-dev, pr-review-toolkit) and `code-simplifier`
                (code-simplifier, pr-review-toolkit), both inside the first-party catalogue. The
                first-party catalogue already collides with itself.
      info      an ENABLED plugin ships agents. Presence only — see below on why this line no
                longer claims that none of them collides.
      (none)    everything else. Enumerated in `--json` and counted in the report's plugin line;
                not a finding, which is what the `inert` tier's "report quietly" means here.

    A NOT-RUN NO LONGER SILENCES WHAT WAS ACTUALLY SEEN, and getting that wrong re-opened the exact
    blind spot this card was written to close. Every problem is still a `not-run` and still forces
    exit 2 — but an early return on the first one suppressed the findings below it under a comment
    claiming they were all absence claims over a short list. Three of the four are PRESENCE claims:
    "X SHADOWS a judging persona", "X is shipped by two plugins", "X binds N hook events". A
    presence claim stays true when the list is short. The demonstrated sequence needed no adversary:
    on a machine with no `~/.codex/config.toml`, an enabled plugin shipping `agents/reviewer.md`
    produced exit 2, one finding about the CODEX surface, and no mention of `reviewer` anywhere.

    So the rule is now per-claim rather than per-run:

      * a PRESENCE claim is emitted whenever the observation behind it was made, with the not-run
        alongside it saying the list may be short;
      * an ABSENCE claim is emitted only when nothing could have hidden its subject. FOUR were
        found, not one — the first pass of this docstring claimed "exactly one left", which is the
        kind of confident completeness sentence that stops the next reader checking, and three more
        were sitting directly under it. All four rode on a two-valued enablement flag that meant
        "no" and "could not tell" with the same False:

          - "would SHADOW ... Not enabled today" — said of a plugin whose enablement was UNREAD;
          - "None is enabled" on the duplicate line — same;
          - the hook and agent lines, gated on `enabled` being true, so a plugin of undetermined
            enablement produced NO line at all: absence by omission, in the loudest tier;
          - the clean phrase, which `Run.add` already withholds on a not-run.

        The first three are fixed at the source rather than per-sentence: `enablement` is now
        three-valued (`enabled` / `not-enabled` / `unknown`) and `unknown` is treated as live. See
        `plugin_surface` and `worst_enablement`. "At the source" needed one further step to become
        true: the three-valued FIELD was correct while the expression deriving it read only the
        unresolved-key list, so the two `enabled_claude_plugins` exits that return an empty dict
        beside a problem still produced `not-enabled`. That is `plugin_surface:1235-1243`.

      * COMPLETENESS IS NOT CLAIMED HERE. This lists the absence claims that were found and fixed;
        it does not assert that no fifth exists. The mechanical guard is the three-valued field —
        an absence claim can no longer be written from a boolean that conflates the two — not a
        promise in this paragraph.
      * the base-persona cross-check needs the persona names, so when THEY are unavailable the
        shadow branch does not run at all. Duplicate detection does not need them and still does.
    """
    surface, claude_problems, codex_problems = plugin_surface()
    base, judging, why = persona_names()
    names_ok = why is None

    excluded = list(PLUGIN_EXCLUSIONS)
    findings = [(NOT_RUN, f"the plugin surface was NOT FULLY ENUMERATED: {p}. {MACHINE_GLOBAL}")
                for p in claude_problems + codex_problems + ([why] if why else [])]

    items = surface["claude"]["items"]
    shipped: dict[str, list[dict]] = {}
    for item in items:
        for agent in item["agents"]:
            shipped.setdefault(agent, []).append(item)

    # The invariant is "base name OR judging roster member", not "base name". They are nested today
    # — every judge is a base persona — but that is a property of the pool, not a rule this file may
    # assume: a judging name that is not in the pool is a roster the pool has drifted from, and it
    # is the LAST name that should stop being protected here. The union costs nothing and does not
    # depend on the nesting holding.
    protected = base | judging

    for agent in sorted(shipped):
        owners = shipped[agent]
        # FILES, not owners. `len(owners) > 1` misses an INTRA-plugin collision entirely: one plugin
        # shipping two files that both register `code-reviewer` has one owner and undefined
        # precedence just the same, and the harness has no more idea which wins than it does across
        # two plugins. Counting sources makes the two cases one case.
        sources = sum(len(o["agent_files"].get(agent, [])) for o in owners)
        state = worst_enablement(owners)
        where = ", ".join(f"`{o['name']}`{from_file(o, agent)}" for o in owners)
        if names_ok and agent in protected:
            role = "a JUDGING persona" if agent in judging else "a base persona"
            where = ", ".join(
                f"`{o['name']}` ("
                + ", ".join(f"agents/{f}" for f in o["agent_files"].get(agent, []))
                + f" in {o['root']})" for o in owners)
            if state == "enabled":
                findings.append(("critical",
                                 f"plugin-supplied agent `{agent}` SHADOWS {role}. Shipped by an "
                                 f"ENABLED plugin: {where}. Neither the roster, nor the judging "
                                 f"allow-list, nor `sync_personas.py --check` compares a plugin's "
                                 f"agents directory, so this persona can be replaced without any "
                                 f"file those checks govern having changed. {MACHINE_GLOBAL}"))
            elif state == "unknown":
                # CRITICAL, not warn, and the presence half only. `not-enabled` would be an absence
                # claim this run cannot make, and `warn` would tell a consumer filtering on severity
                # that a possibly-live shadow of a judging persona is non-gating.
                findings.append(("critical",
                                 f"plugin-supplied agent `{agent}` SHADOWS {role}. Shipped by: "
                                 f"{where}. Whether that plugin is ENABLED could NOT be determined "
                                 f"(see the not-run finding), so this must be read as live: nothing "
                                 f"compares a plugin's agents directory, and the persona may "
                                 f"already be replaced. {MACHINE_GLOBAL}"))
            else:
                findings.append(("warn",
                                 f"plugin-supplied agent `{agent}` would SHADOW {role} if its "
                                 f"plugin were enabled. Shipped by: {where}. Not enabled today, and "
                                 f"nothing compares a plugin's agents directory, so enabling it "
                                 f"would replace the persona silently. {MACHINE_GLOBAL}"))
        elif sources > 1:
            said = {"enabled": "At least one is ENABLED. ",
                    "unknown": "Whether any is enabled could NOT be determined. ",
                    "not-enabled": "None is enabled. "}[state]
            scope = (f"{sources} file(s) in {len(owners)} plugins" if len(owners) > 1
                     else f"{sources} file(s) in ONE plugin")
            findings.append(("info" if state == "not-enabled" else "warn",
                             f"agent name `{agent}` is registered by {scope} ({where}) "
                             f"— precedence between them is undefined by anything this toolchain "
                             f"owns. {said}{MACHINE_GLOBAL}"))

    for item in items:
        # `unknown` is included, and that is the third absence-by-omission this round removes: a
        # plugin whose enablement could not be determined used to produce NO line at all, so the
        # loudest tier went silent about a hook that may well be executing.
        if item["enablement"] == "not-enabled":
            continue
        said = ("ENABLED plugin" if item["enablement"] == "enabled"
                else "plugin (ENABLEMENT UNDETERMINED — see the not-run finding)")
        if item["hook_events"]:
            findings.append(("warn",
                             f"{said} `{item['name']}` binds "
                             f"{len(item['hook_events'])} lifecycle hook event(s): "
                             f"{', '.join(item['hook_events'])}. Its code runs for EVERY persona, "
                             f"including the judging personas that hold no Bash and no write tool. "
                             f"What that code does is out of scope here and was not read. "
                             f"{MACHINE_GLOBAL}"))
        elif item["agents"]:
            # PRESENCE ONLY. This used to end "None collides with a base persona name", which is an
            # absence claim riding on a line whose job is to say what is there — and it was emitted
            # from the same list a not-run may have truncated.
            registered = ", ".join(f"{n}{from_file(item, n)}" for n in item["agents"])
            findings.append(("info",
                             f"{said} `{item['name']}` adds "
                             f"{len(item['agents'])} agent(s), registering as: {registered}. "
                             f"{MACHINE_GLOBAL}"))
    return surface, findings, excluded


def git_probe(root: Path, rel: str) -> tuple[str, str]:
    """Would git commit `rel`, a path relative to `root`? Returns `(state, detail)`.

    `state` is TRACKABLE, IGNORED or UNKNOWN. It is never inferred: 0 and a recognised refusal are
    the only two answers this function will turn into a verdict, and everything else — a git that
    would not start, an exit code nobody has seen, a refusal whose reason is not exclusion — is
    UNKNOWN with the reason attached. The alternative, folding an unrecognised failure into "not
    ignored", is the exonerating-direction control break: nobody asks for evidence behind good news.

    IGNORE RULES GOVERN UNTRACKED PATHS ONLY, so a path ALREADY IN THE INDEX answers TRACKABLE
    unconditionally, whatever the allow-list says — gitignore(5), and measured: commit a file, then
    add `/*` to `.gitignore`, and this still returns TRACKABLE. STATE BOTH HALVES OF THAT, because a
    limitation recorded without its bounds invites someone to route around a probe that was correct.
    It is the RIGHT answer for this sweep and not a false green: a skill directory in the index is
    in the next commit and is therefore not invisible to git, and all three incidents in this
    module's rationale were wholly untracked content. It is a TRAP for exactly one other reader —
    anyone probing a path IN ORDER TO INTERROGATE THE ALLOW-LIST, which is the shape of TC-49. That
    probe must be run on an UNTRACKED path or it measures trackedness instead; `plant_allowlisted_home`
    and `hidden_top_level_states` in the test suite take `commit=False` for this reason.

    Not `git check-ignore`; see the block comment on GIT_ENV for the measurement that rules it out.
    Not a reimplementation of ignore semantics either — this file already carries a narrow
    `.gitignore` parser for a different question, and it took two reviews to stop it eating the
    whole tree. Inheriting the trap in a hand-rolled form is worse than inheriting it directly,
    because it looks like it was thought about.

    RETRIES ON LOCK CONTENTION ONLY, and only because `git add` takes `.git/index.lock` even under
    `--dry-run` — measured, see GIT_ENV, which carries the numbers and their tree. `~/.claude` is
    written by several agent sessions at once, and a single held lock was measured turning a healthy
    eight-directory tree into eight `unknown` results, eight not-run findings and exit 2 — one per
    skill directory, so the count is whatever the tree holds. The retry is bounded, applies to
    nothing but that one recognised message, and ends in UNKNOWN like any other unanswerable state,
    so it cannot convert a real failure into a pass.

    DO NOT RESTATE A MEASURED NUMBER HERE. This sentence previously carried "six", which was the
    six-skill test fixture, and it survived 450 lines below its own retraction in GIT_ENV — leaving
    the file asserting both, with the stale copy in the more-read location: the docstring of the
    function a maintainer opens first when touching the retry. GIT_ENV owns these figures.

    WHEN A MEASURED NUMBER IS RETRACTED, GREP **BOTH FILES IN THE WRITE SET** — this module AND
    `tests/test_check_toolchain.py` — before calling the retraction done. The earlier version of
    this instruction said "grep the file", the grep was duly run against this module alone, and the
    retracted "six" was found a round later sitting in the test suite's docstring for the very retry
    described above. One file is never the unit: a retracted number lives wherever the rationale for
    the code was written down, and the rationale for a retry is written in both the function and the
    test that pins it. Prefer restating the RULE to restating the number, as the paragraph above now
    does — a rule cannot go stale by measurement.
    """
    attempt = 0
    while True:
        try:
            r = subprocess.run(["git", "-C", str(root), "add", "--dry-run", "--", rel],
                               capture_output=True, text=True, timeout=30,
                               env={**os.environ, **GIT_ENV})
        except (OSError, subprocess.SubprocessError) as e:
            return UNKNOWN, f"git could not be run ({e})"
        if r.returncode == 0:
            return TRACKABLE, ""
        noise = (r.stderr + r.stdout).strip()
        if r.returncode == 1 and GIT_IGNORED_MARKER in noise:
            return IGNORED, ""
        # Contention with a sibling git process, not an answer about this path.
        if GIT_LOCK_MARKER in noise.lower() and attempt < GIT_LOCK_RETRIES:
            attempt += 1
            time.sleep(GIT_LOCK_BACKOFF * attempt)
            continue
        detail = noise.splitlines()[0][:120] if noise else "no output"
        if GIT_LOCK_MARKER in noise.lower():
            detail = (f"another process held the index lock through {GIT_LOCK_RETRIES} retries "
                      f"({detail})")
        return UNKNOWN, f"git exited {r.returncode} without saying the path is excluded ({detail})"


def skill_dirs(root: Path) -> tuple[list[str], list[tuple[str, str]]]:
    """Top-level skill directories under `root`, plus the entries that cannot be asked about.

    A SYMLINKED skill directory is a problem rather than an entry, and this is the one place the
    honest answer costs something. `git add` on a link records the LINK — a 120000 blob holding a
    target path — so the probe would exit 0 and the sweep would report "git would commit this" about
    a directory whose entire content lives somewhere git has never heard of. That is the
    invisible-authored-work case wearing a green tick, which is the specific failure this check
    exists to prevent, so it fails closed to UNKNOWN.
    """
    names: list[str] = []
    problems: list[tuple[str, str]] = []
    for p in sorted(root.iterdir(), key=lambda q: q.name):
        if p.name == "__pycache__" or p.name.startswith("."):
            continue
        if p.is_symlink():
            problems.append((p.name, "a symlink; git would record the link, not the content, so "
                                     "whether the content would be committed is unknown"))
            continue
        if p.is_dir():
            names.append(p.name)
    return names, problems


def check_tracking() -> tuple[dict, list[tuple[str, str]], list[tuple[str, str]]]:
    """For every skill directory, ask git whether it would be committed. `(surface, findings, excluded)`.

    Three returns rather than one, matching `check_plugins`: the surface must reach `--json`
    whatever the verdict, and the Codex asymmetry is a declared exclusion rather than a finding.

    SEVERITY: `warn`, and the ruling is the substance of this check rather than a detail of it.

    The case for `critical` is real — silently losing authored work is worse than reporting drift,
    and one of the three measured instances would have dropped an entire skill. The case against is
    what happens on the OTHER machine. `skills/.gitignore` is an allow-list precisely BECAUSE vendor
    skills install themselves into this directory unannounced, so an ignored directory has two
    possible causes and this check cannot distinguish them: authored work went invisible, or a
    vendor arrived. The second is the designed-for, benign case, and it is one `uv tool install`
    away on any machine. At `critical` this check exits 1 at every session start in every directory
    on such a machine, until someone declares the newcomer — a permanently red gate is one the
    reader learns to skip, which is the failure mode this milestone has spent five rounds removing.
    Both arguments are satisfiable at once because TC-06 already separated the two axes: RANK
    GOVERNS VISIBILITY, BLOCKING GOVERNS THE EXIT CODE. So the finding is loud where it is read —
    named per directory, in the summary line, in `--hook`, and structured in `--json` — and does not
    gate the exit.

    KNOWN GAP — THIS SWEEP ASKS ABOUT SKILL DIRECTORIES AND NOTHING ELSE, AND THERE ARE THREE
    UNCOVERED SURFACES ON WHICH A NEW AUTHORED FILE IS INVISIBLE BY DEFAULT. Carded as TC-49;
    measured here so that card is scoped from fact rather than from this docstring.

    TWO allow-lists apply, not one. An earlier version of this paragraph measured a replica that
    omitted the second, which is how it came to state the opposite of what this module detects:

        ~/.claude/.gitignore          /* ; !/docs/ then /docs/* then 4 names ; !/skills/ !/hooks/
                                      !/agents/ !/codex/ ; 5 named top-level files
        ~/.claude/skills/.gitignore   /* ; !/.gitignore !/README.md ; one negation per OWNED skill
                                      ; then __pycache__/ *.pyc *.pyo .DS_Store "never, anywhere"

    Measured against a faithful replica carrying BOTH files, with this check's own probe:

        docs/NEW-LESSON.md                    rc 1  IGNORED BY DEFAULT      surface 1
        skills/NOTES.md                       rc 1  IGNORED BY DEFAULT      surface 2
        MEMORY.md            (new top-level)  rc 1  IGNORED BY DEFAULT      surface 3
        skills/agent-personas/NOTES.md        rc 0  trackable — INSIDE a negated skill directory
        hooks/new.sh, agents/new.md           rc 0  trackable
        skills/new-vendor-skill/              rc 1  ignored — what THIS sweep fires on

    IF YOU RE-MEASURE ANY ROW ABOVE, PROBE AN UNTRACKED PATH. Every row here is a claim about the
    ALLOW-LIST, and `git_probe` answers TRACKABLE unconditionally for anything already in the index
    — see its docstring for the measurement and its bounds — so a probe of a committed path
    silently interrogates trackedness instead, and answers rc 0 for a surface this paragraph
    correctly calls ignored.

    Read the last three rows together. A file inside an already-negated skill directory is
    trackable; a new file at the TOP LEVEL of `skills/` is not, because `skills/.gitignore` is a
    SECOND per-file allow-list. "A new file in skills/ is trackable" would contradict this very
    function: `graphify` measures `ignored` here today and the tests plant exactly that state.

    THE TOP-LEVEL NEGATIONS, AS AN IDENTITY, so the figures below check each other rather than
    each standing alone. `~/.claude/.gitignore` negates TEN top-level entries and they split
    5 + 5:

        5 named FILES        `.gitignore`, `CLAUDE.md`, `settings.json`, `statusline.sh`,
                             `private-identifiers.txt`
        5 named DIRECTORIES  `skills/`, `hooks/`, `agents/`, `codex/`, `docs/`
                             (`docs/` is then re-narrowed by `/docs/*` plus 4 names — that is
                             surface 1, and it does not change the top-level count)

    5 + 5 = the 10 trackable measured below. If a future edit moves one of these three numbers and
    not the other two, the identity stops holding and the paragraph is wrong — which is the point of
    writing it as an identity. The previous version said "4 named top-level files", spent that 4
    arithmetically two paragraphs down, and reconciled against neither the real file nor its own
    "10 trackable".

    THE COST OF CLOSING THEM IS NOT UNIFORM, and an earlier version quoted one figure — "four to six
    paths, nothing to exclude" — for all of it. Right for one surface, wrong for another, and the
    arithmetic failed too: 4 in `docs/` plus the 5 named top-level survivors is 9 before enumerating
    anything to FIND a new entry.

      surface 1, `docs/` — CHEAP, and the one worth doing first. Four files, all four named in the
        allow-list, four probes, `git_probe` unchanged. Measured: `docs/` holds exactly LEDGER.md,
        decisions.md, fleet-lessons.md, RESTORE.md and zero `.DS_Store` or `__pycache__`, so there
        is genuinely nothing to exclude. It is also where the measured incident happened —
        `docs/fleet-lessons.md` invisible for two days, with the `.gitignore` comment recording it
        four lines below the rule that caused it.

      surface 2, top level of `skills/` — CHEAP. Measured `os.listdir("skills")`, non-directory
        entries, DOTFILES INCLUDED: two today, `README.md` and `.gitignore`, both allow-listed.
        (One, if dotfiles are skipped — see the enumerator note below.) Needs only the four OS-noise
        names above held out — a list, not a model.

      surface 3, top level of `~/.claude` — NOT CHEAP, and it needs the very thing this paragraph
        once said was unnecessary. Detecting a NEW top-level entry means enumerating all of them.
        Measured with `os.listdir("~/.claude")`, `.git` excluded as never-authored, DOTFILES
        INCLUDED: 32 entries, 10 trackable, 22 IGNORED. Every one of the 22 is ignored legitimately
        and permanently — `projects/` alone is 2.6 GB holding 22,796 `*.jsonl` transcripts (26,159
        files in total; the transcript figure is the `*.jsonl` count, not the file count). Probed
        with no exclusion model that is 22 unclearable findings at every session start, which is
        exactly the cry-wolf pathology argued against twenty-five lines above. This surface needs a
        DECLARED AUTHORED-SET first, and must not be attempted as an extension of the cheap two.

    THE ENUMERATOR IS PART OF EVERY COUNT ABOVE, and saying so is not pedantry — an earlier version
    of this paragraph reported 28 / 9 / 19 for surface 3 and named no enumerator, which is the same
    tree with dotfiles skipped, and it disagreed with an independent measurement of the same
    directory. Both were honest; neither was reproducible. For the record: dotfiles skipped gives
    28 / 9 / 19, dotfiles included gives 33 / 11 / 22, and excluding `.git` from that gives the
    32 / 10 / 22 quoted above.

    HIDDEN ENTRIES ARE IN SCOPE FOR TC-49, and this is a scoping decision rather than an arithmetic
    one. `skill_dirs` skips dotfiles because a dotfile is not a skill; that convention must NOT be
    inherited by a sweep of authored documents. A newly authored hidden top-level config is STRICTLY
    MORE INVISIBLE than the `MEMORY.md` case this gap describes — ignored by `/*` exactly the same
    way, and additionally passed over by an enumerator that never looks. A sweep built to 28 would
    never see one. Measured, the FIVE hidden entries here today are `.git`, `.gitignore`,
    `.last-cleanup`, `.last-update-result.json` and `.statusline-cache`. `.git` is excluded as
    never-authored, per the enumerator note above — it is the entry that makes 33 − 28 = 5 hidden
    come out, and the one that takes 33 trackable-plus-ignored down to the 32 quoted there — and of
    the remaining four only `.gitignore` is authored, which is what a declared authored-set is for.
    The four-item version of this sentence read as exhaustive and was short by exactly the entry the
    counts twenty lines above turn on.

    `.gitignore` is also the standing REFUTATION of "hidden entries are out of scope", not merely an
    example of one that happens to be authored: it is hidden AND trackable (`!/.gitignore`) AND
    authored AND it is the allow-list this whole sweep polices. That is pinned executably by
    `test_a_hidden_top_level_entry_can_be_trackable_and_the_allowlist_line_decides` in the suite —
    deleting the `!/.gitignore` negation from the fixture or from the real file now fails a test
    rather than a review.

    The in-skill FILE gap is a fourth thing and is nearly empty of risk: `skills/.gitignore` never
    re-narrows INSIDE a negated directory, so the only exclusions reachable within a published skill
    are those four OS-noise names. It remains true that a clean result here covers the skill and not
    its contents — just do not read that as the reason the measured incidents are uncovered.

    An escalation rule was considered and rejected on the evidence: promote to `critical` when the
    ignored directory is named in MIRRORED_SKILLS, i.e. known to be ours. It would have been WRONG
    on the measured case. The skill that actually went invisible was `project-conformance`, which is
    not in MIRRORED_SKILLS — the rule would have quietly demoted the one instance it was invented
    for. A discriminator that fails on the recorded evidence is worse than none.

    `--reviews` rules the opposite way for the opposite reason; see `check_reviews`.
    """
    surface: dict = {}
    findings: list[tuple[str, str]] = []

    # The Codex side first, so the declaration is recorded even on a run where the Claude side
    # cannot be asked at all. See CODEX_TRACKING_ASYMMETRY for stop condition 4.
    surface["codex"] = {"root": str(CODEX_SKILLS), "in_scope": False, "asked": False,
                        "results": {}, "declared_vendor": {},
                        "why_not_asked": CODEX_TRACKING_ASYMMETRY}

    claude: dict = {"root": str(CLAUDE_SKILLS), "in_scope": True, "asked": False,
                    "results": {}, "declared_vendor": dict(DECLARED_VENDOR_SKILLS),
                    "why_not_asked": None}
    surface["claude"] = claude

    def unanswerable(why: str) -> tuple[dict, list, list]:
        claude["why_not_asked"] = why
        findings.append((NOT_RUN, f"skill tracking was NOT RUN: {why}. No skill directory was "
                                  f"asked whether git would commit it, so nothing here says any of "
                                  f"them is safe. {MACHINE_GLOBAL}"))
        return surface, findings, list(TRACKING_EXCLUSIONS)

    if not CLAUDE_SKILLS.is_dir():
        return unanswerable(f"{CLAUDE_SKILLS} is not a directory")
    try:
        top = subprocess.run(["git", "-C", str(CLAUDE_SKILLS), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=30,
                             env={**os.environ, **GIT_ENV})
    except (OSError, subprocess.SubprocessError) as e:
        return unanswerable(f"git could not be run against {CLAUDE_SKILLS} ({e})")
    if top.returncode != 0:
        return unanswerable(f"{CLAUDE_SKILLS} is not inside a git work tree "
                            f"({top.stderr.strip().splitlines()[0][:120] if top.stderr.strip() else 'git said nothing'})")
    claude["work_tree"] = top.stdout.strip()

    try:
        names, problems = skill_dirs(CLAUDE_SKILLS)
    except OSError as e:
        return unanswerable(f"{CLAUDE_SKILLS} could not be listed ({e})")

    claude["asked"] = True
    for name, why in problems:
        claude["results"][name] = UNKNOWN
        findings.append((NOT_RUN, f"skill `{name}` was NOT ASKED whether git would commit it: it is "
                                  f"{why}. {MACHINE_GLOBAL}"))
    for name in names:
        state, why = git_probe(CLAUDE_SKILLS, name)
        claude["results"][name] = state
        if state == UNKNOWN:
            findings.append((NOT_RUN, f"skill `{name}` was NOT ASKED whether git would commit it: "
                                      f"{why}. {MACHINE_GLOBAL}"))
        elif state == IGNORED and name not in DECLARED_VENDOR_SKILLS:
            findings.append(("warn", f"skill `{name}` in {CLAUDE_SKILLS} would NOT be committed — "
                                     f"git excludes it, and it is not on the declared-vendor list "
                                     f"({', '.join(sorted(DECLARED_VENDOR_SKILLS)) or 'empty'}). "
                                     f"Authored content that no commit can carry is how three "
                                     f"files and one whole skill went missing in this milestone. "
                                     f"Fix: declare it as a vendor skill, or add one line to "
                                     f"{CLAUDE_SKILLS / '.gitignore'} — a deliberate act belonging "
                                     f"to whoever owns that allow-list. {MACHINE_GLOBAL}"))

    # A declared vendor WAS asked and its answer IS recorded in `results`; what is excluded is the
    # FINDING, not the question. Both halves of that are now said in the output: the summary header
    # reads "excluded from findings" rather than the old "excluded and NOT compared", which was
    # accurate for the Codex tree and false here, and this entry's own reason names which of the two
    # it is. Pinned by `test_a_declared_vendor_is_reported_as_asked_not_as_uncompared`.
    excluded = list(TRACKING_EXCLUSIONS)
    excluded += [(f"skill {name}", "asked and ignored; exempt by declared vendor, see "
                                   "tracking.claude.declared_vendor")
                 for name in sorted(DECLARED_VENDOR_SKILLS) if name in claude["results"]]
    return surface, findings, excluded


def card_artifacts(reports: Path, card: str) -> tuple[list[str], list[str]]:
    """`(report_names, review_names)` belonging to `card`, matched on the `TC-<id>-` delimiter.

    THE DELIMITER IS LOAD-BEARING, and a bare `startswith(card)` is a silent all-clear generator:
    the real workspace holds TC-04 beside TC-40 and TC-02A beside an orphan `TC-02-review.md`, so a
    prefix match lets one card's review satisfy another card's obligation. Zero-padding makes the
    numeric collision survivable on its own; the suffixed ids do not.
    """
    prefix = f"{card}-"
    stems = [p.name[len(prefix):-len(p.suffix)].lower()
             for p in sorted(reports.glob(f"{prefix}*.md"))]
    # REVIEW WINS A TIE, and the markers are deliberately not disjoint. `TC-NN-security-report.md`
    # contains both `report` and `security`.
    #
    # WHAT THIS DOES AND DOES NOT CHANGE, stated precisely because the first version of this comment
    # implied more. It does NOT change the finding stream: counted in both lists the card had a
    # report AND a review and emitted nothing; counted review-first it has no report and still emits
    # nothing. What changes is the COUNTS — `reviews.cards[id]` no longer reports one file as both
    # `{"reports": 1, "reviews": 1}`, and `totals.with_reports` no longer includes a card whose only
    # artifact is its own reviewer's. The defect was therefore in the reported picture rather than
    # in the verdict: a workspace could show a card as reported-and-reviewed on the strength of a
    # single file. Fail toward silence, never toward an obligation that discharged itself.
    reviews = [s for s in stems if any(m in s for m in REVIEW_MARKERS)]
    return ([s for s in stems if REPORT_MARKER in s and s not in reviews], reviews)


def check_reviews(workspace: Path) -> tuple[dict, list[tuple[str, str]]]:
    """For every card that produced a report, assert an independent review artifact exists.

    SEVERITY: `critical`, under an any-finding exit rule — the opposite of `check_tracking`'s ruling
    on the same class of defect, and the discriminator is worth stating because it is the whole
    reason two sweeps in one card get two answers.

    `check_tracking` runs UNATTENDED at every session start in every directory, and its finding has
    a benign cause it cannot rule out. This mode runs only when a human or an orchestrator names a
    workspace on the command line and asks the question, and "a report exists and no review does"
    has no benign cause: either a judging persona looked at the work or nothing did. A `warn` here
    would exit 0 and print drift, which is precisely the false GREEN `--vendored` was built to kill;
    this mode follows that mode's rule for that reason.

    A large count is not noise. Run against the real workspace this reports sixteen cards, which is
    the milestone's actual review debt measured per card — the number being uncomfortable is the
    finding, not an argument against it.
    """
    surface: dict = {"workspace": str(workspace), "asked": False,
                     "cards": {}, "totals": {"cards": 0, "with_reports": 0, "unreviewed": 0}}

    def unanswerable(why: str) -> tuple[dict, list[tuple[str, str]]]:
        surface["why_not_asked"] = why
        return surface, [(NOT_RUN, f"review coverage was NOT RUN: {why}. No card was asked whether "
                                   f"anything reviewed it, which is not the same as every card "
                                   f"having been reviewed")]

    try:
        cards = sorted(p.stem for p in workspace.glob(CARD_PATTERN))
    except OSError as e:
        return unanswerable(f"{workspace} could not be listed ({e})")
    if not cards:
        return unanswerable(f"no file matching `{CARD_PATTERN}` in {workspace}")
    reports = workspace / REPORTS_DIRNAME
    if not reports.is_dir():
        # Deliberately not "every card is unreviewed". That reading turns one missing directory into
        # a wall of findings nobody can act on, and it is a verdict about a tree that was not read.
        return unanswerable(f"{reports} does not exist, so no card's artifacts could be listed")

    findings: list[tuple[str, str]] = []
    surface["asked"] = True
    unreviewed = with_reports = 0
    for card in cards:
        try:
            report_names, review_names = card_artifacts(reports, card)
        except OSError as e:
            findings.append((NOT_RUN, f"card `{card}` was NOT ASKED whether it was reviewed: "
                                      f"{reports} could not be listed ({e})"))
            continue
        surface["cards"][card] = {"reports": len(report_names), "reviews": len(review_names)}
        if not report_names:
            # No report is work not yet done, not work that skipped its review. Conflating them
            # would make every unstarted card in the workspace red and the sweep unreadable.
            continue
        with_reports += 1
        if review_names:
            continue
        unreviewed += 1
        # WHAT WAS SEARCHED FOR, not what was concluded. The previous wording asserted "nothing
        # independent judged this work", which this function cannot observe and which is FALSE for
        # several of the sixteen cards in the real workspace: it holds `FULL-DIFF-review.md` — a
        # reviewer-persona review of 3585 lines across 13 files and two repositories — plus
        # `SECURITY-review.md` and others, none of which carry a card id and none of which this
        # name-based search can see. A `critical` in a file whose register is measured fact must not
        # carry an inference the measurement does not support.
        findings.append(("critical", f"card `{card}` produced {len(report_names)} report(s) and no "
                                     f"file named `{card}-*.md` containing "
                                     f"{' or '.join(REVIEW_MARKERS)} in {reports}. THIS SEARCH IS "
                                     f"BY NAME: a workspace-wide review that does not carry this "
                                     f"card's id — a full-diff or branch-level review — is not "
                                     f"counted, so this reports a missing PER-CARD artifact and not "
                                     f"that the work went unjudged. Fix: persist the per-card "
                                     f"verdict as {reports / (card + '-review.md')}, or confirm a "
                                     f"broader review covered it"))
    surface["totals"] = {"cards": len(cards), "with_reports": with_reports,
                         "unreviewed": unreviewed}
    return surface, findings


def plugin_line(surface: dict | None) -> str | None:
    """The enumeration, as one line for a human. Counts only; it characterises nothing.

    Separate from the summary on purpose. `Run.summary` is the one sentence allowed to say how the
    run went, and this says neither that nor anything about acceptability — it is the census that
    makes an `inert` plugin visible without making it a finding.
    """
    if not surface:
        return None
    c, x = surface["claude"], surface["codex"]
    tiers = c["tiers"]
    # A count from an enumeration that did not finish is a FLOOR, not a census, and printing it
    # unmarked beside a not-run invited the reader to take it as the total. Each half is marked
    # independently, because after the H1 partition each half can fail on its own.
    claude_mark = "" if c["enumerated"] else " (INCOMPLETE — at least)"
    codex_mark = "" if x["enumerated"] else " (INCOMPLETE — at least)"
    # `N enabled` alone would repeat the two-valued defect in the census: on a run where enablement
    # could not be determined it would print `0 enabled` beside a non-empty `enabled_keys`.
    unknown = c["enablement"]["unknown"]
    enablement = (f"{c['enabled_count']} enabled" if not unknown
                  else f"{c['enabled_count']} enabled, {unknown} of UNDETERMINED enablement")
    return (f"plugin surface (machine-global): Claude{claude_mark} {c['count']} on disk, "
            f"{enablement} — {tiers['hook']} ship hooks, {tiers['agent']} ship "
            f"agents, {tiers['inert']} skills/commands only; Codex{codex_mark} {x['count']} "
            f"enabled, names only (see excluded).")


# The four machine-global checks, paired with the phrase each is allowed to contribute to the
# success line — and only if it produced no `not-run`. The old success line was a single hard-coded
# string asserting all three; this table is what makes it derived. Adding a check here without a
# label is impossible to do accidentally: the label is the second element.
DEFAULT_CHECKS = (
    ("personas", "personas in sync", check_personas),
    ("instruction mirror", "instructions mirrored", check_instructions),
    ("Codex skill mirror", "Codex skills current", check_skills),
)


def collect(run: Run) -> None:
    for label, clean_phrase, fn in DEFAULT_CHECKS:
        run.add(fn(), label, clean_phrase)

    # The plugin check is not in DEFAULT_CHECKS because it returns two things that table cannot
    # carry: the enumeration itself, which `--json` must emit whatever the verdict, and a declared
    # exclusion (the Codex asymmetry). It still routes its findings through `Run.add`, which is the
    # chokepoint that decides whether it may claim coverage — so a run whose enumeration failed
    # cannot contribute the phrase saying it enumerated.
    surface, findings, excluded = check_plugins()
    run.plugins = surface
    run.excluded += excluded
    claude, codex = surface["claude"], surface["codex"]
    # "no CLAUDE plugin agent shadows" — the qualifier is load-bearing and its absence was the L8
    # fix introducing the next false reassurance. Shortening the exclusion notice was right, but
    # what replaced it ("carries names only") no longer says the SHADOW question specifically is
    # open, while this same sentence asserted the shadow absence unqualified. `CODEX_ASYMMETRY`
    # states the opposite in as many words: whether a Codex plugin shadows a persona is UNKNOWN, not
    # known to be false. The qualifier belongs on the claim it qualifies, not in the exclusion.
    run.add(findings, "plugin surface",
            f"plugin surface enumerated: {claude['count']} Claude plugin(s), "
            f"{claude['enabled_count']} enabled, {codex['count']} Codex plugin(s); no CLAUDE plugin "
            f"agent shadows a base persona; the Codex side was enumerated by name only and not "
            f"classified")

    # TC-47, and outside DEFAULT_CHECKS for exactly the reason above: it returns a surface `--json`
    # must carry whatever the verdict, plus a declared exclusion. Its findings still route through
    # `Run.add`, so a sweep that could not ask cannot contribute the phrase saying it asked.
    tracking, tracking_findings, tracking_excluded = check_tracking()
    run.tracking = tracking
    run.excluded += tracking_excluded
    asked = tracking["claude"]["results"]
    # SCOPED TO WHAT WAS ACTUALLY ASKED, and with its tree named. "N skill directories" alone would
    # invite the reader to reconcile it against `git ls-files`, which counts a different tree: this
    # is what the working tree holds right now, not what HEAD carries.
    #
    # TWO NUMBERS, NOT ONE, and this sentence has already been wrong once for having only the total.
    # It read "git would commit EVERY ONE of the {len(asked)}" — a claim about every directory
    # asked, made on a line whose whole job is to be trustworthy, while a declared vendor sits in
    # `tracking.claude.results` answering `ignored` two keys away. That machine is not exotic: one
    # `uv tool install` produces it, and the exemption exists precisely because it is the expected
    # state. The exempt directory produces no finding, so nothing else in the output contradicts the
    # sentence and nothing stops the run being clean — the reader's only signal was the phrase, and
    # the phrase overstated it. Same false-reassurance shape as `Run.summary`'s "excluded and NOT
    # compared" header, one function away, and fixed the same way: report the FILTERED count
    # alongside the TOTAL, in the sentence and not only in the JSON.
    #
    # `exempt` is derived from the answers, never from `len(DECLARED_VENDOR_SKILLS)` — a vendor on
    # the list but not installed was never asked, and a declared vendor that came back TRACKABLE was
    # not exempted from anything. Both counts say what this run measured.
    trackable = sum(1 for state in asked.values() if state == TRACKABLE)
    exempt = sum(1 for name, state in asked.items()
                 if state == IGNORED and name in DECLARED_VENDOR_SKILLS)
    run.add(tracking_findings, "skill tracking",
            f"git would commit {trackable} of the {len(asked)} skill director(ies) on disk in "
            f"{CLAUDE_SKILLS}, with {exempt} exempt as declared vendors "
            f"(machine-global; the ~/.codex mirror is derived and out of scope, see excluded)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hook", action="store_true", help="compact context; silent when healthy")
    ap.add_argument("--json", action="store_true", dest="as_json")
    # MUTUALLY EXCLUSIVE, because they are verdicts about different trees. A run that silently
    # executed one of them would print a status for a question the caller did not ask, which is the
    # same false-reassurance shape as the clean line that named checks it had not run.
    scoped = ap.add_mutually_exclusive_group()
    scoped.add_argument("--vendored", metavar="REPO",
                        help="compare ~/.claude/skills against REPO/install/skills; drift only")
    scoped.add_argument("--reviews", metavar="WORKSPACE",
                        help="assert every card with a report in WORKSPACE also has a review")
    args = ap.parse_args()

    # EXIT SEMANTICS — stated per mode, deliberately, rather than shared.
    #
    #   default / --hook / --json (the Codex + persona + instructions checks):
    #       exit 1 iff some finding is `critical`. `warn` there means "a mirror this tool cannot
    #       fix from here has drifted" and has always exited 0; this runs at every session start
    #       in every directory, so raising it would turn every session into a failure.
    #   --vendored:
    #       exit 1 iff there is ANY finding, of any severity.
    #
    # The second rule is not the first one inherited. `--vendored` compares a *published* mirror,
    # where the direction that used to be a `warn` — content present in the repository and no
    # longer installed — is exactly the stale-published-content case the mode exists to catch.
    # Under an `any critical` rule that result printed drift and exited 0. Both belts are worn
    # here: every `check_vendored` finding is emitted as `critical`, AND the exit rule for this
    # mode ignores severity, so adding a `warn` category later cannot quietly restore the false
    # GREEN. Card TC-03 freezes: 0 clean, 1 finding, 2 usage or environment error.
    #
    # THE THIRD STATE OVERRIDES BOTH RULES. A `not-run` finding, in either mode, exits 2 — see
    # `Run.verdict`. This is not a fourth code and not a new rule for `--vendored`: exit 2 already
    # meant "the check could not run", and a check that did not run is that case whether it was the
    # whole run or one skill inside it.
    #
    # WHY `warn` STILL EXITS 0 IN DEFAULT MODE, having been asked to make drift blocking. Because
    # it would cry wolf: this machine's ordinary state has two genuine `warn`s (Codex-mirror drift
    # awaiting a re-vendor), and this runs at every session start in every directory. TC-06's
    # ruling separates visibility from the exit code precisely so that the answer to "the caller
    # cannot see the drift" is a better report, not a louder exit code. The report now says
    # `NOT A CLEAN RESULT` on its own line and `--json` carries `status` and per-severity `counts`.
    # A caller that discards stdout and reads only `$?` still cannot see it — that is the caller's
    # defect, and it is TC-37's to fix in verify.sh, not this file's to work around.
    #   --reviews:
    #       exit 1 iff there is ANY finding, same as `--vendored` and for the same reason. Both are
    #       deliberate, repository-scoped invocations rather than session-start ones, and both
    #       report a state with no benign cause. See `check_reviews` on why this is the opposite
    #       ruling to `check_tracking`'s `warn`, on what is the same class of defect.
    vendored_mode = args.vendored is not None
    reviews_mode = args.reviews is not None
    mode = "vendored" if vendored_mode else "reviews" if reviews_mode else "default"
    run = Run(mode, BLOCKING_ANY if (vendored_mode or reviews_mode) else BLOCKING_DEFAULT)
    # The `--hook` header, chosen with the mode rather than derived from a boolean at the point of
    # printing. Both repository-scoped modes must deny the default header's two claims — "the SHARED
    # toolchain" and "affects EVERY project" — or the reader is sent to fix a machine-global mirror
    # over a diff scoped to one named directory.
    hook_header = ("AGENT CONTEXT: the shared agent toolchain has drifted. This affects every "
                   "project, not just this one.")

    if reviews_mode:
        if not args.reviews.strip():
            print("error: --reviews requires a workspace path; got an empty value", file=sys.stderr)
            return 2
        workspace = Path(args.reviews).expanduser()
        if not workspace.is_dir():
            print(f"error: workspace not found or unreadable: {workspace}", file=sys.stderr)
            return 2
        hook_header = (f"AGENT CONTEXT: cards in {workspace} produced work that nothing reviewed. "
                       f"This is scoped to that workspace — the installed toolchain and other "
                       f"projects are unaffected.")
        surface, findings = check_reviews(workspace)
        run.reviews = surface
        run.add(findings, "review coverage",
                clean_phrase=f"every card in {workspace} that produced a report also carries a "
                             f"review artifact ({surface['totals']['with_reports']} of "
                             f"{surface['totals']['cards']} card(s) had a report to judge)")
    elif vendored_mode:
        # Truthiness would be wrong: `--vendored ""` is falsy, and under `if args.vendored:` it
        # silently ran the machine-global check and printed "clean" for a vendored-drift request.
        if not args.vendored.strip():
            print("error: --vendored requires a repository path; got an empty value",
                  file=sys.stderr)
            return 2
        repo = Path(args.vendored).expanduser()
        vendored_skills = repo / "install" / "skills"
        hook_header = (f"AGENT CONTEXT: the vendored copy of the shared toolchain in {repo} has "
                       f"drifted from ~/.claude/skills. This is scoped to this repository — the "
                       f"installed toolchain and other projects are unaffected.")

        # Probe the installed side separately. `CLAUDE_SKILLS.iterdir()` raises for problems with
        # ~/.claude/skills, and a shared handler blamed the vendored path — sending the operator
        # to inspect the wrong side of the comparison.
        for label, root in (("installed root", CLAUDE_SKILLS),
                            ("vendored root", vendored_skills)):
            if root.is_symlink():
                print(f"error: {label} is a symlink: {root} -> {os.readlink(root)}. A vendored "
                      f"copy that is a link to its source compares byte-identical forever while "
                      f"the repository publishes nothing. Replace it with a real directory.",
                      file=sys.stderr)
                return 2
            if not root.is_dir():
                print(f"error: {label} not found or unreadable: {root}", file=sys.stderr)
                return 2

        # The leaf `is_symlink()` probes above are necessary but not sufficient, and the case they
        # miss is the likelier one: `ln -s ~/.claude <repo>/install` leaves `<repo>/install/skills`
        # a REAL directory reached through a link, so neither root reports as a symlink, and this
        # mode then compares ~/.claude/skills against itself — byte-identical, exit 0, permanently
        # clean while the repository publishes nothing. Comparing resolved paths is the check the
        # error text above already promises; it subsumes the leaf case rather than duplicating it.
        if vendored_skills.resolve() == CLAUDE_SKILLS.resolve():
            print(f"error: the vendored root and the installed root are the same directory: "
                  f"{vendored_skills} and {CLAUDE_SKILLS} both resolve to "
                  f"{CLAUDE_SKILLS.resolve()}. A vendored copy that resolves to its source "
                  f"compares byte-identical forever while the repository publishes nothing. "
                  f"Replace the link with a real directory.", file=sys.stderr)
            return 2
        try:
            rules, declaration_problems = read_declaration(vendored_skills)
            run.add(declaration_problems)
            # The scope report comes back FROM the comparison, not from a parallel enumeration that
            # can disagree with it. See `check_vendored` on why re-deriving it dropped files
            # silently.
            findings, run.excluded = check_vendored(vendored_skills, rules)
            run.add(findings,
                    label="vendored drift",
                    # Scoped to what the walk can actually see. "byte for byte" would overclaim:
                    # `tree()` cannot surface a directory it is unable to descend into (see its
                    # KNOWN GAP), so this may promise only that nothing it compared differed.
                    clean_phrase=f"no drift found between ~/.claude/skills and {vendored_skills}: "
                                 f"every file this walk could read matches on both sides")
        except OSError as e:
            print(f"error: could not read {e.filename or vendored_skills}: {e}", file=sys.stderr)
            return 2
    else:
        collect(run)

    findings = sorted(run.findings, key=lambda f: severity_sort_key(f[0]))
    status, code = run.verdict()
    summary = run.summary(status)

    if args.as_json:
        print(json.dumps({
            "mode": run.mode,
            "status": status,
            "exit": code,
            "counts": run.counts(),
            "evaluated": run.evaluated,
            "not_evaluated": [{"check": c, "why": w} for c, w in run.not_evaluated],
            "excluded": [{"name": n, "why": w} for n, w in run.excluded],
            "findings": [{"severity": s, "detail": d} for s, d in findings],
            # Always present, `null` outside default mode. A caller acts on the tiers and the
            # `agents` lists directly; it never has to parse a finding's prose to learn what is
            # installed. See `plugin_surface` for the shape.
            "plugins": run.plugins,
            # TC-47, both sweeps, on the same `null`-outside-this-mode terms as `plugins`.
            # `tracking.claude.results` maps a skill directory to `trackable`/`ignored`/`unknown`
            # and `tracking.claude.asked` is false whenever the question could not be put to git,
            # so an unasked question can never be read as a satisfied one. `reviews.cards` maps a
            # card id to its report and review counts, which is where the per-card zero that is
            # invisible in aggregate becomes obvious.
            "tracking": run.tracking,
            "reviews": run.reviews,
            "summary": summary,
        }, indent=2))
    elif args.hook:
        if findings:
            # The header is mode-specific for the same reason the clean line is, and it is CHOSEN
            # WITH THE MODE above rather than re-derived here. The default header's two claims —
            # "the SHARED toolchain" and "this affects EVERY project" — are both false of the
            # repository-scoped modes, which read one named directory and affect nothing outside
            # it. Printing it there told the reader to go and fix a machine-global mirror over a
            # repository-scoped diff, and an `if` chain at the point of printing is a second place
            # for the mode list to fall out of date.
            print(hook_header)
            for s, d in findings:
                print(f"  - [{s}] {d}")
            # The exit code does not carry the whole result in default mode, so the compact mode
            # says the result in words. Printed only when there is something to say, because this
            # mode's contract is silence on a healthy machine.
            print(f"  {summary}")
    else:
        print("agent toolchain:")
        for s, d in findings:
            print(f"  {s.upper():8} {d}")
        # The census, printed whatever the verdict. It is what makes the quiet tier visible: an
        # `inert` plugin produces no finding by design, so without this line the only evidence it
        # was seen at all would be `--json`, and "reported quietly" would have become "not reported".
        census = plugin_line(run.plugins)
        if census:
            print(f"  {census}")
        # Always a summary line, never a hard-coded one. `Run.summary` composes it from what
        # actually ran; the previous success line asserted three named checks unconditionally, and
        # printed nothing at all when there were findings — so a drifted run's last word was its
        # exit code, which was 0.
        print(f"  {summary}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
