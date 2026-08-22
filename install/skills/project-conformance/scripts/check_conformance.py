#!/usr/bin/env python3
"""Ask whether a repository still meets the standard, and repair it when told to.

`project-onboarding` brings a repository under the standard ONCE. This asks whether it still
conforms, every time you want to know, and repairs the subset of drift that is safe to repair
mechanically. It is the founder's instrument, run by hand, in repositories that hold health and
financial data. Nothing here is wired to a hook, a session-start path, or any unattended loop.

IT ORCHESTRATES. IT REIMPLEMENTS NOTHING.
------------------------------------------
Every conformance judgement in this file comes from a checker that already owns it, invoked as a
subprocess through the single `run()` chokepoint, with BOTH its exit code and BOTH its streams
read. There is no second opinion here about what conforming means:

    personas      agent-personas/scripts/sync_personas.py --repo R --check
    persona
    protection    the SAME module's own `absent_restrictions()`, imported, applied to the EMITTED
                  artifact. The definition of "restricted" stays in agent-personas; this file only
                  chooses which artifacts to apply it to and where to read them from.
    route         progressive-disclosure/scripts/validate_disclosure.py R --readme --standard
                  --vs HEAD --json — all four gating flags, because each one it does not get is a
                  family that does not run and a status of `partial`
    hooks         progressive-disclosure/scripts/install_hooks.py R --check
    id guard      progressive-disclosure/scripts/identifier_guard.py, liveness-probed on an empty
                  message, so an absent deny-list is a could-not-be-checked rather than a pass
    methodology   execution-methodology/scripts/sync_methodology.py --repo R --adoption-check
    github        progressive-disclosure/scripts/check_github.py R --json
    plugins       progressive-disclosure/scripts/check_toolchain.py --json, `plugins` key (TC-41)
    preflight     hooks/preflight.sh R

If a conformance question has no owner, it does not get answered here. Adding a check to this file
instead of to the checker that owns it is how a conformance tool becomes the fourteenth thing that
drifts. `tests/test_conformance.py::test_no_conformance_rule_is_defined_in_this_file` holds that
structurally, by AST, rather than by this paragraph.

THREE STATES, AND THE THIRD IS THE POINT
-----------------------------------------
    0   CONFORMS               every check ran and every check was satisfied
    1   DOES NOT CONFORM       every check ran and at least one was not satisfied
    2   COULD NOT BE CHECKED   at least one check did not run

2 OUTRANKS 1, and the reason is the one `check_toolchain.exit_code` gives: the exit code answers
"can you trust this report" before it answers "did it find anything". A repository with one broken
checker and nine clean ones is not a repository that has been checked.

The aggregation therefore never reduces to a boolean. `Verdict` has three members, the summary line
names how many checks landed in each, and `--json` carries `not_run` as its own array with a `why`
per entry. A caller reading only `exit` still cannot mistake not-run for pass, because 2 is not 0.
The failure this closes has three recorded instances in this programme's ledger: fifteen unguarded
reads behind one reported finding, a warn-only path exiting 0, and a summary rendered from an exit
code with the findings on stdout thrown away.

WHY READING THE EXIT CODE ALONE WOULD ANSWER WRONG HERE, MEASURED, NOT ASSUMED
-------------------------------------------------------------------------------
Three of the eight callees deliberately exit 0 while carrying the finding elsewhere:

    sync_personas.py --repo R --check   exits 0 and prints "in sync" on STDOUT while every
                                        unprotected project judge is named on STDERR
    sync_methodology.py --adoption-check ALWAYS exits 0, by contract; the adoption state is stdout
    check_toolchain.py                  exits 0 on `warn`; the plugin surface is in --json only

So `run()` captures both streams always, and no check in this file decides anything from `rc`
alone.

REPORT BEFORE REPAIR
---------------------
The default path is read-only and writes NOTHING — no cache, no temp file, no generated artifact
inside the target. The report ends with a REPAIR PLAN naming every file `--fix` would touch, before
anything is touched. `--fix` then applies only what that plan named, prints each path as it changes
it, and finally asserts the changed set is a subset of the planned set. Running it twice changes
nothing the second time and says so in those words.

WHAT --fix WILL NOT DO, and why each refusal is deliberate:

  * It never deletes an agent file. An unmanaged `<repo>/.claude/agents/<name>.md` is reported with
    its working remedy and left alone; deleting a file a human wrote, in a repository holding
    health data, is not a thing a tool should decide.
  * It never adopts a repository into the execution methodology. Adoption is staggered and
    deliberate — `sync_methodology.py`'s own docstring says nothing there ever adopts a repository
    on its own — so `--fix` re-renders a repository that has ALREADY adopted and drifted, and
    reports the un-adopted one.
  * It never declares a repository public, never creates a remote, never pushes, never changes
    visibility, and never overwrites a tool policy a human wrote by hand.

THE ADVERTISED REMEDY FOR persona-drift IS A NO-OP, AND THIS FILE SAYS THE WORKING ONE
----------------------------------------------------------------------------------------
`validate_disclosure.py`'s `persona-drift` ERROR, and `sync_personas.py`'s own `run:` line, both
tell the operator to run `sync_personas.py --repo .`. For the case that actually fires — an
unmanaged `<repo>/.claude/agents/<name>.md` with no persona source — that command prints
`already up to date`, exits 0, LEAVES the file, and the identical error fires again next session.
Measured on a fixture, with the file still on disk afterwards and the second `--check` returning 1
with the same text.

A maintainer who runs the prescribed fix, sees success, and sees the error again concludes the
CHECK is broken. That is how a true finding gets disabled, and it would happen in exactly the
hostile scenario this skill exists for. So `UNMANAGED_REMEDY` below states the remedy that works —
delete the file, or give it a persona source — and
`tests/test_conformance.py::test_the_advertised_persona_drift_remedy_is_still_a_no_op` drives the
real `sync_personas.py` against a real fixture and fails the day that stops being true, so this
paragraph cannot rot into a lie.

SCOPE OF A FINDING IS NOT ALWAYS THE SCOPE OF THE RUN
-------------------------------------------------------
Every finding carries a `scope`. All are `repository` except the plugin surface, which is
`machine-global`: plugins live in `~/.claude/plugins` and `~/.codex`, and are identical in every
repository on this machine. Printed with a `[machine-global]` tag and segregated in `--json`,
because a per-project tool printing a per-machine fact otherwise has someone fix it in one
repository and expect the others to change. It will not; the same finding will appear in all of
them until the machine changes.

Usage:
  check_conformance.py [ROOT]          # report; writes nothing
  check_conformance.py [ROOT] --json
  check_conformance.py [ROOT] --fix    # apply exactly what the report named
"""
from __future__ import annotations

import argparse
import enum
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path(os.environ.get("PROJECT_CONFORMANCE_HOME", Path.home()))
CLAUDE = HOME / ".claude"
SKILLS = CLAUDE / "skills"
PD = SKILLS / "progressive-disclosure" / "scripts"
SYNC_PERSONAS = SKILLS / "agent-personas" / "scripts" / "sync_personas.py"
SYNC_METHODOLOGY = SKILLS / "execution-methodology" / "scripts" / "sync_methodology.py"
PREFLIGHT = CLAUDE / "hooks" / "preflight.sh"

# The interpreter that is running THIS file, not `python3` off PATH. Two live on a mac —
# /usr/bin/python3 is 3.9 and crashes several of these scripts on `X | Y` annotations — and a
# child resolved through PATH is not necessarily the one the caller chose.
PY = sys.executable or "python3"

TIMEOUT = 300

# The one `validate_disclosure.py` error kind this file drops rather than relays — see
# `check_route` for why, and `test_the_no_op_remedy_string_never_reaches_the_report` for the
# assertion that keeps it dropped.
PERSONA_DRIFT = "persona-drift"

# A KNOWN GAP IN A CHECKER THIS FILE DOES NOT OWN, handled by stating the truth rather than by
# inlining a rule here.
#
# `install_hooks.py --check` prints `post-commit graph refresh: ABSENT` for two different
# situations it cannot tell apart in that output: the hook was never installed, and the hook was
# DELIBERATELY SKIPPED because the repository has no `graphify-out/graph.json`. Its own install run
# says which — `post-commit graph refresh skipped — no graphify-out/graph.json in this repo` — but
# that sentence is on the mutating path, which a read-only checker must never take.
#
# The consequence, if this were treated like the other hooks: `--fix` would run `install_hooks.py`,
# the hook would be skipped again for the same reason, the finding would return unchanged, and the
# tool would offer the same repair forever. That is the shape of the stuck-red check this file is
# largely about, arrived at by accident instead of by bad advice.
#
# So it is reported as the finding it is, with the condition stated, and it is NOT offered as a
# mechanical repair. The real fix belongs in `install_hooks.py --check`: it should distinguish
# "absent" from "not applicable — no graph in this repository". That is a separate card in its
# write set, not something to decide here. graphify is an optional dependency and the core must
# never require it, so this stays a finding with an honest remedy rather than becoming a hard gate.
GRAPH_HOOK_REMEDY = (
    "the post-commit graph hook is skipped by `install_hooks.py` when the repository has no "
    "`graphify-out/graph.json`, so re-running it will NOT install this one and this tool does not "
    "pretend otherwise. Either build the graph first (`graphify extract . --mode deep`) and then "
    "`install_hooks.py {repo}`, or accept its absence — graphify is an optional dependency and "
    "nothing in the core requires it."
)

# The working remedy for an unmanaged generated agent, stated because the advertised one is a
# no-op. See the module docstring; a test drives the no-op against the real tool.
UNMANAGED_REMEDY = (
    "`sync_personas.py --repo .` does NOT fix this — it prints `already up to date`, exits 0, and "
    "leaves the file, so the identical error fires again next session. The remedies that work are: "
    "(a) delete the file, if it was a hand-written agent that should never have existed, or "
    "(b) give it a persona source at `docs/agents/personas/<name>.md`, if the agent is wanted — "
    "then re-render. This tool will not delete it for you."
)


ORPHAN_REMEDY = (
    "an orphan is a file the renderer DELETES, so it is the founder's call and not this tool's. "
    "`sync_personas.py --repo {repo}` will unlink it — and note what else that command does, "
    "because nothing else will tell you: with `--repo` it writes EVERY base persona into "
    "~/.claude/agents and ~/.codex/agents and prunes both of those machine-global trees too. If "
    "the persona was retired on purpose, run it. If the file should survive, restore its source at "
    "docs/agents/personas/<name>.md first, or move the file out of the generated directory."
)

TRUNCATION_REMEDY = (
    "run `sync_personas.py --repo {repo} --check` by hand and read its whole output; this reader "
    "can only see the first twelve entries the callee chooses to print. The durable fix belongs in "
    "`sync_personas.py`, which should print every stale path or emit them as JSON rather than "
    "capping a list whose tail carries the unmanaged and orphaned entries."
)


class Verdict(enum.Enum):
    """Three states. There is deliberately no boolean anywhere near this."""

    CONFORMS = "conforms"
    DOES_NOT_CONFORM = "does not conform"
    NOT_RUN = "could not be checked"


@dataclass
class Finding:
    detail: str
    scope: str = "repository"          # or "machine-global"
    files: list[str] = field(default_factory=list)
    remedy: str = ""


@dataclass
class Repair:
    """One mechanical repair, and the exact files it is allowed to touch.

    `files` is what the REPORT prints before anything is touched. `apply` returns the files it
    actually changed, and `main` asserts that set is a subset of this one.
    """

    label: str
    files: list[Path]
    apply: object                       # Callable[[], tuple[list[Path], str]]


@dataclass
class Check:
    name: str
    verdict: Verdict
    findings: list[Finding] = field(default_factory=list)
    why_not_run: str = ""
    repairs: list[Repair] = field(default_factory=list)
    # Something the reader must know that is NOT a finding. Kept out of `findings` because a
    # consumer counts that array: "not applicable, and here is why" sitting in it would make a
    # conforming repository report a problem it does not have.
    note: str = ""


@dataclass
class Run:
    """The result of one callee. `ok` is about the INVOCATION, never about the finding."""

    argv: list[str]
    ok: bool
    rc: int | None = None
    out: str = ""
    err: str = ""
    why: str = ""

    def undefined_rc(self, defined: tuple[int, ...]) -> bool:
        """True when the callee returned a code its own contract does not define.

        An unrecognised exit code is not a finding and is certainly not a pass — it means the
        contract this caller was written against no longer describes the callee.
        """
        return self.ok and self.rc not in defined


def run(argv: list[str], timeout: int = TIMEOUT) -> Run:
    """The single chokepoint through which every checker is invoked. Never raises.

    Both streams are captured unconditionally, because three of the eight callees exit 0 while
    carrying the answer on stdout or stderr. Every way an invocation can fail to happen at all —
    missing file, missing interpreter, not executable, timeout, any OSError — lands in `ok=False`
    with a `why`, which the caller turns into NOT_RUN. There is no path here that turns a failed
    invocation into a clean result.
    """
    argv = [str(a) for a in argv]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        return Run(argv, False, why=f"not found: {e.filename or argv[0]}")
    except PermissionError as e:
        return Run(argv, False, why=f"not executable: {e.filename or argv[0]}")
    except subprocess.TimeoutExpired:
        return Run(argv, False, why=f"timed out after {timeout}s")
    except OSError as e:
        return Run(argv, False, why=f"could not be invoked: {e}")
    return Run(argv, True, p.returncode, p.stdout or "", p.stderr or "")


def _why(r: Run, what: str) -> str:
    return f"{what} did not run — {r.why or f'exit {r.rc}'}: {' '.join(r.argv)}"


# --------------------------------------------------------------------------------------------
# The persona pool, imported rather than re-described.
# --------------------------------------------------------------------------------------------


class Unavailable(Exception):
    """The owning module could not be consulted. Always becomes NOT_RUN, never a pass."""


_sp_cache: object | None = None


def personas_module():
    """Import `sync_personas.py` so its own definitions can be CALLED, not copied.

    `check_toolchain.py` already reads the persona names out of this module for the same reason,
    so this is the established pattern rather than a new one. Every failure — absent file, syntax
    error, a `SystemExit` from a module body — raises `Unavailable`, and every caller turns that
    into `could not be checked`. An older `sync_personas.py` without `absent_restrictions` is one
    of those failures: this file will not fall back to a private notion of "restricted", because a
    fallback is exactly the second copy the whole design exists to prevent.
    """
    global _sp_cache
    if _sp_cache is not None:
        return _sp_cache
    if not SYNC_PERSONAS.is_file():
        raise Unavailable(f"{SYNC_PERSONAS} is not installed")
    try:
        spec = importlib.util.spec_from_file_location("_pc_sync_personas", SYNC_PERSONAS)
        if spec is None or spec.loader is None:
            raise Unavailable(f"{SYNC_PERSONAS} could not be loaded as a module")
        mod = importlib.util.module_from_spec(spec)
        # Registered before exec: a module that uses `@dataclass` or `typing.get_type_hints`
        # resolves `cls.__module__` through `sys.modules` and fails opaquely without this.
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)          # __main__-guarded; importing runs no sync
    except Unavailable:
        raise
    except BaseException as e:                # SystemExit in a module body is not a dead process
        raise Unavailable(f"{SYNC_PERSONAS} could not be imported: {type(e).__name__}: {e}") from e
    required = ("absent_restrictions", "claims_no_writes", "parse", "JUDGING_PERSONA_NAMES",
                "CLAUDE_KEYS", "JUDGE_SANDBOX", "JUDGE_DENIED_TOOLS", "pool_sources", "_tools")
    missing = [n for n in required if not hasattr(mod, n)]
    if missing:
        raise Unavailable(
            f"{SYNC_PERSONAS} does not export {', '.join(missing)} — this checker calls the "
            f"persona module's own definition of a restricted judge and will not substitute its "
            f"own. Update agent-personas, or accept `could not be checked`."
        )
    _sp_cache = mod
    return mod


def judging_floor(sp) -> list[str]:
    """The allow-list `--fix` writes into an unprotected project judge, DERIVED from the pool.

    Not a literal. It is the intersection of the `claude.tools` allow-lists that every persona on
    the judging roster already declares, read out of the real pool at run time — so the tools a
    judge may hold remain a fact about agent-personas, and this file cannot quietly widen them.
    `test_the_judging_floor_is_derived_and_contains_no_denied_tool` asserts the derivation, and
    `test_no_tool_name_is_written_as_a_literal_in_this_file` asserts by AST that no tool name
    appears here at all.

    Deliberately the INTERSECTION and therefore the narrowest thing any judge on the roster is
    trusted with: `test-judge` holds a shell and nothing derived from a domain specialist's
    description could justify handing one out. `--fix` narrows; widening is a deliberate edit to
    the persona source, and the report says so.
    """
    order: list[str] = []
    common: set[str] | None = None
    try:
        sources = sp.pool_sources()
    except Exception as e:
        raise Unavailable(f"the persona pool could not be read: {e}") from e
    for src in sources:
        try:
            meta, _body = sp.parse(src)
        except Exception as e:
            raise Unavailable(f"{src.name} could not be parsed: {e}") from e
        if meta.get("name") not in sp.JUDGING_PERSONA_NAMES:
            continue
        tools = sp._tools(meta.get("claude.tools"))
        if not order:
            order = list(tools)
        common = set(tools) if common is None else (common & set(tools))
    if not common:
        raise Unavailable(
            "no allow-list is common to every judging persona, so there is no floor to derive. "
            "Refusing to invent one."
        )
    denied = sorted(common & set(sp.JUDGE_DENIED_TOOLS))
    if denied:
        raise Unavailable(
            f"the derived floor contains tool(s) the roster denies its own judges ({', '.join(denied)}). "
            f"That is a contradiction in agent-personas, not something to work around here."
        )
    return [t for t in order if t in common]


def frontmatter(path: Path) -> dict[str, str]:
    """Parse `key: value` frontmatter out of a generated agent file.

    Flat by construction — `sync_personas.render_claude` emits nothing nested, for the reason its
    own comment gives — so this is a reader for a known emitter, not a YAML parser. A file with no
    frontmatter raises, because a generated agent that lost its frontmatter is a finding and must
    never read as an empty policy.
    """
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError(f"{path} has no `---` frontmatter block")
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, sep, v = line.partition(":")
        if sep:
            out[k.strip()] = v.strip()
    return out


def emitted_meta(sp, path: Path) -> dict[str, str]:
    """Rebuild a `meta`-shaped dict from an EMITTED artifact, using the emitter's own key map.

    `CLAUDE_KEYS` maps `claude.tools -> tools`; inverting it is how the emitted frontmatter is read
    back into the shape `absent_restrictions` expects. Inverted rather than restated, so a renamed
    key cannot leave this reader silently looking for something that is no longer emitted.
    """
    emitted = frontmatter(path)
    inverse = {v: k for k, v in sp.CLAUDE_KEYS.items()}
    return {inverse[k]: v for k, v in emitted.items() if k in inverse}


# --------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------

STALE_HEADER = re.compile(r"^\s*STALE — (?P<total>\d+) generated file\(s\)")
# A path, optionally followed by the callee's own parenthesised classification. The kind is
# captured GENERICALLY rather than matched against one known word: `prune` emits both
# `(unmanaged — …)` and `(orphaned — …)`, an earlier version of this reader knew only the first,
# and the anchored pattern silently swallowed `(orphaned — …)` INTO THE PATH — producing a
# filename that does not exist and describing a file about to be DELETED as one about to be
# re-rendered. Anything whose kind this reader does not recognise is counted as unparsed and
# disables the mechanical repair; it is never quietly filed under the benign case.
STALE_ENTRY = re.compile(r"^ {4}(?P<path>\S.*?)(?: \((?P<kind>[a-z]+) — [^)]*\))?$")

REGENERABLE, UNMANAGED, ORPHANED = "regenerable", "unmanaged", "orphaned"


@dataclass
class Stale:
    """What `sync_personas --check` said about one tree, classified by what a WRITE run would do.

    Three classes, and the difference between them is the difference between a safe repair and a
    deletion:

      regenerable  the file exists, has a source, and does not match it. A write run REWRITES it.
      unmanaged    no banner, no source. A write run PRESERVES it — this is the fifth door, and
                   `UNMANAGED_REMEDY` is the only remedy that clears it.
      orphaned     carries our banner, has no source. A WRITE RUN DELETES IT, with `f.unlink()`.

    `truncated` is not a detail. The callee prints its header with the TRUE total and then caps the
    list at twelve, so on a large drift this reader cannot see every path — and because `prune`
    appends after the write loop, the entries that fall off the end are exactly the `unmanaged` and
    `orphaned` ones. Silently repairing what it could see would mean writing files the plan never
    named and, worse, losing the one finding this whole skill exists for. So truncation disables
    the mechanical repair and is reported in those words.
    """

    total: int = 0
    regenerable: list[str] = field(default_factory=list)
    unmanaged: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)

    @property
    def seen(self) -> int:
        return len(self.regenerable) + len(self.unmanaged) + len(self.orphaned) + len(self.unparsed)

    @property
    def truncated(self) -> bool:
        return self.total > self.seen

    @property
    def enumerable(self) -> bool:
        """Whether every file the callee knows about was named to this reader."""
        return not self.truncated and not self.unparsed


def _stale_paths(stdout: str) -> Stale:
    """Read the callee's own STALE block. Classifies; never recomputes."""
    out = Stale()
    inside = False
    for line in stdout.splitlines():
        header = STALE_HEADER.match(line)
        if header:
            inside = True
            out.total = int(header.group("total"))
            continue
        if not inside:
            continue
        if not line.startswith("    "):
            break
        m = STALE_ENTRY.match(line.rstrip())
        if not m:
            out.unparsed.append(line.strip())
            continue
        kind = m.group("kind")
        if kind is None:
            out.regenerable.append(m.group("path"))
        elif kind == UNMANAGED:
            out.unmanaged.append(m.group("path"))
        elif kind == ORPHANED:
            out.orphaned.append(m.group("path"))
        else:
            out.unparsed.append(line.strip())
    return out


def _persona_scopes(repo: Path) -> tuple[dict[str, Stale], Run | None]:
    """Enumerate BOTH scopes the write run acts on. Returns `(scopes, failed_run)`.

    THE ONE-QUERY PROPERTY, AND WHY IT CANNOT BE ONE QUERY TODAY.
    --------------------------------------------------------------
    The rule this file must satisfy is that the set the report enumerates and the set the repair
    touches are derived from the same scope. `sync_personas.sync()` makes that impossible in a
    single invocation, and the reason is one line — `check_global = not (check and repo is not
    None)`:

        --repo R --check    check_global FALSE   compares the project trees only
        --check             check_global TRUE    compares the machine-global trees only
        --repo R  (write)   check_global TRUE    WRITES AND PRUNES BOTH

    There is no read-only invocation whose scope equals the write invocation's. So the enumeration
    is the UNION of the two read-only invocations, and that union is not a convenient assumption —
    it is derivable from `sync()` and it is MEASURED:

      * `expected` for the global trees is the same set in `--check` and in `--repo R`, because
        the `check_global` branch that fills it is identical and does not depend on `repo`.
      * `expected` for the project trees is the same set in `--repo R --check` and in `--repo R`,
        because the overlay and project-specialist branches do not depend on `check`.
      * `prune` is called on exactly those two target lists, with exactly those two `expected`
        sets, in all three invocations.

    `test_the_two_read_scopes_together_equal_what_the_write_touches` drives the real tool against a
    real fixture and asserts SET EQUALITY between the union of the two checks and the files a write
    run actually changes. That is a measurement, not a shape argument, and it fails the day the
    callee's scoping changes.

    WHAT WOULD MAKE IT ONE QUERY, and it is a one-line change in a file this card may not touch:
    `sync_personas.py` should make `--check` honour the same scope as the write it is checking —
    either `check_global = True` unconditionally, or a `--dry-run` that is the write path with the
    two mutating calls suppressed. Handed to `skills/agent-personas/` as its own card.
    """
    scopes: dict[str, Stale] = {}
    for scope, argv in (("repository", [PY, SYNC_PERSONAS, "--repo", repo, "--check"]),
                        ("machine-global", [PY, SYNC_PERSONAS, "--check"])):
        r = run(argv)
        if not r.ok or r.undefined_rc((0, 1, 2)) or r.rc == 2:
            return scopes, r
        stale = _stale_paths(r.out)
        if r.rc == 1 and stale.seen == 0:
            return scopes, Run(r.argv, True, r.rc, r.out, r.err,
                               why=f"the STALE block in the {scope} scope was unreadable")
        scopes[scope] = stale
    return scopes, None


def _stale_findings(scope: str, repo: Path, stale: Stale) -> list[Finding]:
    """One finding per class, with the remedy that matches what a WRITE run would actually do."""
    out: list[Finding] = []
    where = ("the machine-global trees (~/.claude/agents, ~/.codex/agents) — this is NOT a "
             "property of this repository" if scope == "machine-global" else "this repository")
    if stale.regenerable:
        out.append(Finding(
            f"{len(stale.regenerable)} generated agent file(s) in {where} do not match their "
            f"persona source",
            scope=scope, files=list(stale.regenerable),
            remedy=f"re-render: sync_personas.py --repo {repo}"))
    for path in stale.unmanaged:
        out.append(Finding(
            f"{Path(path).name} is a generated-agents file with NO persona source. It overrides "
            f"the same-named user-level persona wholesale in this repository, and nothing "
            f"automatic compares it against anything",
            scope=scope, files=[path], remedy=UNMANAGED_REMEDY))
    for path in stale.orphaned:
        out.append(Finding(
            f"{Path(path).name} in {where} carries the generated banner but its persona is no "
            f"longer in the pool. A WRITE RUN OF THE RENDERER DELETES THIS FILE with `unlink()`. "
            f"This tool will not do that for you",
            scope=scope, files=[path], remedy=ORPHAN_REMEDY.format(repo=repo)))
    if stale.truncated:
        out.append(Finding(
            f"the callee named only {stale.seen} of {stale.total} stale file(s) in {where} — it "
            f"caps its printed list — so this report CANNOT name the rest. Because `prune` appends "
            f"after the write loop, the entries that fall off the end are exactly the unmanaged "
            f"and orphaned ones, which means an unmanaged-agent finding may be hidden right now. "
            f"No mechanical repair is offered while the enumeration is incomplete",
            scope=scope, remedy=TRUNCATION_REMEDY.format(repo=repo)))
    if stale.unparsed:
        out.append(Finding(
            f"{len(stale.unparsed)} line(s) of the callee's STALE block in {where} were in a form "
            f"this reader does not recognise: {stale.unparsed[:3]}. No mechanical repair is "
            f"offered while any line is unread",
            scope=scope, remedy=TRUNCATION_REMEDY.format(repo=repo)))
    return out


def _render_blockers(scopes: dict[str, Stale]) -> list[str]:
    """Why the re-render repair must NOT be offered. Empty means it is safe to offer.

    Three blockers, and each one is a way the plan could fail to authorise what the write does:

      an orphan          the write run would DELETE it, and this tool refuses to delete
      a truncated list   files exist that the plan cannot name
      an unparsed line   a file this reader could not classify

    Checked over BOTH scopes, because the write acts on both.
    """
    why: list[str] = []
    for scope, stale in scopes.items():
        if stale.orphaned:
            why.append(f"{len(stale.orphaned)} orphaned file(s) in the {scope} scope would be "
                       f"DELETED by a write run")
        if stale.truncated:
            why.append(f"the {scope} scope's stale list is truncated at {stale.seen} of "
                       f"{stale.total}")
        if stale.unparsed:
            why.append(f"{len(stale.unparsed)} unreadable line(s) in the {scope} scope")
    return why


def check_personas(repo: Path) -> Check:
    """Persona conformance, asserted on the EMITTED artifact rather than on the source.

    Two questions, one callee each, and they are genuinely different:

      1. Are the generated artifacts what the sources say they should be?  `--check`'s exit code.
      2. Is every judging persona in this repository actually restricted?  `absent_restrictions`,
         the persona module's own function, applied to what is on disk in `.claude/agents/`.

    (2) is asserted on the artifact and not on the source because the artifact is what the harness
    loads. That is the LEDGER B principle and it is the only place the claim counts: a source can
    be impeccable and the emitted file hand-edited, and (1) catches that only while the file is
    still managed.

    WHICH artifacts are judges comes from the SOURCE, and it has to: `writes:` is not among the
    keys `render_claude` emits, so the emitted file does not carry it. So the SELECTION is made by
    the module's own `claims_no_writes` over the parsed sources, and the JUDGEMENT is made on the
    emitted file. Both halves are the module's; neither is this file's.

    TWO SCOPES, NOT ONE, AND THIS FILE HAD TO LEARN THAT THE HARD WAY.
    ---------------------------------------------------------------------
    `sync_personas.sync()` computes `check_global = not (check and repo is not None)`. Read that
    carefully, because it is asymmetric between the two invocations this file makes:

        --repo R --check     check_global is FALSE.  ~/.claude/agents and ~/.codex/agents are
                             neither compared nor pruned.
        --repo R             check_global is TRUE.   Every base persona is WRITTEN into both of
                             those trees, and both are PRUNED.

    So a version of this check that asked only the first question was structurally incapable of
    naming a machine-global file that the repair it offered would then write — the report could not
    have named it even in principle, because the checker was never asked to look. `--fix` inside a
    project repository would silently rewrite, and with `prune`, DELETE from, two trees outside it.

    The fix is to ask the second question too: a second read-only invocation with NO `--repo`,
    which is the mode that does compare the global trees. Both scopes are enumerated before
    anything is repaired, and every machine-global finding is tagged `machine-global` for the same
    reason the plugin surface is — the scope of the finding is not the scope of the run.
    """
    scopes, failed = _persona_scopes(repo)
    if failed is not None:
        return Check("personas", Verdict.NOT_RUN,
                     why_not_run=(failed.why or
                                  f"sync_personas.py --check exited {failed.rc}: "
                                  f"{(failed.err or failed.out).strip()[:400]}")
                     + f" [{' '.join(failed.argv)}]")

    findings: list[Finding] = []
    repairs: list[Repair] = []
    for scope, stale in scopes.items():
        findings.extend(_stale_findings(scope, repo, stale))

    # ONE REPAIR FOR BOTH SCOPES, because one command does both: `sync_personas.py --repo R` writes
    # the project tree AND the machine-global trees. Two repairs would double-run it, and a repair
    # scoped to one tree would be a lie about what the command does.
    regenerable = [p for s in scopes.values() for p in s.regenerable]
    blockers = _render_blockers(scopes)
    if blockers:
        findings.append(Finding(
            "no re-render repair is offered: " + "; ".join(blockers)
            + ". Running the renderer here is the founder's call, not this tool's",
            remedy=ORPHAN_REMEDY.format(repo=repo)))
    elif regenerable:
        repairs.append(Repair(
            "re-render the generated agent files (project AND machine-global trees — one "
            "`sync_personas.py --repo R` writes both)",
            [Path(p) for p in regenerable],
            lambda: _apply_render(repo)))

    try:
        sp = personas_module()
        judge_findings = _unprotected_judges(sp, repo)
    except Unavailable as e:
        # A partial answer is not an answer. Staleness was compared; protection was not, and the
        # whole check therefore reads as not-run rather than as "conforms, minus a bit".
        return Check("personas", Verdict.NOT_RUN, findings=findings,
                     why_not_run=f"persona protection could not be judged: {e}")

    for f, repair in judge_findings:
        findings.append(f)
        if repair is not None:
            repairs.append(repair)

    verdict = Verdict.DOES_NOT_CONFORM if findings else Verdict.CONFORMS
    return Check("personas", verdict, findings=findings, repairs=repairs)


def _unprotected_judges(sp, repo: Path) -> list[tuple[Finding, Repair | None]]:
    """Every project judge in this repository whose EMITTED artifact leaves capability granted.

    A project specialist is off the judging roster by construction — the roster covers base
    personas only — so `restrict_for_roster` returns its meta untouched and NOTHING is derived or
    validated for it. Whatever it declares is rendered verbatim, and the common shape,
    `disallowedTools: Write, Edit, NotebookEdit[, Bash]`, is a deny-list against a tool roster that
    grows: it reads as a judge to every human while still granting `Agent`, `SendMessage` and
    `Monitor`. That condition, live and named, is why this whole skill exists.
    """
    out: list[tuple[Finding, Repair | None]] = []
    sources = sorted((repo / "docs" / "agents" / "personas").glob("*.md"))
    for src in sources:
        if src.name.lower() == "readme.md":
            continue
        try:
            meta, _ = sp.parse(src)
        except Exception:
            continue                      # sync_personas --check already owns "source is invalid"
        name = meta.get("name") or src.stem
        if not sp.claims_no_writes(meta.get("writes")):
            continue
        if name in sp.JUDGING_PERSONA_NAMES:
            continue                      # the roster derives its restrictions; not our business
        artifact = repo / ".claude" / "agents" / f"{name}.md"
        if not artifact.is_file():
            out.append((Finding(
                f"project judge `{name}` has a persona source but NO emitted artifact at "
                f"{artifact} — nothing was rendered, so nothing is loaded and nothing is checked",
                files=[str(artifact)],
                remedy=f"re-render: sync_personas.py --repo {repo}"), None))
            continue
        try:
            meta_out = emitted_meta(sp, artifact)
        except (OSError, ValueError) as e:
            out.append((Finding(
                f"project judge `{name}`: its emitted artifact could not be read, so its tool "
                f"policy is UNKNOWN, not known to be safe — {e}",
                files=[str(artifact)],
                remedy="repair or re-render the file, then re-run"), None))
            continue
        absent = sp.absent_restrictions(meta_out)
        if not absent:
            continue
        lacks = "; ".join(f"{noun} ({', '.join(tools)})" for noun, tools in absent)
        source_meta = sp.parse(src)[0]
        can_fix = "claude.tools" not in source_meta
        remedy = (
            f"add an explicit `claude.tools` allow-list to {src}, then re-render with "
            f"`sync_personas.py --repo {repo}`. A deny-list cannot close this: it is default-open "
            f"against a tool roster that grows, which is the finding that put the base roster on "
            f"an allow-list in the first place."
        )
        if not can_fix:
            remedy += (
                " This one declares an allow-list ALREADY and still grants the above, so a human "
                "wrote that policy deliberately. --fix will not overwrite it; widen or narrow it "
                "yourself."
            )
        out.append((
            Finding(
                f"project judge `{name}` is UNPROTECTED in the emitted artifact. Still granted in "
                f"the Claude harness, because nothing withholds it: {lacks}. It is off the judging "
                f"roster, so nothing derives or validates a tool policy for it",
                files=[str(artifact)],
                remedy=remedy),
            None if not can_fix else Repair(
                f"give project judge `{name}` an explicit allow-list",
                [src, artifact, repo / ".codex" / "agents" / f"{name}.toml"],
                (lambda s=src, r=repo: _apply_allow_list(sp, s, r))),
        ))
    return out


WROTE = re.compile(r"^\s*wrote\s+(?P<path>\S.*?)\s*$")
# `removed` lines carry a trailing parenthetical the `wrote` lines do not.
REMOVED = re.compile(r"^\s*removed\s+(?P<path>\S.*?)(?:\s{2,}\(.*\))?\s*$")


def _apply_render(repo: Path) -> tuple[list[Path], str]:
    """Run the renderer in write mode — but only after re-proving it will not delete anything.

    TWO GUARDS, AND THE ORDER MATTERS.

    BEFORE the write: both scopes are enumerated again, immediately, and the run is ABANDONED if
    anything blocks it. `check_personas` already refused to offer this repair when a blocker
    existed, but that decision was made at report time and the operator reads the report before
    typing `--fix`. Re-checking here closes the window, and it is the guard that keeps the
    refusal — "this tool never deletes a file" — actually true rather than merely intended.

    AFTER the write: `removed` lines are parsed and returned in `changed`, so any deletion trips
    the `changed ⊆ planned` contract check. That backstop is deliberately NOT the only defence.
    Raising CONTRACT VIOLATION after the writes have landed is exactly what this card calls "worse
    than no tool" — it converts a silent deletion into an announced one and authorises neither. It
    exists to catch the case the pre-write guard did not anticipate, not to substitute for it.

    The earlier version of this function parsed only `wrote ` lines. `prune` prints deletions as
    `removed {f}`, so a `--fix` that unlinked two files reported an empty changed set and printed
    `nothing changed — the second run of --fix is a no-op, as it must be`. Both guards exist
    because of that.
    """
    scopes, failed = _persona_scopes(repo)
    if failed is not None:
        return [], (f"FAILED — refusing to run the renderer: the pre-write re-check could not "
                    f"enumerate what it would touch ({failed.why or f'exit {failed.rc}'})")
    blockers = _render_blockers(scopes)
    if blockers:
        return [], ("FAILED — refusing to run the renderer, nothing was written: "
                    + "; ".join(blockers))

    r = run([PY, SYNC_PERSONAS, "--repo", repo])
    if not r.ok or r.rc != 0:
        return [], f"FAILED — {r.why or (r.err or r.out).strip()[:300]}"
    changed: list[Path] = []
    deleted: list[Path] = []
    for line in r.out.splitlines():
        m = WROTE.match(line)
        if m:
            changed.append(Path(m.group("path")))
            continue
        m = REMOVED.match(line)
        if m:
            deleted.append(Path(m.group("path")))
    changed.extend(deleted)
    if deleted:
        return changed, (f"FAILED — the renderer DELETED {len(deleted)} file(s) that the pre-write "
                         f"guard did not predict: {', '.join(str(p) for p in deleted)}. This is a "
                         f"defect in this tool's guard, not an authorised repair")
    if not changed:
        return [], "already up to date"
    return changed, f"re-rendered {len(changed)} file(s)"


def _apply_allow_list(sp, source: Path, repo: Path) -> tuple[list[Path], str]:
    """Write the derived allow-list into the persona SOURCE, then re-render.

    THE SOURCE, NOT THE ARTIFACT, AND THIS IS THE WHOLE POINT OF THE REPAIR. Re-rendering alone
    fixes nothing here: an off-roster persona's meta is returned untouched by `restrict_for_roster`,
    so a re-render emits it exactly as open as it already was — while `sync_personas` exits 0 and
    prints `already up to date`. A repair that reported success and changed no capability would be
    the second no-op remedy in this same subsystem.

    Idempotent by precondition: the caller only offers this repair when the source declares no
    `claude.tools` at all, and after one run it does, so the finding is gone and the repair is
    never offered again.
    """
    text = source.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?\n)---\n", text, re.S)
    if not m:
        return [], f"FAILED — {source} has no frontmatter block to add an allow-list to"
    fm = m.group(1)
    if "claude.tools:" in fm:
        return [], "already declares an allow-list; nothing to do"
    floor = judging_floor(sp)
    addition = f"claude.tools: {', '.join(floor)}\n"
    if "codex.sandbox:" not in fm:
        addition += f"codex.sandbox: {sp.JUDGE_SANDBOX}\n"
    new = text[:m.start(1)] + fm + addition + text[m.end(1):]
    if new == text:
        return [], "FAILED — the source was not modified"
    source.write_text(new, encoding="utf-8")
    changed = [source]
    rendered, note = _apply_render(repo)
    changed.extend(rendered)
    return changed, f"allow-list `{', '.join(floor)}` written to the source; {note}"


def check_route(repo: Path) -> Check:
    """Route validity, from the validator, with its own three states preserved.

    `validate_disclosure.py` reports `clean` / `findings` / `partial` INDEPENDENTLY of its exit
    code, and says so: the exit code is decided by errors alone, so a family of checks that did not
    run neither raises nor lowers it. A caller that read only the exit code would therefore call a
    `partial` run clean. This one reads `status` from `--json` as well, and `partial` becomes
    not-run — a route that was only half examined has not been examined.

    ALL FOUR GATING FLAGS ARE PASSED, and `--vs` is the one that is easy to leave off. Without it
    the README-freshness family does not run, the status is `partial` on EVERY repository, and this
    check would report `could not be checked` universally — a three-state contract that always
    lands on the third state teaches the reader to ignore it, which is the same disablement this
    file exists to prevent, arrived at from the cautious direction. Measured on a fixture: no
    `--vs`, status `partial`, one family not run; with `--vs HEAD`, status `findings`, none. So the
    fix is to REQUEST the family, never to forgive its absence.

    persona-drift is DROPPED here, deliberately, and it is the only kind that is. It duplicates
    what `check_personas` already reports, and its `detail` carries a remedy that does not work —
    `sync_personas.py --repo .` against an unmanaged file exits 0, prints `already up to date`, and
    leaves the file. Relaying that string would put the no-op remedy in front of the operator in
    the one report meant to state the working one. `check_personas` names the same file with
    `UNMANAGED_REMEDY` instead, so nothing is lost by dropping it and the wrong advice never
    appears.
    """
    r = run([PY, PD / "validate_disclosure.py", repo,
             "--readme", "--standard", "--vs", "HEAD", "--json"])
    if not r.ok or r.undefined_rc((0, 1, 2)):
        return Check("route", Verdict.NOT_RUN, why_not_run=_why(r, "validate_disclosure.py"))
    try:
        data = json.loads(r.out)
    except (ValueError, TypeError):
        return Check("route", Verdict.NOT_RUN,
                     why_not_run=("validate_disclosure.py --json did not emit JSON "
                                  f"(exit {r.rc}): {(r.out or r.err).strip()[:800]}"))
    status = data.get("status")
    findings = [Finding(f"{f.get('kind', '?')} at {f.get('where', '?')}: {f.get('detail', '')}",
                        files=[str(repo / str(f.get("where")))] if f.get("where") else [],
                        remedy="see progressive-disclosure; route repair is authoring, not "
                               "mechanical, so --fix does not attempt it")
                for f in data.get("errors") or []
                if f.get("kind") != PERSONA_DRIFT]
    if r.rc == 2 or status in ("could-not-run", "partial"):
        # NOT_RUN **with** its findings attached. `partial` outranks `findings` in the callee's
        # own status, so a run with real route errors reports `partial` — and returning NOT_RUN
        # with an empty findings list would have thrown every one of those errors away. The
        # VERDICT is the safe one either way; the REPORT must still carry what was found. Same
        # shape `check_personas` uses when protection cannot be judged but staleness was.
        return Check("route", Verdict.NOT_RUN, findings=findings,
                     why_not_run=(f"the route was not fully examined (status={status!r}, "
                                  f"exit {r.rc}). A partially examined route is not a clean one. "
                                  f"Any errors listed below were found by the families that DID "
                                  f"run; nothing is known about the families that did not: "
                                  f"{json.dumps(data.get('not_run') or [])[:300]}"))
    if r.rc == 1 and not findings:
        findings = [Finding(f"the route validator exited 1 with status {status!r}; see its own "
                            f"report for detail", remedy="run validate_disclosure.py "
                                                         f"{repo} --readme --standard")]
    return Check("route", Verdict.DOES_NOT_CONFORM if findings else Verdict.CONFORMS,
                 findings=findings)


HOOK_LINE = re.compile(r"^\s{2}(?P<what>[^:]+):\s*(?P<state>.+)$")
PUBLIC_KEY = "repository declares itself PUBLIC"

# `install_hooks.py --check`'s label vocabulary, hoisted for the same reason
# `METHODOLOGY_STATES` is: everything this file knows about interpreting another tool's output is
# a named table, so the coupling is visible and a test can assert no `check_` function classifies
# by a literal typed inline. Every entry is a substring of a label the callee prints.
HOOK_NOT_A_HOOK = ("repository declares", "repo has")   # state lines, not installable hooks
HOOK_GUARD = "private-identifier"                       # public repositories only
HOOK_GRAPH = "graph"                                    # skipped when the repo has no graph

# `check_toolchain.py --json` emits every check's findings into ONE flat `findings` array with no
# key saying which check produced each, so selecting the plugin ones is a substring match on the
# detail. Named here rather than typed inline, and stated as the weakness it is: the correct fix
# is for that emitter to carry the producing check's name per finding, which is its write set, not
# this one's. The failure direction is over-selection — a non-plugin finding mentioning the word
# would be reported as machine-global, which is loud rather than silent.
PLUGIN_FINDING_MARKER = "plugin"


def _hook_states(stdout: str) -> dict[str, str]:
    """`install_hooks.py --check`'s `  name: state` lines, as a dict. One parser, used twice."""
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        m = HOOK_LINE.match(line.rstrip())
        if m:
            out[m.group("what").strip()] = m.group("state").strip()
    return out


def _declares_public(states: dict[str, str]) -> bool:
    """Whether the repository declares itself public, parsed CASE-INSENSITIVELY.

    The callee renders this value through `declaration_line`, which returns `YES ({where}, dated
    {date})` for an active declaration and lowercase `no` otherwise — so the answer is a prefix,
    in uppercase, followed by a stamp. Both readers in this file now go through here, because the
    two of them disagreeing is what made the identifier-guard branch dead code.
    """
    return states.get(PUBLIC_KEY, "").lower().startswith("yes")


def check_hooks(repo: Path) -> Check:
    """Hooks installed, and the dependencies they invoke present.

    `install_hooks.py --check` reports one `name: state` line per hook and is the owner of what
    "installed" means — including, since the fix that made a hook unable to be declared installed
    without verifying what it invokes, the presence of its dependencies. This reads its lines; it
    does not look at `.git/hooks` itself.

    The identifier guard is reported here too and NOT treated as a hole in a private repository:
    it is for repositories that are DELIBERATELY PUBLIC, and `install_hooks.py` says which this is.
    Declaring a repository public is a founder decision and `--fix` never makes it.
    """
    r = run([PY, PD / "install_hooks.py", repo, "--check"])
    if not r.ok or r.undefined_rc((0, 1, 2)):
        return Check("hooks", Verdict.NOT_RUN, why_not_run=_why(r, "install_hooks.py --check"))
    if r.rc == 2:
        return Check("hooks", Verdict.NOT_RUN,
                     why_not_run=f"install_hooks.py --check could not run: {(r.err or r.out).strip()[:300]}")
    states = _hook_states(r.out)
    if not states:
        return Check("hooks", Verdict.NOT_RUN,
                     why_not_run=("install_hooks.py --check printed nothing this reader could "
                                  f"interpret:\n{r.out.strip()[:300]}"))
    public = _declares_public(states)
    findings: list[Finding] = []
    mechanical: list[str] = []
    for what, state in states.items():
        if any(what.startswith(prefix) for prefix in HOOK_NOT_A_HOOK):
            continue
        if not state.upper().startswith("ABSENT"):
            continue
        guard = HOOK_GUARD in what
        if guard and not public:
            continue                      # correctly absent: the guard is for public repos only
        graph = HOOK_GRAPH in what.lower()
        findings.append(Finding(
            f"{what}: ABSENT",
            files=[str(repo / ".git" / "hooks")],
            remedy=(GRAPH_HOOK_REMEDY.format(repo=repo) if graph else
                    f"install_hooks.py {repo}" if not guard else
                    f"the repository declares itself PUBLIC but the guard is absent — "
                    f"install_hooks.py {repo}")))
        if not graph:
            mechanical.append(what)
    # THE HOOK REPAIR REACHES OUTSIDE THE REPOSITORY, and the plan has to say so.
    # `install_hooks.py` also refreshes the Codex skills mirror and re-syncs the persona pool —
    # its own SKILL.md calls that "repairs global drift as a side effect". Harmless, and the
    # founder may even want it, but a report that promised to name every file `--fix` touches and
    # then silently rewrote two machine-global trees would have broken its own contract. Named as
    # directories because the exact file set is decided by the callee at run time, and claiming a
    # precise list this file cannot know would be a worse kind of wrong.
    repairs = [Repair(
        "install the missing git hooks (ALSO refreshes the machine-global Codex skill mirror and "
        "re-renders the persona pool — install_hooks.py does this on every run)",
        [repo / ".git" / "hooks", HOME / ".codex" / "skills", HOME / ".codex" / "agents",
         CLAUDE / "agents"],
        lambda: _apply_install_hooks(repo))] if mechanical else []
    return Check("hooks", Verdict.DOES_NOT_CONFORM if findings else Verdict.CONFORMS,
                 findings=findings, repairs=repairs)


def _apply_install_hooks(repo: Path) -> tuple[list[Path], str]:
    """Install the hooks, and report every tree the callee says it acted on — not just one.

    `install_hooks.py` writes in three places and used to be reported as writing in one. Its own
    stdout says which it touched on this run (`synced .codex/skills: …`, a `personas:` line, and
    the hook lines), so the changed set is read out of that rather than assumed. The exact file
    list inside the two machine-global trees is the callee's to know; naming the directories is
    the most precise honest claim available, and they are all in the plan.
    """
    r = run([PY, PD / "install_hooks.py", repo])
    if not r.ok or r.rc != 0:
        return [], f"FAILED — {r.why or (r.err or r.out).strip()[:300]}"
    changed = [repo / ".git" / "hooks"]
    notes = ["hooks installed"]
    if "synced .codex/skills" in r.out:
        changed.append(HOME / ".codex" / "skills")
        notes.append("machine-global Codex skill mirror refreshed")
    if re.search(r"^\s+wrote\s+\S", r.out, re.M):
        changed += [CLAUDE / "agents", HOME / ".codex" / "agents"]
        notes.append("machine-global persona trees re-rendered")
    return changed, "; ".join(notes)


def check_identifier_guard(repo: Path) -> Check:
    """Whether the identifier guard COULD run, in a repository that declares itself public.

    A guard whose deny-list is absent exits 2 by its own contract, and a guard that cannot run is
    the reason this file has a third state. Probed on an empty message rather than reasoned about:
    an empty message cannot contain an identifier, so a non-zero exit is about the guard, never
    about the content.

    Skipped, and reported as skipped rather than passed, in a repository that does not declare
    itself public — the guard is for deliberately public repositories only.
    """
    hooks = run([PY, PD / "install_hooks.py", repo, "--check"])
    if not hooks.ok or hooks.undefined_rc((0, 1, 2)):
        return Check("identifier guard", Verdict.NOT_RUN,
                     why_not_run=_why(hooks, "install_hooks.py --check (to learn public state)"))
    # THE SAME PARSE `check_hooks` ALREADY DOES, and it is shared now rather than written twice.
    #
    # This used to test for the lowercase literal `repository declares itself PUBLIC: yes`. The
    # callee's `declaration_line` returns `YES ({where}, dated {date})` — uppercase, with a stamp —
    # so the literal matched in NO repository that has ever existed. The whole public branch below
    # was unreachable: the deny-list liveness probe never ran, a genuinely public repository was
    # told in writing that it is not public, and a check that had examined nothing returned
    # CONFORMS and contributed 0 to the exit code. Exactly the class this file exists to prevent,
    # committed by this file, and it survived because the failure is silent in the common case —
    # every fixture and every live repository here is private, so the branch that was never taken
    # was also the branch nobody would notice.
    states = _hook_states(hooks.out)
    if not states:
        return Check("identifier guard", Verdict.NOT_RUN,
                     why_not_run=("install_hooks.py --check printed nothing this reader could "
                                  f"interpret, so whether this repository declares itself public "
                                  f"is UNKNOWN:\n{hooks.out.strip()[:300]}"))
    if not _declares_public(states):
        return Check("identifier guard", Verdict.CONFORMS,
                     note=("not applicable — this repository does not declare itself public, so "
                           "the private-identifier guard is correctly not in force. Nothing was "
                           "checked about it, and nothing needed to be."))
    empty = Path(os.devnull)
    g = run([PY, PD / "identifier_guard.py", "--message", empty])
    if not g.ok or g.undefined_rc((0, 1, 2)):
        return Check("identifier guard", Verdict.NOT_RUN, why_not_run=_why(g, "identifier_guard.py"))
    if g.rc == 2:
        return Check("identifier guard", Verdict.NOT_RUN,
                     why_not_run=("the identifier guard cannot run — its deny-list is absent, "
                                  "unreadable or empty. This repository declares itself PUBLIC, so "
                                  f"that is the guard that matters most: {(g.err or g.out).strip()[:300]}"))
    if g.rc == 1:
        return Check("identifier guard", Verdict.DOES_NOT_CONFORM,
                     findings=[Finding("the identifier guard rejected an EMPTY message, which means "
                                       "it is misconfigured rather than that anything was found",
                                       remedy="run identifier_guard.py --message /dev/null and read it")])
    return Check("identifier guard", Verdict.CONFORMS)


METH_COULD_NOT_EVALUATE = "could-not-evaluate"
METH_STALE = "stale"
METH_UNMANAGED = "unmanaged"
METH_DEFERRED = "deferred"
METH_UNADOPTED = "unadopted"

# THE CALLEE'S FIVE OUTPUT SHAPES, HOISTED OUT OF THE FUNCTION ON PURPOSE.
#
# `adoption_check` documents four states and has a fifth error path, and this table is the whole
# of what this file knows about distinguishing them — every signature is a phrase the callee emits
# and nothing here re-derives adoption from the filesystem. Hoisted to module level so it is
# visible as the coupling it is, and so a test can assert that `check_methodology` contains no
# comparison against a bare string literal of its own.
#
# ORDER MATTERS. `could not be evaluated` must be tested before anything else, and the unmanaged
# sub-case before the plain stale one, because both stale sub-cases share the same first line.
# Two of these five are CONFORMING outcomes and only one is mechanically repairable.
METHODOLOGY_STATES = (
    (METH_COULD_NOT_EVALUATE, "could not be evaluated"),
    (METH_UNMANAGED, "was not generated by this script"),
    (METH_STALE, "no longer matches the methodology source"),
    (METH_DEFERRED, "is deliberately deferred here since"),
    (METH_UNADOPTED, "has not been adopted by this repository"),
)


def _methodology_state(text: str) -> str | None:
    """Which of the callee's documented states this output is, or None when it is none of them."""
    for name, signature in METHODOLOGY_STATES:
        if signature in text:
            return name
    return None


def check_methodology(repo: Path) -> Check:
    """Execution-methodology adoption state, read from STDOUT because the exit code is always 0.

    `--adoption-check` ALWAYS exits 0, by contract, so a caller reading the exit code learns
    nothing at all — it is the clearest instance on this machine of the trap this file is built
    against. Not adopted is reported and NEVER repaired: adoption is staggered and deliberate and
    `sync_methodology.py`'s own docstring says nothing there ever adopts a repository on its own.
    Adopted-but-drifted is mechanical and is repaired.
    """
    r = run([PY, SYNC_METHODOLOGY, "--repo", repo, "--adoption-check"])
    if not r.ok:
        return Check("methodology", Verdict.NOT_RUN, why_not_run=_why(r, "sync_methodology.py"))
    if r.rc != 0:
        return Check("methodology", Verdict.NOT_RUN,
                     why_not_run=(f"--adoption-check exited {r.rc}; its contract is that it ALWAYS "
                                  f"exits 0, so this run cannot be interpreted: "
                                  f"{(r.err or r.out).strip()[:300]}"))
    text = r.out.strip()
    rendered = repo / "docs" / "agents" / "execution" / "methodology.md"

    # State 1 of 5: adopted and current. The callee says nothing at all, by design.
    if not text:
        return Check("methodology", Verdict.CONFORMS)

    state = _methodology_state(text)

    if state is METH_COULD_NOT_EVALUATE:
        return Check("methodology", Verdict.NOT_RUN, why_not_run=text)

    if state is METH_DEFERRED:
        # A CONFORMING OUTCOME, and the previous version got this exactly backwards. A recorded
        # deferral is one of the two ways a repository is allowed to stand; reporting it as
        # non-conformance told the founder to undo a decision he had deliberately written down,
        # on every run, with no remedy that could ever clear it.
        return Check("methodology", Verdict.CONFORMS, note=text)

    if state is METH_UNMANAGED:
        # The rendered file exists but the renderer did not write it, so a re-render REFUSES to
        # clobber it and returns 2. Offering that repair would have made every `--fix` exit 2
        # FAILED with the finding never clearing — the persona-drift no-op defect, rebuilt in a
        # different subsystem by this very file. The callee states the remedy that works; it is
        # relayed VERBATIM and in full rather than replaced with the one that does not.
        return Check("methodology", Verdict.DOES_NOT_CONFORM,
                     findings=[Finding(text, files=[str(rendered)], remedy=text)])

    if state is METH_STALE:
        return Check("methodology", Verdict.DOES_NOT_CONFORM,
                     findings=[Finding(text, files=[str(rendered)],
                                       remedy=f"sync_methodology.py --repo {repo}")],
                     repairs=[Repair("re-render the execution methodology", [rendered],
                                     lambda: _apply_methodology(repo))])

    if state is METH_UNADOPTED:
        return Check("methodology", Verdict.DOES_NOT_CONFORM,
                     findings=[Finding(
                         text,
                         remedy=(f"adoption is deliberate and staggered — nothing adopts a "
                                 f"repository on its own, including this tool. Adopt it on "
                                 f"purpose with `sync_methodology.py --repo {repo}`, or record a "
                                 f"deferral as the output above describes."))])

    # THE FAIL-SAFE, and it is the point of returning a sentinel rather than falling through to a
    # default. Output this reader does not recognise means the callee's states have changed and
    # this classification is stale. That is `could not be checked`, never a pass and never an
    # invented finding — the previous version's final `return DOES_NOT_CONFORM` was the default
    # branch, so every unrecognised state (including "could not be evaluated") was reported as a
    # confident non-conformance.
    return Check("methodology", Verdict.NOT_RUN,
                 why_not_run=("sync_methodology.py --adoption-check produced output matching none "
                              f"of its documented states, so this repository's adoption state is "
                              f"UNKNOWN:\n{text[:500]}"))


def _apply_methodology(repo: Path) -> tuple[list[Path], str]:
    target = repo / "docs" / "agents" / "execution" / "methodology.md"
    before = target.read_bytes() if target.is_file() else None
    r = run([PY, SYNC_METHODOLOGY, "--repo", repo])
    if not r.ok or r.rc != 0:
        return [], f"FAILED — {r.why or (r.err or r.out).strip()[:300]}"
    after = target.read_bytes() if target.is_file() else None
    return ([target], "re-rendered") if after != before else ([], "already up to date")


def check_github(repo: Path) -> Check:
    """GitHub posture, from the checker that owns it. Nothing here is ever repaired.

    `check_github.py` never creates a repository, never pushes and never changes visibility, and
    neither does this: those are the founder's call every time. Its `--apply-settings` is the one
    mutation it offers and it is not invoked from here either — turning off a remote's feature
    toggles is a change to the forge, not to the working tree, and it is not what `--fix` promises.
    """
    r = run([PY, PD / "check_github.py", repo, "--json"])
    if not r.ok or r.undefined_rc((0, 1, 2)):
        return Check("github", Verdict.NOT_RUN, why_not_run=_why(r, "check_github.py"))
    try:
        data = json.loads(r.out)
    except (ValueError, TypeError):
        return Check("github", Verdict.NOT_RUN,
                     why_not_run=(f"check_github.py --json did not emit JSON (exit {r.rc}): "
                                  f"{(r.out or r.err).strip()[:800]}"))
    # SEVERITY IS THE CALLEE'S RANKING AND IT IS HONOURED, NOT FLATTENED.
    #
    # `check_github.exit_code` is explicit: `unable` -> 2, `critical` -> 1, and everything else ->
    # 0. Turning every entry of `findings` into a non-conformance regardless of severity inverted
    # that for the one case it matters most. An ACTIVE, HONOURED public-exception waiver is emitted
    # with severity `exception`, which the callee's own comment describes as not unhealthy and not
    # actionable — so a deliberately-public repository reported `github DOES NOT CONFORM` on every
    # single run, with no remedy that could ever clear it, because the thing being reported was an
    # approval. Nothing is silenced: the non-critical severities go to `note`.
    entries = [(str(f.get("severity", "")), str(f.get("detail", "")))
               for f in (data.get("findings") or []) if isinstance(f, dict)]
    unable = [d for s, d in entries if s == "unable"]
    critical = [d for s, d in entries if s == "critical"]
    other = [(s, d) for s, d in entries if s not in ("unable", "critical")]
    note = ("; ".join(f"[{s}] {d}" for s, d in other)
            + "  (severity ranking is check_github.py's own; these do not gate its exit code)"
            ) if other else ""
    findings = [Finding(d, remedy="see check_github.py's own report; nothing here is auto-repaired")
                for d in critical]
    if r.rc == 2 or unable:
        return Check("github", Verdict.NOT_RUN, findings=findings, note=note,
                     why_not_run=("the GitHub posture was not fully determined — "
                                  + ("; ".join(unable) if unable else
                                     f"exit 2 with no `unable` finding: {r.err.strip()[:300]}")))
    if r.rc == 1 and not findings:
        # The callee raised 1 and this reader found no `critical` to attribute it to. Its contract
        # says only `critical` does that, so the contract has moved and this run is uninterpretable.
        return Check("github", Verdict.NOT_RUN, note=note,
                     why_not_run=("check_github.py exited 1 but emitted no `critical` finding, "
                                  "which its own exit_code contract says cannot happen"))
    return Check("github", Verdict.DOES_NOT_CONFORM if findings else Verdict.CONFORMS,
                 findings=findings, note=note)


def check_plugins() -> Check:
    """The plugin surface — MACHINE-GLOBAL, and consumed from `check_toolchain.py --json`.

    Not enumerated here. `check_toolchain.py` owns global toolchain consistency, already compares
    the two harnesses, and TC-41 put the enumeration there behind its existing `Run` chokepoint
    with a `plugins` key in the emitter. This reads that key.

    Every finding it produces is tagged `machine-global`, and the report prints the tag. A plugin
    lives in `~/.claude/plugins`; it is the same plugin in every repository on this machine, and a
    per-project tool that printed a per-machine fact without saying so would have someone fix it in
    one repository and expect the others to change. They will not.

    `plugins.claude.enumerated` being false means an incomplete list, not a short one — that
    distinction is the reason the field exists — so it becomes not-run rather than a clean plugin
    surface. And `plugins` being null means the enumeration did not happen at all.
    """
    r = run([PY, PD / "check_toolchain.py", "--json"])
    if not r.ok or r.undefined_rc((0, 1, 2)):
        return Check("plugin surface", Verdict.NOT_RUN, why_not_run=_why(r, "check_toolchain.py"))
    try:
        data = json.loads(r.out)
    except (ValueError, TypeError):
        return Check("plugin surface", Verdict.NOT_RUN,
                     why_not_run=(f"check_toolchain.py --json did not emit JSON (exit {r.rc}): "
                                  f"{(r.out or r.err).strip()[:800]}"))
    surface = data.get("plugins")
    if not surface:
        return Check("plugin surface", Verdict.NOT_RUN,
                     why_not_run=("check_toolchain.py emitted no plugin surface (`plugins` is null), "
                                  "so the plugin layer was not enumerated on this run"))
    claude = surface.get("claude") or {}
    if not claude.get("enumerated"):
        return Check("plugin surface", Verdict.NOT_RUN,
                     why_not_run=("the Claude plugin enumeration did not complete, so the list is "
                                  "incomplete rather than short — nothing about plugin shadowing "
                                  "can be concluded from it"))
    findings = [
        Finding(f.get("detail", ""), scope="machine-global",
                remedy="this is a fact about the machine, not this repository. Fixing it here "
                       "changes nothing; the same finding will appear in every repository until "
                       "the machine's plugin set changes.")
        for f in (data.get("findings") or [])
        if PLUGIN_FINDING_MARKER in f.get("detail", "").lower()
    ]
    if not claude.get("classified", True):
        return Check("plugin surface", Verdict.NOT_RUN, findings=findings,
                     why_not_run="the Claude plugin surface was enumerated but not classified")
    return Check("plugin surface",
                 Verdict.DOES_NOT_CONFORM if findings else Verdict.CONFORMS,
                 findings=findings)


def check_preflight(repo: Path) -> Check:
    """The environment preflight — machine facts a gate run will otherwise re-learn one at a time.

    Its contract: exit 0 whenever the checks RAN, findings on stdout as `PREFLIGHT:` lines, exit 2
    only when the check itself could not run. So, again, the exit code is not the answer and the
    stdout is. `NOTE:` lines are coverage statements, never findings, and its own docstring says so.
    """
    r = run([str(PREFLIGHT), str(repo)])
    if not r.ok or r.undefined_rc((0, 2)):
        return Check("preflight", Verdict.NOT_RUN, why_not_run=_why(r, "preflight.sh"))
    if r.rc == 2:
        return Check("preflight", Verdict.NOT_RUN,
                     why_not_run=f"preflight.sh could not complete: {(r.err or r.out).strip()[:300]}")
    findings = [Finding(line.split("PREFLIGHT:", 1)[1].strip(),
                        remedy="a machine fact; fix the machine, not the repository")
                for line in r.out.splitlines()
                if line.strip().startswith("PREFLIGHT:") and "PREFLIGHT: NOTE:" not in line]
    return Check("preflight", Verdict.DOES_NOT_CONFORM if findings else Verdict.CONFORMS,
                 findings=findings)


CHECKS = (
    ("personas", check_personas, True),
    ("route", check_route, True),
    ("hooks", check_hooks, True),
    ("identifier guard", check_identifier_guard, True),
    ("methodology", check_methodology, True),
    ("github", check_github, True),
    ("plugin surface", lambda _repo: check_plugins(), False),
    ("preflight", check_preflight, True),
)


CHECK_NAMES = tuple(name for name, _fn, _scoped in CHECKS)


def collect(repo: Path, only: tuple[str, ...] = ()) -> list[Check]:
    """Run every check. One check raising must never cost the others their turn.

    `only` narrows the selection, for the operator who has just repaired one thing and wants to
    re-check it without waiting on a network call. IT IS NOT A WAY TO GET A GREEN RUN: every
    consumer of this list is told what was excluded — `report` prints `SELECTION` above the
    verdict, `as_json` carries `excluded_by_request`, and the verdict word for a narrowed run is
    never printed without that line. A filtered run that read like a full one would be the
    `--standard`-shaped defect the route validator already had to fix.
    """
    out = []
    for name, fn, _scoped in CHECKS:
        if only and name not in only:
            continue
        try:
            out.append(fn(repo))
        except Exception as e:                # a bug here is a not-run, never a silent pass
            out.append(Check(name, Verdict.NOT_RUN,
                             why_not_run=f"this checker raised {type(e).__name__}: {e}"))
    return out


def aggregate(checks: list[Check]) -> tuple[Verdict, int]:
    """Fold several checkers' verdicts into one WITHOUT collapsing not-run into pass.

    Precedence is NOT_RUN > DOES_NOT_CONFORM > CONFORMS, so a single unexaminable check makes the
    whole run unexaminable. The alternative — reporting the findings that were found and shrugging
    at the check that did not run — is the exact shape of the defect this programme has recorded
    three times, and it is worse here than elsewhere because the repository is the one holding the
    health data.

    2 outranking 1 costs something and it is worth naming: a repository with real findings AND one
    broken checker exits 2, and a caller keying off `!= 0` cannot tell those apart. That is why the
    exit code is not the report. `--json` carries `not_run` and `findings` as separate arrays, and
    the human summary counts all three states in one line, so nothing is lost — only the single
    integer is lossy, and it is lossy in the safe direction.
    """
    if any(c.verdict is Verdict.NOT_RUN for c in checks):
        return Verdict.NOT_RUN, 2
    if any(c.verdict is Verdict.DOES_NOT_CONFORM for c in checks):
        return Verdict.DOES_NOT_CONFORM, 1
    return Verdict.CONFORMS, 0


def plan(checks: list[Check]) -> list[Repair]:
    return [r for c in checks for r in c.repairs]


def planned_files(checks: list[Check]) -> list[Path]:
    seen: list[Path] = []
    for r in plan(checks):
        for f in r.files:
            if f not in seen:
                seen.append(f)
    return seen


def excluded_by_request(checks: list[Check]) -> list[str]:
    ran = {c.name for c in checks}
    return [n for n in CHECK_NAMES if n not in ran]


def report(repo: Path, checks: list[Check], overall: Verdict, code: int) -> str:
    lines = [f"conformance: {repo}", ""]
    for c in checks:
        lines.append(f"  {c.name:<18} {c.verdict.value.upper()}")
        if c.why_not_run:
            lines.append(f"      why: {c.why_not_run}")
        if c.note:
            lines.append(f"      note: {c.note}")
        for f in c.findings:
            tag = "[machine-global] " if f.scope == "machine-global" else ""
            lines.append(f"      - {tag}{f.detail}")
            for path in f.files:
                lines.append(f"          file: {path}")
            if f.remedy:
                lines.append(f"          remedy: {f.remedy}")
    counts = {v: sum(1 for c in checks if c.verdict is v) for v in Verdict}
    lines += ["", f"  {counts[Verdict.CONFORMS]} conform, "
                  f"{counts[Verdict.DOES_NOT_CONFORM]} do not conform, "
                  f"{counts[Verdict.NOT_RUN]} COULD NOT BE CHECKED",
              f"  VERDICT: {overall.value.upper()} (exit {code})"]
    skipped = excluded_by_request(checks)
    if skipped:
        lines.append(f"  SELECTION: {len(checks)} of {len(CHECK_NAMES)} checks ran; NOT RUN BY "
                     f"REQUEST and therefore unknown: {', '.join(skipped)}. This verdict is about "
                     f"the checks that ran and about nothing else.")
    if overall is Verdict.NOT_RUN:
        lines.append("  A check that did not run is not a check that passed. This repository has "
                     "NOT been shown to conform.")
    repairs = plan(checks)
    lines += ["", "  REPAIR PLAN — every file `--fix` would touch, named before anything is touched:"]
    if not repairs:
        lines.append("      (nothing is mechanically repairable here)")
    for r in repairs:
        lines.append(f"      * {r.label}")
        for f in r.files:
            lines.append(f"          {f}")
    unfixable = [f for c in checks for f in c.findings
                 if f.remedy and not any(f.files and set(f.files) & {str(p) for p in r.files}
                                         for r in repairs)]
    if unfixable:
        lines.append("      Everything else above is reported only; read each `remedy:` line.")
    return "\n".join(lines)


def as_json(repo: Path, checks: list[Check], overall: Verdict, code: int) -> str:
    return json.dumps({
        "repo": str(repo),
        "verdict": overall.value,
        "exit": code,
        "counts": {v.value: sum(1 for c in checks if c.verdict is v) for v in Verdict},
        "checks": [{"name": c.name, "verdict": c.verdict.value, "note": c.note} for c in checks],
        "not_run": [{"check": c.name, "why": c.why_not_run}
                    for c in checks if c.verdict is Verdict.NOT_RUN],
        "excluded_by_request": excluded_by_request(checks),
        "findings": [{"check": c.name, "scope": f.scope, "detail": f.detail,
                      "files": f.files, "remedy": f.remedy}
                     for c in checks for f in c.findings],
        "repair_plan": [{"label": r.label, "files": [str(f) for f in r.files]}
                        for r in plan(checks)],
    }, indent=2)


def _key(p: Path) -> str:
    """Compare paths by their resolved form.

    Not cosmetic. `_apply_render` learns which files changed by reading `sync_personas`' stdout,
    which prints whatever path it was handed, and on macOS `/var` is a symlink to `/private/var`.
    A string comparison therefore reported a repair as having stepped outside its own plan when it
    had done nothing of the kind — a false CONTRACT VIOLATION, which is the same disablement as a
    false finding, one level up. Found by the plan-vs-changed test, which is what it is for.
    """
    try:
        return str(Path(p).resolve())
    except OSError:
        return str(p)


def apply_fixes(checks: list[Check]) -> tuple[list[str], list[Path], bool]:
    allowed = {_key(p) for p in planned_files(checks)}
    lines: list[str] = ["", "  APPLYING —"]
    changed_all: list[Path] = []
    ok = True
    for r in plan(checks):
        changed, note = r.apply()
        if note.startswith("FAILED"):
            ok = False
        lines.append(f"    {r.label}: {note}")
        for p in changed:
            lines.append(f"      changed: {p}")
            changed_all.append(p)
    outside = sorted(str(p) for p in changed_all if _key(p) not in allowed)
    if outside:
        ok = False
        lines.append("    CONTRACT VIOLATION — these were changed but were NOT in the plan:")
        lines += [f"      {p}" for p in outside]
    if not changed_all:
        lines.append("    nothing was changed by this run"
                     + (" — there was nothing mechanically repairable to attempt"
                        if not plan(checks) else
                        " — every repair reported it had nothing left to do, which is what a "
                        "second --fix must look like"))
    return lines, changed_all, ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Does this repository still meet the standard? Report, then repair on request.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fix", action="store_true",
                    help="apply exactly what the report named; never anything else")
    ap.add_argument("--only", default="",
                    help=f"comma-separated subset of: {', '.join(CHECK_NAMES)}. "
                         f"The report always names what was excluded.")
    a = ap.parse_args(argv)

    repo = Path(a.root).resolve()
    if not repo.is_dir():
        print(f"conformance: {repo} is not a directory", file=sys.stderr)
        return 2

    only = tuple(n.strip() for n in a.only.split(",") if n.strip())
    unknown = [n for n in only if n not in CHECK_NAMES]
    if unknown:
        print(f"conformance: --only names no such check: {', '.join(unknown)}. "
              f"Known: {', '.join(CHECK_NAMES)}", file=sys.stderr)
        return 2

    checks = collect(repo, only)
    overall, code = aggregate(checks)

    if a.json:
        print(as_json(repo, checks, overall, code))
        if a.fix:
            print("conformance: --fix and --json together is refused; the report must be read "
                  "before the repair", file=sys.stderr)
            return 2
        return code

    print(report(repo, checks, overall, code))

    if not a.fix:
        return code

    lines, _changed, ok = apply_fixes(checks)
    print("\n".join(lines))
    if not ok:
        print("  a repair failed or stepped outside the plan; nothing further was attempted",
              file=sys.stderr)
        return 2

    after = collect(repo, only)
    overall2, code2 = aggregate(after)
    print("")
    print(report(repo, after, overall2, code2))
    return code2


if __name__ == "__main__":
    sys.exit(main())
