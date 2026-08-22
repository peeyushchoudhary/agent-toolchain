#!/usr/bin/env python3
"""Render the execution methodology into a repository so both harnesses read the same rules.

The methodology is authored once, harness-neutral, in `methodology.md`. This renders it to:

  <repo>/docs/agents/execution/methodology.md   the in-repo copy Claude Code and Codex both read

Rendering is not a convenience. Codex CLI has no Skill tool, so a skill living in `~/.claude/skills`
is invisible to it; in-repo markdown is the only channel both harnesses reliably read. Keeping the
copy generated rather than hand-maintained is what stops three repositories from slowly running
three different methodologies.

Per-project use: an overlay at `<repo>/docs/agents/execution/overlay.md` is appended under a
"Repository-specific execution rules" heading. That is where a repo binds the abstract stages to its
real commands — its context script, its area gates, its ledger path. The overlay is authored by the
repo and never generated.

Adoption is staggered and deliberate. Repositories come under this methodology one at a time, by
someone running the render on purpose; nothing here ever adopts a repository on its own. Until a
repository has adopted it, `--adoption-check` says so at every session start — see the adoption
section below.

Adoption also CONFIGURES THE REPOSITORY'S PERSONAS, because a methodology nobody is bound to is
prose. Every mode that reports on a repository also reports its persona configuration: which
validators the repository ships in `docs/agents/personas/`, which of them declare `covers:`, and
which horizontal concerns in its own product definition are owned by NOBODY. It proposes the line
and names the file; it never writes into a persona. Deciding which validator holds which invariant
is a judgement, and a binding a script guessed is a binding nobody holds.

Usage:
  sync_methodology.py --repo PATH                    # render into that repository, report personas
  sync_methodology.py --repo PATH --check            # exit 1 if the rendered copy is stale (gates)
  sync_methodology.py --repo PATH --adoption-check   # report adoption state; ALWAYS exits 0
  sync_methodology.py --list                         # show the source, version, and rendered date
  sync_methodology.py --repo PATH --list             # ... plus that repo's target and overlay state
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

# The persona pool, the `## Horizontals` carrier and the concern matcher are spec_check's, and are
# imported rather than restated. Rule F reads them to decide whether a validator has READ a
# document; this reads them to decide whether a validator has been GIVEN anything to read. Two
# parsers for one carrier drift apart, and a drifted copy is how the defective Verify block in the
# onboarding guide survived a repair to the skill.
from spec_check import (Doc, Findings, SpecError, concern_match, horizontals,  # noqa: E402
                        persona_pool)

SKILL = Path(__file__).resolve().parent.parent
SOURCE = SKILL / "methodology.md"

# Bump when the methodology's rules change. MAJOR for a change that invalidates how a repo already
# works — a stage removed, a gate moved, an artifact renamed. MINOR for additive clarification.
# Rendered copies carry this stamp so a repo running an older methodology can be detected instead of
# silently drifting. validate_disclosure.py reads this constant to decide WARN versus ERROR.
METHODOLOGY_VERSION = "5.0"

TARGET_REL = Path("docs") / "agents" / "execution" / "methodology.md"
OVERLAY_REL = Path("docs") / "agents" / "execution" / "overlay.md"
OVERLAY_HEADING = "## Repository-specific execution rules"

# The repository's own authored route index. Rendering into docs/agents/execution/methodology.md
# without a route pointing at it produces a file nothing reaches — invisible, and invisibly so.
# This script never writes README.md itself; sync_personas.py sets the precedent of preserving
# unmanaged files rather than clobbering them, and the route index is squarely the repo's own work.
README_REL = Path("docs") / "agents" / "README.md"

# A markdown inline link: [text](target) or [text](target "title"). Reference-style links
# (`[text][ref]`) are not matched — the existing route row uses inline form, and that is the only
# form this checks for.
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

# The exact row shape to paste, matching docs/agents/README.md:48's relative-link form
# (`[execution/methodology.md](execution/methodology.md)`, relative to docs/agents/). The middle
# columns are placeholders — what a lane inspects and gates on is per-repository, but the link form
# is not.
ROUTE_ROW = (
    "| Spec, design, plan, or executing a plan | "
    "[execution/methodology.md](execution/methodology.md) — the pipeline, its gates, the task "
    "card, the ledger contract | <the active plan and its workspace> | <this repo's gate for it> |"
)

# The banner names the skill-relative source, never an absolute home path: an absolute path would
# differ between machines and every check on a second machine would report drift.
GENERATED = ("<!-- GENERATED by execution-methodology/scripts/sync_methodology.py from "
             "execution-methodology/methodology.md — do not hand-edit this file; "
             "edit the methodology, or this repo's docs/agents/execution/overlay.md. -->")

# Exactly the single-line JSON comment spelling validate_disclosure.py already parses for personas.
MARKER_RE = re.compile(r"<!--\s*execution-methodology:\s*(\{[^\r\n]*\})\s*-->", re.IGNORECASE)

# Anything that *claims* to be one of our markers, well-formed or not. Counting only well-formed
# markers would let a typo read as "no decision recorded", which is the one reading a deferral must
# never silently collapse into. Mirrors PERSONA_MARKER / PERSONA_MARKER_ANY in validate_disclosure.
MARKER_ANY_RE = re.compile(r"<!--\s*execution-methodology:.*?-->", re.IGNORECASE | re.DOTALL)

# The deferral decision, recorded in the repository's own routed index — docs/agents/README.md, the
# first file every agent in every harness reads. It is the same file, and the same single-line JSON
# comment shape, that carries the `agent-personas` base-only decision; a repository records "I chose
# not to adopt this, for this reason, on this date" exactly where it records "I chose the base
# persona pool, for this reason". A decision filed anywhere else is a decision nobody reads.
#
# Strictness follows that precedent exactly: one marker, valid single-line JSON, and a non-empty
# reason. An empty reason is not a decision, it is silence with punctuation, and it is treated as
# unadopted. The date is this file's own addition — it makes a deferral visibly age instead of
# quietly becoming permanent.
DEFER_MODE = "deferred"
DEFERRAL_EXAMPLE = ('<!-- execution-methodology: {"mode":"deferred",'
                    '"reason":"<one line: why not yet>","date":"YYYY-MM-DD"} -->')

FENCE_RE = re.compile(r"^\s{0,3}(?:```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


class MethodologyError(Exception):
    pass


def strip_code(text: str) -> str:
    """Drop fenced and inline code so a documented example is never read as a decision.

    A repository that documents the marker — in its own route index, under a fence — must not
    thereby be reported as having deferred. validate_disclosure.py strips code before reading the
    persona marker for the same reason.
    """
    out: list[str] = []
    fenced = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            out.append(INLINE_CODE_RE.sub("", line))
    return "\n".join(out)


def source_text() -> str:
    if not SOURCE.is_file():
        raise MethodologyError(f"no methodology source at {SOURCE}")
    text = SOURCE.read_text(encoding="utf-8").strip()
    if not text:
        raise MethodologyError(f"{SOURCE} is empty")
    return text


def rendered_date(explicit: str | None = None) -> str:
    """The date stamped into the marker.

    Taken from the source's mtime, not from today. A date read at check time would differ from the
    date written at render time on the very next day, and `--check` would report drift every morning
    in every repository until someone muted it.
    """
    if explicit:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", explicit):
            raise MethodologyError(f"--rendered must be YYYY-MM-DD, got {explicit!r}")
        return explicit
    return datetime.fromtimestamp(SOURCE.stat().st_mtime, tz=timezone.utc).date().isoformat()


def marker(date: str) -> str:
    payload = json.dumps({"v": METHODOLOGY_VERSION, "rendered": date}, separators=(",", ":"))
    return f"<!-- execution-methodology: {payload} -->"


def render(body: str, date: str, overlay: str | None) -> str:
    parts = [GENERATED, marker(date), "", body.rstrip()]
    if overlay is not None:
        parts += ["", OVERLAY_HEADING, "", overlay.strip()]
    return "\n".join(parts) + "\n"


def read_overlay(repo: Path) -> str | None:
    """An overlay that exists but says nothing is a mistake, not an empty section."""
    path = repo / OVERLAY_REL
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise MethodologyError(f"{OVERLAY_REL.as_posix()} exists but is empty")
    return text


def is_ours(text: str) -> bool:
    """Only files this script generated may be overwritten.

    A hand-written docs/agents/execution/methodology.md is somebody's work. Personas preserve unmanaged files in
    the same situation and let the check report them, rather than deleting or clobbering them.
    """
    return GENERATED in text


def route_status(repo: Path) -> tuple[bool, str]:
    """Whether `docs/agents/README.md` links to the rendered methodology.

    Links are resolved relative to `docs/agents/`, matching the existing row's
    `[execution/methodology.md](execution/methodology.md)` form. Returns (True, "") when routed;
    otherwise (False, <reason>) — either the README does not exist at all, or none of its links
    resolve to the rendered target.
    """
    readme = repo / README_REL
    if not readme.is_file():
        return False, f"{README_REL.as_posix()} does not exist — this repository has no route index"

    text = readme.read_text(encoding="utf-8", errors="replace")
    base = (repo / "docs" / "agents").resolve()
    target = (repo / TARGET_REL).resolve()
    for m in LINK_RE.finditer(text):
        link = m.group(1).split("#", 1)[0].strip()
        if not link or link.startswith(("http://", "https://", "mailto:")):
            continue
        try:
            resolved = (base / link).resolve()
        except (OSError, ValueError):
            continue
        if resolved == target:
            return True, ""
    return False, f"no link in {README_REL.as_posix()} resolves to {TARGET_REL.as_posix()}"


def print_route_advice(detail: str) -> None:
    print(f"    {detail}")
    print(f"  paste this row into {README_REL.as_posix()} (create the file if it does not exist):")
    print(f"    {ROUTE_ROW}")


# --- persona configuration -----------------------------------------------------------------------
# ADOPTING THE METHODOLOGY IN A REPOSITORY MUST ALSO CONFIGURE THAT REPOSITORY'S VALIDATORS.
#
# Rendering the methodology and generating persona files were two unconnected acts:
# `sync_methodology.py --repo .` produced the rules, `agent-personas/scripts/sync_personas.py
# --repo .` produced the personas, and nothing ever asked whether the second knew about the first.
# The result is measurable in the fleet. A project's own domain validators — a tenancy isolation
# validator, a clinical safety validator, a financial integrity validator, a plane boundary
# validator — are cited 100 times at review time and 5 times on a spec, 0 on a PRD or milestone.
# They arrive after the product is defined, which is the expensive end. And spec_check's rule F,
# which exists to pull them forward, reports `RULE F CHECKED NOTHING` in all four repositories
# measured, because no persona anywhere declares a `covers:`.
#
# So adoption now REPORTS the persona configuration alongside the render. Three questions, in the
# order a reader needs them: which validators does this repository have, which of them own a
# concern, and WHICH CONCERNS DOES NOBODY OWN. The third is the useful one — it names the
# invariants this product writes down and binds to no reader.
#
# IT WRITES NOTHING. Not into a persona file, not anywhere. Every script in this skill writes
# nothing, and a `covers:` line is a judgement about which validator holds which invariant; a
# script that guesses it produces a binding nobody decided and everybody trusts. The output names
# the file and the line, and stops there.
#
# THE POOL IS THIS REPOSITORY'S `docs/agents/personas/`, never `~/.claude/agents` and never the
# machine-global pool. A repository with no such directory has not adopted overlays; that is a
# state, not a fault, and it is reported in one plain sentence.
#
# WHY THE CONCERN SCAN READS EVERY MARKDOWN FILE UNDER docs/product AND RULE F DOES NOT:
# measured on the four real repositories, `## Horizontals` sections carrying live concern rows are
# found in 22 of 24 documents in one, 65 of 236 in another, 1 of 8 in a third, 0 of 204 in the
# fourth. Rule F binds documents by PATH — `docs/product/specs/F-*.md`, `docs/product/prd.md`,
# `docs/product/milestones/M*.md` — and the repository with 65 writes its specs as
# `docs/product/specs/<slug>/spec.md`, so rule F binds NONE of them. A configuration report that
# copied that path filter would tell that repository it has no concerns while 545 live concern rows
# sit in its specs: the eighth inert checker of this session, in the same shape as the other seven.
# So the scan reads the CARRIER wherever it is authored, and then says out loud how many of those
# rows rule F can actually reach. Both numbers are printed. Neither is quietly assumed.
PERSONA_REL = Path("docs") / "agents" / "personas"
PRODUCT_REL = Path("docs") / "product"

# How many unowned concerns are listed before the count stands in for the rest. spec_check's
# PRINT_CAP exists for the same reason: a list nobody finishes reading is a list nobody acts on.
UNOWNED_CAP = 8

PersonaConfig = NamedTuple("PersonaConfig", [
    ("pool", str),          # the pool's repo-relative path, or "" when the directory is absent
    ("personas", tuple),    # spec_check.Persona, in filename order
    ("anchors", dict),      # persona name -> the line a `covers:` would be inserted on
    ("documents", int),     # markdown files read under docs/product
    ("with_section", int),  # ... of those, ones carrying a `## Horizontals` heading
    ("bindable", int),      # ... of those with live rows, ones rule F binds by path
    ("concerns", dict),     # live concern label -> rows carrying it
    ("reachable", dict),    # live concern label -> rows of those rule F binds
    ("owned", dict),        # live concern label -> the personas whose `covers:` reaches it
])


def covers_anchor(path: Path) -> int:
    """The line a `covers:` key would be added on: the persona's closing `---`.

    Insertion goes BEFORE that line, so the key lands inside the front matter block where
    `read_persona_overlay` looks for it. A file with no closing fence gets line 1 and the reader
    gets a persona that already reports itself unreadable.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return 1
    if not lines or lines[0].strip() != "---":
        return 1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index + 1
    return 1


def persona_config(repo: Path) -> PersonaConfig:
    """This repository's validators, what they own, and what nothing owns.

    Reads only the repository. Reuses spec_check's pool reader, `## Horizontals` reader and
    concern matcher rather than restating them: two parsers for one carrier drift, and this
    session has already repaired one copy of a duplicated rule and left the other defective.
    """
    directory = repo / PERSONA_REL
    pool = PERSONA_REL.as_posix() if directory.is_dir() else ""
    personas: tuple = ()
    anchors: dict = {}
    if pool:
        found, _ = persona_pool(repo, Findings())
        personas = tuple(found)
        anchors = {p.name: (p.line if p.covers else covers_anchor(directory / p.rel))
                   for p in personas}

    concerns: dict = {}
    reachable: dict = {}
    documents = with_section = bindable = 0
    product = repo / PRODUCT_REL
    for path in sorted(product.glob("**/*.md")) if product.is_dir() else []:
        if not path.is_file():
            continue
        try:
            doc = Doc(path, repo)
        except SpecError:
            continue
        documents += 1
        rows, present, _ = horizontals(doc)
        with_section += present
        live = [row for row in rows if row.live]
        binds = doc.is_spec or doc.is_prd or doc.is_milestone
        bindable += bool(live) and binds
        for row in live:
            concerns[row.label] = concerns.get(row.label, 0) + 1
            if binds:
                reachable[row.label] = reachable.get(row.label, 0) + 1

    owned = {label: sorted(p.name for p in personas
                           if any(concern_match(c, label) for c in p.covers))
             for label in concerns}
    return PersonaConfig(pool, personas, anchors, documents, with_section, bindable,
                         concerns, reachable, owned)


def unowned_concerns(config: PersonaConfig) -> list[tuple[str, int, int]]:
    """(label, rows, rows rule F can reach) for every live concern no persona covers.

    Ordered by how often the product writes the concern down, because that is the order in which
    leaving it unowned costs something.
    """
    rows = [(label, count, config.reachable.get(label, 0))
            for label, count in config.concerns.items() if not config.owned[label]]
    return sorted(rows, key=lambda item: (-item[1], item[0]))


def bound_personas(config: PersonaConfig) -> list:
    return [p for p in config.personas if p.covers]


def persona_summary(config: PersonaConfig) -> str:
    """One line naming the three numbers that are the whole point of this step."""
    if not config.pool:
        return (f"persona configuration: no {PERSONA_REL.as_posix()}/ — this repository has not "
                "adopted persona overlays, so the base pool applies to it unchanged")
    if not config.personas:
        return (f"persona configuration: {config.pool}/ exists but holds no persona overlay")
    head = (f"persona configuration: {len(config.personas)} persona(s) in {config.pool}/, "
            f"{len(bound_personas(config))} with `covers:`")
    if not config.concerns:
        # Nothing to own is not the same state as nothing owned, and collapsing the two into
        # "0 of 0" reads as configured when it means the product has written no concern down yet.
        return head + (f", and no live `## Horizontals` concern row in {config.documents} "
                       f"document(s) under {PRODUCT_REL.as_posix()}/ to own")
    return (f"{head}, {len(unowned_concerns(config))} of {len(config.concerns)} "
            "live concern(s) owned by nobody")


def persona_notes(config: PersonaConfig) -> list[str]:
    """The things worth saying at session start, or none at all.

    Empty when there is nothing configurable — no pool means no overlays to bind, and a check that
    shouts at every repository it does not apply to is a check somebody mutes.
    """
    if not config.pool or not config.personas:
        return []
    notes: list[str] = []
    broken = [p for p in config.personas if p.error]
    for persona in broken:
        notes.append(f"{config.pool}/{persona.rel} cannot be read for its binding: {persona.error}")
    if not config.concerns:
        notes.append(f"{len(config.personas)} validator(s) here, and no live `## Horizontals` "
                     f"concern row in {config.documents} document(s) under "
                     f"{PRODUCT_REL.as_posix()}/ — there is nothing yet for one to be bound to")
        return notes
    missing = unowned_concerns(config)
    if not missing:
        return notes
    shown = ", ".join(f"{label} ({count})" for label, count, _ in missing[:UNOWNED_CAP])
    more = len(missing) - UNOWNED_CAP
    notes.append(f"{len(missing)} of {len(config.concerns)} live concern(s) in this repository's "
                 f"product definition are owned by no persona: {shown}"
                 + (f", and {more} more" if more > 0 else ""))
    if not bound_personas(config):
        notes.append("no persona here declares `covers:`, so spec_check rule F checks nothing and "
                     "these invariants are read at review time only")
    return notes


def print_persona_config(config: PersonaConfig) -> None:
    """The full report: the pool, what each persona owns, what nobody owns, and where to fix it."""
    print(f"  {persona_summary(config)}")
    if not config.pool or not config.personas:
        return
    width = max(len(p.name) for p in config.personas)
    for persona in config.personas:
        if persona.error:
            owns = f"-- unreadable: {persona.error}"
        elif persona.covers:
            owns = "covers: " + ", ".join(persona.covers)
        else:
            owns = "-- declares no `covers:`"
        print(f"    {persona.name.ljust(width)}  {owns}")
    print(f"    {sum(config.concerns.values())} live concern row(s) over "
          f"{len(config.concerns)} label(s), in {config.with_section} of {config.documents} "
          f"document(s) under {PRODUCT_REL.as_posix()}/ carrying `## Horizontals`")
    missing = unowned_concerns(config)
    if not config.concerns:
        return
    if not missing:
        print("    every live concern in this product definition is owned by a persona")
    for label, count, reach in missing[:UNOWNED_CAP]:
        note = "" if reach else "  (in no document rule F binds)"
        print(f"    UNOWNED  {label}  -- {count} row(s){note}")
    if len(missing) > UNOWNED_CAP:
        print(f"    ... and {len(missing) - UNOWNED_CAP} more unowned concern(s)")
    if missing:
        unreachable = sum(1 for _, _, reach in missing if not reach)
        if unreachable:
            print(f"    {unreachable} of them appear only in documents rule F does not bind "
                  "(a spec is `docs/product/specs/F-*.md`, the PRD `docs/product/prd.md`, a "
                  "milestone `docs/product/milestones/M*.md`); binding a persona to those "
                  "configures the review, but spec_check will not demand it")
        print("    decide which validator holds each, then add ONE line inside its front matter:")
        for persona in config.personas:
            if persona.covers or persona.error:
                continue
            line = config.anchors.get(persona.name, 1)
            print(f"      {config.pool}/{persona.rel}:{line}  insert before this line: "
                  "covers: [<concern>, ...]")
        print("    nothing here writes that line; a binding nobody decided is a binding "
              "nobody holds")

def sync(repo: Path, check: bool, explicit_date: str | None) -> int:
    """Render the methodology into a repository, then report that repository's persona configuration.

    Adoption is ONE act with two halves. The rendered methodology tells a repository how work
    moves; the persona configuration says which of its own validators hold which invariant, and
    when. Doing only the first is what the fleet already did, and the measurement is that a
    project's own validators are cast 100 times at review time and 5 times on a spec.

    The persona half never changes the exit code. It reports a state, and states this script does
    not write are not failures it may declare: `--check` gates the RENDER, which this script owns
    end to end, and a repository whose validators are unbound has a decision to make rather than a
    drift to repair. spec_check's rule F is the checker that already owns the binding, and two
    checkers with two opinions on one file is a thing this toolchain refuses on purpose.
    """
    code = render_methodology(repo, check, explicit_date)
    if code != 2:
        # Exit 2 means the source or the target could not be read at all. A configuration report
        # under that is noise stacked on a fault the reader must fix first.
        print_persona_config(persona_config(repo))
    return code


def render_methodology(repo: Path, check: bool, explicit_date: str | None) -> int:
    try:
        body = source_text()
        date = rendered_date(explicit_date)
        overlay = read_overlay(repo)
    except MethodologyError as e:
        print(e, file=sys.stderr)
        return 2

    target = repo / TARGET_REL
    expected = render(body, date, overlay)
    current = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None

    print(f"execution methodology v{METHODOLOGY_VERSION} (source rendered {date})"
          f" -> {repo.name}/{TARGET_REL.as_posix()}"
          + (f", overlay {OVERLAY_REL.as_posix()}" if overlay is not None else ""))

    if current is not None and not is_ours(current):
        where = f"{target} (unmanaged — not generated by this script)"
        if check:
            print("  STALE — the rendered methodology does not match its source:")
            print(f"    {where}")
            print(f"  run: sync_methodology.py --repo {repo}")
            return 1
        print(f"  refusing to overwrite {where}", file=sys.stderr)
        print("  move it aside, then re-run", file=sys.stderr)
        return 2

    if current == expected:
        if check:
            routed, detail = route_status(repo)
            if not routed:
                print("  ERROR — nothing routes to the rendered methodology:")
                print_route_advice(detail)
                return 1
            print("  in sync")
            return 0
        print("  already up to date")
        routed, detail = route_status(repo)
        if not routed:
            print("  WARNING — rendered, but nothing routes to it:")
            print_route_advice(detail)
        return 0

    if check:
        reason = "missing" if current is None else "stale or hand-edited"
        print("  STALE — the rendered methodology does not match its source:")
        print(f"    {target} ({reason})")
        print(f"  run: sync_methodology.py --repo {repo}")
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(expected, encoding="utf-8")
    print(f"  wrote   {target}")
    routed, detail = route_status(repo)
    if not routed:
        print("  WARNING — rendered, but nothing routes to it:")
        print_route_advice(detail)
    return 0


def read_deferral(repo: Path) -> tuple[dict | None, str | None]:
    """The repository's deliberate-deferral decision, if it recorded a valid one.

    Returns (decision, problem). Exactly one of them is ever non-None:
      (None, None)        nothing recorded — the repository has simply not decided
      (None, "<why>")     something is recorded but does not count as a decision
      ({...}, None)       a valid deferral
    """
    readme = repo / README_REL
    if not readme.is_file():
        return None, None

    text = strip_code(readme.read_text(encoding="utf-8", errors="replace"))
    total = len(MARKER_ANY_RE.findall(text))
    if total == 0:
        return None, None
    if total > 1:
        return None, (f"{README_REL.as_posix()} contains {total} `execution-methodology` markers; "
                      "keep exactly one")

    wellformed = MARKER_RE.findall(text)
    if len(wellformed) != 1:
        return None, (f"the `execution-methodology` marker in {README_REL.as_posix()} must be one "
                      "single-line JSON object")
    try:
        parsed = json.loads(wellformed[0])
    except json.JSONDecodeError as exc:
        return None, (f"the `execution-methodology` marker in {README_REL.as_posix()} is not valid "
                      f"JSON: {exc.msg}")

    if not isinstance(parsed, dict) or parsed.get("mode") != DEFER_MODE:
        return None, (f"the `execution-methodology` marker in {README_REL.as_posix()} must declare "
                      f'`"mode":"{DEFER_MODE}"`')
    reason = parsed.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None, (f"the deferral in {README_REL.as_posix()} has no reason — a deferral without "
                      "one is not a decision, so this repository counts as unadopted")
    stamp = parsed.get("date")
    if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
        return None, (f"the deferral in {README_REL.as_posix()} has no `\"date\":\"YYYY-MM-DD\"` — "
                      "without one a deferral cannot age, and counts as unadopted")
    try:
        date.fromisoformat(stamp)
    except ValueError:
        return None, (f"the deferral in {README_REL.as_posix()} has date {stamp!r}, which is not a "
                      "real calendar date")
    return {"reason": reason.strip(), "date": stamp}, None


def adoption_check(repo: Path) -> int:
    """Report one repository's adoption state at session start. ALWAYS returns 0.

    This informs; it never blocks and it never writes. `--check` is the mode that fails a gate, and
    its behaviour is deliberately untouched. Four states, and only three of them say anything:

      adopted and current   silence, UNLESS the persona configuration has something to say
      adopted but stale     a warning naming the file and the re-render command
      deliberately deferred one quiet line, with the reason and how long it has been deferred
      unadopted             a warning naming both ways out — adopt, or record a deferral

    THE PERSONA CONFIGURATION IS PART OF THE STATE, because adoption is not finished when the file
    is rendered. A repository can be perfectly current on the methodology and still have every
    horizontal invariant in its product definition owned by nobody, which is the state all four
    measured repositories are in. So the persona notes are appended to whichever of the four states
    applies, and they can break the silence of the first — but only where there is something to
    configure. A repository with no `docs/agents/personas/` says nothing here: it has not adopted
    overlays, that is a legitimate state, and a line repeated at every session start in every
    repository it does not apply to is a line somebody mutes.

    Output follows the `AGENT CONTEXT:` head-plus-bullets convention that check_github.py and
    check_toolchain.py already emit into this same session hook, so the lines read as one voice.
    """
    head = f"AGENT CONTEXT: execution methodology v{METHODOLOGY_VERSION}"
    adopt_cmd = f"python3 {Path(__file__).resolve()} --repo {repo}"

    try:
        body = source_text()
        stamp = rendered_date(None)
        overlay = read_overlay(repo)
    except MethodologyError as e:
        # A broken toolchain is worth one line, but never a failed session.
        print(f"{head} could not be evaluated for this repository.")
        print(f"  - [warn] {e}")
        return 0

    target = repo / TARGET_REL
    rel = TARGET_REL.as_posix()
    current = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else None
    notes = persona_notes(persona_config(repo))
    configure = (f"python3 {Path(__file__).resolve().parent / 'spec_check.py'} --root {repo} "
                 "--personas")

    def persona_block() -> None:
        """The persona half of the state, under whichever methodology state was printed."""
        for note in notes:
            print(f"  - [warn] {note}")
        if notes:
            print(f"  Decide the owners, then add one `covers:` line per validator — "
                  f"`{configure}` lists the pool and the concerns. Nothing writes it for you.")

    # 1. adopted and current — say nothing at all, unless the validators are unconfigured.
    if current is not None and is_ours(current) and current == render(body, stamp, overlay):
        if not notes:
            return 0
        print(f"{head} is adopted here, but its persona configuration is incomplete.")
        persona_block()
        return 0

    # 2. adopted but stale. An unmanaged hand-written file is also "exists but does not match", and
    #    the re-render refuses to clobber it, so it gets the instruction that actually works.
    if current is not None:
        print(f"{head} is rendered into this repository but out of date.")
        if not is_ours(current):
            print(f"  - [warn] {rel} was not generated by this script and does not match the source")
            print(f"  Move it aside, then re-render: `{adopt_cmd}`")
        else:
            print(f"  - [warn] {rel} no longer matches the methodology source")
            print(f"  Re-render: `{adopt_cmd}`")
        persona_block()
        return 0

    decision, problem = read_deferral(repo)

    # 3. deliberately deferred — one quiet line, carrying its own age.
    if decision is not None:
        age = (datetime.now(timezone.utc).date() - date.fromisoformat(decision["date"])).days
        print(f"{head} is deliberately deferred here since {decision['date']} "
              f"({age} day{'' if age == 1 else 's'}) — {decision['reason']}")
        # A deferral defers the METHODOLOGY. It does not decide who owns this repository's
        # invariants, and the validators it already ships are reading its changes either way.
        persona_block()
        return 0

    # 4. unadopted, including a marker that does not qualify as a decision.
    print(f"{head} has not been adopted by this repository.")
    print(f"  - [warn] {problem}" if problem
          else f"  - [warn] no {rel}, and no deferral decision recorded")
    print(f"  Adopt it deliberately — `{adopt_cmd}` renders it and prints the route row to paste.")
    print(f"  Or record a deferral in {README_REL.as_posix()}:")
    print(f"    {DEFERRAL_EXAMPLE}")
    print("  Adoption is never automatic: nothing here will render into this repository for you.")
    persona_block()
    return 0


def show_info(repo: Path | None) -> int:
    try:
        body = source_text()
        date = rendered_date(None)
    except MethodologyError as e:
        print(e, file=sys.stderr)
        return 2
    headings = [ln[3:].strip() for ln in body.splitlines() if ln.startswith("## ")]
    print(f"{'source':<10}  {SOURCE}")
    print(f"{'version':<10}  {METHODOLOGY_VERSION}")
    print(f"{'rendered':<10}  {date}  (from source mtime)")
    print(f"{'words':<10}  {len(body.split())}")
    print(f"{'stages':<10}  {', '.join(headings) if headings else '-'}")
    if repo is None:
        return 0
    target = repo / TARGET_REL
    overlay = repo / OVERLAY_REL
    state = "absent"
    if target.is_file():
        text = target.read_text(encoding="utf-8", errors="replace")
        found = MARKER_RE.findall(text)
        if not is_ours(text):
            state = "unmanaged"
        elif found:
            try:
                state = f"v{json.loads(found[0]).get('v', '?')}"
            except json.JSONDecodeError:
                state = "malformed marker"
        else:
            state = "no marker"
    print(f"{'target':<10}  {target}  [{state}]")
    print(f"{'overlay':<10}  {overlay}  [{'present' if overlay.is_file() else 'absent'}]")
    # `--repo --list` is the "what is this repository's state" view, and the persona configuration
    # is part of that state. One line here; `--repo` prints the whole report.
    print(f"{'personas':<10}  {persona_summary(persona_config(repo))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="the repository to render the methodology into")
    ap.add_argument("--check", action="store_true", help="exit 1 when the rendered copy is stale")
    ap.add_argument("--adoption-check", action="store_true", dest="adoption",
                    help="report this repo's adoption state for a session hook; always exits 0")
    ap.add_argument("--list", action="store_true", dest="show",
                    help="print the source, version and rendered date")
    ap.add_argument("--rendered", default=None, metavar="YYYY-MM-DD",
                    help="stamp this date instead of the source's mtime")
    args = ap.parse_args()

    repo = Path(args.repo).resolve() if args.repo else None
    if repo and not repo.is_dir():
        # Silent for the session-hook mode: a path that is not there is not a finding to shout at
        # the start of every session, and this mode's contract is that it never fails anything.
        if args.adoption:
            return 0
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2
    if args.adoption:
        if repo is None:
            print("--repo is required for --adoption-check", file=sys.stderr)
            return 2
        try:
            return adoption_check(repo)
        except Exception as e:  # noqa: BLE001 — a session hook may not die on an unexpected fault
            print(f"AGENT CONTEXT: the execution-methodology adoption check failed to run: {e}")
            return 0
    if args.show:
        return show_info(repo)
    if repo is None:
        print("--repo is required (or use --list)", file=sys.stderr)
        return 2
    return sync(repo, args.check, args.rendered)


if __name__ == "__main__":
    raise SystemExit(main())
