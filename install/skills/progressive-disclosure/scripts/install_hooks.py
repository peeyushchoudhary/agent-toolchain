#!/usr/bin/env python3
"""Install the per-repository git hooks that keep agent context true.

Four hooks, all per-repo because git hooks are not shared through git — every clone and every
project needs this run once:

  pre-commit   validates the disclosure route (broken link, missing command, unscoped dir)
               and, with --public, scans the staged diff for private identifiers
  commit-msg   with --public only: scans the commit MESSAGE for private identifiers
  pre-push     blocks the mistakes a push makes permanent (secrets, huge files, pushes to main)
  post-commit  re-extracts changed code into the Graphify graph, via `graphify hook install`

It also wires one machine-global reporter line: the execution-methodology adoption check, added to
the SessionStart script so every repository states whether it has adopted the shared methodology,
drifted from it, or deliberately deferred it. It reports; it never adopts.

pre-push carries the rules that GitHub itself would charge for: secret scanning on a private repo
needs paid Secret Protection, and protected branches need a paid plan. Enforcing them locally costs
nothing and matches the operating model, where local gates are the only gates.

Both are written as a marked block, so an existing hook is preserved and re-running replaces only
our block rather than duplicating it.

The pre-commit hook is deliberately forgiving about *setup* and strict about *breakage*: it skips
silently when the repo has no `docs/agents/README.md` or no validator installed, so it is safe to
install anywhere, including a project that has not been standardised yet. When the route does
exist, it surfaces warnings and fails the commit on structural errors.

--public IS OPT-IN, AND MUST STAY OPT-IN
-----------------------------------------
The identifier guard is for repositories that are DELIBERATELY PUBLIC. It blocks a commit that
carries an absolute home path, the local git identity, or a name from the private deny-list at
~/.claude/private-identifiers.txt. That deny-list lives outside the PUBLIC repository on purpose: a
list of private project names committed to a public repository publishes exactly what it protects,
and unlike a .gitignore rule — which `git add -f` overrides — a file above that work tree cannot be
committed to it at all.

The claim is relative, and was overstated here as "OUTSIDE every repository". ~/.claude is itself a
git repository (allow-list .gitignore, no remote), so the deny-list is not outside every repository
— it is outside the one that is deliberately published, which is the threat this guard addresses.
See identifier_guard.py's module docstring for the full argument.

It is not installed by default, and that is a decision rather than caution:

  * In a PRIVATE repository the rules block nothing that matters. A private project's own name, its
    author's email and its absolute paths are all fine inside it. Every finding there is a false
    positive, and a guard that is wrong every day is a guard whose user learns to type --no-verify —
    which then also disables the route check and the secret scan on the way past.
  * The failure mode of NOT installing it on a public repo is a leak; the failure mode of installing
    it on a private one is that the founder stops trusting all four hooks. The first is loud and
    caught by review; the second is silent and permanent.

So the flag is required, and re-running WITHOUT it removes the guard again — the state of the hook
always matches the last thing that was asked for, with no sticky configuration to forget about.

NO HOOK IS DECLARED INSTALLED WITHOUT VERIFYING WHAT IT INVOKES
---------------------------------------------------------------
Every git hook here is a four-line shell wrapper around a script that lives somewhere else. The
wrapper is trivial to write and always succeeds; the script it runs is the entire value. So the
measured failure was this, with push_guard.py absent and everything else present:

    install_hooks rc=0
      pre-push installed
        blocks: credentials in the pushed range, files over 10 MB (not configurable),
        direct pushes to main.

Exit 0, a 419-byte hook on disk, and three claims — every one false. That is worse than no guard,
because the report is what anyone would check. A machine restored in the wrong order (skills
unpacked after hooks installed, or install.sh's `install_tree` replacing the skill directory
wholesale) reports a guard it does not have.

The defect is NOT that the pre-push branch forgot a check. Two blocks below already handle their
own absence — the identifier guard does it twice, loudly — and the pre-push branch does not, and
nothing in the file made that asymmetry visible. The class is: **a hook can be declared installed
without anything verifying the thing it invokes exists.** So the remedy is not a third hand-written
check. It is that there is now exactly ONE way to write a git hook — `install_hook` — and it:

  1. reads the dependencies OUT OF THE RENDERED BLOCK (`block_dependencies`), so a hook added next
     year is covered without anyone remembering, including scripts its dependencies import;
  2. refuses to write the hook at all when one is missing, leaving any existing hook untouched,
     naming the absent path, and failing the run;
  3. prints the success line and the "blocks:" claims itself, AFTER the write is verified on disk.

Point 3 is the half that is easy to skip. The three claims were false precisely because they were
`print()` literals sitting beside the install rather than derived from it — so they are now derived:
the file-size limit and the branch names are read out of push_guard.py's own module constants, and
anything that cannot be substantiated is simply not claimed. `test_install_hooks_deps.py` enumerates
the hook templates from this source and asserts each one's dependency reaches the chokepoint.

A hook that only REPORTS is treated differently from a hook that BLOCKS, and that distinction is
argued at PRE_COMMIT_IDENTIFIER below: not validating the route is not a claim about the route, but a
guard that did not run reads as a clean result. The SessionStart adoption reporter therefore still
installs when its script is missing — it just says, in its own status line, that it will not report.

Usage:
  install_hooks.py [ROOT]              # install / update
  install_hooks.py [ROOT] --check      # report status, change nothing
  install_hooks.py [ROOT] --uninstall  # remove only our block
  install_hooks.py [ROOT] --standard   # pre-commit also enforces the structure standard
  install_hooks.py [ROOT] --public     # add the private-identifier guard (public repos ONLY)
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import subprocess
import sys
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

# Rendered into the SAME marked block as the route check rather than a block of its own, so that
# `write_hook` — which replaces our one block wholesale — takes the stanza away again the moment
# --public is dropped. A second marked block would need its own strip/rewrite path and would settle
# its ordering against the first differently on every run.
#
# Two hooks, not one, and it is not a choice: git runs `pre-commit` BEFORE the commit message
# exists, so that hook cannot see it, while `commit-msg` receives the message file as $1. One
# SCRIPT with two modes serves both — the rule set, the deny-list loader and the exit contract have
# to be identical in each, and two scripts would drift the first time a rule was added to one.
#
# THE MISSING-GUARD BRANCH IS NOT A SKIP. Every other block here skips silently when its script is
# absent, and that is right for a reporter: not validating the route is not a claim about the route.
# It is wrong for this one. identifier_guard.py's governing invariant is "a scan that did not run
# must never read as clean", and `if [ -f ] … fi` broke it from outside the script — a guard that
# was renamed, or deleted by install.sh's install_tree replacing the skill directory wholesale,
# produced exit 0 and no output, which is indistinguishable from a clean commit. So absence exits 2
# and says so. The propagated exit code is the guard's own, which is what makes the 1-vs-2
# distinction described below true rather than merely asserted: `|| exit 1` collapsed both to 1.
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
  echo "  This hook was installed with --public, so this repository is treated as PUBLIC and the" >&2
  echo "  staged content has NOT been scanned. A scan that did not run is not a clean result." >&2
  echo "  Reinstall the progressive-disclosure skill, or re-run install_hooks.py WITHOUT --public" >&2
  echo "  to remove this hook deliberately. Do not commit past it." >&2
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
  echo "  result. Reinstall the progressive-disclosure skill, or re-run install_hooks.py WITHOUT" >&2
  echo "  --public to remove this hook deliberately. Do not commit past it." >&2
  exit 2
fi
{end}
"""

# THE RUNTIME `[ -f ]` HERE IS DELIBERATELY LEFT AS A SKIP, AND IT IS THE ONE REMAINING HOLE.
#
# `install_hook` now refuses to write this hook at all unless push_guard.py is present, which closes
# the case that was measured (restore in the wrong order, then read a report claiming a guard that
# is not there). What it does not close is the guard being deleted AFTER a good install — which is a
# real path, not a hypothetical: install.sh's `install_tree` replaces the skill directory wholesale.
# In that window this block skips silently and the push goes through unscanned.
#
# Making it exit non-zero instead is the same one-line change the identifier guard already carries
# twice, for the same reason. It is not made here because it changes what every already-installed
# repository does on its next push the moment that repository is re-installed, and a fleet-wide
# change to push behaviour is not an implementer's call. Flagged for the founder, not forgotten.
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

# The SessionStart hook is not a git hook. It is the machine-global reporter at
# ~/.claude/hooks/disclosure-check.sh, wired once in ~/.claude/settings.json, which already runs
# validate_disclosure.py, check_github.py and check_toolchain.py against whatever directory a
# session opens in. The execution-methodology adoption check belongs beside them: adoption is
# staggered, so a repository that has not adopted the methodology has to say so every session until
# it does, and only a session-level reporter can say it.
#
# Installing it from here — rather than shipping it inside that script — is what keeps the two
# skills decoupled and what makes adopting the progressive-disclosure standard the thing that turns
# the warning on. install_hooks.py invokes both scripts; neither imports the other.
SESSION_BEGIN = "# >>> execution-methodology adoption >>>"
SESSION_END = "# <<< execution-methodology adoption <<<"

# The insertion point: everything above it builds $notes, and this line is where the reporter stops
# collecting and emits. Anchoring on it (rather than appending) is required — an appended block
# would sit after the emit and never run.
SESSION_ANCHOR = '[ -n "$notes" ] || exit 0'

SESSION_BLOCK = """{begin}
# Reports whether this repository has adopted the shared execution methodology, has drifted from
# it, or deliberately deferred it. Reports only: it never renders, never adopts, and never fails a
# session. --adoption-check exits 0 by contract, and `|| true` covers anything it does not.
# Skips silently when this repo has no route or the script is not installed.
_em_sync="$HOME/.claude/skills/execution-methodology/scripts/sync_methodology.py"
if [ -f "$root/docs/agents/README.md" ] && [ -f "$_em_sync" ]; then
  _em_out=$(PYTHONDONTWRITEBYTECODE=1 python3 "$_em_sync" --repo "$root" --adoption-check 2>/dev/null || true)
  [ -n "$_em_out" ] && add "$_em_out"
fi
{end}
"""

SESSION_HOOK = Path.home() / ".claude" / "hooks" / "disclosure-check.sh"


def render_pre_commit(*, standard: bool = False, public: bool = False) -> str:
    """The one composition of the pre-commit block. Every caller goes through here.

    PRE_COMMIT is a four-placeholder template whose two interesting slots are not free text: the
    flag is `--standard` or `--readme` and nothing else, and the identifier stanza is present or
    absent according to --public. Exposing the template alone made every caller re-derive both, and
    a caller that re-derives a composition drifts from it silently. That is not hypothetical here:
    adding `{identifier}` broke a test which had hand-formatted the same template, and the test
    failed for the wrong reason — not because the hook was wrong, but because it was a copy. The
    same finding was already made against the push-guard suite in this programme.

    So the argument is the argparse flag, not the rendered string. A caller cannot now omit a
    placeholder, cannot invent a flag combination `main()` never emits (the broken test asked for
    `flags=""`, which no install produces), and the next placeholder added to the template reaches
    every caller by construction.
    """
    return PRE_COMMIT.format(
        begin=BEGIN,
        end=END,
        # --readme by default: the seven-section README contract is part of the standard, and a
        # check nothing runs is a check that does not exist. Nine README errors sat invisible in a
        # repository for weeks because the hooks passed neither --readme nor --standard, while the
        # route summary printed a reassuring "0 error(s)". --standard is the superset and implies it.
        flags=" --standard" if standard else " --readme",
        identifier=PRE_COMMIT_IDENTIFIER if public else "",
    )


def hook_path(root: Path, name: str) -> Path:
    return root / ".git" / "hooks" / name


# ---------------------------------------------------------------------------------------------
# Dependency resolution: one place, and it reads the hook rather than being told about the hook.
# ---------------------------------------------------------------------------------------------

# Every block above names the script it runs the same way, because a shell hook has no other way to
# name it: a double-quoted "$HOME/.claude/.../thing.py" literal. Extracting the dependency FROM THE
# RENDERED TEXT is what makes this cover a hook nobody has written yet. A hand-maintained
# {hook: dependency} table would be one more thing to remember, and the defect being fixed here is
# precisely the thing that was not remembered once already.
HOOK_SCRIPT_REF = re.compile(r'"\$HOME/(\.claude/[A-Za-z0-9._/+-]+\.py)"')

# A sibling import inside a dependency is a dependency too. push_guard.py does
# `from validate_disclosure import SECRET_PATTERNS` at module scope: without that file the pre-push
# guard exits 2 on every push, so "push_guard.py is present" is not on its own enough to justify
# claiming the pushed range gets scanned. Only names that resolve to a .py beside the dependency
# count; stdlib and third-party imports are not ours to verify.
SIBLING_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]+import|import[ \t]+([A-Za-z_][A-Za-z0-9_]*))",
    re.M,
)


def block_dependencies(block: str) -> list[Path]:
    """Every script this rendered hook block invokes, in first-appearance order, de-duplicated.

    Resolved against `Path.home()` because that is what `$HOME` expands to for the same user who is
    running the installer, and the installed hook is only ever run by that user. A hook installed
    for one user and run as another is outside what a per-repository `.git/hooks` file can express
    at all, and pretending otherwise here would be a check that looks stricter than it is.
    """
    return [Path.home() / rel for rel in dict.fromkeys(HOOK_SCRIPT_REF.findall(block))]


def script_dependencies(script: Path) -> list[Path]:
    """Sibling scripts this dependency imports, so a broken chain does not read as "present".

    The interesting case is the sibling that is NOT on disk — that is the whole point — so this
    cannot filter to files that exist. An imported bare name is treated as a sibling when it is
    neither in the standard library nor importable from anywhere else on this interpreter's path;
    `find_spec` on a single-segment name resolves without executing anything. Dotted imports
    (`from a.b import c`) are not matched at all, deliberately: nothing in this toolchain ships one,
    and guessing at package layout here would invent failures rather than find them.
    """
    try:
        source = script.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        # Unreadable is reported by the caller as missing; do not also guess at its imports.
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
        if name in sys.stdlib_module_names:
            continue
        try:
            if importlib.util.find_spec(name) is not None:
                continue
        except (ImportError, ValueError, AttributeError):
            pass
        found.append(sibling)
    return found


def missing_dependencies(block: str) -> list[Path]:
    """The scripts this block needs that are not on disk. Empty means the hook can honestly install.

    Transitive one level past each direct dependency, which is where the chain actually is. Deeper
    than that would need real import resolution, and every dependency in this toolchain that has a
    dependency of its own also fails closed and says so — the hole being closed here is the one
    where NOTHING says anything.
    """
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
    """Read a module-level constant out of a script WITHOUT importing it, or None.

    Parsed, not executed: this runs during an install, against a file whose whole reason for being
    inspected is that we are not yet sure it is intact. `literal_eval` succeeding is itself the
    evidence that the value is a source literal rather than something read from the environment,
    which is how the "not configurable" claim below is substantiated instead of asserted.
    """
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
    """What the pre-push guard on this disk actually enforces, read out of the guard.

    Nothing here is a sentence about push_guard.py written from memory. `MAX_FILE_MB` and
    `DEFAULT_BRANCHES` are its own module constants, so the printed number and the printed branch
    names cannot drift from the ones that will run; the escape hatch is named only if the guard
    still honours it; and anything that cannot be read out of the source is simply NOT CLAIMED.
    Under-claiming is free. Over-claiming is the defect this file exists to stop repeating.
    """
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
        # A literal that `literal_eval` accepted is a literal in the source: there is no environment
        # variable to raise it. That is what earns the parenthetical, which used to be a bare
        # assertion typed next to the print.
        claims.append(f"files over {mb:g} MB (not configurable)")

    branches = _module_constant(guard, "DEFAULT_BRANCHES")
    if isinstance(branches, (list, tuple)) and branches:
        names = " or ".join(str(b).rsplit("/", 1)[-1] for b in branches)
        hatch = " unless PD_ALLOW_MAIN_PUSH=1" if "PD_ALLOW_MAIN_PUSH" in source else ""
        claims.append(f"direct pushes to {names}{hatch}")
    return claims


def _pre_commit_claims(block: str) -> list[str]:
    """Read out of the rendered block, because the block is what will run.

    The two things that vary — which validator flag was passed, and whether the identifier stanza
    is present — are both visible in the text, so neither can be claimed by a caller that thinks it
    passed `--standard` when it did not.
    """
    claims = []
    if "--standard" in block:
        claims.append("route errors and the structure standard (--standard)")
    elif "--readme" in block:
        claims.append("route errors and the seven-section README contract (--readme)")
    if any(d.name == "identifier_guard.py" for d in block_dependencies(block)):
        claims.append("private identifiers in the STAGED CONTENT (--public)")
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
        # Previously stated unconditionally. With no deny-list on disk the guard still blocks home
        # paths and the git identity, but it blocks no project name at all, and saying otherwise is
        # the same overstatement in a smaller font.
        claims.append("no deny-list at ~/.claude/private-identifiers.txt yet, so NO project name "
                      "is blocked — create it to enable that half")
    return claims


def _no_claims(_block: str) -> list[str]:
    return []


# Keyed by git hook name. A hook with no entry claims nothing, which is the right default: silence
# is not a false report.
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


def wire_session_start(remove: bool = False) -> str:
    """Add (or remove) the execution-methodology adoption check in the SessionStart reporter.

    Defensive in exactly the way the git-hook blocks are: every failure mode ends in a printed
    status and a normal return, never an exception and never a broken hook. The block is marked, so
    re-running replaces it instead of duplicating, and uninstalling takes back only our lines.

    This is the one machine-global edit here, matching sync_codex above, which also writes outside
    the repository being installed into. That is correct: SessionStart is configured once per
    machine, not once per repository, and the adoption question is asked of whichever repository the
    session opens in.
    """
    if not SESSION_HOOK.is_file():
        return "skipped — no SessionStart reporter at ~/.claude/hooks/disclosure-check.sh"
    try:
        text = SESSION_HOOK.read_text(encoding="utf-8", errors="replace")
        # Not strip_block(): that one normalises leading and trailing blank lines, which is fine for
        # a git hook we own outright and wrong for a script we are only a guest in. Removing our
        # block must leave the file byte-identical to what it was before we added it.
        if SESSION_BEGIN in text and SESSION_END in text:
            head, _, rest = text.partition(SESSION_BEGIN)
            _, _, tail = rest.partition(SESSION_END)
            stripped = head + tail.lstrip("\n")
        else:
            stripped = text
        if remove:
            if stripped == text:
                return "absent"
            SESSION_HOOK.write_text(stripped, encoding="utf-8")
            SESSION_HOOK.chmod(0o755)
            return "removed"

        if SESSION_ANCHOR not in stripped:
            return ("skipped — the reporter has been restructured and no longer contains its emit "
                    f"anchor ({SESSION_ANCHOR}); add the block by hand")
        # A REPORTER, NOT A GUARD — and that is the whole reason a missing script is not fatal here
        # the way it is in `install_hook`. The argument is the one made above PRE_COMMIT_IDENTIFIER:
        # a guard that did not run reads as a clean result, while a reporter that did not run makes
        # no claim at all. What it may NOT do is report itself as installed and working when it will
        # never emit a line, so the status says which of the two it is.
        block = SESSION_BLOCK.format(begin=SESSION_BEGIN, end=SESSION_END)
        inert = "" if not missing_dependencies(block) else (
            " (INERT — " + ", ".join(p.name for p in missing_dependencies(block))
            + " is not on this machine, so no adoption line will ever be reported)")
        updated = stripped.replace(SESSION_ANCHOR, block + "\n" + SESSION_ANCHOR, 1)
        if updated == text:
            return "already current" + inert
        SESSION_HOOK.write_text(updated, encoding="utf-8")
        SESSION_HOOK.chmod(0o755)
        return ("installed" if SESSION_BEGIN not in text else "updated") + inert
    except OSError as e:
        return f"skipped — {e}"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return action


def install_hook(root: Path, name: str, block: str, *, suffix: str = "") -> bool:
    """THE ONLY WAY A GIT HOOK IS WRITTEN, AND THE ONLY PLACE ITS INSTALLATION IS CLAIMED.

    `write_hook` still does the file surgery; what this adds is that the surgery cannot be reached
    without the dependency check, and the success line cannot be reached without the surgery. Those
    two facts are what make the report trustworthy, and they are asserted structurally by
    `test_install_hooks_deps.py` rather than left to the next person's discipline — the same shape
    as `read_doc` in validate_disclosure.py, where the rule is enforced by the absence of a bypass.

    A MISSING DEPENDENCY IS FATAL FOR THIS HOOK AND NOTHING ELSE. The run continues, so one absent
    script does not cost a repository the three hooks that are fine, but the process exits non-zero
    and the summary names what did not install. Exit 0 was half of the measured defect: a caller
    that checks the code got told everything was fine.

    IT DOES NOT WRITE, SO AN EXISTING HOOK IS LEFT EXACTLY AS IT WAS. Overwriting a working hook
    with a wrapper around a script that is not there would turn a repair into a regression, and the
    hook already on disk is the better of the two states.

    Returns True when the hook is installed and its claims are honest.
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
    action = write_hook(path, block)

    # Read back rather than trust the write. This is a claim about the state of a file, printed to
    # someone who will not check, and `write_hook` reports the action it intended, not the result.
    if BEGIN not in read(path):
        print(f"  {name} FAILED — the block is not present in {path} after writing it.")
        return False

    print(f"  {name} {action}{suffix}")
    for i, claim in enumerate(CLAIM_SOURCES.get(name, _no_claims)(block)):
        print(f"    blocks: {claim}" if i == 0 else f"            {claim}")
    return True


def remove_hook_block(path: Path) -> str:
    """Take our block out of a hook, deleting the file only if nothing else was in it.

    The same contract as the --uninstall loop, factored out because --public toggling OFF has to do
    exactly this and doing it inline would have been a second, subtly different implementation of
    "leave the user's own hook alone".
    """
    if not path.is_file():
        return "absent"
    cleaned = strip_block(read(path))
    if cleaned.strip() in ("", "#!/bin/sh"):
        path.unlink()
        return "removed"
    path.write_text(cleaned + "\n", encoding="utf-8")
    path.chmod(0o755)
    return "removed (kept the rest)"


def sync_codex(root: Path) -> str | None:
    """Mirror the skills wherever Codex will look, so both agents run the same version.

    Prefers Codex's global skills directory — one copy that every project sees — and also refreshes
    a repo-local `.codex/skills` if the project already keeps one. Hand-copying drifts the first
    time anyone forgets, and the failure is silent: Codex quietly follows an older standard.
    """
    import shutil
    # The set of mirrored skills is defined once, by the checker that reports drift in it. A second
    # hardcoded copy here is how `execution-methodology` came to be checked but never copied: the
    # checker's own suggested fix could not satisfy the checker. Import rather than restate; the two
    # scripts ship in the same directory, so an ImportError means a broken install, not a fallback.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_toolchain import MIRRORED_SKILLS

    targets = [d for d in (Path.home() / ".codex" / "skills", root / ".codex" / "skills")
               if d.is_dir()]
    if not targets:
        return None
    copied: set[str] = set()
    for dest_root in targets:
        for name in MIRRORED_SKILLS:
            src = Path.home() / ".claude" / "skills" / name
            if not src.is_dir():
                continue
            dest = dest_root / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
            copied.add(name)
    where = " + ".join("global" if t == Path.home() / ".codex" / "skills" else "repo" for t in targets)
    return f"{', '.join(sorted(copied))} -> {where}" if copied else None


def graphify_root(root: Path) -> Path | None:
    """Directory whose graphify-out/graph.json is the repository's graph, or None.

    The graph does not always sit at the repository root. A repo that keeps its runnable
    implementation in a subtree builds the graph there, and looking only at the root silently
    skipped the post-commit refresh — so documentation-only commits never rebuilt the graph and the
    always-loaded route kept pointing agents at a graph that was stale or absent. Checks the root
    first, then one level down, which covers the implementation-subtree layout without walking the
    whole tree.
    """
    if (root / "graphify-out" / "graph.json").is_file():
        return root
    for child in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if (child / "graphify-out" / "graph.json").is_file():
            return child
    return None


def graphify_available() -> bool:
    try:
        subprocess.run(["graphify", "--help"], capture_output=True, timeout=20, check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def install_graph_hook(root: Path, *, no_graph: bool) -> bool:
    """The post-commit graph refresh, which `graphify` installs rather than us.

    Separated from `main` so that the structural test can allow exactly this one function to print
    an "installed" line outside `install_hook`, with a reason, rather than allow-listing `main` and
    thereby allowing everything. Its dependency is a BINARY ON PATH, not a script inside a hook
    block, so `block_dependencies` cannot see it — `graphify_available()` is the equivalent check
    and it already ran before any claim, which is why this branch was never part of the defect.
    """
    if no_graph:
        print("  post-commit graph refresh skipped (--no-graph)")
        return False
    if (graph_dir := graphify_root(root)) is None:
        print("  post-commit graph refresh skipped — no graphify-out/graph.json in this repo")
        return False
    if not graphify_available():
        print("  post-commit graph refresh skipped — graphify is not installed")
        return False
    r = subprocess.run(["graphify", "hook", "install"], cwd=graph_dir, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  post-commit graph refresh FAILED: {r.stderr.strip()[:120]}")
        return False
    print("  post-commit graph refresh installed")
    print("    note: it re-extracts changed CODE only. Documentation changes still need a")
    print("    semantic rebuild — `graphify extract . --mode deep --backend <backend>`.")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--check", action="store_true", help="report status only")
    ap.add_argument("--uninstall", action="store_true", help="remove our block from the hooks")
    ap.add_argument("--standard", action="store_true",
                    help="pre-commit also enforces the structure standard")
    ap.add_argument("--public", action="store_true",
                    help="install the private-identifier guard (pre-commit + commit-msg). "
                         "DELIBERATELY PUBLIC repositories only — see the module docstring")
    ap.add_argument("--no-graph", action="store_true", help="skip the Graphify post-commit hook")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    print(f"hooks: {root}")

    if not (root / ".git").is_dir():
        print("  not a git repository — git hooks cannot be installed here.")
        print("  the agent-side hooks (query advisor, session lessons) still apply: they are")
        print("  configured once in ~/.claude/settings.json and run in every project.")
        return 0

    pre = hook_path(root, "pre-commit")

    if args.check:
        state = "present" if BEGIN in read(pre) else "ABSENT"
        push = "present" if BEGIN in read(hook_path(root, "pre-push")) else "ABSENT"
        post = read(hook_path(root, "post-commit"))
        graph = "present" if "graphify" in post else "ABSENT"
        route = "yes" if (root / "docs" / "agents" / "README.md").is_file() else "no route yet"
        ident = "present" if "identifier_guard.py" in read(pre) else "ABSENT"
        msg = "present" if BEGIN in read(hook_path(root, "commit-msg")) else "ABSENT"
        print(f"  pre-commit route check: {state}")
        print(f"  pre-commit private-identifier guard: {ident} (public repos only)")
        print(f"  commit-msg private-identifier guard: {msg} (public repos only)")
        print(f"  pre-push secret/size/main guard: {push}")
        print(f"  post-commit graph refresh: {graph}")
        print(f"  repo has a disclosure route: {route}")
        session = read(SESSION_HOOK)
        print("  session-start methodology adoption check: "
              + ("present" if SESSION_BEGIN in session else
                 "ABSENT" if session else "ABSENT (no SessionStart reporter)"))
        return 0

    if args.uninstall:
        for name in ("pre-commit", "commit-msg", "pre-push", "post-commit"):
            p = hook_path(root, name)
            if not p.is_file():
                continue
            print(f"  {name} {remove_hook_block(p)}")
        if graphify_available():
            subprocess.run(["graphify", "hook", "uninstall"], cwd=root, capture_output=True)
            print("  removed graphify post-commit hook")
        print(f"  session-start methodology adoption check {wire_session_start(remove=True)}")
        return 0

    synced = sync_codex(root)
    if synced:
        print(f"  synced .codex/skills: {synced}")

    # Personas render into both harnesses. Generated agent files are committed, so a clone that
    # never syncs would commit stale ones; the validator's persona-drift check catches that, and
    # this makes the common case correct without a separate step to remember.
    personas = Path.home() / ".claude" / "skills" / "agent-personas" / "scripts" / "sync_personas.py"
    if personas.is_file():
        r = subprocess.run(["python3", str(personas), "--repo", str(root)],
                           capture_output=True, text=True)
        first = (r.stdout.strip().splitlines() or ["no output"])[0]
        print(f"  personas: {first}")

    refused: list[str] = []

    pre_commit_block = render_pre_commit(standard=args.standard, public=args.public)
    if not install_hook(root, "pre-commit", pre_commit_block,
                        suffix=" (enforcing the standard)" if args.standard else ""):
        refused.append("pre-commit")

    # Both halves of the identifier guard move together. Installing one without the other is the
    # only genuinely dangerous state: the message half alone leaves file content unscanned, and the
    # staged half alone leaves the message unscanned — and either one, seen in --check, reads as
    # "the guard is installed".
    msg_hook = hook_path(root, "commit-msg")
    if args.public:
        if install_hook(root, "commit-msg", COMMIT_MSG.format(begin=BEGIN, end=END),
                        suffix=" (commit message)"):
            print("    THIS IS FOR DELIBERATELY PUBLIC REPOSITORIES. In a private repository every")
            print("    finding is a false positive, and that is how --no-verify becomes a habit.")
        else:
            refused.append("commit-msg")
    else:
        removed = remove_hook_block(msg_hook)
        if removed != "absent":
            print(f"  commit-msg identifier guard {removed} (no --public)")

    # Adoption of the execution methodology is staggered and deliberate. This block only ever
    # reports; it is what makes an unadopted repository say so at every session start instead of
    # drifting onto a methodology of its own. Nothing here renders anything into any repository.
    print(f"  session-start methodology adoption check {wire_session_start()}")

    if not install_hook(root, "pre-push", PRE_PUSH.format(begin=BEGIN, end=END)):
        refused.append("pre-push")

    install_graph_hook(root, no_graph=args.no_graph)

    if refused:
        # The summary must not claim what did not install, and the exit code must not say fine.
        print()
        print(f"  NOT INSTALLED: {', '.join(refused)} — see the reason above each. This repository")
        print(f"  does NOT have the protection those hooks provide. Reinstall the")
        print(f"  progressive-disclosure skill and re-run before treating this repo as guarded.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
