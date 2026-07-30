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

`--vendored` adds a fourth concern, and unlike the three above it IS repository-scoped:

  4. A repository that publishes a vendored copy of the installed shared layer — `install/skills`
     mirroring `~/.claude/skills`. That copy is refreshed by hand, so it drifts in both directions:
     a skill edited or added in `~/.claude` and never re-vendored publishes stale instructions, and
     a skill deleted or renamed in `~/.claude` but left in the repository publishes a dead one
     forever. Neither side of that drift is visible from either side alone. It is a fourth concern
     rather than a fifth mode of the first three because the comparison is between a machine and a
     *specific* repository, named on the command line, and never runs implicitly.

Exit codes: 0 clean, 1 finding, 2 usage or environment error. Which severities gate the exit
differs by mode — see EXIT SEMANTICS in `main()`.

Usage:
  check_toolchain.py           # human report
  check_toolchain.py --hook    # compact agent context, silent when healthy
  check_toolchain.py --json
  check_toolchain.py --vendored <repo>   # diff ~/.claude/skills against <repo>/install/skills
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
CODEX_MD = HOME / ".codex" / "AGENTS.md"
CODEX_SKILLS = HOME / ".codex" / "skills"
CLAUDE_SKILLS = HOME / ".claude" / "skills"
SYNC = CLAUDE_SKILLS / "agent-personas" / "scripts" / "sync_personas.py"

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


def section(text: str, start: str, end: str) -> str | None:
    try:
        return text[text.index(start):text.index(end)]
    except ValueError:
        return None


def check_personas() -> list[tuple[str, str]]:
    if not SYNC.is_file():
        return [("warn", f"persona sync tool missing at {SYNC}")]
    try:
        r = subprocess.run(["python3", str(SYNC), "--check"],
                           capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return [("warn", f"could not run the persona sync check: {e}")]
    if r.returncode == 1:
        n = sum(1 for line in r.stdout.splitlines() if line.strip().startswith("/"))
        return [("critical", f"{n} generated agent file(s) do not match the persona pool. Both "
                             f"harnesses are running a stale persona. Fix: python3 {SYNC}")]
    if r.returncode not in (0, 1):
        return [("warn", f"persona sync check failed: {r.stderr.strip()[:120]}")]
    return []


def check_instructions() -> list[tuple[str, str]]:
    if not CLAUDE_MD.is_file() or not CODEX_MD.is_file():
        return [("warn", "one of ~/.claude/CLAUDE.md or ~/.codex/AGENTS.md is missing")]
    a, b = CLAUDE_MD.read_text(), CODEX_MD.read_text()
    out = []
    for start, end in MIRRORED:
        sa, sb = section(a, start, end), section(b, start, end)
        if sa is None or sb is None:
            out.append(("warn", f"section `{start}` is missing from "
                                f"{'~/.claude/CLAUDE.md' if sa is None else '~/.codex/AGENTS.md'}"))
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
        return [("warn", "~/.codex/skills does not exist; Codex has none of the shared skills")]
    out = []
    for name in MIRRORED_SKILLS:
        src, dst = CLAUDE_SKILLS / name, CODEX_SKILLS / name
        if not src.is_dir():
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
            detail = ", ".join(links[:3]) + (f", +{len(links) - 3} more" if len(links) > 3 else "")
            out.append(("warn", f"skill `{name}` contains a symlink that was not compared "
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


def check_vendored(vendored_skills: Path) -> list[tuple[str, str]]:
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
    """
    out: list[tuple[str, str]] = []

    # Symlinked top-level entries are excluded from the directory sets and reported by the
    # top-level `tree()` sweep below: a symlinked skill directory is walked as empty (see tree()),
    # so treating it as a real skill would compare two empty trees and call the region clean.
    installed = {p.name for p in CLAUDE_SKILLS.iterdir()
                 if p.is_dir() and not p.is_symlink()}
    vendored = {p.name for p in vendored_skills.iterdir()
                if p.is_dir() and not p.is_symlink()}

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
    out += _compare(CLAUDE_SKILLS, vendored_skills, "*",
                    lambda rel: f"top-level entry `{rel}`")

    for name in sorted(installed & vendored):
        out += _compare(CLAUDE_SKILLS / name, vendored_skills / name, "**/*",
                        lambda rel, _n=name: _describe_vendored(_n, rel))
    return out


def _compare(installed_root: Path, vendored_root: Path, pattern: str,
             describe) -> list[tuple[str, str]]:
    """One `tree()` per side, rendered as the three drift categories plus unreadable entries."""
    a, a_bad = tree(installed_root, pattern)
    b, b_bad = tree(vendored_root, pattern)
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
    return out


def collect() -> list[tuple[str, str]]:
    return check_personas() + check_instructions() + check_skills()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hook", action="store_true", help="compact context; silent when healthy")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--vendored", metavar="REPO",
                    help="compare ~/.claude/skills against REPO/install/skills; report drift only")
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
    vendored_mode = args.vendored is not None

    if vendored_mode:
        # Truthiness would be wrong: `--vendored ""` is falsy, and under `if args.vendored:` it
        # silently ran the machine-global check and printed "clean" for a vendored-drift request.
        if not args.vendored.strip():
            print("error: --vendored requires a repository path; got an empty value",
                  file=sys.stderr)
            return 2
        repo = Path(args.vendored).expanduser()
        vendored_skills = repo / "install" / "skills"

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
            findings = check_vendored(vendored_skills)
        except OSError as e:
            print(f"error: could not read {e.filename or vendored_skills}: {e}", file=sys.stderr)
            return 2
    else:
        findings = collect()

    if args.as_json:
        print(json.dumps([{"severity": s, "detail": d} for s, d in findings], indent=2))
    elif args.hook:
        if findings:
            # The header is mode-specific for the same reason the clean line is. The default
            # header's two claims — "the SHARED toolchain" and "this affects EVERY project" — are
            # both false of `--vendored`, which compares one named repository's published copy and
            # affects nothing outside it. Printing it there told the reader to go and fix a
            # machine-global mirror over a repository-scoped diff.
            if vendored_mode:
                print(f"AGENT CONTEXT: the vendored copy of the shared toolchain in {repo} has "
                      f"drifted from ~/.claude/skills. This is scoped to this repository — the "
                      f"installed toolchain and other projects are unaffected.")
            else:
                print("AGENT CONTEXT: the shared agent toolchain has drifted. This affects every "
                      "project, not just this one.")
            for s, d in findings:
                print(f"  - [{s}] {d}")
    else:
        print("agent toolchain:")
        for s, d in findings:
            print(f"  {s.upper():8} {d}")
        if not findings:
            # Name what was actually compared. The default line asserts three checks that
            # `--vendored` never runs, and printing it there was a claim of a guarantee the run
            # did not provide — from the one tool whose job is to be trusted about staleness.
            if vendored_mode:
                # Scoped to what the walk can actually see. "byte for byte" overclaimed: `tree()`
                # cannot surface a directory it is unable to descend into (see its KNOWN GAP), so
                # this line cannot promise the two trees hold the same files — only that nothing
                # it compared differed and nothing it touched was unreadable.
                print(f"  clean — no drift found between ~/.claude/skills and {vendored_skills}: "
                      f"every file this walk could read matches on both sides")
            else:
                print("  clean — personas in sync, instructions mirrored, Codex skills current")
    return (1 if findings else 0) if vendored_mode \
        else (1 if any(s == "critical" for s, _ in findings) else 0)


if __name__ == "__main__":
    raise SystemExit(main())
