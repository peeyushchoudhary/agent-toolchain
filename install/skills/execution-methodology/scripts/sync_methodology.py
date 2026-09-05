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
  sync_methodology.py --repo PATH --repair-approved AUTHORIZATION_JSON
                                                    # repair output iff identity is unchanged
  sync_methodology.py --repo PATH --check            # exit 1 if the rendered copy is stale (gates)
  sync_methodology.py --repo PATH --adoption-check   # report adoption state; ALWAYS exits 0
  sync_methodology.py --repo PATH --status-json      # structured runtime readiness; 0 inspected/2 error
  sync_methodology.py --list                         # show the source, version, and source digest
  sync_methodology.py --repo PATH --list             # ... plus that repo's target and overlay state
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

# The persona report lazily imports spec_check so --status-json can still report that spec_check or
# one of its direct helpers is missing. Eager import made the status owner itself disappear at the
# exact moment it was needed to classify a declared dependency.
def _load_spec_check() -> None:
    global Doc, Findings, SpecError, concern_match, horizontals, persona_pool
    if "Doc" in globals():
        return
    from spec_check import (Doc as _Doc, Findings as _Findings, SpecError as _SpecError,
                            concern_match as _concern_match, horizontals as _horizontals,
                            persona_pool as _persona_pool)
    Doc, Findings, SpecError = _Doc, _Findings, _SpecError
    concern_match, horizontals, persona_pool = _concern_match, _horizontals, _persona_pool

SKILL = Path(__file__).resolve().parent.parent
SOURCE = SKILL / "methodology.md"

# Bump when the methodology's rules change. MAJOR for a change that invalidates how a repo already
# works — a stage removed, a gate moved, an artifact renamed. MINOR for additive clarification.
# Rendered copies carry this stamp so a repo running an older methodology can be detected instead of
# silently drifting. validate_disclosure.py reads this constant to decide WARN versus ERROR.
METHODOLOGY_VERSION = "5.1"

TARGET_REL = Path("docs") / "agents" / "execution" / "methodology.md"
OVERLAY_REL = Path("docs") / "agents" / "execution" / "overlay.md"
OVERLAY_HEADING = "## Repository-specific execution rules"
RUNTIME_REL = Path("docs") / "agents" / "execution" / "runtime.json"
RUNTIME_SCHEMA_VERSION = 1
RUNTIME_GENERATOR = "execution-methodology/scripts/sync_methodology.py"

# One explicit declaration is used by rendering and status inspection. Paths are relative to the
# skills bundle root (the parent of execution-methodology), so references can be resolved without
# assuming they live beside the rendered project guide. History and maintenance material are
# deliberately absent: they are not runtime inputs to ordinary governed execution.
RUNTIME_FILES = (
    ("common", "execution-methodology/methodology.md"),
    ("runtime-owner", "execution-methodology/scripts/sync_methodology.py"),
    ("runtime-owner", "execution-methodology/scripts/runtime-status.schema.json"),
    ("controller", "execution-methodology/references/execution-loop.md"),
    ("product-definition", "execution-methodology/references/specs.md"),
    ("full-task", "execution-methodology/references/task-card.md"),
    ("evidence", "execution-methodology/references/junit-evidence.md"),
    ("gate", "execution-methodology/references/codex-gate-sandbox.md"),
    ("command", "execution-methodology/scripts/plan_waves.py"),
    ("command", "execution-methodology/scripts/validate_card.py"),
    ("command", "execution-methodology/scripts/check_review_budget.py"),
    ("command", "execution-methodology/scripts/trace_check.py"),
    ("command", "execution-methodology/scripts/start_junit_run.py"),
    ("command", "execution-methodology/scripts/verify_junit.py"),
    ("command", "execution-methodology/scripts/spec_check.py"),
    ("command", "execution-methodology/scripts/milestone_seal.py"),
    ("command", "execution-methodology/scripts/weekly_review.py"),
    ("helper", "execution-methodology/scripts/ratio_meter.py"),
    ("persona-command", "agent-personas/scripts/sync_personas.py"),
    ("persona-policy", "agent-personas/SKILL.md"),
    ("persona-policy", "agent-personas/ROSTER"),
    ("persona-policy", "agent-personas/references/roster.md"),
    *(("persona-policy", f"agent-personas/personas/{name}.md") for name in (
        "acceptance", "architect", "chief-of-staff", "contract-architect", "developer",
        "docs-steward", "migration-validator", "planner", "product-steward", "reviewer",
        "scout", "security-validator", "senior-developer", "test-judge",
    )),
    ("gate", "gate-sandbox/SKILL.md"),
    ("gate-command", "gate-sandbox/scripts/gate.sh"),
    ("gate-command", "gate-sandbox/scripts/readiness.sh"),
    ("gate-helper", "gate-sandbox/scripts/gate_lib.sh"),
    ("gate-helper", "gate-sandbox/scripts/gate_config.sh"),
    ("gate-helper", "gate-sandbox/scripts/evidence_supervisor.py"),
)

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


def source_sha256(body: str) -> str:
    """Bind a render to the normalized source bytes returned by source_text()."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_declared_path(bundle_root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise MethodologyError(f"runtime dependency escapes bundle root: {relative}")
    candidate = bundle_root / rel
    resolved_root = bundle_root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    if not _within(resolved, resolved_root):
        raise MethodologyError(f"runtime dependency escapes bundle root: {relative}")
    cursor = resolved_root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise MethodologyError(f"runtime dependency is a symlink: {relative}")
    if not resolved.is_file():
        raise MethodologyError(f"runtime dependency is not a file: {relative}")
    return resolved


def runtime_declaration(bundle_root: Path | None = None) -> dict:
    """Build the single runtime declaration used by render and inspection."""
    root = (bundle_root or SKILL.parent).resolve(strict=True)
    files = []
    for stage, relative in RUNTIME_FILES:
        path = _safe_declared_path(root, relative)
        files.append({"path": relative, "stage": stage, "sha256": file_sha256(path)})
    digest_input = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    methodology = (root / "execution-methodology" / "methodology.md").read_text(
        encoding="utf-8").strip()
    if not methodology:
        raise MethodologyError("runtime methodology source is empty")
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "source_sha256": source_sha256(methodology),
        "runtime_sha256": hashlib.sha256(digest_input).hexdigest(),
        "bundle_root": str(root),
        "source_revision": source_revision(root),
        "files": files,
    }


def source_revision(bundle_root: Path) -> str | None:
    """Return the local Git revision plus declared-runtime dirty state, when available.

    Dirty scope is deliberately the explicit declaration, not the surrounding checkout. An
    unrelated documentation edit must not change runtime provenance or cause a rewrite.
    """
    top = subprocess.run(["git", "-C", str(bundle_root), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    head = subprocess.run(["git", "-C", str(bundle_root), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    if top.returncode or head.returncode:
        return None
    top_path = Path(top.stdout.strip()).resolve()
    declared = []
    for _, relative in RUNTIME_FILES:
        absolute = bundle_root / relative
        try:
            declared.append(absolute.resolve().relative_to(top_path).as_posix())
        except (OSError, ValueError):
            return None
    dirty = subprocess.run(["git", "-C", str(top_path), "status", "--porcelain", "--", *declared],
                           capture_output=True, text=True)
    if dirty.returncode:
        return None
    return head.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "")


def overlay_sha256(overlay: str | None) -> str | None:
    if overlay is None:
        return None
    return hashlib.sha256(overlay.strip().encode("utf-8")).hexdigest()


def runtime_inventory(body: str, overlay: str | None) -> dict:
    declaration = runtime_declaration()
    return {
        "generated_by": RUNTIME_GENERATOR,
        **declaration,
        "source_sha256": source_sha256(body),
        "overlay_sha256": overlay_sha256(overlay),
    }


def inventory_text(inventory: dict) -> str:
    return json.dumps(inventory, indent=2, sort_keys=True) + "\n"


def _finding(code: str, message: str, path: str | None = None,
             severity: str = "error") -> dict:
    return {"code": code, "severity": severity, "message": message, "path": path}


def _base_status(state: str, findings: list[dict], *, route_valid: bool = False,
                 route_detail: str = "", overlay: dict | None = None,
                 approved: dict | None = None, installed: dict | None = None,
                 dependencies: list[dict] | None = None,
                 repairs: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "state": state,
        "ready": state == "current",
        "approved": approved,
        "installed": installed,
        "route": {"valid": route_valid, "detail": route_detail},
        "overlay": overlay or {"valid": True, "sha256": None,
                               "expected_sha256": None, "detail": ""},
        "dependencies": dependencies or [],
        "findings": findings,
        "repair_candidates": repairs or [],
    }


IDENTITY_KEYS = ("version", "source_sha256", "runtime_sha256", "bundle_root")
RUNTIME_STATES = {"current", "repairable", "legacy", "source_changed", "unadopted",
                  "deferred", "unmanaged", "invalid"}


def validate_status_payload(payload: object) -> None:
    """Validate the frozen schema shape plus coherence JSON Schema cannot express."""
    required = {"schema_version", "state", "ready", "approved", "installed", "route",
                "overlay", "dependencies", "findings", "repair_candidates"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise MethodologyError("runtime status has an invalid top-level shape")
    if payload["schema_version"] != 1 or payload["state"] not in RUNTIME_STATES:
        raise MethodologyError("runtime status has an unknown schema version or state")
    if type(payload["ready"]) is not bool:
        raise MethodologyError("runtime status ready must be boolean")
    for key in ("approved", "installed"):
        value = payload[key]
        if value is not None and (not isinstance(value, dict) or set(value) != set(IDENTITY_KEYS)
                                  or not all(isinstance(value[k], str) for k in IDENTITY_KEYS)):
            raise MethodologyError(f"runtime status {key} identity is invalid")
    route = payload["route"]
    if (not isinstance(route, dict) or set(route) != {"valid", "detail"}
            or type(route["valid"]) is not bool or not isinstance(route["detail"], str)):
        raise MethodologyError("runtime status route is invalid")
    overlay = payload["overlay"]
    if (not isinstance(overlay, dict)
            or set(overlay) != {"valid", "sha256", "expected_sha256", "detail"}
            or type(overlay["valid"]) is not bool or not isinstance(overlay["detail"], str)
            or any(overlay[k] is not None and not isinstance(overlay[k], str)
                   for k in ("sha256", "expected_sha256"))):
        raise MethodologyError("runtime status overlay is invalid")
    if not isinstance(payload["dependencies"], list):
        raise MethodologyError("runtime status dependencies must be an array")
    for item in payload["dependencies"]:
        if (not isinstance(item, dict)
                or set(item) != {"path", "stage", "status", "expected_sha256", "actual_sha256"}
                or not isinstance(item["path"], str) or not isinstance(item["stage"], str)
                or item["status"] not in {"current", "missing", "changed", "invalid"}
                or any(item[k] is not None and not isinstance(item[k], str)
                       for k in ("expected_sha256", "actual_sha256"))):
            raise MethodologyError("runtime status dependency is invalid")
    if not isinstance(payload["findings"], list):
        raise MethodologyError("runtime status findings must be an array")
    for item in payload["findings"]:
        if (not isinstance(item, dict) or set(item) != {"code", "severity", "message", "path"}
                or not isinstance(item["code"], str)
                or item["severity"] not in {"info", "warning", "error"}
                or not isinstance(item["message"], str)
                or (item["path"] is not None and not isinstance(item["path"], str))):
            raise MethodologyError("runtime status finding is invalid")
    if not isinstance(payload["repair_candidates"], list):
        raise MethodologyError("runtime status repair_candidates must be an array")
    for item in payload["repair_candidates"]:
        if (not isinstance(item, dict) or set(item) != {"action", "paths"}
                or item["action"] != "render_approved" or not isinstance(item["paths"], list)
                or not item["paths"] or not all(isinstance(p, str) for p in item["paths"])):
            raise MethodologyError("runtime status repair candidate is invalid")
    current = payload["state"] == "current"
    if payload["ready"] != current:
        raise MethodologyError("runtime status ready contradicts state")
    if current:
        if (payload["approved"] is None or payload["installed"] is None
                or payload["approved"] != payload["installed"] or not route["valid"]
                or not overlay["valid"] or not payload["dependencies"]
                or any(item["status"] != "current" for item in payload["dependencies"])
                or payload["repair_candidates"]):
            raise MethodologyError("current runtime status is semantically contradictory")
    if payload["state"] == "repairable":
        if (not payload["repair_candidates"] or payload["approved"] is None
                or payload["installed"] is None
                or payload["approved"] != payload["installed"]):
            raise MethodologyError("repairable runtime status lacks an approved repair")
    elif payload["repair_candidates"]:
        raise MethodologyError("only repairable status may include repair candidates")


def marker(body: str, runtime_sha256: str) -> str:
    payload = json.dumps(
        {"v": METHODOLOGY_VERSION, "source_sha256": source_sha256(body),
         "runtime_sha256": runtime_sha256},
        separators=(",", ":"),
    )
    return f"<!-- execution-methodology: {payload} -->"


def render(body: str, overlay: str | None, runtime_sha256: str | None = None) -> str:
    digest = runtime_sha256 or runtime_declaration()["runtime_sha256"]
    parts = [GENERATED, marker(body, digest), "", body.rstrip()]
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


@contextmanager
def _output_directory(repo: Path, *, create: bool):
    """Open the output directory component-by-component without following symlinks."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise MethodologyError("safe no-follow repository writes are unavailable on this platform")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(repo.anchor, flags)
    try:
        for part in repo.parts[1:] + TARGET_REL.parent.parts:
            try:
                child = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, dir_fd=fd)
                child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _read_output(fd: int, name: str) -> str | None:
    try:
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    except FileNotFoundError:
        return None
    try:
        with os.fdopen(os.dup(file_fd), "r", encoding="utf-8", errors="replace") as stream:
            return stream.read()
    finally:
        os.close(file_fd)


def _open_output_for_write(fd: int, name: str, acceptable) -> int:
    """Bind a write to the verified file inode; a path swap cannot redirect the write."""
    flags = os.O_RDWR | os.O_NOFOLLOW
    try:
        file_fd = os.open(name, flags, dir_fd=fd)
        with os.fdopen(os.dup(file_fd), "r", encoding="utf-8", errors="replace") as stream:
            current = stream.read()
        if not acceptable(current):
            os.close(file_fd)
            raise MethodologyError(f"refusing to overwrite {name} (unmanaged output)")
        return file_fd
    except FileNotFoundError:
        try:
            return os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o644, dir_fd=fd)
        except FileExistsError as exc:
            raise MethodologyError(
                f"refusing to overwrite {name} after a concurrent path change") from exc


def _write_open_output(fd: int, text: str) -> None:
    data = text.encode("utf-8")
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]
    os.fsync(fd)


def _inventory_is_ours(text: str) -> bool:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict) and value.get("generated_by") == RUNTIME_GENERATOR


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
    _load_spec_check()
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


def _project_path(repo: Path, relative: Path, *, may_be_missing: bool = True) -> Path:
    """Resolve a project-owned path without accepting a symlink or escape."""
    root = repo.resolve(strict=True)
    candidate = repo / relative
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise MethodologyError(f"project runtime path is a symlink: {relative.as_posix()}")
        if not cursor.exists() and may_be_missing:
            break
    resolved_parent = candidate.parent.resolve(strict=False)
    if not _within(resolved_parent, root):
        raise MethodologyError(f"project runtime path escapes repository: {relative.as_posix()}")
    return candidate


def _identity(inventory: dict) -> dict:
    return {
        "version": inventory["methodology_version"],
        "source_sha256": inventory["source_sha256"],
        "runtime_sha256": inventory["runtime_sha256"],
        "bundle_root": inventory["bundle_root"],
    }


def _load_inventory(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MethodologyError(f"runtime inventory is unreadable: {exc}") from exc
    required = {"generated_by", "schema_version", "methodology_version", "source_sha256",
                "runtime_sha256", "bundle_root", "source_revision", "overlay_sha256", "files"}
    if not isinstance(value, dict) or set(value) != required:
        raise MethodologyError("runtime inventory has an invalid top-level shape")
    if (value["generated_by"] != RUNTIME_GENERATOR or value["schema_version"] != 1
            or not all(isinstance(value[k], str) for k in
                       ("methodology_version", "source_sha256", "runtime_sha256", "bundle_root"))
            or value["source_revision"] is not None
            and not isinstance(value["source_revision"], str)
            or value["overlay_sha256"] is not None
            and not isinstance(value["overlay_sha256"], str)
            or not isinstance(value["files"], list)):
        raise MethodologyError("runtime inventory has invalid field types")
    expected_pairs = list(RUNTIME_FILES)
    actual_pairs = []
    for item in value["files"]:
        if (not isinstance(item, dict) or set(item) != {"path", "stage", "sha256"}
                or not all(isinstance(item[k], str) for k in ("path", "stage", "sha256"))):
            raise MethodologyError("runtime inventory has an invalid file entry")
        actual_pairs.append((item["stage"], item["path"]))
    if actual_pairs != expected_pairs:
        raise MethodologyError("runtime inventory file declaration is incomplete or reordered")
    digest_input = json.dumps(value["files"], sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(digest_input).hexdigest() != value["runtime_sha256"]:
        raise MethodologyError("runtime inventory digest does not match its file declaration")
    return value


def runtime_status(repo: Path) -> dict:
    """Return the repository's complete execution runtime status.

    This function never discovers releases or falls back to another live installation. The
    inventory's explicit bundle root is the approved source; the running owner's bundle is the
    installed identity being compared with it.
    """
    findings: list[dict] = []
    try:
        repo = repo.resolve(strict=True)
        if not repo.is_dir():
            raise MethodologyError("repository is not a directory")
        target = _project_path(repo, TARGET_REL)
        inventory_path = _project_path(repo, RUNTIME_REL)
        overlay_path = _project_path(repo, OVERLAY_REL)
        readme_path = _project_path(repo, README_REL)
    except (OSError, MethodologyError) as exc:
        status = _base_status("invalid", [_finding("inspection_error", str(exc))],
                              route_detail=str(exc))
        validate_status_payload(status)
        return status

    current_text = None
    try:
        if target.is_file():
            current_text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        status = _base_status("invalid", [_finding("inspection_error", str(exc),
                                                          TARGET_REL.as_posix())],
                              route_detail="rendered methodology unreadable")
        validate_status_payload(status)
        return status

    if current_text is None and not inventory_path.is_file():
        decision, problem = read_deferral(repo)
        if decision is not None:
            findings.append(_finding("methodology_deferred",
                                     f"deferred since {decision['date']}: {decision['reason']}",
                                     README_REL.as_posix(), "info"))
            status = _base_status("deferred", findings)
        else:
            findings.append(_finding("methodology_unadopted", problem or
                                     "no rendered methodology or deferral decision",
                                     TARGET_REL.as_posix(), "warning"))
            status = _base_status("unadopted", findings)
        validate_status_payload(status)
        return status

    if current_text is not None and not is_ours(current_text):
        status = _base_status("unmanaged", [_finding(
            "methodology_unmanaged", "rendered methodology is not owned by this generator",
            TARGET_REL.as_posix())])
        validate_status_payload(status)
        return status

    if not inventory_path.is_file():
        status = _base_status("legacy", [_finding(
            "runtime_identity_legacy", "rendered methodology has no complete runtime identity",
            TARGET_REL.as_posix(), "warning")])
        validate_status_payload(status)
        return status

    try:
        inventory = _load_inventory(inventory_path)
        bundle_root = Path(inventory["bundle_root"])
        if not bundle_root.is_absolute():
            raise MethodologyError("runtime inventory bundle_root must be absolute")
        approved_root = bundle_root.resolve(strict=True)
        if str(approved_root) != inventory["bundle_root"]:
            raise MethodologyError("runtime inventory bundle_root is not canonical")
    except (OSError, MethodologyError) as exc:
        status = _base_status("invalid", [_finding("inspection_error", str(exc),
                                                          RUNTIME_REL.as_posix())],
                              route_detail="runtime inventory invalid")
        validate_status_payload(status)
        return status

    approved = _identity(inventory)
    dependencies = []
    for declared in inventory["files"]:
        actual = None
        status_name = "missing"
        try:
            dependency = _safe_declared_path(approved_root, declared["path"])
            actual = file_sha256(dependency)
            status_name = "current" if actual == declared["sha256"] else "changed"
        except FileNotFoundError:
            pass
        except (OSError, MethodologyError):
            status_name = "invalid"
        dependencies.append({"path": declared["path"], "stage": declared["stage"],
                             "status": status_name, "expected_sha256": declared["sha256"],
                             "actual_sha256": actual})

    try:
        installed_decl = runtime_declaration()
        installed = _identity(installed_decl)
    except (OSError, MethodologyError):
        installed = None

    actual_overlay = None
    overlay_problem = ""
    try:
        actual_overlay = overlay_sha256(read_overlay(repo))
    except MethodologyError as exc:
        overlay_problem = str(exc)
    expected_overlay = inventory["overlay_sha256"]
    overlay_valid = not overlay_problem and actual_overlay == expected_overlay
    overlay_status = {"valid": overlay_valid, "sha256": actual_overlay,
                      "expected_sha256": expected_overlay, "detail": overlay_problem or
                      ("" if overlay_valid else "overlay differs from approved identity")}

    routed, route_detail = route_status(repo)
    all_dependencies = bool(dependencies) and all(d["status"] == "current"
                                                  for d in dependencies)
    identity_current = installed == approved

    if not identity_current or not all_dependencies or not overlay_valid:
        if not identity_current:
            findings.append(_finding("installed_identity_changed",
                                     "installed runtime differs from the approved identity"))
        for dependency in dependencies:
            if dependency["status"] != "current":
                findings.append(_finding("runtime_dependency_" + dependency["status"],
                                         f"runtime dependency is {dependency['status']}",
                                         dependency["path"]))
        if not overlay_valid:
            findings.append(_finding("overlay_changed", overlay_status["detail"],
                                     OVERLAY_REL.as_posix()))
        status = _base_status("source_changed", findings, route_valid=routed,
                              route_detail=route_detail, overlay=overlay_status,
                              approved=approved, installed=installed, dependencies=dependencies)
    elif not routed:
        findings.append(_finding("route_invalid", route_detail, README_REL.as_posix()))
        # `invalid` is reserved for an inspection that could not complete (CLI exit 2). A changed
        # project route is a completely inspected runtime-input difference, so it follows the same
        # non-repairable classification as a changed overlay or dependency.
        status = _base_status("source_changed", findings, route_valid=False, route_detail=route_detail,
                              overlay=overlay_status, approved=approved, installed=installed,
                              dependencies=dependencies)
    else:
        expected = render(source_text(), read_overlay(repo), inventory["runtime_sha256"])
        if current_text != expected:
            repairs = [{"action": "render_approved", "paths": [TARGET_REL.as_posix()]}]
            findings.append(_finding("rendered_output_changed",
                                     "generated methodology differs from approved inputs",
                                     TARGET_REL.as_posix()))
            status = _base_status("repairable", findings, route_valid=True,
                                  overlay=overlay_status, approved=approved, installed=installed,
                                  dependencies=dependencies, repairs=repairs)
        else:
            status = _base_status("current", findings, route_valid=True,
                                  overlay=overlay_status, approved=approved, installed=installed,
                                  dependencies=dependencies)
    validate_status_payload(status)
    return status


def repair_approved_methodology(repo: Path, authorization: object) -> int:
    """Repair only generated output for the exact identity an earlier plan approved."""
    if (not isinstance(authorization, dict)
            or set(authorization) != {"identity", "overlay_expected_sha256"}):
        print("--repair-approved requires approved runtime and overlay identity JSON", file=sys.stderr)
        return 2
    approved = authorization["identity"]
    planned_overlay = authorization["overlay_expected_sha256"]
    if (not isinstance(approved, dict) or set(approved) != set(IDENTITY_KEYS)
            or not all(isinstance(approved[key], str) for key in IDENTITY_KEYS)):
        print("--repair-approved requires approved runtime and overlay identity JSON", file=sys.stderr)
        return 2
    if planned_overlay is not None and not isinstance(planned_overlay, str):
        print("--repair-approved requires approved runtime and overlay identity JSON", file=sys.stderr)
        return 2
    try:
        repo = repo.resolve(strict=True)
        with _output_directory(repo, create=False) as output_fd:
            status = runtime_status(repo)
            expected_candidate = [{"action": "render_approved",
                                   "paths": [TARGET_REL.as_posix()]}]
            if (status["state"] != "repairable" or status["approved"] != approved
                    or status["installed"] != approved
                    or status["overlay"]["expected_sha256"] != planned_overlay
                    or status["overlay"]["sha256"] != planned_overlay
                    or status["repair_candidates"] != expected_candidate
                    or not status["route"]["valid"] or not status["overlay"]["valid"]
                    or not status["dependencies"]
                    or any(row["status"] != "current" for row in status["dependencies"])):
                raise MethodologyError("approved identity changed; refusing repair")

            body = source_text()
            overlay_raw = _read_output(output_fd, OVERLAY_REL.name)
            if overlay_raw is not None and not overlay_raw.strip():
                raise MethodologyError(f"{OVERLAY_REL.as_posix()} exists but is empty")
            overlay = overlay_raw.strip() if overlay_raw is not None else None
            declaration = runtime_declaration()
            if (_identity(declaration) != approved
                    or source_sha256(body) != approved["source_sha256"]
                    or overlay_sha256(overlay) != planned_overlay):
                raise MethodologyError("approved identity changed; refusing repair")
            expected = render(body, overlay, approved["runtime_sha256"])

            # This is deliberately adjacent to the descriptor-bound write. It guards route,
            # overlay, dependencies, inventory and the generated target after materialization.
            final_status = runtime_status(repo)
            if (final_status["state"] != "repairable"
                    or final_status["approved"] != approved
                    or final_status["installed"] != approved
                    or final_status["overlay"]["expected_sha256"] != planned_overlay
                    or final_status["overlay"]["sha256"] != planned_overlay
                    or final_status["repair_candidates"] != expected_candidate):
                raise MethodologyError("approved identity changed; refusing repair")
            target_fd = _open_output_for_write(output_fd, TARGET_REL.name, is_ours)
            try:
                _write_open_output(target_fd, expected)
            finally:
                os.close(target_fd)
    except (OSError, UnicodeError, MethodologyError) as exc:
        print(exc, file=sys.stderr)
        return 2

    verified = runtime_status(repo)
    if (verified["state"] != "current" or verified["approved"] != approved
            or verified["installed"] != approved
            or verified["overlay"]["expected_sha256"] != planned_overlay
            or verified["overlay"]["sha256"] != planned_overlay):
        print("repair completed but the frozen approved identity did not reverify", file=sys.stderr)
        return 2
    print("repaired approved runtime")
    return 0


def sync(repo: Path, check: bool) -> int:
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
    code = render_methodology(repo, check)
    if code != 2:
        # Exit 2 means the source or the target could not be read at all. A configuration report
        # under that is noise stacked on a fault the reader must fix first.
        print_persona_config(persona_config(repo))
    return code


def render_methodology(repo: Path, check: bool) -> int:
    try:
        repo = repo.resolve(strict=True)
        body = source_text()
        overlay = read_overlay(repo)
        inventory = runtime_inventory(body, overlay)
    except (OSError, MethodologyError) as e:
        print(e, file=sys.stderr)
        return 2

    try:
        with _output_directory(repo, create=not check) as output_fd:
            return _render_methodology_open(repo, check, body, overlay, inventory, output_fd)
    except FileNotFoundError as e:
        if check:
            # A repository that has never rendered the output has no execution directory to open.
            # That is ordinary stale state (exit 1), not an inspection failure. This branch is
            # read-only; all mutation paths still require descriptor-bound destinations.
            return _render_methodology_open(repo, check, body, overlay, inventory, None)
        print(e, file=sys.stderr)
        return 2
    except (OSError, UnicodeError, MethodologyError) as e:
        print(e, file=sys.stderr)
        return 2


def _render_methodology_open(repo: Path, check: bool, body: str, overlay: str | None,
                             inventory: dict, output_fd: int | None) -> int:

    target = repo / TARGET_REL
    inventory_path = repo / RUNTIME_REL
    expected = render(body, overlay, inventory["runtime_sha256"])
    current = _read_output(output_fd, TARGET_REL.name) if output_fd is not None else None
    current_inventory = (_read_output(output_fd, RUNTIME_REL.name)
                         if output_fd is not None else None)
    if current_inventory is not None:
        try:
            previous = json.loads(current_inventory)
        except json.JSONDecodeError:
            previous = None
        if isinstance(previous, dict):
            previous_identity = {k: v for k, v in previous.items() if k != "source_revision"}
            current_identity = {k: v for k, v in inventory.items() if k != "source_revision"}
            if previous_identity == current_identity:
                # The recorded revision describes the approved content. A later unrelated commit
                # or dirty path cannot rewrite an otherwise identical adopted inventory.
                inventory["source_revision"] = previous.get("source_revision")
    expected_inventory = inventory_text(inventory)

    print(f"execution methodology v{METHODOLOGY_VERSION} "
          f"(source sha256 {source_sha256(body)})"
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

    if current == expected and current_inventory == expected_inventory:
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
        if current is None:
            reason = "missing"
        elif current != expected:
            reason = "stale or hand-edited"
        else:
            reason = f"{RUNTIME_REL.as_posix()} missing or stale"
        print("  STALE — the rendered methodology does not match its source:")
        print(f"    {target} ({reason})")
        print(f"  run: sync_methodology.py --repo {repo}")
        return 1

    if current_inventory is not None:
        try:
            parsed_inventory = json.loads(current_inventory)
        except json.JSONDecodeError:
            parsed_inventory = None
        if not isinstance(parsed_inventory, dict) or parsed_inventory.get("generated_by") != RUNTIME_GENERATOR:
            print(f"  refusing to overwrite {inventory_path} (unmanaged — not generated by this script)",
                  file=sys.stderr)
            return 2
    target_fd = inventory_fd = None
    try:
        inventory_fd = _open_output_for_write(
            output_fd, RUNTIME_REL.name, _inventory_is_ours,
        )
        target_fd = _open_output_for_write(output_fd, TARGET_REL.name, is_ours)
        _write_open_output(target_fd, expected)
        _write_open_output(inventory_fd, expected_inventory)
    finally:
        if inventory_fd is not None:
            os.close(inventory_fd)
        if target_fd is not None:
            os.close(target_fd)
    print(f"  wrote   {target}")
    print(f"  wrote   {inventory_path}")
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
    """Translate the owning structured runtime status into compact session-hook text; always 0."""
    head = f"AGENT CONTEXT: execution methodology v{METHODOLOGY_VERSION}"
    adopt_cmd = f"python3 {Path(__file__).resolve()} --repo {repo}"
    try:
        status = runtime_status(repo)
    except Exception as e:  # noqa: BLE001 -- a session hook must never fail the session
        print(f"{head} could not be evaluated for this repository.")
        print(f"  - [warn] {e}")
        print(f"  Invoke methodology-management for {repo} to assess the runtime gap.")
        return 0

    rel = TARGET_REL.as_posix()
    try:
        notes = persona_notes(persona_config(repo))
    except Exception as exc:  # noqa: BLE001 -- status remains useful when persona reporting cannot load
        notes = [f"persona configuration could not be evaluated: {exc}"]
    configure = (f"python3 {Path(__file__).resolve().parent / 'spec_check.py'} --root {repo} "
                 "--personas")

    def persona_block() -> None:
        """The persona half of the state, under whichever methodology state was printed."""
        for note in notes:
            print(f"  - [warn] {note}")
        if notes:
            print(f"  Decide the owners, then add one `covers:` line per validator — "
                  f"`{configure}` lists the pool and the concerns. Nothing writes it for you.")

    def finding_block() -> None:
        for finding in status["findings"][:3]:
            location = f" ({finding['path']})" if finding["path"] else ""
            print(f"  - [warn] {finding['message']}{location}")
        if len(status["findings"]) > 3:
            print(f"  - [warn] ... and {len(status['findings']) - 3} more runtime finding(s)")

    state = status["state"]
    if state == "current":
        if not notes:
            return 0
        print(f"{head} is adopted here, but its persona configuration is incomplete.")
        persona_block()
        return 0

    if state == "repairable":
        print(f"{head} is rendered into this repository but out of date.")
        finding_block()
        print(f"  Re-render: exact approved runtime with `{adopt_cmd}`")
        persona_block()
        return 0

    if state == "deferred":
        message = status["findings"][0]["message"] if status["findings"] else "deferred"
        match = re.fullmatch(r"deferred since (\d{4}-\d{2}-\d{2}): (.*)", message)
        if match:
            stamp, reason = match.groups()
            age = (datetime.now(timezone.utc).date() - date.fromisoformat(stamp)).days
            print(f"{head} is deliberately deferred here since {stamp} "
                  f"({age} day{'' if age == 1 else 's'}) — {reason}")
        else:
            print(f"{head} is deliberately deferred here — {message}")
        persona_block()
        return 0

    if state == "unadopted":
        print(f"{head} has not been adopted by this repository.")
        finding_block()
        print(f"  Invoke methodology-management for {repo} to assess adoption or deferral.")
        print(f"  A deferral is recorded in {README_REL.as_posix()} as:")
        print(f"    {DEFERRAL_EXAMPLE}")
        print("  Adoption is never automatic: nothing here will render into this repository for you.")
        persona_block()
        return 0

    if state == "invalid":
        print(f"{head} could not be evaluated for this repository.")
    elif state == "legacy":
        print(f"{head} is rendered here with a legacy runtime identity.")
    elif state == "unmanaged":
        print(f"{head} is rendered into this repository but out of date and unmanaged.")
    else:  # source_changed
        print(f"{head} is rendered here, but its approved runtime inputs are out of date.")
    finding_block()
    print(f"  Invoke methodology-management for {repo} to assess the runtime gap.")
    persona_block()
    return 0


def show_info(repo: Path | None) -> int:
    try:
        body = source_text()
    except MethodologyError as e:
        print(e, file=sys.stderr)
        return 2
    headings = [ln[3:].strip() for ln in body.splitlines() if ln.startswith("## ")]
    print(f"{'source':<10}  {SOURCE}")
    print(f"{'version':<10}  {METHODOLOGY_VERSION}")
    print(f"{'source sha':<10}  {source_sha256(body)}")
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
                    help="print the source, version and source digest")
    ap.add_argument("--status-json", action="store_true",
                    help="print exactly one structured runtime status object")
    ap.add_argument("--repair-approved", metavar="AUTHORIZATION_JSON",
                    help=("repair generated output only when route, overlay, inventory and source "
                          "still match this exact approved identity"))
    args = ap.parse_args()

    repo = Path(args.repo).resolve(strict=False) if args.repo else None
    if args.status_json:
        if repo is None or args.adoption or args.show or args.check or args.repair_approved:
            print("--status-json requires only --repo PATH", file=sys.stderr)
            return 2
        try:
            status = runtime_status(repo)
            validate_status_payload(status)
        except Exception as exc:  # noqa: BLE001 -- status must fail closed as structured JSON
            status = _base_status("invalid", [_finding("inspection_error", str(exc))],
                                  route_detail=str(exc))
        print(json.dumps(status, separators=(",", ":")))
        return 2 if any(f["code"] == "inspection_error" for f in status["findings"]) else 0
    if repo and not repo.is_dir():
        # Silent for the session-hook mode: a path that is not there is not a finding to shout at
        # the start of every session, and this mode's contract is that it never fails anything.
        if args.adoption:
            return 0
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2
    if args.repair_approved is not None:
        if repo is None or args.adoption or args.show or args.check:
            print("--repair-approved requires only --repo PATH", file=sys.stderr)
            return 2
        try:
            approved = json.loads(args.repair_approved)
        except json.JSONDecodeError as exc:
            print(f"--repair-approved identity is not valid JSON: {exc.msg}", file=sys.stderr)
            return 2
        return repair_approved_methodology(repo, approved)
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
    return sync(repo, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
