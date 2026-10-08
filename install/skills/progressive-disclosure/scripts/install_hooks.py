#!/usr/bin/env python3
"""Install the per-repository git hooks that keep agent context true.

Git hooks are not shared through git, so every clone needs this run once:

  pre-commit   validates the disclosure route and, in a repository that DECLARES ITSELF PUBLIC,
               scans the staged diff for private identifiers
  commit-msg   declaring repositories only: scans the commit MESSAGE for private identifiers
  pre-push     blocks secrets, files over the size limit, and direct pushes to the default branch
  post-commit  re-extracts changed code into the Graphify graph (with post-checkout): the blocks
               `graphify hook install` renders in a sandbox repository, written here by us

Each hook is written as a marked block, so an existing hook is preserved and a re-run replaces only
our block. The pre-commit route check skips silently when the repository has no route yet.

PUBLIC IS STATE THE REPOSITORY DECLARES, NOT A FLAG. The identifier guard is for deliberately
public repositories; in a private one every finding is a false positive. The installer reads the
repository's own `public-exception` marker through `check_github.public_exception()` — one marker,
one parser — and renders the guard because the repository says it is public:

  1. A declaring repository gets the guard on every run, with or without --public.
  2. --public only WRITES the declaration, once, and re-reads it through the parser.
  3. Removing the guard requires removing the declaration: a visible edit to a tracked file.
  4. A declaration with the guard absent is a finding with a non-zero exit, never silence.

Parser states: "active" renders the guard; "invalid", or "none" with a diagnostic, is marker text
nobody can act on, so each half of the guard keeps the state it is in and the run exits 1;
"unknown" (the parser could not be imported or raised) is treated the same way. Only "none" with
an empty diagnostic removes the guard.

OPEN, ESCALATED: `check_github.py` skips a candidate marker file it cannot read, so a public
repository whose only marker file is unreadable reads as "nothing declared" and is disarmed at
exit 0. Fixing it needs the shared parser to tell "unreadable" from "absent"; it is not closed here.

NO HOOK IS DECLARED INSTALLED WITHOUT VERIFYING WHAT IT INVOKES. `install_hook` is the only way a
git hook is written: it reads the dependencies out of the rendered block (and their sibling
imports), refuses to write when one is missing, and prints the success line and the "blocks:"
claims only after the write is verified on disk. The claims are read out of the guards' own module
constants, and anything that cannot be substantiated is not claimed.

Usage:
  install_hooks.py [ROOT]              # install / update
  install_hooks.py [ROOT] --check      # report status, change nothing
  install_hooks.py [ROOT] --uninstall  # remove only our block
  install_hooks.py [ROOT] --standard   # pre-commit also enforces the structure standard
  install_hooks.py [ROOT] --public     # DECLARE this repository public, once (public repos ONLY)
  install_hooks.py [ROOT] --scope project [--preview [--json]]   # one inspectable plan
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

BEGIN = "# >>> progressive-disclosure >>>"
END = "# <<< progressive-disclosure <<<"

PRE_COMMIT = """{begin}
# Validates the agent disclosure route and the README contract. Skips silently when this repo
# has no route yet or the validator is not installed. Warnings remain visible; structural
# errors block the commit.
#
# The two failing exit codes are NOT the same sentence, and saying so is the whole point of the
# distinction: 1 is "I looked, and the route is broken"; 2 is "I could not look, so nothing below
# is a verdict". The tail line used to say "the route is broken" for both, which overstated the
# check in exactly the direction that costs trust — it reported a finding the validator never made
# and sent at least one fix pass at a route that was fine. The guard's own code is propagated, so
# the two stay distinguishable at the hook's boundary (git collapses both to a blocked commit).
_pd_validator="$HOME/.claude/skills/progressive-disclosure/scripts/validate_disclosure.py"
if [ -f "docs/agents/README.md" ] && [ -f "$_pd_validator" ]; then
  _pd_out=$(PYTHONDONTWRITEBYTECODE=1 python3 "$_pd_validator" .{flags} --hook 2>&1)
  _pd_rc=$?
  [ -z "$_pd_out" ] || printf '%s\\n' "$_pd_out"
  if [ "$_pd_rc" -eq 1 ]; then
    echo "pre-commit: the agent disclosure route is broken. Fix the reported finding."
    exit 1
  elif [ "$_pd_rc" -ne 0 ]; then
    echo "pre-commit: the agent disclosure route was NOT CHECKED (validator exit $_pd_rc)." >&2
    echo "  This is not a finding against the route — it is the absence of a verdict, and a check" >&2
    echo "  that did not run is not a clean result. Fix what it reported above, then commit." >&2
    exit "$_pd_rc"
  fi
fi
{identifier}{end}
"""

# Rendered into the SAME marked block as the route check, so `write_hook` takes the stanza away
# again when the repository stops declaring itself public. Two hooks, because `pre-commit` runs
# before the message exists and only `commit-msg` receives it; one script serves both.
#
# THE MISSING-GUARD BRANCH IS NOT A SKIP: a guard that did not run must never read as a clean
# commit, so absence exits 2, and the guard's own exit code is propagated.
PRE_COMMIT_IDENTIFIER = """
# Public repositories only. Blocks private identifiers — home paths, the local git identity, and
# names from ~/.claude/private-identifiers.txt — from entering the STAGED CONTENT. Exit 1 is a
# finding, exit 2 is a guard that could not run; neither may be committed past, and the guard's own
# code is propagated so the two stay distinguishable.
_pd_ident="$HOME/.claude/skills/progressive-disclosure/scripts/identifier_guard.py"
if [ -f "$_pd_ident" ]; then
  PYTHONDONTWRITEBYTECODE=1 python3 "$_pd_ident" --staged
  _pd_rc=$?
  [ "$_pd_rc" -eq 0 ] || exit "$_pd_rc"
else
  echo "commit BLOCKED: the private-identifier guard is not installed at" >&2
  echo "  $_pd_ident" >&2
  echo "  This repository DECLARES itself public (a public-exception marker in its routed" >&2
  echo "  contract), so it is treated as PUBLIC and the staged content has NOT been scanned." >&2
  echo "  A scan that did not run is not a clean result." >&2
  echo "  Reinstall the progressive-disclosure skill, or — if this repository is not in fact" >&2
  echo "  public — remove the public-exception marker and re-run install_hooks.py. Dropping" >&2
  echo "  --public no longer removes this hook; the declaration does. Do not commit past it." >&2
  exit 2
fi
"""

COMMIT_MSG = """{begin}
# Public repositories only. The other half of the identifier guard: a pre-commit hook runs before
# the commit message exists, so the MESSAGE can only be checked here, where git passes its path as
# $1. An absent guard BLOCKS rather than skipping, for the reason given above PRE_COMMIT_IDENTIFIER:
# this hook's whole job is to assert that the message was scanned, and silence would assert it
# falsely. Exit 1 is a finding, exit 2 is a guard that could not run; the guard's own code is
# propagated.
_pd_ident="$HOME/.claude/skills/progressive-disclosure/scripts/identifier_guard.py"
if [ -f "$_pd_ident" ]; then
  PYTHONDONTWRITEBYTECODE=1 python3 "$_pd_ident" --message "$1"
  _pd_rc=$?
  [ "$_pd_rc" -eq 0 ] || exit "$_pd_rc"
else
  echo "commit BLOCKED: the private-identifier guard is not installed at" >&2
  echo "  $_pd_ident" >&2
  echo "  The commit MESSAGE has NOT been scanned, and a scan that did not run is not a clean" >&2
  echo "  result. Reinstall the progressive-disclosure skill, or — if this repository is not in" >&2
  echo "  fact public — remove its public-exception marker and re-run install_hooks.py. Dropping" >&2
  echo "  --public no longer removes this hook; the declaration does. Do not commit past it." >&2
  exit 2
fi
{end}
"""

# THE RUNTIME `[ -f ]` HERE IS DELIBERATELY LEFT AS A SKIP, AND IT IS THE ONE REMAINING HOLE.
# `install_hook` refuses to write this hook unless push_guard.py is present, but a guard deleted
# AFTER a good install makes this block skip silently. Making it exit non-zero changes push
# behaviour across every installed repository, so it is a founder decision, not made here.
PRE_PUSH = """{begin}
# Blocks credentials, oversized blobs, and direct pushes to the default branch. The installer will
# not write this block unless the guard exists; if the guard is removed afterwards this skips
# silently. Fix a reported finding before pushing.
_pd_guard="$HOME/.claude/skills/progressive-disclosure/scripts/push_guard.py"
if [ -f "$_pd_guard" ]; then
  PYTHONDONTWRITEBYTECODE=1 python3 "$_pd_guard" "$@" || exit 1
fi
{end}
"""


def render_pre_commit(*, standard: bool = False, public: bool = False) -> str:
    """The one composition of the pre-commit block. Every caller goes through here.

    `public` is NOT the --public flag: `main()` derives it from the repository's own declaration.
    `test_the_guard_is_not_decided_by_the_flag` checks by data flow that it never derives from
    `args.public`. --readme by default, because the README contract is part of the standard and
    --standard is its superset.
    """
    return PRE_COMMIT.format(
        begin=BEGIN,
        end=END,
        flags=" --standard" if standard else " --readme",
        identifier=PRE_COMMIT_IDENTIFIER if public else "",
    )


def hook_path(root: Path, name: str) -> Path:
    return root / ".git" / "hooks" / name


def guard_state(root: Path) -> tuple[bool, bool]:
    """(pre-commit carries the identifier stanza, commit-msg carries it). BOTH halves, always.

    The halves are independent on disk and are read and preserved independently; reducing them to
    one boolean once stripped a surviving half while printing that nothing had changed.
    """
    return ("identifier_guard.py" in read(hook_path(root, "pre-commit")),
            "identifier_guard.py" in read(hook_path(root, "commit-msg")))


# ---------------------------------------------------------------------------------------------
# The declaration: what the REPOSITORY says about its own visibility. One marker, one parser.
# ---------------------------------------------------------------------------------------------

# An instruction rather than a justification: check_github.py prints it back as the grounds for
# waiving a critical finding, and "because a tool wrote it" is not grounds.
DECLARATION_REASON = ("declared public with install_hooks.py --public; replace this reason with why "
                      "this repository is deliberately world readable")

# Exactly the shape check_github.py's anchored pattern requires; `write_declaration` re-reads it
# through the parser, so a marker the parser will not honour is caught at write time.
DECLARATION_TEMPLATE = "<!-- public-exception: {payload} -->"


def _undetermined(detail: str) -> dict:
    """Visibility was NOT determined. Not "none": that is an answer, and this is its absence."""
    return {"state": "unknown", "reason": "", "date": "", "detail": detail, "where": "",
            "committed": None, "age_days": None}


def _check_github():
    """The sibling module that owns the marker. Imported, never reimplemented."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import check_github
    return check_github


def public_declaration(root: Path) -> dict:
    """Does this repository declare itself public? Answered by check_github.py's parser, or not at all.

    An import failure or a parser exception becomes "unknown", which the caller treats as grounds to
    KEEP a guard and never as grounds to remove one.
    """
    try:
        cg = _check_github()
    except Exception as exc:  # noqa: BLE001 — any import failure is the same answer: nobody knows
        return _undetermined(f"check_github.py could not be imported ({type(exc).__name__}), so this "
                             f"repository's public-exception declaration was NOT read")
    try:
        return cg.public_exception(root)
    except Exception as exc:  # noqa: BLE001 — the parser reads attacker-writable text
        return _undetermined(f"the public-exception marker could not be evaluated "
                             f"({type(exc).__name__}), so visibility was NOT determined")


def declaration_line(decl: dict) -> str:
    """One line naming the state and, when there is one, the diagnostic the parser produced."""
    why = f" — {decl['detail']}" if decl.get("detail") else ""
    if decl["state"] == "active":
        stamp = f"{decl['where']}, dated {decl['date']}"
        if decl.get("committed") is False:
            stamp += ", marker NOT COMMITTED so nothing in history records it"
        return f"YES ({stamp})"
    if decl["state"] == "invalid":
        return f"NO — a marker was found but it is not a decision{why}"
    if decl["state"] == "unknown":
        return f"NOT DETERMINED{why}"
    return f"no{why}"


def write_declaration(root: Path, decl: dict) -> tuple[bool, str]:
    """Record the public declaration in the repository, once. Returns (wrote, explanation).

    Refuses when a declaration is already active, when any marker text was already found (the
    parser rejects two markers), and when no routed file exists to record it in. Written, read back
    through the parser, and reverted byte for byte if the parser does not honour it.
    """
    if decl["state"] == "active":
        return False, f"already declared in {decl['where']}, dated {decl['date']} — nothing written"
    if decl["state"] == "unknown":
        return False, decl["detail"]
    if decl["state"] == "invalid" or decl.get("detail"):
        return False, (f"a `public-exception` marker is already present and is not honoured "
                       f"({decl['detail'] or 'see check_github.py'}). Writing a second one would "
                       f"make the pair unreadable — fix the existing marker by hand")
    try:
        cg = _check_github()
    except Exception as exc:  # noqa: BLE001
        return False, f"check_github.py could not be imported ({type(exc).__name__})"

    target = next((rel for rel in cg.MARKER_FILES
                   if (root / rel).is_file() and cg.resolves_inside(root / rel, root)), None)
    if target is None:
        return False, ("none of " + ", ".join(cg.MARKER_FILES) + " exists in this repository, so "
                       "there is no routed file to record the decision in. Create the route first")

    path = root / target
    payload = json.dumps({"reason": DECLARATION_REASON,
                          "date": time.strftime("%Y-%m-%d")},
                         ensure_ascii=False, separators=(",", ":"))
    marker = DECLARATION_TEMPLATE.format(payload=payload)
    try:
        before = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return False, f"{target} could not be read ({e.__class__.__name__})"
    try:
        path.write_text(before.rstrip("\n") + "\n\n" + marker + "\n", encoding="utf-8")
    except OSError as e:
        return False, f"{target} could not be written ({e.__class__.__name__})"

    after = public_declaration(root)
    if after["state"] != "active" or after["where"] != target:
        try:
            path.write_text(before, encoding="utf-8")
        except OSError:
            return False, (f"the marker written to {target} is NOT honoured by the parser "
                           f"({declaration_line(after)}) and {target} could NOT be restored — "
                           f"remove the last line of that file by hand")
        return False, (f"the marker appended to {target} is NOT honoured by the parser "
                       f"({declaration_line(after)}); {target} has been restored unchanged. This is "
                       f"usually an unclosed code fence earlier in the file swallowing everything "
                       f"after it. Place the marker by hand at column zero, outside any code block")
    return True, (f"recorded in {target}: {marker}  — this repository now declares itself public, "
                  f"and the identifier guard follows from that declaration rather than from the flag")


# ---------------------------------------------------------------------------------------------
# Dependency resolution: one place, and it reads the hook rather than being told about the hook.
# ---------------------------------------------------------------------------------------------

# Every hook names its script as a double-quoted "$HOME/.claude/.../thing.py" literal, so the
# dependency is read FROM THE RENDERED TEXT and a hook nobody has written yet is covered too.
HOOK_SCRIPT_REF = re.compile(r'"\$HOME/(\.claude/[A-Za-z0-9._/+-]+\.py)"')

# A sibling import inside a dependency is a dependency too: push_guard.py imports
# validate_disclosure at module scope and exits 2 on every push without it.
SIBLING_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]+import|import[ \t]+([A-Za-z_][A-Za-z0-9_]*))",
    re.M,
)


def block_dependencies(block: str) -> list[Path]:
    """Every script this rendered hook block invokes, in first-appearance order, de-duplicated."""
    return [Path.home() / rel for rel in dict.fromkeys(HOOK_SCRIPT_REF.findall(block))]


def script_dependencies(script: Path) -> list[Path]:
    """Sibling scripts this dependency imports, including the ones NOT on disk.

    A bare imported name is a sibling when it is neither in the standard library nor importable from
    elsewhere on this interpreter's path. Dotted imports are not matched; nothing here ships one.
    """
    try:
        source = script.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return []
    found: list[Path] = []
    for a, b in SIBLING_IMPORT.findall(source):
        name = a or b
        sibling = script.parent / f"{name}.py"
        if sibling in found:
            continue
        if sibling.is_file():
            found.append(sibling)
            continue
        # `getattr`: `sys.stdlib_module_names` is 3.10+, and a traceback here would end the run that
        # decides whether a guard may honestly be claimed.
        if name in getattr(sys, "stdlib_module_names", ()):
            continue
        try:
            if importlib.util.find_spec(name) is not None:
                continue
        except (ImportError, ValueError, AttributeError):
            pass
        found.append(sibling)
    return found


def missing_dependencies(block: str) -> list[Path]:
    """The scripts this block needs that are not on disk, one level past each direct dependency."""
    missing: list[Path] = []
    for dep in block_dependencies(block):
        if not dep.is_file():
            missing.append(dep)
            continue
        for onward in script_dependencies(dep):
            if not onward.is_file() and onward not in missing:
                missing.append(onward)
    return missing


def _module_constant(script: Path, name: str):
    """Read a module-level literal out of a script WITHOUT importing it, or None."""
    try:
        tree = ast.parse(script.read_text(encoding="utf-8", errors="strict"))
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return None
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        if node.value is None:
            return None
        try:
            return ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return None
    return None


# ---------------------------------------------------------------------------------------------
# Claims: derived from the scripts that were just verified, never written beside the install.
# ---------------------------------------------------------------------------------------------

def _pre_push_claims(block: str) -> list[str]:
    """What the pre-push guard on this disk enforces, read out of its own module constants."""
    deps = block_dependencies(block)
    guard = next((d for d in deps if d.name == "push_guard.py"), None)
    if guard is None or not guard.is_file():
        return []
    source = guard.read_text(encoding="utf-8", errors="replace")
    claims: list[str] = []

    if any(d.name == "validate_disclosure.py" for d in script_dependencies(guard)):
        claims.append("credentials in the pushed range")

    mb = _module_constant(guard, "MAX_FILE_MB")
    if isinstance(mb, (int, float)) and not isinstance(mb, bool):
        # A source literal: there is no environment variable to raise it.
        claims.append(f"files over {mb:g} MB (not configurable)")

    branches = _module_constant(guard, "DEFAULT_BRANCHES")
    if isinstance(branches, (list, tuple)) and branches:
        names = " or ".join(str(b).rsplit("/", 1)[-1] for b in branches)
        hatch = " unless PD_ALLOW_MAIN_PUSH=1" if "PD_ALLOW_MAIN_PUSH" in source else ""
        claims.append(f"direct pushes to {names}{hatch}")
    return claims


def _pre_commit_claims(block: str) -> list[str]:
    """Read out of the rendered block, because the block is what will run.

    No provenance for the identifier stanza: the block records THAT it is present, never WHY, and
    `main()` already prints why on the one path that knows.
    """
    claims = []
    if "--standard" in block:
        claims.append("route errors and the structure standard (--standard)")
    elif "--readme" in block:
        claims.append("route errors and the seven-section README contract (--readme)")
    if any(d.name == "identifier_guard.py" for d in block_dependencies(block)):
        claims.append("private identifiers in the STAGED CONTENT")
    return claims


def _commit_msg_claims(block: str) -> list[str]:
    """The identifier guard's claims, and only the ones its deny-list file supports today."""
    deps = block_dependencies(block)
    guard = next((d for d in deps if d.name == "identifier_guard.py"), None)
    if guard is None or not guard.is_file():
        return []
    claims = ["absolute home paths and the local git identity"]
    denylist = Path.home() / ".claude" / "private-identifiers.txt"
    if denylist.is_file():
        try:
            names = [ln for ln in denylist.read_text(encoding="utf-8", errors="replace").splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")]
        except OSError:
            names = []
        # The count, not the names — this line is printed in a terminal and often pasted.
        claims.append(f"{len(names)} name(s) from ~/.claude/private-identifiers.txt, which is NOT in "
                      f"any repository")
    else:
        claims.append("no deny-list at ~/.claude/private-identifiers.txt yet, so NO project name "
                      "is blocked — create it to enable that half")
    return claims


def _no_claims(_block: str) -> list[str]:
    return []


CLAIM_SOURCES = {
    "pre-commit": _pre_commit_claims,
    "pre-push": _pre_push_claims,
    "commit-msg": _commit_msg_claims,
}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def strip_block(text: str, begin: str = BEGIN, end: str = END) -> str:
    if begin not in text:
        return text
    head, _, rest = text.partition(begin)
    _, _, tail = rest.partition(end)
    return (head.rstrip("\n") + "\n" + tail.lstrip("\n")).strip("\n")


def _commit_hook(path: Path, content: str | None) -> None:
    """Write (None: delete) a hook through the scoped plan's destination check and no-follow
    commit, so no path writes or removes a file outside the project's own hooks directory."""
    path = path.absolute()
    roots = _scope_file_roots(path.parents[2])
    if error := _destination_error(path, roots):
        raise OSError(f"unsafe hook destination {path}: {error}")
    action = "delete" if content is None else "update" if path.exists() else "create"
    _commit_file(PlannedFile(action, path, content, executable=True), roots)


def write_hook(path: Path, block: str) -> str:
    """Insert or replace our block, preserving any hook the user already had."""
    existing = strip_block(read(path))
    if not existing.strip():
        body = "#!/bin/sh\n" + block
        action = "installed"
    else:
        lines = existing.splitlines()
        if lines and lines[0].startswith("#!"):
            body = lines[0] + "\n" + "\n".join(lines[1:]).strip("\n") + "\n\n" + block
        else:
            body = "#!/bin/sh\n" + existing + "\n\n" + block
        action = "updated (existing hook preserved)"
    _commit_hook(path, body)
    return action


def install_hook(root: Path, name: str, block: str, *, suffix: str = "") -> bool:
    """THE ONLY WAY A GIT HOOK IS WRITTEN, AND THE ONLY PLACE ITS INSTALLATION IS CLAIMED.

    A missing dependency is fatal for this hook only: nothing is written, an existing hook is left
    exactly as it was, and the caller exits non-zero. Returns True when the hook is installed and
    its claims are honest. `test_install_hooks_deps.py` asserts there is no bypass.
    """
    missing = missing_dependencies(block)
    if missing:
        print(f"  {name} NOT INSTALLED — it invokes a script that is not on this machine:")
        for p in missing:
            print(f"      {p}")
        print(f"      Writing the hook anyway would put a wrapper around nothing and report it as")
        print(f"      installed. Any {name} hook already in this repository has been left alone.")
        print(f"      Fix: reinstall the progressive-disclosure skill, then re-run this command.")
        return False

    path = hook_path(root, name)
    try:
        action = write_hook(path, block)
    except OSError as exc:
        print(f"  {name} NOT INSTALLED — {exc}")
        return False

    # Read back rather than trust the write.
    if BEGIN not in read(path):
        print(f"  {name} FAILED — the block is not present in {path} after writing it.")
        return False

    print(f"  {name} {action}{suffix}")
    for i, claim in enumerate(CLAIM_SOURCES.get(name, _no_claims)(block)):
        print(f"    blocks: {claim}" if i == 0 else f"            {claim}")
    return True


def remove_hook_block(path: Path) -> str:
    """Take our block out of a hook, deleting the file only if nothing else was in it.

    Reached from the commit-msg path only when the parser found no HONOURED marker in any candidate
    file it COULD READ — not a guarantee that it read every routed file (the open escalation in the
    module docstring).
    """
    if not path.is_file():
        return "absent"
    content = _desired_removed_hook(path)
    _commit_hook(path, content)
    return "removed" if content is None else "removed (kept the rest)"


def graphify_root(root: Path) -> Path | None:
    """Directory whose graphify-out/graph.json is the repository's graph (root, or one level down)."""
    if (root / "graphify-out" / "graph.json").is_file():
        return root
    canonical = root.resolve()
    for child in sorted(root.iterdir()):
        # A symlinked child, or one resolving outside the root, is another repository's graph.
        if child.name.startswith(".") or child.is_symlink() or not child.is_dir() \
                or canonical not in child.resolve().parents:
            continue
        if (child / "graphify-out" / "graph.json").is_file():
            return child
    return None


def graphify_available() -> bool:
    """Found on PATH, not run: graphify only ever runs inside `_render_graphify_blocks`' sandbox."""
    return shutil.which("graphify") is not None


# graphify renders, we write. Its own installer picks the hooks directory from its cwd, GIT_DIR and
# core.hooksPath, and each of those once led outside the checked hooks, so it never runs against
# the project: it renders into a throwaway repository and we copy its two marked blocks into
# .git/hooks through `_commit_hook`, where our own hooks live whatever core.hooksPath says.
GRAPHIFY_MARKERS = {
    "post-commit": ("# graphify-hook-start", "# graphify-hook-end"),
    "post-checkout": ("# graphify-checkout-hook-start", "# graphify-checkout-hook-end"),
}


def _marked_block(text: str, begin: str, end: str) -> str | None:
    """`begin` through `end`, inclusive; None when neither is present. ValueError if malformed."""
    if begin not in text and end not in text:
        return None
    start = text.find(begin)
    stop = text.find(end, start) if start >= 0 else -1
    if stop < 0 or text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError(f"malformed `{begin}` … `{end}` block")
    return text[start:stop + len(end)]


def _render_graphify_blocks() -> dict[str, str]:
    """Run `graphify hook install` in a fresh sandbox repository with no inherited git state."""
    with tempfile.TemporaryDirectory(prefix="graphify-render-") as tmp:
        sandbox = Path(tmp).resolve()
        repo = sandbox / "repo"
        repo.mkdir()
        (sandbox / "gitconfig").write_text("", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(sandbox / "gitconfig"),
                   HOME=str(sandbox))
        for cmd in (["git", "init", "-q"], ["graphify", "hook", "install"]):
            r = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                raise RuntimeError(f"`{' '.join(cmd)}` exited {r.returncode}: "
                                   f"{r.stderr.strip()[:120]}")
        blocks = {}
        for name, (begin, end) in GRAPHIFY_MARKERS.items():
            if (block := _marked_block(read(repo / ".git" / "hooks" / name), begin, end)) is None:
                raise ValueError(f"graphify rendered no {name} block")
            blocks[name] = block
        return blocks


def _graph_edits(root: Path, blocks: dict[str, str] | None) -> list[tuple[Path, str | None]]:
    """Project hook contents that add `blocks`, or strip graphify's blocks when None (None content:
    delete). Every hook is read and checked before the caller writes any; malformed raises."""
    edits: list[tuple[Path, str | None]] = []
    for name, (begin, end) in GRAPHIFY_MARKERS.items():
        path = hook_path(root, name)
        current = read(path)
        old = _marked_block(current, begin, end)
        if blocks is None:
            if old is not None:
                rest = strip_block(current, begin, end)
                edits.append((path, None if rest.strip() in ("", "#!/bin/sh", "#!/bin/bash")
                              else rest + "\n"))
        elif old != blocks[name] or not os.access(path, os.X_OK):
            if old is not None:
                text = current.replace(old, blocks[name])
            elif current.strip() in ("", "#!/bin/sh"):
                text = "#!/bin/sh\n" + blocks[name] + "\n"
            else:
                text = (("" if current.startswith("#!") else "#!/bin/sh\n")
                        + current.rstrip("\n") + "\n\n" + blocks[name] + "\n")
            edits.append((path, text))
    return edits


def remove_graph_blocks(root: Path) -> bool:
    """Strip graphify's blocks from the project's hooks. graphify is not run."""
    try:
        for path, content in _graph_edits(root, None):
            _commit_hook(path, content)
            print(f"  graphify {path.name} block removed")
    except (OSError, ValueError) as exc:
        print(f"  graphify blocks NOT removed — {exc}")
        return False
    return True


REPO_LOCATION_ENV = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_PREFIX"}


def install_graph_hook(root: Path, *, no_graph: bool) -> bool:
    """The post-commit and post-checkout graph refresh: rendered by `graphify`, written by us.

    Its dependency is a BINARY ON PATH, not a script inside a hook block, so `graphify_available()`
    is the equivalent check and it runs before any claim.
    """
    if no_graph:
        print("  post-commit graph refresh skipped (--no-graph)")
        return False
    if graphify_root(root) is None:
        print("  post-commit graph refresh skipped — no graphify-out/graph.json in this repo")
        return False
    if not graphify_available():
        print("  post-commit graph refresh skipped — graphify is not installed")
        return False
    # Install only when core.hooksPath is unset at every level (exit 1); any other outcome skips.
    # The query must see the configuration a running git sees: drop the repository-location
    # variables and GIT_CONFIG, which only `git config` reads; every other config variable applies.
    env = {k: v for k, v in os.environ.items() if k not in REPO_LOCATION_ENV | {"GIT_CONFIG"}}
    try:
        unset = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=root, env=env,
                               capture_output=True, text=True, timeout=30).returncode == 1
    except (OSError, subprocess.SubprocessError):
        unset = False
    if not unset:
        print("  post-commit graph refresh skipped — core.hooksPath is configured; "
              "git may not run hooks in .git/hooks")
        return False
    try:
        for path, content in _graph_edits(root, _render_graphify_blocks()):
            _commit_hook(path, content)
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        print(f"  post-commit graph refresh FAILED: {exc}")
        return False
    print("  post-commit graph refresh installed")
    print("    note: it re-extracts changed CODE only. Documentation changes still need a")
    print("    semantic rebuild — `graphify extract . --mode deep --backend <backend>`.")
    return True


# ---------------------------------------------------------------------------------------------
# --scope project: one inspectable plan, committed through no-follow directory descriptors.
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PlannedFile:
    action: str
    path: Path
    content: str | None
    executable: bool = False

    def public(self) -> dict[str, str]:
        return {"action": self.action, "path": str(self.path)}


@dataclass(frozen=True)
class FileAuthority:
    lexical: Path
    canonical: Path


def _scope_file_roots(root: Path, scope: str = "project") -> tuple[FileAuthority, ...]:
    """Freeze the lexical and canonical project authority once for plan and commit."""
    lexical = root.absolute()
    return (FileAuthority(lexical, lexical.resolve(strict=False)),)


def _destination_error(path: Path, roots: tuple[FileAuthority, ...]) -> str | None:
    """Reject escape paths and every symlink from an authorized root through the leaf."""
    if not path.is_absolute():
        return "destination is not absolute"
    selected: FileAuthority | None = None
    relative: Path | None = None
    for authority in sorted(roots, key=lambda item: len(item.lexical.parts), reverse=True):
        try:
            candidate = path.relative_to(authority.lexical)
        except ValueError:
            continue
        selected, relative = authority, candidate
        break
    if selected is None or relative is None:
        return "destination is outside the authorized roots"
    resolved_path = path.resolve(strict=False)
    if resolved_path != selected.canonical and selected.canonical not in resolved_path.parents:
        return "destination resolves outside its authorized root"
    current = selected.lexical
    if current.is_symlink():
        return f"authorized root is a symlink: {current}"
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            return f"destination contains a symlink: {current}"
    return None


def _open_directory_nofollow(path: Path, *, create: bool) -> int:
    """Open an absolute directory by descriptor, refusing symlinks at every component."""
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            try:
                child = os.open(component, flags | nofollow, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, mode=0o777, dir_fd=descriptor)
                child = os.open(component, flags | nofollow, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _authorized_relative(path: Path, roots: tuple[FileAuthority, ...]) -> tuple[FileAuthority, Path]:
    for authority in sorted(roots, key=lambda item: len(item.lexical.parts), reverse=True):
        try:
            return authority, path.relative_to(authority.lexical)
        except ValueError:
            continue
    raise OSError(f"unsafe destination outside authorized roots: {path}")


def _commit_file(operation: PlannedFile, roots: tuple[FileAuthority, ...]) -> None:
    """Commit one operation relative to pinned no-follow directory descriptors."""
    if operation.action not in ("create", "update", "delete"):
        raise OSError(f"unsupported planned file action: {operation.action}")
    authority, relative = _authorized_relative(operation.path, roots)
    if not relative.parts:
        raise OSError(f"refusing to mutate authorized root itself: {operation.path}")
    # The canonical spelling was frozen before planning. Re-resolving here would let an authority
    # replacement redirect the commit between preview and apply.
    root_fd = _open_directory_nofollow(authority.canonical, create=True)
    parent_fd = root_fd
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) \
                | getattr(os, "O_NOFOLLOW", 0)
        for component in relative.parts[:-1]:
            try:
                child = os.open(component, flags, dir_fd=parent_fd)
            except FileNotFoundError:
                os.mkdir(component, mode=0o777, dir_fd=parent_fd)
                child = os.open(component, flags, dir_fd=parent_fd)
            if parent_fd != root_fd:
                os.close(parent_fd)
            parent_fd = child
        leaf = relative.parts[-1]
        try:
            existing = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and stat.S_ISLNK(existing.st_mode):
            raise OSError(f"unsafe symlink destination at commit: {operation.path}")
        if operation.action == "delete":
            os.unlink(leaf, dir_fd=parent_fd)
            return
        temporary = f".{leaf}.install-hooks-{os.getpid()}-{time.time_ns()}"
        write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) \
                      | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(temporary, write_flags, 0o666, dir_fd=parent_fd)
        try:
            data = (operation.content or "").encode("utf-8")
            view = memoryview(data)
            while view:
                written = os.write(file_fd, view)
                view = view[written:]
            if operation.executable:
                os.fchmod(file_fd, 0o755)
            elif existing is not None:
                os.fchmod(file_fd, existing.st_mode & 0o777)
        finally:
            os.close(file_fd)
        try:
            os.replace(temporary, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            raise
    finally:
        if parent_fd != root_fd:
            os.close(parent_fd)
        os.close(root_fd)


def _desired_hook(path: Path, block: str) -> str:
    current = read(path)
    if BEGIN in current and END in current:
        installed = current[current.index(BEGIN):current.index(END) + len(END)]
        if installed == block.strip("\n"):
            return current
    existing = strip_block(current)
    if not existing.strip():
        return "#!/bin/sh\n" + block
    lines = existing.splitlines()
    if lines and lines[0].startswith("#!"):
        return lines[0] + "\n" + "\n".join(lines[1:]).strip("\n") + "\n\n" + block
    return "#!/bin/sh\n" + existing + "\n\n" + block


def _desired_removed_hook(path: Path) -> str | None:
    cleaned = strip_block(read(path))
    return None if cleaned.strip() in ("", "#!/bin/sh") else cleaned + "\n"


def _file_operation(path: Path, content: str | None, *, executable: bool = False) -> PlannedFile | None:
    if content is None:
        return PlannedFile("delete", path, None) if path.is_file() else None
    if not path.exists():
        return PlannedFile("create", path, content, executable)
    current = read(path)
    mode_wrong = executable and not bool(path.stat().st_mode & 0o111)
    return PlannedFile("update", path, content, executable) if current != content or mode_wrong else None


def _planned_declaration(root: Path, decl: dict) -> tuple[PlannedFile | None, dict | None]:
    """Preview --public through the owning parser in an isolated replica, without touching ROOT."""
    if decl["state"] == "active":
        return None, None
    if decl["state"] == "unknown" or decl["state"] == "invalid" or decl.get("detail"):
        return None, {"code": "public-declaration-unresolved", "message": decl.get("detail", "")}
    try:
        checker = _check_github()
    except Exception as exc:  # noqa: BLE001
        return None, {"code": "public-declaration-owner-missing",
                      "message": f"check_github.py could not be imported ({type(exc).__name__})"}
    target = next((rel for rel in checker.MARKER_FILES
                   if (root / rel).is_file() and checker.resolves_inside(root / rel, root)), None)
    if target is None:
        return None, {"code": "public-declaration-route-missing",
                      "message": "no routed marker file exists"}
    path = root / target
    before = path.read_text(encoding="utf-8")
    payload = json.dumps({"reason": DECLARATION_REASON, "date": time.strftime("%Y-%m-%d")},
                         ensure_ascii=False, separators=(",", ":"))
    desired = before.rstrip("\n") + "\n\n" + DECLARATION_TEMPLATE.format(payload=payload) + "\n"
    with tempfile.TemporaryDirectory(prefix="hooks-public-preview-") as tmp:
        replica = Path(tmp)
        for rel in checker.MARKER_FILES:
            source = root / rel
            if source.is_file() and checker.resolves_inside(source, root):
                destination = replica / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(desired if rel == target else source.read_text(encoding="utf-8"),
                                       encoding="utf-8")
        parsed = checker.public_exception(replica)
    if parsed.get("state") != "active" or parsed.get("where") != target:
        return None, {"code": "public-declaration-unpreviewable",
                      "message": "the proposed marker is not honoured by the shared parser"}
    return _file_operation(path, desired), None


HOOK_NAMES = ("pre-commit", "commit-msg", "pre-push", "post-commit")
# The graphify blocks go into both of these; neither may lead outside the project.
GRAPHIFY_HOOK_NAMES = ("post-commit", "post-checkout")


def _unsafe_hooks(root: Path, roots: tuple[FileAuthority, ...]) -> list[str]:
    """Every hook destination that escapes the project; checked before any write on every path."""
    names = dict.fromkeys(HOOK_NAMES + GRAPHIFY_HOOK_NAMES)
    return [f"unsafe hook destination {path}: {error}"
            for path in (hook_path(root, name) for name in names)
            if (error := _destination_error(path, roots)) is not None]


def _scoped_plan(root: Path, *, uninstall: bool, standard: bool, public_flag: bool,
                 no_graph: bool, roots: tuple[FileAuthority, ...] | None = None
                 ) -> tuple[list[PlannedFile], list[dict]]:
    """The project plan: (files to write, findings). Any finding blocks the apply."""
    roots = roots or _scope_file_roots(root)
    files: list[PlannedFile] = []
    findings: list[dict] = []
    if not (root / ".git").is_dir():
        findings.append({"code": "not-git-repository", "message": f"not a git repository: {root}"})
        return files, findings
    if unsafe := _unsafe_hooks(root, roots):
        findings.extend({"code": "unsafe-file-destination", "message": m} for m in unsafe)
        return files, findings
    decl = public_declaration(root)
    planned_declaration = None
    if public_flag:
        planned_declaration, declaration_finding = _planned_declaration(root, decl)
        if declaration_finding:
            findings.append(declaration_finding)
        if planned_declaration:
            files.append(planned_declaration)
    unresolved = decl["state"] in ("invalid", "unknown") or (
        decl["state"] == "none" and bool(decl["detail"]))
    if unresolved:
        findings.append({"code": "public-declaration-unresolved", "message": decl["detail"]})
    elif uninstall:
        for name in HOOK_NAMES:
            path = hook_path(root, name)
            op = _file_operation(path, _desired_removed_hook(path), executable=True)
            if op:
                files.append(op)
    else:
        public = decl["state"] == "active" or planned_declaration is not None
        blocks = {
            "pre-commit": render_pre_commit(standard=standard, public=public),
            "pre-push": PRE_PUSH.format(begin=BEGIN, end=END),
        }
        if public:
            blocks["commit-msg"] = COMMIT_MSG.format(begin=BEGIN, end=END)
        for name, block in blocks.items():
            missing = missing_dependencies(block)
            if missing:
                findings.append({"code": "hook-dependency-missing",
                                 "message": f"{name}: " + ", ".join(str(p) for p in missing)})
                continue
            path = hook_path(root, name)
            op = _file_operation(path, _desired_hook(path, block), executable=True)
            if op:
                files.append(op)
        if not public:
            msg = hook_path(root, "commit-msg")
            op = _file_operation(msg, _desired_removed_hook(msg), executable=True)
            if op:
                files.append(op)
    if not no_graph and graphify_root(root) is not None and graphify_available():
        findings.append({"code": "graph-operation-unpreviewable",
                         "message": "graphify hook install has no write-equivalent preview"})
    safe: list[PlannedFile] = []
    for operation in files:
        if error := _destination_error(operation.path, roots):
            findings.append({"code": "unsafe-file-destination",
                             "message": f"unsafe destination {operation.path}: {error}"})
        else:
            safe.append(operation)
    return safe, findings


def _apply_files(operations: list[PlannedFile], roots: tuple[FileAuthority, ...]) -> None:
    for operation in operations:
        _commit_file(operation, roots)


def _explicit_scope(root: Path, args) -> int:
    roots = _scope_file_roots(root)
    files, findings = _scoped_plan(
        root, uninstall=args.uninstall, standard=args.standard,
        public_flag=args.public, no_graph=args.no_graph, roots=roots)
    operations = [item.public() for item in files]
    if args.preview:
        if args.json:
            print(json.dumps({"schema_version": 1, "scope": args.scope,
                              "operations": operations, "findings": findings}, sort_keys=True))
        else:
            for operation in operations:
                print(f"{operation['action']}: {operation['path']}")
            for finding in findings:
                print(f"FINDING {finding['code']}: {finding['message']}")
        return 2 if findings else 0
    if findings:
        for finding in findings:
            print(f"FINDING {finding['code']}: {finding['message']}")
        return 2
    if args.check:
        return 1 if operations else 0
    _apply_files(files, roots)
    for operation in operations:
        print(f"  {operation['action']}: {operation['path']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--check", action="store_true", help="report status only")
    ap.add_argument("--uninstall", action="store_true", help="remove our block from the hooks")
    ap.add_argument("--standard", action="store_true",
                    help="pre-commit also enforces the structure standard")
    ap.add_argument("--public", action="store_true",
                    help="DECLARE this repository deliberately public, once, by recording a "
                         "public-exception marker in its routed contract. The private-identifier "
                         "guard then follows from that declaration on every later run, with or "
                         "without this flag; dropping the flag does NOT remove it. DELIBERATELY "
                         "PUBLIC repositories only — see the module docstring")
    ap.add_argument("--no-graph", action="store_true", help="skip the Graphify post-commit hook")
    ap.add_argument("--scope", choices=("project",),
                    help="plan and apply through one inspectable, symlink-safe plan")
    ap.add_argument("--preview", action="store_true",
                    help="show the complete scoped operation plan and write nothing")
    ap.add_argument("--json", action="store_true", help="emit preview as one JSON object")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if args.json and not args.preview:
        ap.error("--json requires --preview")
    if args.preview and not args.scope:
        ap.error("--preview requires explicit --scope")
    if args.check and args.uninstall:
        ap.error("--check and --uninstall are mutually exclusive")
    if args.scope:
        return _explicit_scope(root, args)
    print(f"hooks: {root}")

    if not (root / ".git").is_dir():
        print("  not a git repository — git hooks cannot be installed here.")
        print("  the agent-side hooks (query advisor, session lessons) still apply: they are")
        print("  configured once in ~/.claude/settings.json and run in every project.")
        return 0

    pre = hook_path(root, "pre-commit")
    decl = public_declaration(root)

    # Before any write, including --public and graphify: a refused destination writes nothing.
    if not args.check and (unsafe := _unsafe_hooks(root, _scope_file_roots(root))):
        for message in unsafe:
            print(f"  REFUSED: {message}")
        print("  Nothing was written. Make .git/hooks a real directory inside this repository.")
        return 1

    if args.check:
        state = "present" if BEGIN in read(pre) else "ABSENT"
        push = "present" if BEGIN in read(hook_path(root, "pre-push")) else "ABSENT"
        post = read(hook_path(root, "post-commit"))
        graph = "present" if "graphify" in post else "ABSENT"
        route = "yes" if (root / "docs" / "agents" / "README.md").is_file() else "no route yet"
        ident = "present" if "identifier_guard.py" in read(pre) else "ABSENT"
        msg = "present" if BEGIN in read(hook_path(root, "commit-msg")) else "ABSENT"
        print(f"  pre-commit route check: {state}")
        print(f"  repository declares itself PUBLIC: {declaration_line(decl)}")
        print(f"  pre-commit private-identifier guard: {ident} (public repos only)")
        print(f"  commit-msg private-identifier guard: {msg} (public repos only)")
        print(f"  pre-push secret/size/main guard: {push}")
        print(f"  post-commit graph refresh: {graph}")
        print(f"  repo has a disclosure route: {route}")
        # BEHAVIOUR 4: a declaring repository without the guard is a finding, not a shrug.
        if decl["state"] == "active" and (ident == "ABSENT" or msg == "ABSENT"):
            print()
            print("  FINDING: this repository DECLARES itself public and the private-identifier")
            print("  guard is not in place, so nothing stops a home path, the local git identity")
            print("  or a private project name from reaching world-readable history.")
            print("  Fix: re-run `install_hooks.py .` — the declaration is enough, no flag needed.")
            return 1
        if decl["state"] == "unknown" or (decl["state"] == "invalid") or (
                decl["state"] == "none" and decl["detail"]):
            print()
            print("  NOT RESOLVED: this repository's public-exception declaration could not be")
            print(f"  turned into an answer ({decl['detail']}), so the two guard lines above are a")
            print("  report of what is on disk and NOT a verdict on whether it is what this")
            print("  repository needs. Fix the marker, or delete it if this repository is private.")
            return 1
        return 0

    if args.uninstall:
        if decl["state"] == "active":
            print(f"  NOTE: this repository declares itself PUBLIC ({decl['where']}, dated "
                  f"{decl['date']}). --uninstall is an explicit request, so the identifier guard")
            print("  goes with the rest — but the declaration stays, and the next `install_hooks.py .`")
            print("  will bring the guard back. Remove the marker if that is not what you want.")
        for name in HOOK_NAMES:
            p = hook_path(root, name)
            if not p.is_file():
                continue
            print(f"  {name} {remove_hook_block(p)}")
        return 0 if remove_graph_blocks(root) else 1

    refused: list[str] = []
    undetermined = False
    # Set only by the `unresolved` branch; otherwise the two halves move together.
    preserve_commit_msg = False

    # WHAT DECIDES THE IDENTIFIER GUARD: the repository's declaration (`decl`), never `args.public`.
    # Both halves are read independently; see `guard_state`.
    guard_pre, guard_msg = guard_state(root)

    # The ONE read of the flag that decides anything, and what it decides is whether to WRITE.
    if args.public:
        wrote, why = write_declaration(root, decl)
        print(f"  public declaration: {why}")
        if wrote:
            # Re-read through the parser, so this run rests on the evidence every later run will read.
            decl = public_declaration(root)

    # Only ONE parser verdict may remove the guard: `none` with an empty detail. A marker the
    # parser saw and declined to honour (two markers, a fenced or indented marker, a bad date, a
    # control character, an unclosed fence above it, a symlinked marker file) is NOT a statement
    # that the repository is private, and collapsing those into "not active" once disarmed a public
    # repository at exit 0 while printing the parser's own diagnostic.
    declared = decl["state"] == "active"
    unresolved = not declared and (decl["state"] in ("invalid", "unknown") or bool(decl["detail"]))

    if declared:
        # BEHAVIOURS 1 and 3: the flag is not consulted.
        public = True
        print(f"  private-identifier guard REQUIRED by this repository's own declaration "
              f"({decl['where']}, dated {decl['date']}).")
        print("    It follows from the declaration, not from --public, so no re-run can drop it.")
        print("    To stop treating this repository as public, delete that marker — a visible edit")
        print("    to a tracked file — and re-run.")
    elif unresolved:
        # FAIL CLOSED: this run does not know whether the repository is public, so it has no
        # standing to change either half. `public` drives only the pre-commit render, from that
        # half's own state; `preserve_commit_msg` takes the commit-msg branch out of the run.
        public = guard_pre
        preserve_commit_msg = True
        undetermined = True
        if decl["state"] == "unknown":
            print(f"  public declaration NOT DETERMINED — {decl['detail']}.")
        else:
            print(f"  public declaration NOT HONOURED — {decl['detail']}.")
            print("    A marker the parser refuses is NOT a statement that this repository is")
            print("    private. It is marker text nobody can act on, so this run will not act on it.")
        print(f"    Each half of the identifier guard therefore keeps the state it is already in "
              f"(pre-commit: {'present' if guard_pre else 'absent'}, "
              f"commit-msg: {'present' if guard_msg else 'absent'}).")
        print("    That is an intention until it is verified on disk at the end of this run; it is")
        print("    checked there and reported if it did not hold. Fix the marker, or delete it")
        print("    outright if this repository is genuinely private, then re-run.")
    else:
        # The only verdict that may disarm: no honoured marker in any candidate file the parser
        # COULD READ. An unreadable marker file also reaches here — the open escalation in the
        # module docstring, not closed by anything in this file.
        public = False
        if args.public:
            # The write was refused and said why. A guard with no declaration behind it would be
            # removed by the next ordinary run, so render nothing and say so.
            print("    Nothing is declared, so the identifier guard is NOT rendered into the hooks:")
            print("    a guard with no declaration behind it is removed again by the next ordinary")
            print("    run, which is the failure this flag was changed to prevent. Record the")
            print("    declaration by hand, then re-run.")
            refused.append("private-identifier guard (no declaration)")
        if guard_pre or guard_msg:
            print("  removing the private-identifier guard: no honoured `public-exception` marker")
            print("  was found in any candidate file the parser could read, so this repository does")
            print("  not declare itself public and the guard is only for repositories that do.")

    pre_commit_block = render_pre_commit(standard=args.standard, public=public)
    if not install_hook(root, "pre-commit", pre_commit_block,
                        suffix=" (enforcing the standard)" if args.standard else ""):
        refused.append("pre-commit")

    # Both halves move together, except when this run has no standing to move either.
    msg_hook = hook_path(root, "commit-msg")
    if preserve_commit_msg:
        print(f"  commit-msg identifier guard left untouched "
              f"({'present' if guard_msg else 'absent'}) — this run could not resolve the")
        print("    declaration, so it changes neither half of the guard.")
    elif public:
        if install_hook(root, "commit-msg", COMMIT_MSG.format(begin=BEGIN, end=END),
                        suffix=" (commit message)"):
            print("    THIS IS FOR DELIBERATELY PUBLIC REPOSITORIES. In a private repository every")
            print("    finding is a false positive, and that is how --no-verify becomes a habit.")
        else:
            refused.append("commit-msg")
    else:
        removed = remove_hook_block(msg_hook)
        if removed != "absent":
            print(f"  commit-msg identifier guard {removed} — no honoured `public-exception` "
                  f"marker was found in any candidate file the parser could read")

    if not install_hook(root, "pre-push", PRE_PUSH.format(begin=BEGIN, end=END)):
        refused.append("pre-push")

    install_graph_hook(root, no_graph=args.no_graph)

    # Verified on disk rather than inferred from the branches above. Under `unresolved` the
    # read-back checks that each half is exactly where it started.
    if undetermined:
        now_pre, now_msg = guard_state(root)
        if (now_pre, now_msg) != (guard_pre, guard_msg):
            print()
            print("  FINDING: this run could not resolve the declaration and therefore promised to")
            print("  change neither half of the identifier guard, but the state on disk MOVED:")
            print(f"    pre-commit  {'present' if guard_pre else 'absent'} -> "
                  f"{'present' if now_pre else 'absent'}")
            print(f"    commit-msg  {'present' if guard_msg else 'absent'} -> "
                  f"{'present' if now_msg else 'absent'}")
            print("  Treat the printed guard state above as unreliable and re-run once the")
            print("  declaration is resolved.")
            if "guard state moved under an unresolved declaration" not in refused:
                refused.append("guard state moved under an unresolved declaration")

    if decl["state"] == "active":
        after_pre = "identifier_guard.py" in read(pre)
        after_msg = "identifier_guard.py" in read(msg_hook)
        if not (after_pre and after_msg):
            print()
            print("  FINDING: this repository DECLARES itself public and the private-identifier")
            print(f"  guard is NOT in place after this run (pre-commit: "
                  f"{'yes' if after_pre else 'NO'}, commit-msg: {'yes' if after_msg else 'NO'}).")
            print("  Nothing stops a home path, the local git identity or a private project name")
            print("  from reaching world-readable history. Do not treat this repo as guarded.")
            if "declaration-vs-guard disagreement" not in refused:
                refused.append("declaration-vs-guard disagreement")

    if refused:
        print()
        print(f"  NOT INSTALLED: {', '.join(refused)} — see the reason above each. This repository")
        print(f"  does NOT have the protection those hooks provide. Reinstall the")
        print(f"  progressive-disclosure skill and re-run before treating this repo as guarded.")
        return 1
    if undetermined:
        # No hook was refused, but the question the identifier guard answers was never answered.
        print()
        print("  NOT RESOLVED: this repository's public-exception declaration could not be turned")
        print("  into an answer, so whether it needs the private-identifier guard is unknown.")
        print("  Both halves of the guard were left in the state they were already in, and that")
        print("  was verified against the disk above rather than assumed. Resolve the declaration")
        print("  and re-run before treating this repository as either guarded or private.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
