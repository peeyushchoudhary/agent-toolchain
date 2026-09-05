#!/usr/bin/env python3
"""Aggregate owning conformance checks and apply only their approved mechanical repairs.

Every subprocess runs from the sibling skill bundle containing this checker. Methodology readiness
comes only from `sync_methodology.py --status-json`; malformed or contradictory status fails
closed. Hook and persona repairs use their explicit project scopes, so repository maintenance has
no machine-global write side effect. `--fix` can render only an already approved `repairable`
runtime and reverifies owner status after every apply. It never adopts, upgrades, publishes, or
deletes unmanaged content.

Exit 0 means all selected checks conform, 1 means a completed check found drift, and 2 means at
least one selected check could not be trusted. Findings already collected remain in either case.

Usage:
  check_conformance.py [ROOT]
  check_conformance.py [ROOT] --json
  check_conformance.py [ROOT] --fix
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

EXPLICIT_TOOLCHAIN_HOME = os.environ.get("PROJECT_CONFORMANCE_HOME")
HOME = Path(EXPLICIT_TOOLCHAIN_HOME) if EXPLICIT_TOOLCHAIN_HOME else Path.home()
CLAUDE = HOME / ".claude"
# Maintenance runs against the bundle that contains this checker. Falling back to a live HOME
# could mix the candidate consumer with older installed producers and, under --fix, write output
# from an unapproved source.
SKILLS = (CLAUDE / "skills" if EXPLICIT_TOOLCHAIN_HOME
          else Path(__file__).resolve().parents[2])
PD = SKILLS / "progressive-disclosure" / "scripts"
SYNC_PERSONAS = SKILLS / "agent-personas" / "scripts" / "sync_personas.py"
SYNC_METHODOLOGY = SKILLS / "execution-methodology" / "scripts" / "sync_methodology.py"
SPEC_CHECK = SKILLS / "execution-methodology" / "scripts" / "spec_check.py"
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
# The working remedy for an unmanaged generated agent, stated because the advertised one is a
# no-op. See the module docstring; a test drives the no-op against the real tool.
UNMANAGED_REMEDY = (
    "The project-scoped renderer preserves unmanaged content and refuses all writes while this "
    "finding exists. The remedies that work are: "
    "(a) delete the file, if it was a hand-written agent that should never have existed, or "
    "(b) give it a persona source at `docs/agents/personas/<name>.md`, if the agent is wanted — "
    "then re-render. This tool will not delete it for you."
)


ORPHAN_REMEDY = (
    "an orphan is a file the project-scoped renderer would delete, so it remains a founder "
    "decision. If it was retired on purpose, invoke that deletion explicitly. If it should "
    "survive, restore its source under docs/agents/personas/ first."
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

@dataclass
class Stale:
    """Project operations from the persona owner's complete structured preview."""

    total: int = 0
    regenerable: list[str] = field(default_factory=list)
    orphaned: list[str] = field(default_factory=list)

    @property
    def seen(self) -> int:
        return len(self.regenerable) + len(self.orphaned)


def _persona_scopes(repo: Path) -> tuple[dict[str, Stale], Run | None]:
    """Adapt the persona owner's project preview to the existing stale categories."""
    argv = [PY, SYNC_PERSONAS, "--scope", "project", "--repo", repo, "--preview", "--json"]
    r = run(argv)
    operations, findings, error = _scoped_plan(r, "sync_personas.py", "project",
                                                (repo / ".claude" / "agents",
                                                 repo / ".codex" / "agents"))
    if error or findings:
        why = error or "; ".join(f.detail for f in findings)
        return {}, Run(r.argv, r.ok, r.rc, r.out, r.err, why=why)
    stale = Stale(total=len(operations))
    for action, path in operations:
        if action == "delete":
            stale.orphaned.append(str(path))
        else:
            stale.regenerable.append(str(path))
    return {"repository": stale}, None


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
    for path in stale.orphaned:
        out.append(Finding(
            f"{Path(path).name} in {where} carries the generated banner but its persona is no "
            f"longer in the pool. A WRITE RUN OF THE RENDERER DELETES THIS FILE with `unlink()`. "
            f"This tool will not do that for you",
            scope=scope, files=[path], remedy=ORPHAN_REMEDY.format(repo=repo)))
    return out


def _render_blockers(scopes: dict[str, Stale]) -> list[str]:
    """Why the re-render repair must NOT be offered. Empty means it is safe to offer.

    Deletions remain a founder decision even when the owning preview names them exactly.
    """
    why: list[str] = []
    for scope, stale in scopes.items():
        if stale.orphaned:
            why.append(f"{len(stale.orphaned)} orphaned file(s) in the {scope} scope would be "
                       f"DELETED by a write run")
    return why


def check_personas(repo: Path) -> Check:
    """Check the owner's project preview and emitted project judge restrictions.

    Preview, apply and recheck all use explicit project scope. The owner identifies generated
    drift and unmanaged content; this consumer separately applies the owner's own restriction
    function to emitted project judge artifacts because those are what the harness loads.
    """
    scopes, failed = _persona_scopes(repo)
    if failed is not None:
        _operations, owner_findings, owner_error = _scoped_plan(
            failed, "sync_personas.py", "project", (repo / ".claude" / "agents",
                                                     repo / ".codex" / "agents"))
        for finding in owner_findings:
            if PERSONA_UNMANAGED_MARKER in finding.detail:
                finding.remedy = UNMANAGED_REMEDY
        return Check("personas", Verdict.NOT_RUN,
                     findings=owner_findings,
                     why_not_run=(owner_error or failed.why or
                                  f"sync_personas.py --check exited {failed.rc}: "
                                  f"{(failed.err or failed.out).strip()[:400]}")
                     + f" [{' '.join(failed.argv)}]")

    findings: list[Finding] = []
    repairs: list[Repair] = []
    for scope, stale in scopes.items():
        findings.extend(_stale_findings(scope, repo, stale))

    # The explicit project plan is the exact mutation scope of the repair.
    regenerable = [p for s in scopes.values() for p in s.regenerable]
    blockers = _render_blockers(scopes)
    if blockers:
        findings.append(Finding(
            "no re-render repair is offered: " + "; ".join(blockers)
            + ". Running the renderer here is the founder's call, not this tool's",
            remedy=ORPHAN_REMEDY.format(repo=repo)))
    elif regenerable:
        repairs.append(Repair(
            "re-render the project generated agent files",
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
            f"`sync_personas.py --scope project --repo {repo}`. A deny-list cannot close this: "
            f"it is default-open "
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


def _apply_render(repo: Path) -> tuple[list[Path], str]:
    """Re-preview, apply exactly project scope, then require an empty owner preview."""
    scopes, failed = _persona_scopes(repo)
    if failed is not None:
        return [], (f"FAILED — refusing to run the renderer: the pre-write re-check could not "
                    f"enumerate what it would touch ({failed.why or f'exit {failed.rc}'})")
    blockers = _render_blockers(scopes)
    if blockers:
        return [], ("FAILED — refusing to run the renderer, nothing was written: "
                    + "; ".join(blockers))

    planned = [Path(path) for stale in scopes.values() for path in stale.regenerable]
    before = {path: path.read_bytes() if path.is_file() else None for path in planned}
    r = run([PY, SYNC_PERSONAS, "--scope", "project", "--repo", repo])
    if not r.ok or r.rc != 0:
        return [], f"FAILED — {r.why or (r.err or r.out).strip()[:300]}"
    changed = [path for path in planned
               if (path.read_bytes() if path.is_file() else None) != before[path]]
    after_scopes, after_failed = _persona_scopes(repo)
    if after_failed is not None or any(stale.seen for stale in after_scopes.values()):
        return changed, "FAILED — project persona apply did not reverify cleanly"
    if not changed:
        return [], "already up to date"
    return changed, f"re-rendered {len(changed)} project file(s)"


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


def _scoped_plan(r: Run, owner: str, scope: str, roots: tuple[Path, ...]) \
        -> tuple[list[tuple[str, Path]], list[Finding], str | None]:
    """Read the shared preview envelope used by the hook and persona owners."""
    if not r.ok or r.rc not in (0, 2):
        return [], [], _why(r, owner)
    if not r.out.strip():
        return [], [], f"{owner} preview printed no JSON object"
    try:
        payload = json.loads(r.out)
    except json.JSONDecodeError as exc:
        return [], [], f"{owner} preview printed malformed JSON: {exc}"
    if not (isinstance(payload, dict)
            and set(payload) == {"schema_version", "scope", "operations", "findings"}
            and payload["schema_version"] == 1 and payload["scope"] == scope
            and isinstance(payload["operations"], list) and isinstance(payload["findings"], list)):
        return [], [], f"{owner} preview envelope is invalid"
    findings: list[Finding] = []
    for item in payload["findings"]:
        if not (isinstance(item, dict) and isinstance(item.get("code"), str)
                and isinstance(item.get("message"), str)):
            return [], findings, f"{owner} preview contains an invalid finding"
        findings.append(Finding(f"{item['code']}: {item['message']}"))
    operations: list[tuple[str, Path]] = []
    resolved_roots = tuple(root.resolve() for root in roots)
    for item in payload["operations"]:
        if not (isinstance(item, dict) and set(item) == {"action", "path"}
                and item["action"] in {"create", "update", "delete"}
                and isinstance(item["path"], str)):
            return [], findings, f"{owner} preview contains an invalid operation"
        path = Path(item["path"])
        if not path.is_absolute():
            return [], findings, f"{owner} preview contains a non-absolute path: {path}"
        resolved = path.resolve()
        if not any(resolved == root or root in resolved.parents for root in resolved_roots):
            return [], findings, f"{owner} preview path escapes scope {scope}: {path}"
        operations.append((item["action"], resolved))
    if r.rc == 2 and not findings:
        return operations, findings, f"{owner} preview exited 2 without a finding"
    return operations, findings, None


def check_hooks(repo: Path) -> Check:
    """Consume the hook owner's write-equivalent project preview."""
    r = run([PY, PD / "install_hooks.py", repo, "--scope", "project", "--preview", "--json"])
    operations, owner_findings, error = _scoped_plan(
        r, "install_hooks.py", "project", (repo,))
    if error or owner_findings:
        return Check("hooks", Verdict.NOT_RUN, findings=owner_findings,
                     why_not_run=error or "install_hooks.py project preview reported blockers")
    if not operations:
        return Check("hooks", Verdict.CONFORMS)
    files = [path for _action, path in operations]
    findings = [Finding(f"hook owner plans {action}: {path}", files=[str(path)],
                        remedy=f"install_hooks.py {repo} --scope project")
                for action, path in operations]
    return Check("hooks", Verdict.DOES_NOT_CONFORM, findings=findings,
                 repairs=[Repair("apply the project-scoped hook plan", files,
                                 lambda: _apply_install_hooks(repo))])


def _apply_install_hooks(repo: Path) -> tuple[list[Path], str]:
    before_check = check_hooks(repo)
    if before_check.verdict is Verdict.NOT_RUN or not before_check.repairs:
        return [], "FAILED — hook plan is no longer verified repairable"
    files = before_check.repairs[0].files
    before = {path: path.read_bytes() if path.is_file() else None for path in files}
    r = run([PY, PD / "install_hooks.py", repo, "--scope", "project"])
    if not r.ok or r.rc != 0:
        return [], f"FAILED — {r.why or (r.err or r.out).strip()[:300]}"
    changed = [path for path in files
               if (path.read_bytes() if path.is_file() else None) != before[path]]
    verified = check_hooks(repo)
    if verified.verdict is not Verdict.CONFORMS:
        return changed, "FAILED — project hook apply did not reverify cleanly"
    notes = ["project hooks installed"]
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


RUNTIME_STATES = frozenset({"current", "repairable", "legacy", "source_changed", "unadopted",
                            "deferred", "unmanaged", "invalid"})
RUNTIME_NON_READY_REMEDIES = {
    "legacy": "the runtime identity needs explicit reconciliation; --fix will not upgrade it",
    "source_changed": "restore or approve the changed source explicitly; --fix will not upgrade it",
    "unadopted": "adoption is deliberate; invoke methodology management to approve it",
    "deferred": "the recorded deferral remains in force; no adoption is attempted",
    "unmanaged": "move or reconcile the unmanaged output before rendering",
    "invalid": "repair the owning runtime inspection and run conformance again",
}
PERSONA_UNMANAGED_MARKER = "unmanaged_persona"


def _runtime_status_error(payload: object) -> str | None:
    """Validate frozen wire types and the semantic coherence consumers depend on."""
    if not isinstance(payload, dict):
        return "the JSON value is not an object"
    required = {"schema_version", "state", "ready", "approved", "installed", "route", "overlay",
                "dependencies", "findings", "repair_candidates"}
    if set(payload) != required:
        return f"top-level fields differ from schema_version 1 (got {sorted(payload)})"
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1 \
            or not isinstance(payload["state"], str) or payload["state"] not in RUNTIME_STATES:
        return "schema_version or state is unknown"
    state = payload["state"]
    if type(payload["ready"]) is not bool or payload["ready"] != (state == "current"):
        return "ready contradicts state"

    identity_keys = {"version", "source_sha256", "runtime_sha256", "bundle_root"}

    def identity(value: object) -> bool:
        return (value is None or (isinstance(value, dict) and set(value) == identity_keys
                and all(isinstance(value[key], str) for key in identity_keys)))

    if not identity(payload["approved"]) or not identity(payload["installed"]):
        return "approved or installed identity has an invalid shape"
    route = payload["route"]
    if not (isinstance(route, dict) and set(route) == {"valid", "detail"}
            and type(route["valid"]) is bool and isinstance(route["detail"], str)):
        return "route has an invalid shape"
    overlay = payload["overlay"]
    if not (isinstance(overlay, dict)
            and set(overlay) == {"valid", "sha256", "expected_sha256", "detail"}
            and type(overlay["valid"]) is bool and isinstance(overlay["detail"], str)
            and all(overlay[key] is None or isinstance(overlay[key], str)
                    for key in ("sha256", "expected_sha256"))):
        return "overlay has an invalid shape"

    dependencies = payload["dependencies"]
    dependency_keys = {"path", "stage", "status", "expected_sha256", "actual_sha256"}
    if not isinstance(dependencies, list):
        return "dependencies is not an array"
    for item in dependencies:
        if not (isinstance(item, dict) and set(item) == dependency_keys
                and isinstance(item["path"], str) and isinstance(item["stage"], str)
                and isinstance(item["status"], str)
                and item["status"] in {"current", "missing", "changed", "invalid"}
                and all(item[key] is None or isinstance(item[key], str)
                        for key in ("expected_sha256", "actual_sha256"))):
            return "a dependency has an invalid shape"

    findings = payload["findings"]
    finding_keys = {"code", "severity", "message", "path"}
    if not isinstance(findings, list):
        return "findings is not an array"
    for item in findings:
        if not (isinstance(item, dict) and set(item) == finding_keys
                and isinstance(item["code"], str)
                and isinstance(item["severity"], str)
                and item["severity"] in {"info", "warning", "error"}
                and isinstance(item["message"], str)
                and (item["path"] is None or isinstance(item["path"], str))):
            return "a finding has an invalid shape"

    candidates = payload["repair_candidates"]
    if not isinstance(candidates, list):
        return "repair_candidates is not an array"
    for item in candidates:
        if not (isinstance(item, dict) and set(item) == {"action", "paths"}
                and item["action"] == "render_approved" and isinstance(item["paths"], list)
                and item["paths"] and all(isinstance(path, str) for path in item["paths"])):
            return "a repair candidate has an invalid shape"
    if (state == "repairable") != bool(candidates):
        return "repair_candidates contradict state"
    if state in {"current", "repairable"}:
        if payload["approved"] is None or payload["installed"] is None:
            return f"{state} requires approved and installed identities"
        if payload["approved"] != payload["installed"]:
            return f"{state} approved and installed identities differ"
    if state == "current" and (not route["valid"] or not overlay["valid"] or not dependencies
                                or any(item["status"] != "current" for item in dependencies)):
        return "current has an invalid route, overlay, or dependency"
    if state == "repairable" and (not route["valid"] or not overlay["valid"] or not dependencies
                                   or any(item["status"] != "current" for item in dependencies)):
        return "repairable has a changed route, overlay, or dependency"
    return None


def _runtime_findings(payload: dict) -> list[Finding]:
    findings = [Finding(
        f"[{item['severity']}] {item['code']}: {item['message']}",
        files=[item["path"]] if item["path"] is not None else [],
        remedy=RUNTIME_NON_READY_REMEDIES.get(payload["state"], ""),
    ) for item in payload["findings"]]
    if not findings and payload["state"] != "current":
        findings.append(Finding(f"execution runtime state is {payload['state']}",
                                remedy=RUNTIME_NON_READY_REMEDIES.get(payload["state"], "")))
    return findings


def _candidate_paths(repo: Path, payload: dict) -> tuple[list[Path], str | None]:
    paths: list[Path] = []
    root = repo.resolve()
    for candidate in payload["repair_candidates"]:
        for raw in candidate["paths"]:
            path = Path(raw)
            path = path if path.is_absolute() else repo / path
            try:
                resolved = path.resolve()
            except OSError as exc:
                return [], f"repair candidate could not be resolved: {exc}"
            if resolved != root and root not in resolved.parents:
                return [], f"repair candidate escapes the repository: {raw}"
            if resolved not in paths:
                paths.append(resolved)
    return paths, None


def check_methodology(repo: Path) -> Check:
    """Consume the methodology owner's typed status without reclassifying adoption."""
    r = run([PY, SYNC_METHODOLOGY, "--repo", repo, "--status-json"])
    if not r.ok:
        return Check("methodology", Verdict.NOT_RUN, why_not_run=_why(r, "sync_methodology.py"))
    if r.rc not in (0, 2):
        return Check("methodology", Verdict.NOT_RUN,
                     why_not_run=f"--status-json exited undefined status {r.rc}: "
                                 f"{(r.err or r.out).strip()[:300]}")
    if not r.out.strip():
        return Check("methodology", Verdict.NOT_RUN,
                     why_not_run="sync_methodology.py --status-json printed no JSON object")
    try:
        payload = json.loads(r.out)
    except json.JSONDecodeError as exc:
        return Check("methodology", Verdict.NOT_RUN,
                     why_not_run=f"sync_methodology.py --status-json printed malformed JSON: {exc}")
    invalid = _runtime_status_error(payload)
    try:
        findings = (_runtime_findings(payload) if isinstance(payload, dict)
                    and isinstance(payload.get("findings"), list) else [])
    except (KeyError, TypeError):
        findings = []
    if invalid:
        return Check("methodology", Verdict.NOT_RUN, findings=findings,
                     why_not_run=f"runtime status contradicted schema_version 1: {invalid}")
    if r.rc == 2:
        if payload["state"] != "invalid":
            return Check("methodology", Verdict.NOT_RUN, findings=findings,
                         why_not_run="runtime status exited 2 without state=invalid")
        if not any(item["code"] == "inspection_error" for item in payload["findings"]):
            return Check("methodology", Verdict.NOT_RUN, findings=findings,
                         why_not_run="invalid runtime status lacks inspection_error")
        return Check("methodology", Verdict.NOT_RUN, findings=findings,
                     why_not_run="the owning runtime inspection failed")
    if payload["state"] == "invalid":
        return Check("methodology", Verdict.NOT_RUN, findings=findings,
                     why_not_run="runtime status reported invalid with exit 0")
    if payload["state"] == "current":
        return Check("methodology", Verdict.CONFORMS, note="execution runtime is current")
    repairs: list[Repair] = []
    if payload["state"] == "repairable":
        paths, unsafe = _candidate_paths(repo, payload)
        if unsafe:
            return Check("methodology", Verdict.NOT_RUN, findings=findings, why_not_run=unsafe)
        approved = dict(payload["approved"])
        planned_overlay = payload["overlay"]["expected_sha256"]
        repairs.append(Repair("render the exact approved execution runtime", paths,
                              lambda approved=approved, planned_overlay=planned_overlay,
                              paths=tuple(paths):
                              _apply_methodology(repo, approved, planned_overlay, list(paths))))
    return Check("methodology", Verdict.DOES_NOT_CONFORM, findings=findings, repairs=repairs,
                 note=("recorded exclusion: deferred" if payload["state"] == "deferred" else ""))


def _apply_methodology(repo: Path, approved: dict, planned_overlay: str | None,
                       candidates: list[Path]) -> tuple[list[Path], str]:
    """Carry the plan's exact approved identity through owner repair and postcondition."""
    before = {path: path.read_bytes() if path.is_file() else None for path in candidates}
    authorization = {"identity": approved, "overlay_expected_sha256": planned_overlay}
    frozen = json.dumps(authorization, sort_keys=True, separators=(",", ":"))
    r = run([PY, SYNC_METHODOLOGY, "--repo", repo, "--repair-approved", frozen])
    if not r.ok or r.rc != 0:
        return [], f"FAILED — {r.why or (r.err or r.out).strip()[:300]}"
    changed = [path for path in candidates
               if (path.read_bytes() if path.is_file() else None) != before[path]]
    verified = run([PY, SYNC_METHODOLOGY, "--repo", repo, "--status-json"])
    try:
        payload = json.loads(verified.out)
    except (json.JSONDecodeError, TypeError):
        payload = None
    invalid = _runtime_status_error(payload)
    if (not verified.ok or verified.rc != 0 or invalid or payload["state"] != "current"
            or payload["approved"] != approved or payload["installed"] != approved
            or payload["overlay"]["expected_sha256"] != planned_overlay
            or payload["overlay"]["sha256"] != planned_overlay):
        return changed, "FAILED — repair completed but the frozen approved identity did not reverify"
    return (changed, "re-rendered approved runtime") if changed else ([], "already up to date")


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


# `spec_check.py` PRINTS this count and does not carry it in `--json`. `binding_payload()` emits
# `no_front_matter` but not `unbound_specs`, and the whole `binding` object is absent from the JSON
# when the repository has no persona pool. Adding the key there is the obvious repair and is not
# this file's to make: `spec_check.py` is owned by `execution-methodology`, and the copy this
# toolchain publishes is a vendored mirror of the installed one, so a key added on one side alone
# is drift. So the count is read from the human run, and `check_product_definition` says so out
# loud rather than quietly reporting a zero it never measured.
UNBOUND_SPECS = re.compile(r"(?P<n>\d+) document\(s\) under docs/product/specs/ are not named")

PRODUCT_REMEDY = (
    "read `spec_check.py --root <repo>`'s own output, then plan the move with "
    "`migrate_to_standard.py <repo> --product`, which is dry-run by default and prints every "
    "rename and every front-matter key it would add before it is given `--apply`. It refuses the "
    "documents it cannot derive an id for rather than inventing one, and it never edits a body. "
    "NOTHING HERE REWRITES A PRODUCT DOCUMENT: this check reports and stops. A spec is a human "
    "artifact whose front matter records who reviewed it and when, and a tool that invented those "
    "keys would be forging the review record the whole layer exists to hold — which is why the "
    "migrator adds `id`, `title` and `updated` from what the document already says, and leaves "
    "`status` and `reviewed_by` for a person."
)


def check_product_definition(repo: Path) -> Check:
    """The product-definition layer: does it exist, and is any of it in a shape a rule can read?

    THE CHECK THIS FILE WAS MISSING FOR A REASON WORTH STATING. The eight checks above predate the
    product-definition layer entirely — specs, front matter, acceptance criteria, waves, traces,
    milestone seals. On a repository that has not migrated to that layer, all eight can be satisfied
    at once: the personas are synced, the route validates, the hooks are installed, and the
    methodology render is current. The tool then printed CONFORMS. The one thing it repaired was the
    methodology render — the DOCUMENT DESCRIBING the layer — while the layer itself was absent. A
    conformance report whose only mechanical act is to refresh the description of something that is
    not there is worse than silence, because it is signed.

    REPORTS ONLY, AND OWNS NO REPAIR. Every other check that reports also repairs, and this one
    deliberately does not, so the asymmetry is explained here rather than left to look like an
    oversight. `--fix` may only do what the report named, and what this report names is a migration:
    writing front matter onto a document, or renaming it into the shape a rule binds. Front matter
    carries `reviewed_by:` and a status enum — a claim about a human. Generating it would manufacture
    the approval record. Renaming a spec silently re-points every reference to it. Both are the
    migrator's work, performed once, watched. `plan()` therefore never sees a `Repair` from here and
    the repair plan cannot grow a product document by accident.

    THREE FACTS, IN THE ORDER THEY STOP MATTERING. Whether `docs/product/` exists at all; how many
    of the documents a schema rule binds carry no front matter; how many sit under
    `docs/product/specs/` in a naming shape no rule reads. The third is the quiet one and it is why
    the exit code of `spec_check.py` is not the answer here either: a repository whose specs are all
    named outside `F-<n>-<slug>.md` has NOTHING inspected and exits 0 for it.
    """
    product = repo / "docs" / "product"
    if not product.is_dir():
        # Not a not-run. The absence IS the measurement, and it is the loudest form of the finding:
        # there is no product-definition layer in this repository at all. Reported without running
        # spec_check, because a linter pointed at a directory that does not exist reports nothing
        # and exits 0, which is indistinguishable from a clean one.
        return Check("product definition", Verdict.DOES_NOT_CONFORM,
                     findings=[Finding("`docs/product/` does not exist: this repository has no "
                                       "product-definition layer, so no specification, acceptance "
                                       "criterion, wave plan, trace or milestone seal can be read "
                                       "from it, and every product-definition rule in this "
                                       "toolchain is silent here rather than satisfied",
                                       files=[str(product)], remedy=PRODUCT_REMEDY)])

    r = run([PY, SPEC_CHECK, "--root", repo, "--json"])
    if not r.ok or r.undefined_rc((0, 1)):
        return Check("product definition", Verdict.NOT_RUN, why_not_run=_why(r, "spec_check.py"))
    try:
        data = json.loads(r.out)
    except (ValueError, TypeError):
        return Check("product definition", Verdict.NOT_RUN,
                     why_not_run=(f"spec_check.py --json did not emit JSON (exit {r.rc}): "
                                  f"{(r.out or r.err).strip()[:800]}"))

    # THE SECOND INVOCATION, and it is not laziness. See `UNBOUND_SPECS` above: the count of
    # documents no rule binds exists only on the human-readable run. A failure here is NOT a
    # not-run for the whole check — the two facts already in hand are still facts — so it degrades
    # to "not measured" and says which of the three numbers is missing.
    human = run([PY, SPEC_CHECK, "--root", repo])
    unbound, unbound_why = None, ""
    if not human.ok or human.undefined_rc((0, 1)):
        unbound_why = _why(human, "spec_check.py (second, non-JSON run)")
    else:
        found = UNBOUND_SPECS.search(human.out)
        # No match means the note was silent, and the note is silent exactly when the count is 0.
        unbound = int(found.group("n")) if found else 0

    binding = data.get("binding") or {}
    findings: list[Finding] = []
    notes: list[str] = []

    if not binding:
        # `binding` is omitted when the repository has no `docs/agents/personas/`. `no_front_matter`
        # is a member of that object, so it was not measured — not zero.
        notes.append("spec_check.py emitted no `binding` object, which happens when the repository "
                     "has no `docs/agents/personas/` pool; the front-matter count is part of that "
                     "object and so was NOT MEASURED on this run, which is not the same as zero")
    else:
        no_fm = int(binding.get("no_front_matter") or 0)
        bound_docs = int(binding.get("documents") or 0)
        product_docs = int(binding.get("product_documents") or 0)
        notes.append(f"{product_docs} document(s) under docs/product, {bound_docs} of them bound "
                     f"by a schema rule")
        if no_fm:
            findings.append(Finding(
                f"{no_fm} of the {bound_docs} spec/PRD/milestone document(s) a schema rule binds "
                f"carry no `---` front-matter block, so status, id and `reviewed_by:` cannot be "
                f"read from them and every rule that keys on those is silent for them",
                files=[str(product)], remedy=PRODUCT_REMEDY))
        if bound_docs == 0 and product_docs:
            findings.append(Finding(
                f"none of the {product_docs} document(s) under docs/product is bound by a schema "
                f"rule: nothing there is a spec, a PRD or a milestone as this toolchain names "
                f"them, so the layer is present in name and unread in fact",
                files=[str(product)], remedy=PRODUCT_REMEDY))

    if unbound is None:
        notes.append("the count of documents under docs/product/specs/ that no rule binds was NOT "
                     "MEASURED: " + unbound_why)
    elif unbound:
        findings.append(Finding(
            f"{unbound} document(s) under docs/product/specs/ are not named `F-<n>-<slug>.md`, so "
            f"no schema rule and no persona binding reads them. spec_check.py inspected none of "
            f"them and can still exit 0 for it, which is why this is reported here",
            files=[str(product / "specs")], remedy=PRODUCT_REMEDY))

    count = int(data.get("count") or 0)
    if count:
        notes.append(f"spec_check.py itself reports {count} finding(s) (exit {data.get('exit')}); "
                     f"they are its to explain, not restated here")

    # A `spec_check` exit of 1 with nothing this reader could attribute it to is not a pass. It is
    # the same shape as `check_github`'s guard above: the callee's contract has moved out from under
    # the reader, and a reader that reports CONFORMS on a callee it no longer understands is the
    # false green this whole file is built against.
    if r.rc == 1 and not findings:
        return Check("product definition", Verdict.NOT_RUN, note="; ".join(n for n in notes if n),
                     why_not_run=(f"spec_check.py exited 1 with {count} finding(s), and none of "
                                  f"them is one of the three facts this check reads, so the "
                                  f"product-definition state was not determined here"))

    return Check("product definition",
                 Verdict.DOES_NOT_CONFORM if findings else Verdict.CONFORMS,
                 findings=findings, note="; ".join(n for n in notes if n))


CHECKS = (
    ("personas", check_personas, True),
    ("route", check_route, True),
    ("hooks", check_hooks, True),
    ("identifier guard", check_identifier_guard, True),
    ("methodology", check_methodology, True),
    ("github", check_github, True),
    ("plugin surface", lambda _repo: check_plugins(), False),
    ("preflight", check_preflight, True),
    ("product definition", check_product_definition, True),
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
