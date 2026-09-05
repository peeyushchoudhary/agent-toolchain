"""Regression barrier for `check_toolchain.py --vendored`.

The mode shipped with none: of the card's five validation commands, one exercised the new code and
it only printed output for a human to eyeball. Deleting the body of `check_vendored` and returning
`[]` would have passed four of five. Every test here asserts a finding AND the process exit code,
because the original blocker was drift that printed and exited 0.

Synthetic trees, never the real `~/.claude`. Every subprocess case runs under a temp `HOME` — the
`--vendored` ones against a purpose-built installed/vendored pair, the two default-mode shape
checks against an empty one — so no test reads the developer's actual toolchain and none of them
can spawn the real `sync_personas.py`. The in-process cases patch `toolchain.CLAUDE_SKILLS` for
the same reason.
"""

from __future__ import annotations

import ast
import contextlib
import fnmatch
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import hermetic
from hermetic import reaches_home, synthetic_home


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


toolchain = load_module("check_toolchain_test", SCRIPTS / "check_toolchain.py")


# A success CLAIM is any string that would reassure a reader on its own. Deliberately a family
# rather than one literal: the defect these tests guard is a reassuring sentence in the wrong
# place, and `"no drift detected"` or an ASCII-hyphen variant of the same sentence is that defect
# just as much as `"clean — ..."` is. Matching one prefix would have let both through.
CLAIM_MARKERS = ("clean", "no drift", "in sync", "no findings", "up to date", "nothing to report",
                 "all match", "matches on both sides", "everything matches")

# ...and a DENIAL is not a claim, however many claim words it contains. `"NOT A CLEAN RESULT"` and
# `"this is not a clean result"` exist precisely to refuse the reassurance, and a test that flagged
# them would push an author to delete the honest sentence to get to green.
CLAIM_DENIALS = ("not a clean", "not clean", "no verdict", "cannot be read as clean",
                 "is not a clean result")


# --------------------------------------------------------------------------------------------
# TC-41 fixture helpers. A synthetic HOME has no persona source and no Codex config, so both are
# planted explicitly by every plugin fixture — and by the two pre-existing fixtures that must now
# produce exactly one finding, since without them the plugin check would add a not-run and the
# assertion under test would be measuring the scaffolding.

# The fixture's persona namespace, chosen HERE and deliberately unlike the real roster. These tests
# exercise the MECHANISM — does a plugin agent name get cross-checked against whatever
# `sync_personas.py` exposes — and pinning the real thirteen names into this file would be the
# second copy of the roster that TC-41 forbids. That the mechanism reads the REAL sets is asserted
# separately and against the real module, by `test_persona_names_come_from_sync_personas`.
FIXTURE_BASE = ("reviewer", "developer", "docs-steward")
FIXTURE_JUDGING = ("reviewer",)


def plant_persona_source(claude_skills: Path, base=FIXTURE_BASE, judging=FIXTURE_JUDGING) -> Path:
    """Write a `sync_personas.py` that `check_toolchain.persona_names()` can import.

    Guarded entry point, deliberately: `persona_names` imports this file, and an unguarded
    `sys.exit(0)` in a module body raises SystemExit through `exec_module`. The real
    `sync_personas.py` guards its `main`; a stub that did not would be testing against a shape the
    real file does not have.

    `--check` still exits 0 so `check_personas` reports the personas as compared, keeping the
    fixture's only finding the one the test planted.
    """
    path = claude_skills / "agent-personas" / "scripts" / "sync_personas.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import sys\n"
        f"BASE_PERSONA_NAMES = frozenset({sorted(base)!r})\n"
        f"JUDGING_PERSONA_NAMES = frozenset({sorted(judging)!r})\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(0)\n",
        encoding="utf-8")
    return path


def plant_codex_config(home: Path, keys=()) -> Path:
    """An empty-or-populated `~/.codex/config.toml`.

    ABSENT IS NOT EMPTY on the Codex side, which is the whole point of planting it: with no config
    file the Codex plugin surface is UNKNOWN and the check reports not-run, so a fixture that omits
    this file measures its own omission.
    """
    (home / ".codex").mkdir(parents=True, exist_ok=True)
    path = home / ".codex" / "config.toml"
    path.write_text("".join(f'[plugins."{k}"]\nenabled = true\n\n' for k in keys),
                    encoding="utf-8")
    return path


# The command a fixture hook binds. Distinctive on purpose: a test asserts this string never
# reaches the report, and a plausible command like `"true"` would be a substring of half the output.
HOOK_COMMAND_SENTINEL = "zzz-fixture-hook-body-must-not-be-reported"


def plant_plugin(plugins_root: Path, name: str, *, agents=(), hook_events=(),
                 skills: bool = False, commands: bool = False,
                 hooks_via_manifest: str | None = None, agent_frontmatter=None) -> Path:
    """One plugin root, built the way the real ones on this machine are built.

    Shapes copied from observed manifests under `~/.claude/plugins`, not reconstructed from memory:
    a `.claude-plugin/plugin.json` carrying `name`, a `hooks/hooks.json` whose `hooks` key maps an
    event name to a list of matchers, `agents/<name>.md` carrying YAML frontmatter with `name:`, and
    — for `hooks_via_manifest` — the `"hooks": "./path"` form observed in a sibling
    `.cursor-plugin/plugin.json` on this machine.

    `agents` names the FILE stems. `agent_frontmatter` optionally overrides what a given file
    declares as its `name:`, which is how the two are driven apart.
    """
    root = plugins_root / name
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    manifest = {"name": name, "description": f"fixture plugin {name}"}
    hooks_body = json.dumps({"hooks": {
        event: [{"hooks": [{"type": "command", "command": HOOK_COMMAND_SENTINEL}]}]
        for event in hook_events}})
    if hook_events and hooks_via_manifest:
        target = root / hooks_via_manifest.lstrip("./")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(hooks_body, encoding="utf-8")
        manifest["hooks"] = hooks_via_manifest
    elif hook_events:
        (root / "hooks").mkdir(exist_ok=True)
        (root / "hooks" / "hooks.json").write_text(hooks_body, encoding="utf-8")
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    if agents:
        (root / "agents").mkdir(exist_ok=True)
        for agent in agents:
            declared = (agent_frontmatter or {}).get(agent, agent)
            (root / "agents" / f"{agent}.md").write_text(
                f"---\nname: {declared}\ndescription: fixture\n---\nfixture\n", encoding="utf-8")
    for flag, directory in ((skills, "skills"), (commands, "commands")):
        if flag:
            (root / directory).mkdir(exist_ok=True)
    return root


def enable_plugins(home: Path, roots: dict[str, Path]) -> None:
    """Mark plugins enabled the way the harness does: settings.json plus installed_plugins.json.

    Both files, because the two answer different questions and the check needs both — settings.json
    says WHICH keys are on, installed_plugins.json says WHERE each one lives. A fixture that wrote
    only the first would exercise the unresolvable-path not-run, not enablement.
    """
    claude = home / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "settings.json").write_text(
        json.dumps({"enabledPlugins": {k: True for k in roots}}), encoding="utf-8")
    (claude / "plugins").mkdir(exist_ok=True)
    (claude / "plugins" / "installed_plugins.json").write_text(json.dumps({
        "version": 2,
        "plugins": {k: [{"scope": "user", "installPath": str(p)}] for k, p in roots.items()},
    }), encoding="utf-8")


# --------------------------------------------------------------------------------------------
# TC-47 fixture helpers.

def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """One git invocation against `root`, with output captured and never checked here.

    Deliberately NOT `check=True`: two callers below run git precisely to observe a NON-zero exit
    (`check-ignore` on a path a negation matched), and a helper that raised on those would make the
    trap unprovable.
    """
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def git_init(root: Path) -> Path:
    """Make `root` a work tree with an identity, and assert it actually became one.

    The assertion is the point rather than politeness: a `git init` that silently failed leaves the
    tracking sweep answering NOT-RUN, and a test that then observed "no ignored-skill finding" would
    read that absence as a pass.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "fixture")
    top = git(root, "rev-parse", "--show-toplevel")
    assert top.returncode == 0, f"git init did not produce a work tree at {root}: {top.stderr}"
    return root


# THE TWO ALLOW-LISTS, as committed literals. TC-47 fix round 3.
#
# WHY THIS EXISTS. Three versions of the KNOWN GAP paragraph in `check_tracking` were written from
# ad-hoc replicas built at a shell prompt and thrown away. Two were wrong, and the second was wrong
# precisely BECAUSE its replica carried only the top-level allow-list and omitted
# `skills/.gitignore` — so it measured a tree where all three surfaces answer `trackable`, the
# opposite of this machine. No artifact survived either time, so neither claim was falsifiable from
# this repository, and "the fix is to the method" was a promise with no mechanism behind it.
#
# `green_home` cannot serve here and must NOT be changed to. It writes no `.gitignore` at any level,
# deliberately: every tracking test plants the exact ignore state it means, and giving the shared
# baseline a real allow-list would silently rewrite what all of them measure. But that does leave
# the repository's only reusable replica a tree on which all three surfaces are trackable — the very
# tree that produced the wrong claim, and the one the next measurer reaches for. Hence a SECOND,
# purpose-built fixture rather than an edit to the shared one.
#
# UNIFYING THE TWO WAS CONSIDERED UNDER TC-48 — the shared-fixture-builder card an earlier version
# of this comment forward-referenced — AND REFUSED. Recorded here rather than left as a pointer to a
# closed card, because a comment promising queued work is worse than no comment: the next reader
# stops looking.
#
# The reason is the card's own stop condition, "consolidation would require changing a test's
# meaning rather than its fixture". These are not two builders of one tree. `green_home` is defined
# by its VERDICT — it asserts `status == "clean"` through the checker before returning, and its
# defining property is that no check objects to it; `plant_allowlisted_home` is defined by its
# RULES, carries both allow-lists, and is deliberately not green. Merging them means one of the two
# gives up its defining property, and the 44 `green_home` callers would then be measuring mutations
# against a baseline whose ignore state nobody chose. What the unification would have bought — a
# fixture that cannot silently stop being what it claims — both already have: `green_home`
# self-asserts clean, and `plant_allowlisted_home` self-asserts complete. That is the whole of the
# benefit, obtained without the merge.
#
# Shapes copied from the real files, reduced to the rules that decide the three surfaces.
# `test_the_committed_allowlists_still_decide_the_surfaces_the_real_ones_do` re-runs the same
# assertions against the actual `~/.claude` files whenever they are present, so these literals
# cannot silently drift from the policy they stand in for.
CLAUDE_ALLOWLIST = """\
/*

!/.gitignore
!/CLAUDE.md
!/settings.json
!/skills/
!/hooks/
!/agents/
!/codex/
!/docs/
/docs/*
!/docs/LEDGER.md
!/docs/fleet-lessons.md
!/docs/RESTORE.md
!/docs/decisions.md

__pycache__/
*.pyc
.DS_Store
"""

SKILLS_ALLOWLIST = """\
/*

!/.gitignore
!/README.md

!/progressive-disclosure
!/agent-personas

__pycache__/
*.pyc
*.pyo
.DS_Store
"""

# The allow-lists' claim, as data: relative path -> is it trackable when newly authored?
# FALSE is a DEFAULT-INVISIBLE surface; TRUE is a control that keeps the test non-vacuous.
#
# THIS IS A STATEMENT ABOUT THE ALLOW-LISTS, NOT ABOUT COVERAGE, and the distinction became
# load-bearing at TC-49. Under TC-47 every FALSE row was also a surface the sweep did not ask
# about, so one table said both things. TC-49 closes surfaces 1 and 2 — a FALSE row there is now
# swept and produces a finding — while surface 3 stays deferred for the noise reason argued in
# `check_tracking`. The rows below do not move: `git add --dry-run` still answers exactly this,
# and whether the sweep ASKS is a separate assertion in `TrackedContentTest`.
GAP_SURFACES = {
    "docs/NEW-LESSON.md": False,              # surface 1 — per-file allow-list under /docs/*
    "skills/NOTES.md": False,                 # surface 2 — the SECOND per-file allow-list
    "MEMORY.md": False,                       # surface 3 — a new top-level entry under /*
    ".hidden-config": False,                  # surface 3, hidden — strictly more invisible
    "skills/agent-personas/NOTES.md": True,   # INSIDE a negated skill directory
    "hooks/new.sh": True,
    "agents/new.md": True,
}

# THE HIDDEN PAIR, and it is a separate table from GAP_SURFACES on purpose. TC-47 fix round 4.
#
# GAP_SURFACES answers "is a NEWLY AUTHORED file at this path trackable?", and every TRUE row in it
# is a VISIBLE path. So as data it was consistent with the rule "hidden entries are out of scope" —
# the very rule `check_tracking`'s docstring calls false. A one-sided table is not a counterexample.
#
# These two rows are the counterexample, and they are a PAIR by construction: same directory, same
# probe, both hidden, both untracked, and the ONLY thing that differs is whether the allow-list
# names the path. `.gitignore` is hidden AND trackable AND authored AND it is the allow-list this
# whole sweep polices; `.hidden-config` is hidden and ignored. Together they say "hidden decides
# nothing; the allow-list line decides", which one row alone cannot say.
HIDDEN_TOP_LEVEL = {
    ".gitignore": True,       # negated by `!/.gitignore` — hidden, authored, and TRACKABLE
    ".hidden-config": False,  # not negated — the control that keeps the TRUE row meaningful
}


# WHAT THE REPLICA MUST CONTAIN, READ OUT OF THE ALLOW-LISTS THEMSELVES.
#
# TC-48 fix round 1, finding 5. This used to be three hand-written tuples under a comment claiming
# they were "the directories and files the allow-lists name". Nothing checked the correspondence and
# THE CLAIM WAS ALREADY FALSE: `CLAUDE_ALLOWLIST` carries `!/settings.json` and `REQUIRED_FILES` did
# not. Every negation whose path is absent from the replica is a rule about nothing — the allow-list
# under test re-includes a surface that is not there, and every probe near it answers about a tree
# nobody has.
#
# So the required set is now READ OUT of whatever rules the builder was handed, which removes the
# correspondence by construction rather than checking it. A negation added to the real
# `~/.claude/.gitignore` is planted by the replica on the same run that reads it, because
# `test_the_committed_allowlists_still_decide_the_surfaces_the_real_ones_do` hands these functions
# the real file.
def negated_entries(rules: str, prefix: str = "") -> list[str]:
    """Every path an allow-list adds back — the `!/...` lines, in file order, `prefix`ed.

    A trailing `/` is PRESERVED, because it is the only evidence in the file about whether the
    author meant a directory. `!/docs/` and `!/settings.json` must not materialise the same way.
    """
    out = []
    for line in rules.splitlines():
        stripped = line.strip()
        if stripped.startswith("!/") and len(stripped) > 2:
            out.append(prefix + stripped[2:])
    return out


def required_entries(claude_rules: str | None = None,
                     skills_rules: str | None = None) -> list[str]:
    """Both allow-lists' negations, as one ordered list of replica-relative entries."""
    return (negated_entries(CLAUDE_ALLOWLIST if claude_rules is None else claude_rules)
            + negated_entries(SKILLS_ALLOWLIST if skills_rules is None else skills_rules,
                              "skills/"))


def is_gitignore_entry(entry: str) -> bool:
    return entry.rstrip("/").rsplit("/", 1)[-1] == ".gitignore"


def is_directory_entry(entry: str) -> bool:
    """A trailing slash says directory; so does a final component with no suffix.

    `.gitignore` never reaches this — `Path(".gitignore").suffix` is empty, so the suffix rule alone
    would `mkdir` it, and the allow-lists themselves are written by the builder. `!/agent-personas`
    (a skill directory, no slash, no suffix) is the case the suffix rule exists for.
    """
    return entry.endswith("/") or not Path(entry.rstrip("/")).suffix


# EVERY `.gitignore` THE REPLICA MUST CARRY — derived from the same negations. A replica that
# carries one allow-list and not the other measures a tree that does not exist: the second bad
# TC-47 claim came from exactly that, and it produced confident, specific, wrong output TWICE —
# because a missing DIRECTORY announces itself and a missing CONFIG FILE does not. Every path still
# resolves and every answer stays plausible.
#
# `test_every_gitignore_the_real_tree_has_is_planted_by_the_builder` compares this set against a
# FULL WALK of the real `~/.claude`, split by git's own answer about which of them it consults, so
# its total comes from a different source than its count. TC-48 round 1 found the previous version
# of that test comparing a hardcoded two-element list against a constant identical to it — a
# tautology that could not fail, and that was already false: the machine carries SIX `.gitignore`
# files and the detector knew two.
REQUIRED_GITIGNORES = tuple(e for e in required_entries() if is_gitignore_entry(e))


class IncompleteReplica(AssertionError):
    """THE FIXTURE IS WRONG, NOT THE CODE.

    Deliberately not a skip. A replica that silently degrades does not fail — it ANSWERS, and the
    answer is about a tree nobody has. That is the defect class this file exists to remove.
    """


def plant_allowlisted_home(root: Path, claude_rules: str = CLAUDE_ALLOWLIST,
                           skills_rules: str = SKILLS_ALLOWLIST, commit: bool = True,
                           omit: tuple[str, ...] = ()) -> Path:
    """A work tree carrying BOTH allow-lists and the directories they name.

    Committed, reusable, and re-asserted against the real files by a sibling test — the three
    properties the ad-hoc replicas lacked.

    `commit=False` INITIALISES BUT DOES NOT COMMIT, and that is not a convenience. `git add
    --dry-run` exits 0 for any path already in the index REGARDLESS of the ignore rules — measured:
    commit a file, then add `/*` to `.gitignore`, and the probe still says 0. So a probe of a
    committed path answers "is this tracked?", not "does the allow-list admit it", and the hidden
    pair below must be probed UNTRACKED for the ALLOW-LIST rather than this builder's own
    `git add -A` to be the discriminator.

    DO NOT READ THAT AS "ASSERTIONS ON THE COMMITTED FIXTURE ARE VACUOUS". They are not, and an
    earlier version of this paragraph said so and was wrong about this fixture's ordering. The rules
    are written BEFORE the staging here — `.gitignore` at the top of the body, `git add -A` at the
    bottom — so deleting `!/.gitignore` from `CLAUDE_ALLOWLIST` makes the file ignored AT STAGING
    TIME and it is never committed at all. Measured on this builder with that one line stripped:
    `git ls-files` does not list `.gitignore`, and the probe returns IGNORED on the committed tree
    as well as the uncommitted one. The mutation IS caught either way; on the committed fixture it
    is caught INDIRECTLY, by staging, rather than by the probe. `commit=False` is the direct
    construction, which is the whole of the reason to prefer it.

    IT ASSERTS ITSELF BEFORE HANDING THE TREE BACK, and raises `IncompleteReplica` naming what is
    absent rather than returning something partial. `omit` is not a feature — it exists only so
    `AllowlistReplicaTest` can request each incomplete replica and prove the refusal fires. An
    `omit` value naming nothing the allow-lists re-include is a `ValueError`: TC-48 round 1 found
    `omit=("Docs",)` silently returning a COMPLETE replica and reporting success, which is a request
    for an incomplete tree answered with "yes, done".
    """
    entries = required_entries(claude_rules, skills_rules)
    unknown = sorted(set(omit) - set(entries))
    if unknown:
        raise ValueError(
            f"omit={unknown} names nothing these allow-lists re-include, so the replica would come "
            f"back COMPLETE and the caller would be told it had got what it asked for. Known "
            f"entries: {entries}")

    root.mkdir(parents=True, exist_ok=True)
    # Directories first, in path order, so a file's parent is never missing. Everything here is
    # READ OUT of the two allow-lists rather than listed: see `required_entries`.
    for entry in sorted(entries, key=lambda e: e.count("/")):
        if entry in omit:
            continue
        relative = entry.rstrip("/")
        if is_gitignore_entry(entry):
            rules = claude_rules if relative == ".gitignore" else skills_rules
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_text(rules, encoding="utf-8")
        elif is_directory_entry(entry):
            (root / relative).mkdir(parents=True, exist_ok=True)
        else:
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_text("x\n", encoding="utf-8")
    # A negated skill directory with no `SKILL.md` is a directory git will not commit, so the
    # probes would see nothing there. This is the one thing the allow-lists do not say.
    for skill in (root / "skills").iterdir() if (root / "skills").is_dir() else ():
        if skill.is_dir() and not any(skill.iterdir()):
            (skill / "SKILL.md").write_text("x\n", encoding="utf-8")
    git_init(root)
    if commit:
        git(root, "add", "-A")
        git(root, "commit", "-qm", "base")
    require_complete_replica(root, claude_rules, skills_rules)
    return root


def replica_gaps(root: Path, claude_rules: str | None = None,
                 skills_rules: str | None = None) -> list[str]:
    """Everything the allow-lists re-include that this replica does not actually contain."""
    gaps = []
    entries = required_entries(claude_rules, skills_rules)
    found = {str(p.relative_to(root)) for p in root.rglob(".gitignore")}
    for entry in entries:
        relative = entry.rstrip("/")
        if is_gitignore_entry(entry):
            if relative not in found:
                gaps.append(f"the allow-list `{relative}` is ABSENT — every git answer about this "
                            f"tree is decided by a rule set that is not this machine's")
        elif is_directory_entry(entry):
            if not (root / relative).is_dir():
                gaps.append(f"the directory `{relative}/` is ABSENT, so `!{'/' + entry}` "
                            f"re-includes nothing")
        elif not (root / relative).is_file():
            gaps.append(f"the file `{relative}` is ABSENT, so `!{'/' + entry}` re-includes nothing")
    if not (root / ".git").is_dir():
        gaps.append("this is not a git work tree, so every tracking probe answers NOT-RUN")
    return gaps


def require_complete_replica(root: Path, claude_rules: str | None = None,
                             skills_rules: str | None = None) -> None:
    """Raise unless the replica carries everything the probes run against it will ask about."""
    gaps = replica_gaps(root, claude_rules, skills_rules)
    entries = required_entries(claude_rules, skills_rules)
    if not gaps:
        return
    raise IncompleteReplica(
        f"THE FIXTURE IS WRONG, NOT THE CODE.\nThe replica at {root} is incomplete "
        f"({len(gaps)} gap(s) against the {len(entries)} path(s) these two allow-lists "
        f"re-include):\n  - "
        + "\n  - ".join(gaps)
        + "\nMeasured twice in TC-47: a replica missing one of these does not fail, it ANSWERS, and "
          "the answer is about a tree that does not exist."
    )


def split_gitignores_by_whether_git_consults_them(root: Path) -> tuple[list[str], list[str]]:
    """Every `.gitignore` under `root`, split into (governing, inert) BY ASKING GIT.

    The total comes from a full `rglob` and the filter comes from `git check-ignore`, which is the
    point: a filtered count whose total is derived from the same place as the filter cannot fail.
    TC-48 round 1 found exactly that here — a two-element list of levels, identical to the constant
    it was compared against, described in four comments as a walk.

    INERT means git never reads it. A `.gitignore` inside an IGNORED DIRECTORY is not consulted,
    because git does not descend into a directory it has already excluded, so no rule in that file
    can decide any surface this suite probes. Naming the excluded directory here instead would be
    an annotation, and an annotation is only as true as whatever checks it; git's own answer moves
    when the allow-list moves.

    THE PROBE IS THE CONTAINING DIRECTORY, NOT THE FILE, and the difference is not pedantry. git
    reads a directory's `.gitignore` when it descends into that directory whether or not the file
    itself is ignored — `~/.claude/docs/.gitignore` would be ignored by `/docs/*` and CONSULTED all
    the same. Probing the file would classify that one inert and hand back exactly the blind spot
    this function was written to remove.
    """
    governing, inert = [], []
    for path in sorted(root.rglob(".gitignore")):
        relative = str(path.relative_to(root))
        holder = str(path.parent.relative_to(root))
        if holder == ".":
            governing.append(relative)           # the root is never ignored
            continue
        probe = git(root, "check-ignore", "-q", "--", holder)
        # 0 = ignored, 1 = not ignored, anything else = git could not answer and must not be
        # silently read as "governing" — an error here would quietly shrink the excluded set.
        assert probe.returncode in (0, 1), (
            f"git check-ignore could not answer for {holder} under {root} "
            f"(rc={probe.returncode}): {probe.stderr}")
        (inert if probe.returncode == 0 else governing).append(relative)
    return governing, inert


def plant_workspace(root: Path, cards: dict[str, tuple[str, ...]]) -> Path:
    """A card workspace: `TC-*.yaml` beside a `reports/` directory.

    `cards` maps a card id to the report-directory filenames it owns, so a test states the exact
    artifact set it means — `("TC-40-report.md",)` for the measured near-miss, and the same plus a
    review for its remedy.
    """
    (root / "reports").mkdir(parents=True, exist_ok=True)
    for card, artifacts in cards.items():
        (root / f"{card}.yaml").write_text(f"id: {card}\n", encoding="utf-8")
        for artifact in artifacts:
            (root / "reports" / artifact).write_text(f"# {artifact}\n", encoding="utf-8")
    return root


def _docstring_ids(tree: ast.AST) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant):
            out.add(id(body[0].value))
    return out


def claim_strings(tree: ast.AST) -> list[ast.Constant]:
    """Every string constant in `tree` that asserts success, excluding docstrings and denials.

    Takes a PARSED TREE, not source. An earlier version parsed internally while its caller parsed
    separately, so the two `id()` spaces never intersected and every claim looked like it was in
    the wrong place. That version could only ever fail — loudly, so it was caught — but a helper
    whose answer does not depend on the code it is asked about is the vacuity the reviewer flagged,
    arriving from the other direction.
    """
    skip = _docstring_ids(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        lowered = node.value.lower()
        if any(d in lowered for d in CLAIM_DENIALS):
            continue
        if any(m in lowered for m in CLAIM_MARKERS):
            found.append(node)
    return found


def printed_nodes(tree: ast.AST) -> set[int]:
    """Ids of every node underneath a `print(...)` call — everything that can reach a stream."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "print":
            out.update(id(child) for child in ast.walk(node))
    return out


def find_function(case: unittest.TestCase, tree: ast.AST, name: str) -> ast.FunctionDef:
    """Locate a function by name, FAILING rather than raising StopIteration if it was renamed.

    A structural test that errors out on rename reports the wrong condition: the reader sees a
    broken test, not "the chokepoint this rule protects no longer exists under that name".
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    case.fail(f"no function named `{name}` — if it was renamed, this rule now protects nothing "
              f"and the new name must be recorded here deliberately")


class VendoredDriftTest(unittest.TestCase):
    """Build installed/vendored pairs and assert the finding and the exit code together."""

    def make_pair(self, tmp: Path) -> tuple[Path, Path]:
        """A minimal in-sync pair: one skill, one file, byte-identical on both sides."""
        installed = tmp / "home" / ".claude" / "skills"
        vendored = tmp / "repo" / "install" / "skills"
        (installed / "alpha").mkdir(parents=True)
        (vendored / "alpha").mkdir(parents=True)
        (installed / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
        (vendored / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
        return installed, vendored

    def run_vendored(self, tmp: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "check_toolchain.py"),
             "--vendored", str(tmp / "repo"), *extra],
            capture_output=True,
            text=True,
            env={**dict(os.environ), "HOME": str(tmp / "home")},
        )

    # --- the three drift categories, one finding each, with their exit codes ----------------

    def test_in_sync_pair_is_clean_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self.make_pair(tmp)

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("clean", r.stdout)
            # The success line must name what was compared, not the three checks this mode skips.
            self.assertNotIn("personas in sync", r.stdout)
            self.assertNotIn("Codex skills current", r.stdout)

    def test_skill_missing_from_vendored_is_one_finding_and_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, _ = self.make_pair(tmp)
            (installed / "beta").mkdir()
            (installed / "beta" / "SKILL.md").write_text("beta\n", encoding="utf-8")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertEqual(self.findings(r), 1)
            self.assertIn("skill `beta`", r.stdout)
            self.assertIn("absent from the vendored copy", r.stdout)

    def test_skill_extra_in_vendored_is_one_finding_and_exits_one(self) -> None:
        """The original blocker: stale published content printed a warn and exited 0."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            _, vendored = self.make_pair(tmp)
            (vendored / "stale").mkdir()
            (vendored / "stale" / "SKILL.md").write_text("dead\n", encoding="utf-8")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertEqual(self.findings(r), 1)
            self.assertIn("skill `stale`", r.stdout)
            self.assertIn("stale published content", r.stdout)
            # Severity, explicitly. Exit 1 alone does not pin this: `findings()` counts WARN lines
            # too, and the mode-specific exit rule returns 1 for a warn as readily as a critical,
            # so demoting this emission back to the severity the blocker had would leave every
            # other assertion in this test green.
            self.assertIn("CRITICAL", r.stdout)
            self.assertNotIn("WARN", r.stdout)

    def test_content_differs_is_one_finding_and_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            _, vendored = self.make_pair(tmp)
            (vendored / "alpha" / "SKILL.md").write_text("alpha EDITED\n", encoding="utf-8")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertEqual(self.findings(r), 1)
            self.assertIn("skill `alpha` file `SKILL.md` content differs from vendored", r.stdout)

    def test_same_size_edit_is_caught(self) -> None:
        """Bytes, not a stat signature: same length and a copied mtime must still differ."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            (vendored / "alpha" / "SKILL.md").write_text("ALPHA\n", encoding="utf-8")
            src = installed / "alpha" / "SKILL.md"
            os.utime(vendored / "alpha" / "SKILL.md",
                     (src.stat().st_atime, src.stat().st_mtime))

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("content differs", r.stdout)

    # --- fail-open paths that previously reported clean -------------------------------------

    def test_unreadable_on_both_sides_is_a_finding_not_a_match(self) -> None:
        """`b"<unreadable>"` made two unreadable files compare EQUAL and report in sync."""
        if os.geteuid() == 0:
            self.skipTest("root ignores mode 000")
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            a = installed / "alpha" / "SKILL.md"
            b = vendored / "alpha" / "SKILL.md"
            b.write_text("different content entirely\n", encoding="utf-8")
            a.chmod(0o000)
            b.chmod(0o000)
            try:
                r = self.run_vendored(tmp)
            finally:
                a.chmod(0o644)
                b.chmod(0o644)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("could not be compared in ~/.claude/skills", r.stdout)
            self.assertIn("could not be compared in the vendored copy", r.stdout)
            self.assertNotIn("clean", r.stdout)
            # Unreadable is not "missing": it must not also be reported as absent.
            self.assertNotIn("absent from vendored", r.stdout)

    def test_symlinked_vendored_root_is_rejected_with_exit_two(self) -> None:
        """A vendored copy that is a link to its source compares identical forever."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            for child in vendored.iterdir():
                (child / "SKILL.md").unlink()
                child.rmdir()
            vendored.rmdir()
            vendored.symlink_to(installed)

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("vendored root is a symlink", r.stderr)

    def test_symlinked_subdirectory_is_a_finding_not_an_empty_tree(self) -> None:
        """rglob does not descend into a symlinked dir while is_dir() follows it."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            real = tmp / "elsewhere"
            (real / "nested").mkdir(parents=True)
            (real / "nested" / "deep.md").write_text("deep\n", encoding="utf-8")
            (installed / "alpha" / "linked").symlink_to(real)
            (vendored / "alpha" / "linked").symlink_to(real)

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("symlink, not compared", r.stdout)

    def test_top_level_regular_files_are_compared(self) -> None:
        """Only directories used to be enumerated; a top-level README could drift freely."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            (installed / "README.md").write_text("installed index\n", encoding="utf-8")
            (vendored / "README.md").write_text("published index\n", encoding="utf-8")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertEqual(self.findings(r), 1)
            self.assertIn("top-level entry `README.md` content differs from vendored", r.stdout)

    def test_skills_root_reached_through_a_symlinked_parent_is_rejected(self) -> None:
        """The leaf probe misses the likelier shape: `ln -s ~/.claude <repo>/install`.

        `<repo>/install/skills` is then a REAL directory reached through a link, so `is_symlink()`
        is False on both roots and the mode compares the installed tree against itself: identical,
        exit 0, permanently clean while the repository publishes nothing. The fail-open is silent
        and never self-corrects, which is the worst shape this whole review is about.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            for child in sorted(vendored.iterdir()):
                (child / "SKILL.md").unlink()
                child.rmdir()
            vendored.rmdir()
            (tmp / "repo" / "install").rmdir()
            (tmp / "repo" / "install").symlink_to(installed.parent)  # -> <home>/.claude

            self.assertTrue((tmp / "repo" / "install" / "skills").is_dir())
            self.assertFalse((tmp / "repo" / "install" / "skills").is_symlink(),
                             "fixture must NOT be a leaf symlink; that case is already covered")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("same directory", r.stderr)
            self.assertNotIn("clean", r.stdout)

    def test_skill_symlinked_on_one_side_is_not_called_stale(self) -> None:
        """A skill installed as a link is uncompared, not stale and not unpublished."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            real = tmp / "elsewhere"
            real.mkdir()
            (real / "SKILL.md").write_text("alpha\n", encoding="utf-8")
            (installed / "alpha" / "SKILL.md").unlink()
            (installed / "alpha").rmdir()
            (installed / "alpha").symlink_to(real)

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("symlink, not compared", r.stdout)
            # It is present on both sides. Neither presence category may claim otherwise.
            self.assertNotIn("stale published content", r.stdout)
            self.assertNotIn("absent from the vendored copy", r.stdout)
            # And a symlinked directory is not a "file".
            self.assertNotIn("top-level file", r.stdout)

    # --- the other two output modes, which no test covered -----------------------------------

    def test_hook_mode_header_is_repository_scoped_not_machine_global(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            _, vendored = self.make_pair(tmp)
            (vendored / "stale").mkdir()
            (vendored / "stale" / "SKILL.md").write_text("dead\n", encoding="utf-8")

            r = self.run_vendored(tmp, "--hook")

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertTrue(r.stdout.startswith("AGENT CONTEXT:"), r.stdout)
            self.assertIn("scoped to this repository", r.stdout)
            # Both clauses of the default header are false here.
            self.assertNotIn("shared agent toolchain has drifted", r.stdout)
            self.assertNotIn("affects every project", r.stdout)
            self.assertIn("- [critical] skill `stale`", r.stdout)

    def test_hook_mode_is_silent_when_the_vendored_copy_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self.make_pair(tmp)

            r = self.run_vendored(tmp, "--hook")

            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout, "")

    def test_json_mode_carries_the_findings_and_the_exit_code(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            _, vendored = self.make_pair(tmp)
            (vendored / "stale").mkdir()
            (vendored / "stale" / "SKILL.md").write_text("dead\n", encoding="utf-8")

            r = self.run_vendored(tmp, "--json")

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            payload = json.loads(r.stdout)
            self.assertEqual(payload["status"], "findings")
            self.assertEqual(payload["exit"], 1)
            self.assertEqual(len(payload["findings"]), 1, payload)
            self.assertEqual(payload["findings"][0]["severity"], "critical")
            self.assertIn("stale published content", payload["findings"][0]["detail"])

    # --- usage and environment errors --------------------------------------------------------

    def test_empty_and_whitespace_vendored_argument_exit_two(self) -> None:
        for value in ("", "   ", "\t"):
            with self.subTest(value=repr(value)), tempfile.TemporaryDirectory() as t:
                tmp = Path(t)
                self.make_pair(tmp)

                r = subprocess.run(
                    [sys.executable, str(SCRIPTS / "check_toolchain.py"), "--vendored", value],
                    capture_output=True,
                    text=True,
                    env={**dict(os.environ), "HOME": str(tmp / "home")},
                )

                # Must NOT fall through to the machine-global check and print its clean line.
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("requires a repository path", r.stderr)
                self.assertEqual(r.stdout, "")

    def test_missing_vendored_root_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            (vendored / "alpha" / "SKILL.md").unlink()
            (vendored / "alpha").rmdir()
            vendored.rmdir()

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("vendored root not found", r.stderr)

    def test_missing_installed_root_blames_the_installed_side(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, _ = self.make_pair(tmp)
            (installed / "alpha" / "SKILL.md").unlink()
            (installed / "alpha").rmdir()
            installed.rmdir()

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("installed root not found", r.stderr)
            self.assertNotIn("vendored root", r.stderr)

    # --- naming --------------------------------------------------------------------------

    def test_persona_naming_requires_exactly_two_parts(self) -> None:
        describe = toolchain._describe_vendored
        self.assertEqual(describe("agent-personas", "personas/scout.md"), "persona `scout`")
        self.assertEqual(
            describe("agent-personas", "personas/archive/scout.md"),
            "skill `agent-personas` file `personas/archive/scout.md`",
        )
        self.assertEqual(
            describe("agent-personas", "personas/README.md"),
            "skill `agent-personas` file `personas/README.md`",
        )
        self.assertEqual(
            describe("other-skill", "personas/scout.md"),
            "skill `other-skill` file `personas/scout.md`",
        )

    # --- helpers ---------------------------------------------------------------------------

    def findings(self, r: subprocess.CompletedProcess) -> int:
        return sum(1 for line in r.stdout.splitlines()
                   if line.startswith("  CRITICAL") or line.startswith("  WARN"))


class CodexMirrorRemedyTest(unittest.TestCase):
    """`check_skills()` prints at every session start; a remedy it prints must be able to work."""

    @contextlib.contextmanager
    def mirror(self, tmp: Path):
        claude, codex = tmp / "claude" / "skills", tmp / "codex" / "skills"
        (claude / "demo").mkdir(parents=True)
        (codex / "demo").mkdir(parents=True)
        saved = (toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS, toolchain.MIRRORED_SKILLS)
        toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS = claude, codex
        toolchain.MIRRORED_SKILLS = ("demo",)
        try:
            yield claude, codex
        finally:
            (toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS,
             toolchain.MIRRORED_SKILLS) = saved

    def test_symlink_finding_does_not_prescribe_install_hooks(self) -> None:
        """`install_hooks.py` cannot clear a symlink under either `copytree` setting.

        It re-copies the link or copies the target's contents; the reported path stays a link
        either way. Sending the reader to run a command that provably will not clear the finding
        is worse than saying nothing, because it teaches them the check is noise.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            with self.mirror(tmp) as (claude, codex):
                real = tmp / "elsewhere"
                real.mkdir()
                (real / "deep.md").write_text("deep\n", encoding="utf-8")
                (claude / "demo" / "linked").symlink_to(real)
                (codex / "demo" / "linked").symlink_to(real)

                findings = toolchain.check_skills()

            joined = " ".join(d for _, d in findings)
            self.assertIn("symlink", joined, findings)
            self.assertIn("replace the symlink with a real directory", joined)
            self.assertNotIn("Fix: install_hooks.py", joined)

    def test_a_declared_claude_only_path_is_not_reported_as_drift(self) -> None:
        """The reason the exemption exists: a difference no remedy can clear must not be reported.

        `install_hooks.py` is what this check prescribes, and for a path that must NOT reach the
        Codex side that command can never clear the finding. A warning firing at every session
        start under a remedy that does not work is the cry-wolf failure this file names repeatedly.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            with self.mirror(tmp) as (claude, codex):
                saved = toolchain.CLAUDE_ONLY_IN_MIRROR
                toolchain.CLAUDE_ONLY_IN_MIRROR = {"demo/tests": "declared for this test"}
                try:
                    (claude / "demo" / "tests").mkdir()
                    (claude / "demo" / "tests" / "only_here.py").write_text("x\n", encoding="utf-8")
                    findings = toolchain.check_skills()
                finally:
                    toolchain.CLAUDE_ONLY_IN_MIRROR = saved

            self.assertEqual(findings, [], findings)

    def test_emptying_the_declaration_makes_it_a_finding_again(self) -> None:
        """The exemption must be load-bearing rather than decorative — the same property
        `test_deleting_the_declaration_makes_the_vendor_skill_a_finding_again` asserts for the
        vendor list. If the finding does not come back when the list is emptied, the list is not
        what is suppressing it and the entry is documenting something that is not happening."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            with self.mirror(tmp) as (claude, codex):
                (claude / "demo" / "tests").mkdir()
                (claude / "demo" / "tests" / "only_here.py").write_text("x\n", encoding="utf-8")
                saved = toolchain.CLAUDE_ONLY_IN_MIRROR
                toolchain.CLAUDE_ONLY_IN_MIRROR = {}
                try:
                    findings = toolchain.check_skills()
                finally:
                    toolchain.CLAUDE_ONLY_IN_MIRROR = saved

            self.assertEqual([sev for sev, _ in findings], ["warn"], findings)
            self.assertIn("differs from the Codex copy", findings[0][1])

    def test_a_claude_only_path_PRESENT_on_the_codex_side_is_still_a_finding(self) -> None:
        """The exemption is scoped to one direction, and the other one fails CLOSED.

        Absent on the Codex side is the declared state and is silent. Present there means something
        copied the region where it cannot work, which is a real defect with a real remedy — and the
        remedy is a deletion, so it must NOT inherit the `install_hooks.py` line that would not
        clear it. An exemption that silenced both directions would be the fail-open shape this file
        exists to remove.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            with self.mirror(tmp) as (claude, codex):
                saved = toolchain.CLAUDE_ONLY_IN_MIRROR
                toolchain.CLAUDE_ONLY_IN_MIRROR = {"demo/tests": "cannot run on the Codex side."}
                try:
                    for side in (claude, codex):
                        (side / "demo" / "tests").mkdir()
                        (side / "demo" / "tests" / "t.py").write_text("x\n", encoding="utf-8")
                    findings = toolchain.check_skills()
                finally:
                    toolchain.CLAUDE_ONLY_IN_MIRROR = saved

            self.assertEqual([sev for sev, _ in findings], ["warn"], findings)
            self.assertIn("Claude-only path(s) present in ~/.codex/skills", findings[0][1])
            self.assertIn("delete them", findings[0][1])
            self.assertNotIn("Fix: install_hooks.py", findings[0][1])

    def test_the_claude_only_list_is_short_and_every_entry_carries_a_reason(self) -> None:
        """The other half of the exemption, matching the vendor list's cap exactly. A list that may
        grow silently is an allow-list again, and an exclusion set large enough to skim is one
        nobody audits. Two is one more than today's single legitimate entry."""
        declared = toolchain.CLAUDE_ONLY_IN_MIRROR
        self.assertIsInstance(declared, dict)
        self.assertGreaterEqual(len(declared), 1, "an empty list makes the exemption vacuous")
        self.assertLessEqual(len(declared), 2, sorted(declared))
        for rel, why in declared.items():
            self.assertIn("/", rel, f"`{rel}` must be <skill>/<path within it>, not a bare name — "
                                    f"a bare basename would exempt that name in every skill")
            self.assertIn(rel.split("/", 1)[0], toolchain.MIRRORED_SKILLS,
                          f"`{rel}` names a skill that is not mirrored, so it exempts nothing")
            self.assertGreater(len(why), 40,
                               f"`{rel}` is excluded with no argument a reader can weigh: {why!r}")

    def test_the_copier_reads_the_same_declaration_as_the_checker(self) -> None:
        """The defect this file already suffered once, one turn later.

        `sync_codex`'s own comment records it: a second hardcoded copy of the mirrored-skill roster
        is how `execution-methodology` came to be checked but never copied, so the checker's own
        suggested fix could not satisfy the checker. A Claude-only list that the COPIER does not
        read is the same shape — the checker would report a path it must not see while the copier
        kept putting it there, forever, under a remedy that causes the finding.

        Asserted against the AST, not the text: READING the name is the whole point, so a line
        containing it proves nothing on its own and a substring rule cannot tell a use from a
        redefinition. What must not exist is an ASSIGNMENT to the name — that is the second copy.
        """
        src = (Path(toolchain.__file__).resolve().parent / "install_hooks.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)

        imported = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                    and n.module == "check_toolchain"
                    and any(a.name == "CLAUDE_ONLY_IN_MIRROR" for a in n.names)]
        self.assertTrue(imported,
                        "sync_codex does not import the Claude-only declaration, so it will copy "
                        "the very paths check_skills reports as intruders — the checker's own "
                        "remedy would then be the thing causing the finding")

        assigned = []
        for n in ast.walk(tree):
            targets = ([n.target] if isinstance(n, ast.AnnAssign)
                       else getattr(n, "targets", []) if isinstance(n, ast.Assign) else [])
            for t in targets:
                if isinstance(t, ast.Name) and t.id == "CLAUDE_ONLY_IN_MIRROR":
                    assigned.append(n.lineno)
        self.assertEqual(assigned, [],
                         f"install_hooks.py RESTATES the declaration at line(s) {assigned} rather "
                         f"than importing it — the second-copy defect its own comment describes")

    def test_ordinary_drift_still_prescribes_install_hooks(self) -> None:
        """The remedy that DOES work must survive the split, unchanged."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            with self.mirror(tmp) as (claude, codex):
                (claude / "demo" / "SKILL.md").write_text("new\n", encoding="utf-8")
                (codex / "demo" / "SKILL.md").write_text("old\n", encoding="utf-8")

                findings = toolchain.check_skills()

            self.assertEqual(len(findings), 1, findings)
            self.assertEqual(findings[0][0], "warn")
            self.assertIn("differs from the Codex copy", findings[0][1])
            self.assertIn("Fix: install_hooks.py", findings[0][1])


class ExitContractTest(unittest.TestCase):
    """Pin the two belts of the F1 blocker fix SEPARATELY.

    The fix wears two: every `check_vendored` finding is emitted as `critical`, AND `--vendored`'s
    exit rule ignores severity. The first barrier tested only their conjunction — reverting either
    one alone left all 17 tests green, because with belt 2 in place a demoted finding still exits
    1, and with belt 1 in place every finding is critical so the inherited `any critical` rule
    still exits 1. A barrier that fires only when both belts are removed at once is not a barrier;
    it cannot stop the first of the two edits, which is the one that would actually happen.

    So each test here removes the other belt's protection by construction: the severity test reads
    severities directly and never looks at an exit code, and the exit-rule test feeds `main()` a
    finding that is deliberately NOT critical.
    """

    def build_drifted(self, tmp: Path) -> tuple[Path, Path]:
        """An installed/vendored pair exercising all seven emission sites in `check_vendored`.

        The five drift sites — presence both directions at skill level and at file level, plus
        content-differs — and BOTH `could not be compared` sites in `_compare`, which need an entry
        `tree()` refuses to read. A symlink is the cheapest such entry (an unreadable file needs a
        chmod that root ignores and that CI may run as), and the two sites are per-side, so one
        symlink on each side is required: `shared/linked` reaches the installed-side emission and
        `shared/linked2` the vendored-side one. Without both, demoting either site's severity
        leaves the whole suite green.
        """
        installed = tmp / "home" / ".claude" / "skills"
        vendored = tmp / "repo" / "install" / "skills"
        for root in (installed, vendored):
            (root / "shared").mkdir(parents=True)
        # content differs
        (installed / "shared" / "SKILL.md").write_text("installed\n", encoding="utf-8")
        (vendored / "shared" / "SKILL.md").write_text("published\n", encoding="utf-8")
        # file present installed, absent from vendored / present in vendored, not installed
        (installed / "shared" / "only-installed.md").write_text("a\n", encoding="utf-8")
        (vendored / "shared" / "only-vendored.md").write_text("b\n", encoding="utf-8")
        # whole skill missing from vendored, and a stale one left behind in vendored
        (installed / "only-installed-skill").mkdir()
        (installed / "only-installed-skill" / "SKILL.md").write_text("x\n", encoding="utf-8")
        (vendored / "stale-skill").mkdir()
        (vendored / "stale-skill" / "SKILL.md").write_text("y\n", encoding="utf-8")
        # top-level entries, both directions
        (installed / "README.md").write_text("installed index\n", encoding="utf-8")
        (vendored / "EXTRA.md").write_text("orphan\n", encoding="utf-8")
        # one uncomparable entry per side, so `_compare` emits on both its installed-side and its
        # vendored-side `could not be compared` path. Distinct names: a matching pair would still
        # be two findings, but it could not distinguish the two sites if one stopped firing.
        (installed / "shared" / "linked").symlink_to(tmp)
        (vendored / "shared" / "linked2").symlink_to(tmp)
        return installed, vendored

    def test_every_vendored_finding_is_critical(self) -> None:
        """BELT 1, in-process and blind to the exit code.

        Asserts the severity SET, not "some finding is critical": demoting any single emission
        site to `warn` must fail this, and an `assertIn`-style check would not notice.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.build_drifted(tmp)
            original = toolchain.CLAUDE_SKILLS
            toolchain.CLAUDE_SKILLS = installed
            try:
                findings, _excluded = toolchain.check_vendored(vendored)
            finally:
                toolchain.CLAUDE_SKILLS = original

            # Guard the guard: a fixture that stopped producing drift would make the set assertion
            # below vacuously true against an empty set.
            # 7 drift findings + the two `could not be compared` emissions the symlinks force.
            self.assertGreaterEqual(len(findings), 9, findings)
            self.assertEqual({s for s, _ in findings}, {"critical"}, findings)

    def test_vendored_exit_rule_ignores_severity(self) -> None:
        """BELT 2, in-process, with the only finding deliberately non-critical.

        `--vendored` must exit 1 for ANY finding. Reverting to the shared `any critical` rule is
        invisible while belt 1 holds, so the only way to see it is to hand `main()` a finding that
        belt 1 would never produce.

        HERMETIC SINCE TC-57. It used to rebind `CLAUDE_SKILLS` alone, which is all that
        `--vendored` reads TODAY — but `main()` is one `elif` away from `collect()`, and a mode
        that fell through to it would have read this machine's plugins and this machine's git
        index while the test read as fixture-driven. `synthetic_home` rebinds all ten home-derived
        globals at once, so the reach cannot widen underneath this test. Note it plants nothing:
        `tmp / "home" / ".claude" / "skills"` is where `CLAUDE_SKILLS` lands by construction, which
        the assertion below states rather than assumes.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed = tmp / "home" / ".claude" / "skills"
            (installed / "alpha").mkdir(parents=True)
            (tmp / "repo" / "install" / "skills" / "alpha").mkdir(parents=True)

            saved_argv = sys.argv
            saved_check = toolchain.check_vendored
            toolchain.check_vendored = (
                lambda _root, _rules=(), _preserved=frozenset():
            ([("warn", "synthetic non-critical finding")], []))
            sys.argv = ["check_toolchain.py", "--vendored", str(tmp / "repo")]
            buffer = io.StringIO()
            try:
                with synthetic_home(toolchain, tmp / "home"):
                    self.assertEqual(toolchain.CLAUDE_SKILLS, installed,
                                     "the rebind did not land on the tree this test built")
                    with contextlib.redirect_stdout(buffer):
                        rc = toolchain.main()
            finally:
                toolchain.check_vendored = saved_check
                sys.argv = saved_argv

            self.assertEqual(rc, 1, buffer.getvalue())
            self.assertIn("synthetic non-critical finding", buffer.getvalue())
            self.assertNotIn("clean", buffer.getvalue())


class PreserveAcrossInstallsTest(unittest.TestCase):
    """`PRESERVE_ACROSS_INSTALLS` retires the installed-only finding, and ONLY that one.

    The four permanent CRITICALs this closes were all the same shape: a path the installer puts
    into `~/.claude/skills` on purpose, absent from the vendored copy on purpose, reported as drift
    with no action that could ever clear it. The declaration that creates them already exists in
    `install/install.sh`; the check was reading a different file.

    Direction-awareness is the part worth pinning. `install.sh` promises "a vendored copy always
    WINS... the entry just goes inert", so a preserved path that IS published must be compared
    normally. An exclusion that ignored direction would make vendoring one of these paths silently
    uncompared — a quieter failure than the loud one it replaced.
    """

    def build(self, tmp: Path, preserve_block: str) -> tuple[Path, Path]:
        """Installed and vendored roots sharing one skill, with an installer carrying `preserve_block`.

        The preserved entries are one FILE and one DIRECTORY, because the real list holds both and
        a directory is the case a naive equality match gets wrong.
        """
        installed = tmp / "home" / ".claude" / "skills"
        vendored = tmp / "repo" / "install" / "skills"
        for root in (installed, vendored):
            (root / "alpha").mkdir(parents=True)
            (root / "alpha" / "SKILL.md").write_text("same\n", encoding="utf-8")
        (installed / "alpha" / "LEDGER.tsv").write_text("local\n", encoding="utf-8")
        (installed / "alpha" / "tests").mkdir()
        (installed / "alpha" / "tests" / "test_local.py").write_text("pass\n", encoding="utf-8")
        (vendored.parent / "install.sh").write_text(preserve_block, encoding="utf-8")
        return installed, vendored

    INSTALLER = 'PRESERVE_ACROSS_INSTALLS="\nalpha/LEDGER.tsv\nalpha/tests\n"\n'

    def run_check(self, installed: Path, vendored: Path):
        preserved, problems = toolchain.read_preserved(vendored)
        self.assertEqual(problems, [], problems)
        original = toolchain.CLAUDE_SKILLS
        toolchain.CLAUDE_SKILLS = installed
        try:
            return toolchain.check_vendored(vendored, (), preserved)
        finally:
            toolchain.CLAUDE_SKILLS = original

    def test_preserved_installed_only_paths_are_excluded_not_critical(self) -> None:
        """No finding — and NOT silence. Every retired path is named in `excluded`, with its file.

        Both halves matter. Dropping the finding alone would trade a permanent CRITICAL for an
        invisible one, which is the failure mode this module has spent itself removing; and the
        reason string has to name `install/install.sh`, because that is the file an operator edits
        to change the answer.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.build(tmp, self.INSTALLER)
            findings, excluded = self.run_check(installed, vendored)

            self.assertEqual(findings, [], findings)
            self.assertEqual([rel for rel, _ in excluded],
                             ["alpha/LEDGER.tsv", "alpha/tests/test_local.py"], excluded)
            for _rel, why in excluded:
                self.assertEqual(why, "declared preserved across installs by install/install.sh")

    def test_a_preserved_path_that_is_vendored_is_compared_normally(self) -> None:
        """The direction-awareness test. A published copy wins, so its content is still compared.

        Fails loudly if `is_preserved` is ever folded into `is_excluded`: a symmetric exclusion
        drops the path from both sides before any category is computed, and this content difference
        would vanish.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.build(tmp, self.INSTALLER)
            (vendored / "alpha" / "LEDGER.tsv").write_text("published\n", encoding="utf-8")

            findings, excluded = self.run_check(installed, vendored)

            self.assertEqual(len(findings), 1, findings)
            self.assertEqual(findings[0][0], "critical")
            self.assertIn("LEDGER.tsv", findings[0][1])
            self.assertIn("content differs", findings[0][1])
            self.assertNotIn("alpha/LEDGER.tsv", [rel for rel, _ in excluded], excluded)

    def test_deleting_the_installer_entry_brings_the_finding_back(self) -> None:
        """Nothing is special-cased in check_toolchain.py; the answer comes from install.sh.

        Same construction as the declaration test on the `.gitignore` side: remove the line and the
        CRITICAL returns. If it did not, the exclusion would be a hard-coded name list wearing a
        reader's clothes.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.build(tmp, 'PRESERVE_ACROSS_INSTALLS="\nalpha/tests\n"\n')

            findings, excluded = self.run_check(installed, vendored)

            self.assertEqual(len(findings), 1, findings)
            self.assertIn("LEDGER.tsv", findings[0][1])
            self.assertIn("present installed, absent from vendored", findings[0][1])
            # The other entry still holds, so this is the LINE that was removed and not the reader.
            self.assertEqual([rel for rel, _ in excluded], ["alpha/tests/test_local.py"], excluded)

    def test_an_absent_installer_preserves_nothing(self) -> None:
        """"No declaration" reads as "nothing preserved", never as "everything preserved".

        The opposite reading is the fail-open: a repository that lost its install.sh would report
        clean over whatever the installed tree happens to hold.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.build(tmp, self.INSTALLER)
            (vendored.parent / "install.sh").unlink()

            preserved, problems = toolchain.read_preserved(vendored)
            self.assertEqual((preserved, problems), (frozenset(), []))

    def test_preserved_by_matches_a_directory_prefix_not_a_bare_name(self) -> None:
        """`alpha/tests` must cover what is beneath it, and must not cover `alpha/tests-extra`."""
        preserved = frozenset({"alpha/tests", "alpha/LEDGER.tsv"})
        self.assertTrue(toolchain.preserved_by(preserved, "alpha/tests"))
        self.assertTrue(toolchain.preserved_by(preserved, "alpha/tests/deep/x.py"))
        self.assertTrue(toolchain.preserved_by(preserved, "alpha/LEDGER.tsv"))
        self.assertFalse(toolchain.preserved_by(preserved, "alpha/tests-extra/x.py"))
        self.assertFalse(toolchain.preserved_by(preserved, "beta/tests/x.py"))


class UnchangedModesTest(unittest.TestCase):
    """The default and --hook paths run at every session start; they must not have moved."""

    def test_tree_still_returns_bytes_keyed_by_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "scripts").mkdir()
            (root / "scripts" / "a.py").write_bytes(b"x")
            (root / "scripts" / "__pycache__").mkdir()
            (root / "scripts" / "__pycache__" / "a.pyc").write_bytes(b"junk")
            (root / "b.pyc").write_bytes(b"junk")

            files, problems = toolchain.tree(root)

            self.assertEqual(files, {os.path.join("scripts", "a.py"): b"x"})
            self.assertEqual(problems, [])

    def test_tree_top_level_pattern_does_not_recurse(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "sub").mkdir()
            (root / "sub" / "deep.md").write_bytes(b"deep")
            (root / "top.md").write_bytes(b"top")

            files, problems = toolchain.tree(root, "*")

            self.assertEqual(files, {"top.md": b"top"})
            self.assertEqual(problems, [])

    def run_default(self, tmp: Path, *extra: str) -> subprocess.CompletedProcess:
        """Default-mode run under a synthetic HOME.

        These two cases assert output SHAPE, nothing about content, so a synthetic HOME serves
        them exactly as well as the real one — and without it they read the developer's actual
        ~/.claude, making the result machine-dependent, and spawn `sync_personas.py` with a 60s
        timeout, making the suite's runtime unbounded by anything in this file.
        """
        (tmp / ".claude").mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "check_toolchain.py"), *extra],
            capture_output=True, text=True,
            env={**dict(os.environ), "HOME": str(tmp)},
        )

    def test_hook_mode_emits_no_stray_output_shape(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            r = self.run_default(Path(t), "--hook")

            # 2 is the correct answer for this fixture, so assert it. `assertIn(rc, (0, 1, 2))`
            # cannot fail — `main` returns nothing else — and widening an assertion to accommodate
            # a new value rather than updating it to that value is how a test stops being one.
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            if r.stdout:
                self.assertTrue(r.stdout.startswith("AGENT CONTEXT:"), r.stdout)
                # The default header, not the repository-scoped one: this mode IS machine-global.
                self.assertIn("affects every project", r.stdout)

    def test_json_mode_is_parseable(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as t:
            r = self.run_default(Path(t), "--json")

            payload = json.loads(r.stdout)
            # An OBJECT, not a bare array. An array cannot distinguish "nothing was wrong" from
            # "nothing was looked at", which is the whole defect; `status` and `counts` can.
            self.assertIsInstance(payload, dict)
            for key in ("mode", "status", "exit", "counts", "evaluated",
                        "not_evaluated", "excluded", "findings", "summary"):
                self.assertIn(key, payload, payload)
            for item in payload["findings"]:
                self.assertEqual(sorted(item), ["detail", "severity"])
            # Countable by severity without parsing prose — the contract TC-37's verify.sh consumes.
            self.assertEqual(payload["counts"]["total"], len(payload["findings"]))
            for severity in toolchain.SEVERITY_RANK:
                self.assertIn(severity, payload["counts"])


class NotRunStateTest(unittest.TestCase):
    """THE THIRD STATE. A check that did not run may not read as a check that passed.

    Every case here has the same shape as the defect: before the change, the failure path and the
    success path produced the same output. The assertions are always the emitted TEXT and the exit
    code together, because either one alone can be made green by a fix that lies in the other.
    """

    @contextlib.contextmanager
    def mirror(self, tmp: Path, installed: tuple[str, ...], mirrored: tuple[str, ...]):
        claude, codex = tmp / "claude" / "skills", tmp / "codex" / "skills"
        claude.mkdir(parents=True)
        codex.mkdir(parents=True)
        for name in installed:
            (claude / name).mkdir()
            (codex / name).mkdir()
        saved = (toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS, toolchain.MIRRORED_SKILLS)
        toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS = claude, codex
        toolchain.MIRRORED_SKILLS = mirrored
        try:
            yield claude, codex
        finally:
            (toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS,
             toolchain.MIRRORED_SKILLS) = saved

    def test_uninstalled_mirrored_skill_is_not_run_rather_than_silence(self) -> None:
        """The original swallow, exactly: `if not src.is_dir(): continue`.

        A skill named in MIRRORED_SKILLS but absent from ~/.claude/skills produced NO output, so a
        run that compared nothing was byte-identical to a run that compared everything and then
        printed "Codex skills current".
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            with self.mirror(tmp, installed=("demo",), mirrored=("demo", "absent")):
                findings = toolchain.check_skills()

            self.assertEqual([s for s, _ in findings], [toolchain.NOT_RUN], findings)
            self.assertIn("skill `absent` was NOT COMPARED", findings[0][1])

    def test_a_not_run_check_cannot_contribute_to_the_clean_line(self) -> None:
        """Text and exit code together, end to end.

        A HOME with an empty `.claude` and nothing else can compare nothing at all. The old build
        printed three `warn`s and exited 0; worse, each of the three phrases it would have claimed
        is hard-coded in one string, so nothing structurally prevented that string appearing.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / ".claude").mkdir()

            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "check_toolchain.py")],
                capture_output=True, text=True, env={**dict(os.environ), "HOME": str(tmp)})

            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertNotIn("clean", r.stdout)
            for claim in ("personas in sync", "instructions mirrored", "Codex skills current"):
                self.assertNotIn(claim, r.stdout, "a check that did not run claimed its result")
            self.assertIn("NOT RUN", r.stdout.upper())
            self.assertIn("NOT A CLEAN RESULT", r.stdout)

    def test_not_run_json_says_which_checks_did_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / ".claude").mkdir()

            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "check_toolchain.py"), "--json"],
                capture_output=True, text=True, env={**dict(os.environ), "HOME": str(tmp)})

            payload = json.loads(r.stdout)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)
            self.assertEqual(payload["exit"], 2)
            self.assertEqual(payload["evaluated"], [])
            # Five, not four: TC-41's plugin surface joined the original three, and TC-47's skill
            # tracking joined those — an empty HOME has no ~/.codex/config.toml, so the Codex plugin
            # surface is UNKNOWN rather than empty, and no ~/.claude/skills at all, so git cannot be
            # asked whether anything would be committed. Updated to the new value rather than
            # widened to a subset check, for the reason `test_hook_mode_emits_no_stray_output_shape`
            # gives about widening an assertion to accommodate a new value.
            self.assertEqual({item["check"] for item in payload["not_evaluated"]},
                             {"personas", "instruction mirror", "Codex skill mirror",
                              "plugin surface", toolchain.TRACKING_LABEL})

    def test_drift_is_machine_visible_while_the_exit_code_stays_zero(self) -> None:
        """FACE 1. Real Codex-mirror drift, `warn`, exit 0 — and now impossible to miss.

        The exit code deliberately does NOT change: TC-06 rules that `warn` must not be fatal here,
        because this runs at every session start and this machine's ordinary state carries genuine
        re-vendor drift. So the remedy is a result a caller can read, not a louder code. This test
        pins BOTH halves — the 0 that must not become 1, and the report that must no longer be
        indistinguishable from a pass.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            home = tmp / "home"
            claude, codex = home / ".claude" / "skills", home / ".codex" / "skills"
            for name in toolchain.MIRRORED_SKILLS:
                (claude / name).mkdir(parents=True)
                (codex / name).mkdir(parents=True)
                (claude / name / "SKILL.md").write_text("same\n", encoding="utf-8")
                (codex / name / "SKILL.md").write_text("same\n", encoding="utf-8")
            # One skill drifts. Assert the fixture actually bit: a mutation that silently failed to
            # apply produces a green run proving nothing.
            drifted = claude / toolchain.MIRRORED_SKILLS[0] / "SKILL.md"
            original = drifted.read_bytes()
            drifted.write_text("edited\n", encoding="utf-8")
            self.assertNotEqual(drifted.read_bytes(), original, "fixture did not mutate")

            # A sync tool that reports the personas are fine, and instruction files that mirror, so
            # the ONLY finding is the Codex drift.
            sync = plant_persona_source(claude)
            # Mirror it, or the stub itself is a second Codex-mirror difference and the test would
            # be asserting against its own scaffolding rather than the drift it planted.
            mirrored_sync = codex / "agent-personas" / "scripts" / "sync_personas.py"
            mirrored_sync.parent.mkdir(parents=True)
            mirrored_sync.write_bytes(sync.read_bytes())
            shared = "\n".join(start + "\nx\n" + end for start, end in toolchain.MIRRORED)
            (home / ".claude" / "CLAUDE.md").write_text(shared, encoding="utf-8")
            (home / ".codex").mkdir(exist_ok=True)
            (home / ".codex" / "AGENTS.md").write_text(shared, encoding="utf-8")
            # TC-41: no ~/.claude/plugins at all is a legitimate EMPTY plugin surface, but an
            # absent ~/.codex/config.toml is an UNKNOWN one. Plant the config so the plugin check
            # enumerates zero rather than adding a not-run that would mask the drift under test.
            plant_codex_config(home)
            # TC-47, same reasoning one check over: a HOME that is not a work tree cannot be asked
            # whether git would commit its skills, and that not-run would turn this run's status
            # into not-run and its exit code into 2 — measuring the missing repository instead of
            # the single warn this test exists to pin.
            git_init(home / ".claude")

            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "check_toolchain.py"), "--json"],
                capture_output=True, text=True, env={**dict(os.environ), "HOME": str(home)})

            payload = json.loads(r.stdout)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)   # TC-06: warn is not fatal
            self.assertEqual(payload["status"], "findings")          # ...and not a pass either
            self.assertEqual(payload["counts"]["warn"], 1, payload)
            self.assertEqual(payload["counts"]["critical"], 0, payload)
            self.assertNotIn("clean", payload["summary"])
            self.assertIn("differs from the Codex copy", payload["findings"][0]["detail"])

    def test_unknown_severity_is_loud_but_not_fatal(self) -> None:
        """TC-06's ruling, pinned as behaviour rather than as a comment.

        Rank governs visibility; the BLOCKING set governs the exit code. An advisory level added
        next year must sort to the top of the report and must NOT start failing sessions.

        THIS IS THE TEST TC-57 WAS WRITTEN FOR, and what it did wrong is worth keeping on the page.
        It replaced `DEFAULT_CHECKS` with a synthetic pair, made an empty `tmp/.claude`, and called
        `main()` — believing the synthetic table was the whole run. It is not: `collect()` calls
        `check_plugins()` and `check_tracking()` UNCONDITIONALLY, outside that table, and both read
        module globals frozen from `Path.home()` at import. So the run reached this developer's
        real `~/.claude/plugins` and real `~/.codex/config.toml`, found them, added no `not-run`,
        and returned 1. Unpack a COMPLETE `git archive HEAD` of this repository under a redirected
        HOME and the same test returns 2, with two `not-run` findings about the replica's absent
        plugin surface — a confident, specific failure about a machine, presented as a defect in
        the exit-code contract. TC-48 made the half-TREE unconstructible; nothing stopped a test
        from stepping outside the tree entirely.

        THE HOME IS NOW BUILT AND REBOUND. `synthetic_home` points all ten home-derived globals at
        `tmp`, and the two inputs whose ABSENCE is a `not-run` rather than an empty answer are
        planted with the same helpers the neighbouring drift test uses and for the same recorded
        reasons: `plant_codex_config` (absent is UNKNOWN on the Codex side, not empty) and
        `git_init` (a HOME that is not a work tree cannot be asked whether git would commit its
        skills). `~/.claude/plugins` is deliberately NOT planted — absent there is a legitimate
        EMPTY surface, and planting it would be the fixture drifting past what the check needs.

        AND THE BASELINE IS ASSERTED, not assumed. With NO synthetic findings at all the run must
        be clean and exit 0. Without that control, "rc == 1" cannot distinguish the critical this
        test planted from a `not-run` the fixture leaked, which is the exact confusion above.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / ".claude" / "skills").mkdir(parents=True)
            plant_persona_source(tmp / ".claude" / "skills")
            plant_codex_config(tmp)
            git_init(tmp / ".claude")

            saved = (toolchain.DEFAULT_CHECKS, sys.argv)

            def run(*findings) -> tuple[int, str]:
                toolchain.DEFAULT_CHECKS = (
                    ("synthetic", "synthetic fine", lambda: list(findings)),
                )
                sys.argv = ["check_toolchain.py"]
                buffer = io.StringIO()
                try:
                    with synthetic_home(toolchain, tmp), contextlib.redirect_stdout(buffer):
                        return toolchain.main(), buffer.getvalue()
                finally:
                    toolchain.DEFAULT_CHECKS, sys.argv = saved

            # THE POSITIVE CONTROL, first: this fixture contributes no finding of its own, so every
            # exit code below is attributable to the synthetic severities and to nothing else.
            rc, out = run()
            self.assertEqual(rc, 0, out)
            self.assertNotIn(toolchain.NOT_RUN, out)

            rc, out = run(("advisory", "a brand new level"), ("critical", "a known one"))
            self.assertEqual(rc, 1, out)  # from the critical, never from the unknown level
            self.assertLess(out.index("a brand new level"), out.index("a known one"),
                            "an unrecognised severity must sort loudest, above critical")

            # And alone, it must not be fatal.
            rc, out = run(("advisory", "a brand new level"))
            self.assertEqual(rc, 0, out)


class DeclaredUnpublishedTest(unittest.TestCase):
    """The repository's own `install/skills/.gitignore` decides what it publishes; so does this.

    graphify is a vendor skill that installs itself into ~/.claude/skills and is deliberately never
    vendored, so `--vendored` reported it as a permanent CRITICAL that no re-vendor could clear —
    the kind of finding that teaches a reader to ignore the whole report. The remedy is to read the
    declaration git already obeys. There is no second exception list and no special case for any
    name, which the structural test at the bottom of this class asserts.
    """

    # Shaped like the real `install/skills/.gitignore`: an anchored allowlist for the top level,
    # then a "Never, anywhere" tail. Both halves matter — the tail is the only thing that reaches
    # a path INSIDE a published skill, and a fixture with only the allowlist would have let the
    # depth-wise half of F1 pass untested.
    ALLOWLIST = ("# ignore everything, then name what we own\n"
                 "/*\n"
                 "!/.gitignore\n"
                 "!/alpha\n"
                 "\n"
                 "# Never, anywhere.\n"
                 "__pycache__/\n"
                 "*.pyc\n"
                 "*.pyo\n"
                 ".DS_Store\n")

    def make_pair(self, tmp: Path) -> tuple[Path, Path]:
        installed = tmp / "home" / ".claude" / "skills"
        vendored = tmp / "repo" / "install" / "skills"
        (installed / "alpha").mkdir(parents=True)
        (vendored / "alpha").mkdir(parents=True)
        (installed / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
        (vendored / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
        # A vendor skill that installed itself on the machine and is not published.
        (installed / "vendorskill").mkdir()
        (installed / "vendorskill" / "SKILL.md").write_text("third party\n", encoding="utf-8")
        return installed, vendored

    def declare(self, installed: Path, vendored: Path) -> Path:
        """Write the declaration on both sides, as the real machine has it.

        The vendored copy is the one that governs — it is the file git consults for that directory
        — but the installed layer carries the same file, so writing it on only one side would
        manufacture a top-level presence finding and test the fixture instead of the feature.
        Returns the governing (vendored) copy.
        """
        (installed / ".gitignore").write_text(self.ALLOWLIST, encoding="utf-8")
        (vendored / ".gitignore").write_text(self.ALLOWLIST, encoding="utf-8")
        return vendored / ".gitignore"

    def run_vendored(self, tmp: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "check_toolchain.py"),
             "--vendored", str(tmp / "repo"), *extra],
            capture_output=True, text=True,
            env={**dict(os.environ), "HOME": str(tmp / "home")})

    def test_declared_unpublished_is_not_a_finding_but_is_still_reported(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            self.declare(installed, vendored)

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("vendorskill` present in ~/.claude/skills", r.stdout)
            # Excluded, never silent: the summary states the scope beside the verdict, so "clean"
            # is never read as "everything was compared".
            self.assertIn("clean", r.stdout)
            self.assertIn("1 excluded from findings: vendorskill", r.stdout)
            self.assertIn("install/skills/.gitignore", r.stdout)

    def test_deleting_the_declaration_makes_it_a_finding_again(self) -> None:
        """The card's own test: a check that passes because it ignores everything is the defect.

        Same tree, same command, one file removed. If the exclusion came from anywhere other than
        the declaration — a hard-coded name, a second list — this stays green and says so.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            declaration = self.declare(installed, vendored)

            before = self.run_vendored(tmp)
            self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

            original = declaration.read_bytes()
            declaration.unlink()
            (installed / ".gitignore").unlink()   # both copies, or the delete plants a new finding
            self.assertFalse(declaration.exists(), "fixture did not mutate")
            self.assertTrue(original, "fixture was empty to begin with")

            after = self.run_vendored(tmp)

            self.assertEqual(after.returncode, 1, after.stdout + after.stderr)
            self.assertIn("skill `vendorskill` present in ~/.claude/skills, "
                          "absent from the vendored copy", after.stdout)
            self.assertNotIn("clean", after.stdout)

    def test_a_published_skill_is_still_compared(self) -> None:
        """The allowlist re-includes `alpha`; drift in it must still be caught."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            self.declare(installed, vendored)
            target = vendored / "alpha" / "SKILL.md"
            original = target.read_bytes()
            target.write_text("alpha EDITED\n", encoding="utf-8")
            self.assertNotEqual(target.read_bytes(), original, "fixture did not mutate")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("skill `alpha` file `SKILL.md` content differs", r.stdout)

    def test_an_unreadable_declaration_is_not_run_not_an_empty_exclusion_set(self) -> None:
        """Falling back to "nothing is excluded" would be a guess presented as a fact."""
        if os.geteuid() == 0:
            self.skipTest("root ignores mode 000")
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            declaration = self.declare(installed, vendored)
            declaration.chmod(0o000)
            try:
                r = self.run_vendored(tmp)
            finally:
                declaration.chmod(0o644)

            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertNotIn("clean", r.stdout)
            self.assertIn("could not be read", r.stdout)

    def test_no_declaration_excludes_nothing(self) -> None:
        """"No declaration" means "everything is published", never "assume an exclusion"."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            self.make_pair(tmp)

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("skill `vendorskill`", r.stdout)

    def test_rules_that_address_a_nested_path_do_not_match_a_bare_name(self) -> None:
        rules = toolchain._gitignore_rules("a/b\n!c/d\n/*\n!/keep\ndrop/\n")
        self.assertEqual(rules, [("*", False, True), ("keep", True, True), ("drop", False, False)])

    def test_anchoring_is_preserved_so_a_top_level_rule_cannot_eat_the_tree(self) -> None:
        """`/*` and `.DS_Store` mean opposite-scoped things and must not collapse together.

        Applying an unanchored `*` at every depth would exclude every path in both trees and turn
        the whole comparison into a silent pass — the defect class this card removes, reintroduced
        by the fix for it. This is the unit-level guard on that.
        """
        rules = toolchain._gitignore_rules("/*\n!/alpha\n.DS_Store\n*.pyo\n")

        # Anchored: top level only.
        self.assertTrue(toolchain.excluded_by(rules, "vendorskill"))
        self.assertFalse(toolchain.excluded_by(rules, "alpha"))
        # The catastrophe: `/*` must NOT match a component below the top.
        self.assertFalse(toolchain.excluded_by(rules, "alpha/scripts/run.py"))
        self.assertFalse(toolchain.excluded_by(rules, "alpha/SKILL.md"))
        # Unanchored: any depth, which is what "never, anywhere" means in the real declaration.
        self.assertTrue(toolchain.excluded_by(rules, ".DS_Store"))
        self.assertTrue(toolchain.excluded_by(rules, "alpha/.DS_Store"))
        self.assertTrue(toolchain.excluded_by(rules, "alpha/scripts/x.pyo"))
        # An excluded directory takes its contents with it.
        self.assertTrue(toolchain.excluded_by(rules, "vendorskill/scripts/x.py"))

    def test_a_declared_top_level_file_is_not_a_permanent_critical(self) -> None:
        """F1, reproduced. `.DS_Store` is declared, and git will never publish it.

        Opening `~/.claude/skills` in Finder once creates one. Because exclusion reached the two
        directory sets but not the top-level entry sweep, the result was a CRITICAL that no
        re-vendor could ever clear — precisely the pathology named in this class's own docstring.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            self.declare(installed, vendored)

            baseline = self.run_vendored(tmp)
            self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)

            litter = installed / ".DS_Store"
            litter.write_bytes(b"\x00\x01Bud1")
            self.assertTrue(litter.exists() and litter.stat().st_size > 0,
                            "fixture did not mutate")

            after = self.run_vendored(tmp)

            self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
            # NOT a finding — but not absent either. This was `assertNotIn(".DS_Store", stdout)`,
            # which PINNED the silence that finding R3 is about: the file was dropped from the
            # comparison and from every report, so an entry wrongly excluded looked exactly like
            # one correctly compared. "Not a CRITICAL" is the property. "Never mentioned" never was.
            self.assertNotIn("CRITICAL", after.stdout)
            self.assertIn(".DS_Store", after.stdout)
            self.assertIn("excluded from findings", after.stdout)

    def test_an_excluded_top_level_file_is_reported_not_silently_dropped(self) -> None:
        """R3. "Reported, never silent" has to hold for FILES, not only for skill directories.

        The scope report was re-derived by enumerating top-level DIRECTORIES, so an excluded file —
        which the real anchored `/*` produces for every entry not explicitly negated — was removed
        from the comparison and named in no output at all. `touch NOTES.md` and it simply vanished.
        If NOTES.md were something the repository should publish and someone had forgotten the
        negation, the failure path and the success path produced identical output: this card's own
        defect class, arriving through the fix for F1.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            self.declare(installed, vendored)
            notes = installed / "NOTES.md"
            notes.write_text("scratch\n", encoding="utf-8")
            self.assertTrue(notes.exists(), "fixture did not mutate")

            r = self.run_vendored(tmp, "--json")
            payload = json.loads(r.stdout)

            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("NOTES.md", {item["name"] for item in payload["excluded"]}, payload)
            # ...and in the human report too, since that is where a person would look.
            human = self.run_vendored(tmp)
            self.assertIn("NOTES.md", human.stdout)

    def test_an_excluded_path_at_depth_is_reported_too(self) -> None:
        """Same rule below the top level, where the "never, anywhere" tail of the declaration bites."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            self.declare(installed, vendored)
            litter = installed / "alpha" / ".DS_Store"
            litter.write_bytes(b"\x00\x01Bud1")
            self.assertTrue(litter.exists(), "fixture did not mutate")

            r = self.run_vendored(tmp, "--json")
            payload = json.loads(r.stdout)

            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("alpha/.DS_Store", {item["name"] for item in payload["excluded"]}, payload)

    def test_a_declared_path_inside_a_published_skill_is_excluded_too(self) -> None:
        """"Never, anywhere" is the declaration's own wording; depth must not defeat it."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            self.declare(installed, vendored)
            nested = installed / "alpha" / ".DS_Store"
            nested.write_bytes(b"\x00\x01Bud1")
            self.assertTrue(nested.exists(), "fixture did not mutate")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            # Excluded, therefore not a finding — and named, therefore not silent. See the sibling
            # above on why `assertNotIn` was the wrong assertion here.
            self.assertNotIn("CRITICAL", r.stdout)
            self.assertIn("alpha/.DS_Store", r.stdout)

    def test_a_published_file_inside_a_skill_is_still_compared(self) -> None:
        """Guard the guard for the two tests above: depth-wise exclusion must not be total."""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            self.declare(installed, vendored)
            extra = installed / "alpha" / "scripts" / "run.py"
            extra.parent.mkdir()
            extra.write_text("x\n", encoding="utf-8")
            self.assertTrue(extra.exists(), "fixture did not mutate")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("scripts/run.py", r.stdout)

    def test_a_declared_name_present_only_in_the_vendored_copy_is_not_stale_content(self) -> None:
        """F2. Uninstall a vendor skill while untracked litter remains in the repository.

        Candidates were drawn from the installed side alone, so this direction was never a
        candidate for exclusion and reported `stale published content` for a directory git will
        never track — another permanent finding with no available remedy.
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed, vendored = self.make_pair(tmp)
            self.declare(installed, vendored)
            # Present ONLY in the vendored copy, and covered by the declaration.
            (vendored / "vendorskill").mkdir()
            (vendored / "vendorskill" / "SKILL.md").write_text("stale\n", encoding="utf-8")
            (installed / "vendorskill" / "SKILL.md").unlink()
            (installed / "vendorskill").rmdir()
            self.assertFalse((installed / "vendorskill").exists(), "fixture did not mutate")

            r = self.run_vendored(tmp)

            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("stale published content", r.stdout)
            self.assertIn("1 excluded from findings: vendorskill", r.stdout)


class NoSecondExceptionListTest(unittest.TestCase):
    """Structural, and blind to behaviour. The rule, not today's instance of it."""

    SOURCE = (SCRIPTS / "check_toolchain.py").read_text(encoding="utf-8")

    def test_no_skill_is_special_cased_by_name(self) -> None:
        """A hard-coded name would pass every behavioural test above and be the wrong fix.

        The exclusion must come from the declaration the repository already carries, so that
        deleting it restores the finding — which is exactly what a hard-coded name would defeat.

        Asserted against the AST, not the text: prose may (and does) name the skill when explaining
        WHY the declaration is read. What must not exist is a string this code can compare against.
        Docstrings are excluded by identity, so the explanation cannot be mistaken for a rule.

        WHAT THIS RULE ACTUALLY MATCHES, stated because the TC-47 review found all three places
        justifying the exemption below describing it as forbidding "any skill name". It does not:
        it matches ONE literal, `"graphify" in n.value.lower()`. The proof is in the file it guards
        — `MIRRORED_SKILLS` holds six skill names as module-level constants and has always passed.
        The exemption therefore widens a one-name rule by one assignment, a materially smaller
        trade than the earlier description implied. Approving it was right; describing it as a
        breach of a general prohibition was not.

        ONE EXEMPTION, ADDED BY TC-47 AND NARROWED TO A SINGLE ASSIGNMENT: the right-hand side of
        `DECLARED_VENDOR_SKILLS`. That card requires a code-resident vendor list because its sweep
        has no declaration to read — `~/.claude/skills/.gitignore` is an allow-list of what this
        repository OWNS, so a vendor skill's absence from it is the very state under test rather
        than a statement that the absence was deliberate. Reading it as a declaration would make
        every dropped skill self-exonerating, which is this rule's own failure mode arriving from
        the other side.

        The exemption is scoped to that one assignment and nowhere else, so a name in any FUNCTION
        still fails, and it is paid for behaviourally in `TrackedContentTest`: the list is capped at
        two entries, every entry must carry an argument, and emptying it must restore the finding —
        which is the "delete it and the finding comes back" property this test was written to
        protect, asserted directly instead of inferred from the absence of a literal.
        """
        tree = ast.parse(self.SOURCE)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) \
                        and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))

        exempt: set[int] = set()
        for stmt in tree.body:
            targets = ([stmt.target] if isinstance(stmt, ast.AnnAssign)
                       else getattr(stmt, "targets", []))
            if any(isinstance(t, ast.Name) and t.id == "DECLARED_VENDOR_SKILLS" for t in targets) \
                    and stmt.value is not None:
                exempt.update(id(n) for n in ast.walk(stmt.value))
        # Guard the guard: the exemption must actually cover something, or a rename has quietly
        # turned it into a no-op AND left the list unprotected by the behavioural tests that name it.
        self.assertTrue(exempt, "DECLARED_VENDOR_SKILLS is gone — either the exemption below is "
                                "dead and must be deleted, or the list was renamed and the "
                                "narrowing now protects nothing")

        offenders = [f"line {n.lineno}: {n.value!r}" for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and id(n) not in docstrings and id(n) not in exempt
                     and "graphify" in n.value.lower()]
        self.assertEqual(offenders, [], "a skill named in code, not read from the declaration:\n  "
                                        + "\n  ".join(offenders))

    def test_the_clean_sentence_is_composed_in_exactly_one_place(self) -> None:
        """EXACTLY one, which means EXISTENCE as well as uniqueness.

        The first version of this test collected success sentences outside `Run.summary` and
        asserted the list was empty. Deleting the sentence from `Run.summary` as well — leaving the
        program unable to report success at all — passed it. "Exactly one place" was implemented as
        "at most one place": a test that cannot tell one from zero, which is a swallow that reads
        as clean, inside the test written to prevent swallows. Both halves are asserted now.

        The match is a FAMILY of claim shapes rather than one literal prefix, because
        `print("no drift detected")` or an ASCII-hyphen variant of the same sentence is the same
        false reassurance and a prefix test could not see either.

        The rule is about EMISSION, not mere presence. `DEFAULT_CHECKS` holds "personas in sync"
        and `main` holds the vendored success phrase; both are data handed to `Run.add`, which can
        only release them through `Run.summary` and only when the check produced no `not-run`.
        Flagging those would push an author to obfuscate the phrases rather than fix anything. What
        must never exist is a claim that reaches a stream without passing the chokepoint.
        """
        tree = ast.parse(self.SOURCE)
        claims = claim_strings(tree)
        printed = printed_nodes(tree)
        summary = find_function(self, tree, "summary")
        inside_ids = {id(n) for n in ast.walk(summary)}

        emitted = [f"line {n.lineno}: {n.value!r}" for n in claims
                   if id(n) in printed and id(n) not in inside_ids]
        self.assertEqual(emitted, [], "a success claim printed without passing Run.summary:\n  "
                                      + "\n  ".join(emitted))

        # ...and the sentence has not simply been deleted. Without this half, removing the success
        # line entirely — leaving the tool unable to report success at all — passes, which is a
        # test that cannot tell one from zero.
        #
        # `>= 1`, not `== 1`, and the reason is the widened matcher rather than laxity: inside
        # `Run.summary` the word "clean" is also the STATUS TOKEN (`if status == "clean"`) and
        # "no findings" is a fragment of the non-clean head. Demanding exactly one would be
        # counting incidental vocabulary and would break on any rewording that kept the rule
        # intact. End-to-end existence — that a clean run actually prints a success line — is
        # pinned behaviourally by `test_in_sync_pair_is_clean_and_exits_zero`, which fails on
        # deletion of the literal; the two together distinguish one from zero.
        inside = [n for n in claims if id(n) in inside_ids]
        self.assertGreaterEqual(len(inside), 1,
                                "Run.summary contains no success claim at all — the success line "
                                "has been deleted, not relocated")

    def test_the_verdict_is_the_only_thing_main_returns_to_the_shell(self) -> None:
        """No second decision site. `main` reports what `Run.verdict` decided; it never re-decides.

        The only returns permitted are the chokepoint's `code` and the bare literal 2 of the usage
        and environment errors, every one of which writes to stderr with stdout empty. A recomputed
        exit expression here would be free to disagree with the summary printed two lines above it,
        which is this card's defect wearing a different hat.
        """
        main = find_function(self, ast.parse(self.SOURCE), "main")
        returned = set()
        for node in ast.walk(main):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if isinstance(node.value, ast.Name):
                returned.add(node.value.id)
            elif isinstance(node.value, ast.Constant):
                returned.add(repr(node.value.value))
            else:
                returned.add(f"a computed expression at line {node.value.lineno}")
        self.assertEqual(returned, {"code", "2"}, returned)

    def test_every_comparison_applies_the_declaration(self) -> None:
        """R2. Every `_compare` call site must pass the exclusion predicate.

        This is the claim the `check_vendored` docstring was already making before this test
        existed. Completeness was asserted only BEHAVIOURALLY, by two tests each pinning one call
        site, so a third call site added later would compare unexcluded, reintroduce the permanent
        CRITICAL, and leave the whole suite green. `_compare` now also has no default for
        `is_excluded`, so omission is a TypeError — but a default is one edit away from being
        restored, and this test outlives that.

        Same rule as `test_every_flag_gated_check_declares_its_absence` on the other side of this
        diff. Enforcing it there while merely claiming it here is what made the comment worse than
        no comment: the next reader would not have checked.
        """
        tree = ast.parse(self.SOURCE)
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_compare"]

        # Guard the guard: a matcher finding no call sites would pass vacuously.
        self.assertGreaterEqual(len(calls), 2, "no _compare call sites found — matcher is broken")

        offenders = [f"line {c.lineno}: _compare(...) with {len(c.args)} positional args and no "
                     f"is_excluded= keyword"
                     for c in calls
                     if len(c.args) < 5 and not any(k.arg == "is_excluded" for k in c.keywords)]
        self.assertEqual(offenders, [], "a comparison that does not apply the declaration:\n  "
                                        + "\n  ".join(offenders))

        # The SECOND declaration, under the same rule. `PRESERVE_ACROSS_INSTALLS` reaches every
        # comparison or it reaches none of them usefully: a call site that omits it re-emits the
        # permanent CRITICAL for whichever region it covers, and every test above stays green
        # because they all read the region that still has it.
        missing = [f"line {c.lineno}: _compare(...) with {len(c.args)} positional args and no "
                   f"is_preserved= keyword"
                   for c in calls
                   if len(c.args) < 6 and not any(k.arg == "is_preserved" for k in c.keywords)]
        self.assertEqual(missing, [], "a comparison that does not apply the installer's preserve "
                                      "list:\n  " + "\n  ".join(missing))

    def test_every_severity_emitted_is_ranked(self) -> None:
        """Every severity this file emits, not a whitelist of the six we happen to have used.

        The first version gated on a hard-coded six-name tuple, so a new `("blocker", …)` or
        `("fatal", …)` was invisible — its empty result was true for a reason unrelated to the rule
        it claimed to enforce. The second reached `X.append((sev, …))` and `return [(sev, …)]` and
        missed a `return` whose value is a TUPLE CONTAINING A LIST, which is exactly
        `read_declaration`'s `return [], [(NOT_RUN, …)]` — the precise gap it was raised to close,
        one emission shape over.

        So the rule is now structural rather than syntactic: every 2-tuple inside ANY list literal,
        plus every `.append(...)` argument. Module-level assignments are subtracted, because
        `MIRRORED` is a list of string 2-tuples that are section markers, not severities.

        THE THIRD WIDENING WAS THE LAST ONE THIS MATCHER GETS FOR A HEAD SHAPE. The first three
        rounds each named one more accepted node type, and each time the shape after it was already
        in the file: the fourth was `findings.append(("info" if state == "not-enabled" else "warn",
        …))`, an `ast.IfExp` head, which two rounds of "structural rather than syntactic" walked
        straight past. The failing input is one word: make that literal `("blocker" if … else
        "warn", …)` and the old matcher stayed green while a severity of rank −1 reached the output
        with visibility and blocking both undefined.
        The fix is not a fifth accepted type. `head_severities` WALKS the head expression, so
        anything built out of the shapes it knows — a conditional, a boolean fallback, a constant, a
        module constant, nested in any combination — resolves to the set of strings it can evaluate
        to. That is what makes the "structural" claim above true rather than aspirational.
        WHAT IT STILL DOES NOT REACH, stated because an unreachable head is silently invisible and
        this test's whole history is a claim of totality that was not. TWO kinds, and the second is
        the one the walker will meet first:
          - A head computed at runtime — a dict subscript, a call, a `.format`, an f-string, an
            attribute. Not resolvable from the AST at all.
          - A NAME BOUND ANYWHERE BUT MODULE SCOPE. `head_severities` accepts `ast.Name` but
            resolves it only as a module global, so a local binding yields `[]`. The failing input
            is row 4's, restructured into two lines: `severity = "blocker" if state == "not-enabled"
            else "warn"` followed by `findings.append((severity, …))` passes every assertion below
            while `blocker` reaches the output at rank −1. No live instance today. Resolving an
            enclosing-scope `Assign` would close it and was declined at this stage as too much
            machinery for a shape the file does not yet contain — which is exactly the reasoning
            that let the `IfExp` shape sit here for three rounds, so weigh it again if one appears.
        Neither kind can be made an error: most 2-tuples in this file are not findings
        (`("skill x", "reason")` exclusions, `(state, detail)` probe returns), and rejecting
        unresolved heads fires immediately on four of them. A severity emitted through either shape
        is out of this rule's reach; do not read the empty `unranked` as covering it.
        """
        tree = ast.parse(self.SOURCE)
        emitted: dict[str, int] = {}

        # Module-level data is not an emission. Collect the whole subtree of every top-level
        # assignment so `MIRRORED`'s entries cannot be mistaken for findings.
        module_data: set[int] = set()
        for stmt in tree.body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and stmt.value is not None:
                module_data.update(id(n) for n in ast.walk(stmt.value))

        def head_severities(head: ast.AST) -> list[str]:
            """Every string the head can evaluate to THAT IS RESOLVABLE FROM THE AST ALONE.

            `[]` MEANS UNRESOLVED, NOT NONE. Read it as "this head was not resolved", never as
            "this head emits no severity" — the residue paragraph in the caller's docstring lists
            the two shapes that land here, and an unqualified reading of this return is how the
            previous version of this matcher came to claim a totality it did not have.

            `Constant` and `Name` are leaves; `IfExp` and `BoolOp` are branches and BOTH sides of
            each are taken, because a severity that is only reachable on one branch is still
            emitted. A `Name` is resolved as a MODULE GLOBAL only — that is what covers `NOT_RUN`,
            and it is also the limit: a name bound inside a function returns `[]`.
            """
            if isinstance(head, ast.Constant):
                return [head.value] if isinstance(head.value, str) else []
            if isinstance(head, ast.Name):
                value = getattr(toolchain, head.id, None)
                return [value] if isinstance(value, str) else []
            if isinstance(head, ast.IfExp):
                return head_severities(head.body) + head_severities(head.orelse)
            if isinstance(head, ast.BoolOp):
                return [s for value in head.values for s in head_severities(value)]
            return []

        def record(node: ast.AST) -> None:
            if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
                return
            for severity in head_severities(node.elts[0]):
                emitted.setdefault(severity, node.lineno)

        for node in ast.walk(tree):
            # `<list>.append((severity, detail))`
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append" and node.args):
                record(node.args[0])
            # ANY list literal, wherever it sits. This is what reaches `return [], [(NOT_RUN, …)]`
            # — a list nested inside a returned tuple — and `out += [...]`, both of which the
            # `return`-shaped matcher walked straight past.
            if isinstance(node, ast.List) and id(node) not in module_data:
                for element in node.elts:
                    record(element)

        # Guard the guard: an emission-site matcher that matched nothing would make the assertion
        # below vacuously true, which is the failure mode this whole test class exists to catch.
        # FOUR, not three. The file emits `critical`, `warn`, `info` and `not-run` today, and a
        # floor set below the real count is slack this guard hands to the next regression: at 3 a
        # matcher that stopped reaching the `info` sites would still pass here, and then find
        # nothing unranked below because it was no longer looking. The floor is only a guard while
        # it equals what the matcher currently reaches — if a severity is deliberately retired,
        # move this number down in the same commit and say which one went.
        self.assertGreaterEqual(len(emitted), 4, emitted)
        self.assertIn(toolchain.NOT_RUN, emitted,
                      "the matcher no longer reaches the not-run emission sites")
        unranked = {s: line for s, line in emitted.items() if s not in toolchain.SEVERITY_RANK}
        self.assertEqual(unranked, {}, f"emitted but unranked (visibility and blocking are both "
                                       f"undefined for these): {unranked}")


class GreenHomeMixin:
    """The one synthetic HOME that every check passes, and the runners that drive it.

    EXTRACTED FROM `PluginSurfaceTest` BY TC-47 RATHER THAN COPIED, which is that card's own
    instruction: reuse a fixture already observed green rather than reconstructing a layout. A
    second hand-built "green" HOME is a second thing that can quietly stop being green, and a
    tracking test whose baseline is not actually clean measures its own scaffolding.
    """

    def green_home(self, tmp: Path) -> Path:
        """A synthetic HOME on which every check passes. Asserted green here, not assumed.

        Built by satisfying each existing check the way the pre-TC-41 `--json` drift fixture
        already did — mirrored skills, mirrored instruction sections, a sync stub that exits 0 —
        plus the two inputs the plugin check needs: an importable persona source and a Codex
        config. The assertion at the end is the positive control for every absence claim made by a
        test that mutates this baseline.
        """
        home = tmp / "home"
        claude, codex = home / ".claude" / "skills", home / ".codex" / "skills"
        for name in toolchain.MIRRORED_SKILLS:
            (claude / name).mkdir(parents=True)
            (claude / name / "SKILL.md").write_text("same\n", encoding="utf-8")
        plant_persona_source(claude)
        shared = "\n".join(start + "\nx\n" + end for start, end in toolchain.MIRRORED)
        (home / ".claude" / "CLAUDE.md").write_text(shared, encoding="utf-8")
        plant_codex_config(home)
        (home / ".codex" / "AGENTS.md").write_text(shared, encoding="utf-8")
        # Mirror AFTER planting, or the persona stub is itself Codex-mirror drift.
        for name in toolchain.MIRRORED_SKILLS:
            shutil.copytree(claude / name, codex / name)
        # TC-47. The tracking sweep asks git whether each skill directory would be committed, and a
        # HOME that is not a work tree can only answer NOT-RUN — which would deny this baseline its
        # clean verdict and make every test below measure the missing repository instead of the
        # thing it planted. The work tree IS part of the green baseline now.
        git_init(home / ".claude")

        rc, payload, err = self.run_json(home)
        self.assertEqual(rc, 0, err)
        self.assertEqual(payload["status"], "clean", payload["summary"])
        return home

    def green_home_with_declared_vendor(self, tmp: Path) -> tuple[Path, str]:
        """The green baseline plus one DECLARED VENDOR skill, ignored the way the real one is.

        THE STATE NO OTHER FIXTURE REACHES, and the gap is why a false clean line survived a round
        of review: `vendor_tree` calls `check_tracking()` directly and never renders a summary, and
        `green_home` has no vendor, so nothing in the suite had ever seen a CLEAN RUN whose tracking
        sweep answered `ignored` for something. That is the ordinary state of any machine with a
        vendor skill installed, and it is precisely the state the clean sentence describes.
        Still asserted green after the mutation: an exempt vendor must not cost the run its clean
        verdict, or every assertion made from here would be measuring a finding instead.
        """
        home = self.green_home(tmp)
        vendor = sorted(toolchain.DECLARED_VENDOR_SKILLS)[0]
        skills = home / ".claude" / "skills"
        (skills / vendor).mkdir(parents=True)
        (skills / vendor / "SKILL.md").write_text("vendor\n", encoding="utf-8")
        (skills / ".gitignore").write_text(f"/{vendor}\n", encoding="utf-8")

        rc, payload, err = self.run_json(home)
        self.assertEqual(rc, 0, err)
        self.assertEqual(payload["status"], "clean", payload["summary"])
        self.assertEqual(payload["tracking"]["claude"]["results"].get(vendor), "ignored",
                         "fixture did not reproduce the ignored-vendor state it exists for")
        return home, vendor

    def run_json(self, home: Path, *extra: str):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_toolchain.py"), "--json", *extra],
            capture_output=True, text=True, env={**dict(os.environ), "HOME": str(home)})
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None), r.stdout + r.stderr

    def run_human(self, home: Path):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_toolchain.py")],
            capture_output=True, text=True, env={**dict(os.environ), "HOME": str(home)})
        return r.returncode, r.stdout

    def install(self, home: Path, name: str, **kw) -> Path:
        """Plant a plugin under ~/.claude/plugins and assert the tree actually changed."""
        root = home / ".claude" / "plugins"
        before = sorted(p.name for p in root.iterdir()) if root.is_dir() else []
        root.mkdir(parents=True, exist_ok=True)
        planted = plant_plugin(root, name, **kw)
        self.assertNotEqual(sorted(p.name for p in root.iterdir()), before,
                            "fixture did not mutate: no plugin was planted")
        return planted


class PluginSurfaceTest(GreenHomeMixin, unittest.TestCase):
    """TC-41. The plugin surface: enumerated, classified, never approved.

    THE CARD'S DEFECT, in one sentence: a plugin shipping `agents/reviewer.md` replaces a judging
    persona from a directory that the roster, the judging allow-list and `sync_personas.py --check`
    all do not look at. Everything below either proves that is now seen, or proves that a failed
    look cannot be mistaken for a clear one.

    Every case runs against a GREEN BASELINE built by `green_home` and then mutated, and every
    mutation is asserted to have taken effect before anything is concluded from it — a fixture that
    silently failed to apply produces a pass that proves nothing.
    """

    # ---- the test the card exists for -----------------------------------------------------

    def test_a_plugin_agent_shadowing_a_judging_persona_is_a_finding(self) -> None:
        """THE ONE. `agents/reviewer.md` in an enabled plugin must name the persona it shadows.

        `reviewer` is on the fixture's judging set, so the finding must say so: shadowing a judge
        is not merely a duplicate name, it is the no-edit guarantee being replaced by a file the
        roster does not govern.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "rogue", agents=["reviewer"])
            enable_plugins(home, {"rogue@fixture": root})

            rc, payload, err = self.run_json(home)

            self.assertEqual(rc, 1, err)
            hits = [f for f in payload["findings"] if "`reviewer`" in f["detail"]]
            self.assertEqual(len(hits), 1, payload["findings"])
            self.assertEqual(hits[0]["severity"], "critical", hits[0])
            self.assertIn("SHADOWS", hits[0]["detail"])
            self.assertIn("JUDGING persona", hits[0]["detail"])
            self.assertIn("MACHINE-GLOBAL", hits[0]["detail"])
            # ...and the enumeration itself is actionable without reading that prose.
            item = payload["plugins"]["claude"]["items"][0]
            self.assertEqual((item["name"], item["enablement"], item["agents"], item["tier"]),
                             ("rogue", "enabled", ["reviewer"], "agent"))

    def test_a_shadowing_plugin_that_is_not_enabled_is_a_warning_not_a_critical(self) -> None:
        """Severity tracks enablement, because only an enabled plugin executes.

        Still a FINDING — the invariant says so, and precedence is one `/plugin install` away from
        mattering — but not the exit-gating severity, or a downloaded marketplace catalogue would
        fail every session start on a machine where nothing is enabled.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            self.install(home, "rogue", agents=["reviewer"])

            rc, payload, err = self.run_json(home)

            hits = [f for f in payload["findings"] if "`reviewer`" in f["detail"]]
            self.assertEqual([f["severity"] for f in hits], ["warn"], payload["findings"])
            self.assertIn("would SHADOW", hits[0]["detail"])
            self.assertEqual(rc, 0, err)  # warn is visible, not fatal — TC-06
            self.assertEqual(payload["status"], "findings")
            self.assertNotIn("clean", payload["summary"])

    def test_the_same_agent_name_from_two_plugins_is_reported(self) -> None:
        """Undefined precedence between two packages. True of the real catalogue today."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            self.install(home, "alpha", agents=["code-reviewer"])
            self.install(home, "beta", agents=["code-reviewer"])

            rc, payload, err = self.run_json(home)

            hits = [f for f in payload["findings"] if "`code-reviewer`" in f["detail"]]
            self.assertEqual(len(hits), 1, payload["findings"])
            self.assertIn("registered by 2 file(s) in 2 plugins", hits[0]["detail"])
            self.assertIn("`alpha`", hits[0]["detail"])
            self.assertIn("`beta`", hits[0]["detail"])
            self.assertIn("precedence", hits[0]["detail"])
            self.assertEqual(rc, 0, err)

    def test_the_shadow_is_the_frontmatter_name_not_the_filename(self) -> None:
        """M3. The harness resolves a subagent by frontmatter `name:`; the stem is only where the
        two usually agree.

        Baseline and mutation together: `agents/helper.md` declaring `name: helper` collides with
        nothing, and the SAME file declaring `name: reviewer` is the card's defect one field over.
        On this machine all 31 real plugin agent files match their stem, so this is a convention the
        check must not depend on.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "sneaky", agents=["helper"])
            enable_plugins(home, {"sneaky@fixture": root})

            # BASELINE: stem and frontmatter agree; nothing is shadowed.
            base_rc, base_payload, err = self.run_json(home)
            self.assertEqual(base_rc, 0, err)
            self.assertEqual(base_payload["plugins"]["claude"]["items"][0]["agents"], ["helper"])
            self.assertNotIn("SHADOWS", json.dumps(base_payload["findings"]))

            # MUTATION: same filename, different declared name.
            agent = root / "agents" / "helper.md"
            original = agent.read_bytes()
            agent.write_text("---\nname: reviewer\ndescription: fixture\n---\nx\n", encoding="utf-8")
            self.assertNotEqual(agent.read_bytes(), original, "fixture did not mutate")

            rc, payload, err = self.run_json(home)

            item = payload["plugins"]["claude"]["items"][0]
            self.assertEqual(item["agents"], ["reviewer"], "resolved by stem, not frontmatter")
            self.assertEqual(item["agent_files"], {"reviewer": ["helper.md"]})
            shadow = [f for f in payload["findings"] if "SHADOWS" in f["detail"]]
            self.assertEqual(len(shadow), 1, payload["findings"])
            self.assertEqual(shadow[0]["severity"], "critical")
            # The report must name BOTH: the name that resolves and the file it came from.
            self.assertIn("`reviewer`", shadow[0]["detail"])
            self.assertIn("agents/helper.md", shadow[0]["detail"])
            self.assertEqual(rc, 1, err)

    def test_two_files_in_one_plugin_registering_one_name_are_both_reported(self) -> None:
        """L-5. `agent_files` was `name -> file`, so the loser of an INTRA-plugin collision was
        named nowhere: `agents` one short, the "adds N agent(s)" line undercounting, and no
        duplicate finding, because the cross-plugin check counts plugin ITEMS and one plugin is one
        item. The enumeration was silently short in the one directory this card exists for.

        Baseline and mutation together: two files registering DIFFERENT names, then the same name.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "twofer", agents=["helper", "other"])
            enable_plugins(home, {"twofer@fixture": root})

            # BASELINE: two files, two distinct names, both enumerated.
            _, base, err = self.run_json(home)
            base_item = base["plugins"]["claude"]["items"][0]
            self.assertEqual(base_item["agents"], ["helper", "other"], err)
            self.assertEqual(base_item["agent_files"],
                             {"helper": ["helper.md"], "other": ["other.md"]})

            # MUTATION: `other.md` now declares `name: helper` too.
            other = root / "agents" / "other.md"
            original = other.read_bytes()
            other.write_text("---\nname: helper\ndescription: fixture\n---\nx\n",
                             encoding="utf-8")
            self.assertNotEqual(other.read_bytes(), original, "fixture did not mutate")

            rc, payload, err = self.run_json(home)
            item = payload["plugins"]["claude"]["items"][0]

            # Both files survive under the one registered name — the collapse is gone.
            self.assertEqual(item["agent_files"], {"helper": ["helper.md", "other.md"]})
            # ...and the intra-plugin collision is a finding: the same undefined precedence as the
            # cross-plugin case, which `len(owners) > 1` could never reach.
            dup = [f for f in payload["findings"] if "`helper`" in f["detail"]]
            self.assertEqual(len(dup), 1, payload["findings"])
            self.assertIn("registered by 2 file(s) in ONE plugin", dup[0]["detail"])
            self.assertIn("agents/helper.md", dup[0]["detail"])
            self.assertIn("agents/other.md", dup[0]["detail"])
            self.assertEqual(rc, 0, err)

    def test_an_intra_plugin_collision_on_a_persona_names_both_files(self) -> None:
        """The same collapse where it costs something: the shadow finding named ONE file while two
        were shadowing, in the directory nothing else looks at."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "rogue", agents=["reviewer", "helper"],
                                agent_frontmatter={"helper": "reviewer"})
            enable_plugins(home, {"rogue@fixture": root})

            rc, payload, err = self.run_json(home)

            item = payload["plugins"]["claude"]["items"][0]
            self.assertEqual(item["agent_files"], {"reviewer": ["helper.md", "reviewer.md"]})
            shadow = [f for f in payload["findings"] if "SHADOW" in f["detail"]]
            self.assertEqual(len(shadow), 1, payload["findings"])
            self.assertEqual(shadow[0]["severity"], "critical")
            self.assertIn("agents/helper.md", shadow[0]["detail"])
            self.assertIn("agents/reviewer.md", shadow[0]["detail"])
            self.assertEqual(rc, 1, err)

    def test_a_judging_name_outside_the_base_pool_is_still_protected(self) -> None:
        """L7. The invariant is "base name OR judging roster member", and the nesting that makes
        those the same set today is a property of the pool, not a rule this file may assume."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            # `reviewer` is on the judging roster and deliberately NOT in the base pool.
            plant_persona_source(home / ".claude" / "skills",
                                 base=("developer",), judging=("reviewer",))
            root = self.install(home, "rogue", agents=["reviewer"])
            enable_plugins(home, {"rogue@fixture": root})

            rc, payload, err = self.run_json(home)

            shadow = [f for f in payload["findings"] if "SHADOWS" in f["detail"]]
            self.assertEqual(len(shadow), 1, payload["findings"])
            self.assertIn("JUDGING persona", shadow[0]["detail"])
            self.assertEqual(rc, 1, err)

    # ---- the three tiers ------------------------------------------------------------------

    def test_a_hook_plugin_is_loud_and_a_skills_only_plugin_is_quiet(self) -> None:
        """Distinguishable in the human output AND in --json, which are different requirements.

        In the report the hook plugin is a `warn` line and the inert one is not a finding at all —
        so the inert one must still be VISIBLE, or "reported quietly" would have become "not
        reported". The census line is what carries it, and this asserts both halves.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            loud = self.install(home, "loud", hook_events=["SessionStart", "UserPromptSubmit"])
            quiet = self.install(home, "quiet", skills=True, commands=True)
            enable_plugins(home, {"loud@fixture": loud, "quiet@fixture": quiet})

            rc, payload, err = self.run_json(home)
            _, human = self.run_human(home)

            tiers = {i["name"]: i["tier"] for i in payload["plugins"]["claude"]["items"]}
            self.assertEqual(tiers, {"loud": "hook", "quiet": "inert"})
            self.assertEqual(payload["plugins"]["claude"]["tiers"],
                             {"hook": 1, "agent": 0, "inert": 1})

            details = " ".join(f["detail"] for f in payload["findings"])
            self.assertIn("ENABLED plugin `loud` binds 2 lifecycle hook event(s)", details)
            self.assertIn("SessionStart, UserPromptSubmit", details)
            # The quiet one is in the census and in --json, and in no finding.
            self.assertNotIn("`quiet`", details)
            self.assertIn("2 on disk, 2 enabled", human)
            self.assertIn("1 ship hooks", human)
            self.assertIn("1 skills/commands only", human)
            self.assertEqual(rc, 0, err)

    def test_hook_classification_names_the_event_and_not_the_command(self) -> None:
        """Enumerate THAT it binds, and which event. Never what the code does.

        Reading intent out of third-party script bodies is out of scope and would be a false
        assurance; this pins that the command string never reaches the report.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "loud", hook_events=["PreToolUse"])
            enable_plugins(home, {"loud@fixture": root})

            _, payload, _ = self.run_json(home)
            item = payload["plugins"]["claude"]["items"][0]

            self.assertEqual(item["hook_events"], ["PreToolUse"])
            self.assertNotIn(HOOK_COMMAND_SENTINEL, json.dumps(payload),
                             "the hook body reached the report")

    def test_hooks_declared_by_manifest_path_are_found(self) -> None:
        """M5. A fail-open in the LOUDEST tier: the manifest may declare `"hooks": "./path.json"`
        — the form a sibling `.cursor-plugin/plugin.json` uses on this machine — and reading only
        `hooks/hooks.json` classified such a plugin `inert`, emitted no warn, and counted it in the
        skills-only census.

        Baseline and mutation together: the same plugin with the conventional path is `hook`, so
        the mutation isolates the declaration form and nothing else.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            conventional = self.install(home, "byconvention", hook_events=["SessionStart"])
            declared = self.install(home, "bymanifest", hook_events=["SessionStart"],
                                    hooks_via_manifest="./hooks/hooks-cursor.json")
            self.assertFalse((declared / "hooks" / "hooks.json").exists(), "fixture did not mutate")
            enable_plugins(home, {"a@fixture": conventional, "b@fixture": declared})

            rc, payload, err = self.run_json(home)

            tiers = {i["name"]: i["tier"] for i in payload["plugins"]["claude"]["items"]}
            self.assertEqual(tiers, {"byconvention": "hook", "bymanifest": "hook"})
            self.assertEqual(payload["plugins"]["claude"]["tiers"]["inert"], 0)
            loud = [f for f in payload["findings"] if "binds 1 lifecycle" in f["detail"]]
            self.assertEqual(len(loud), 2, payload["findings"])
            self.assertEqual(rc, 0, err)

    def test_the_two_hook_sources_are_unioned_not_ranked(self) -> None:
        """M-3. The manifest-wins rule had no source, and was wrong in a shape that exists on this
        machine: `"hooks": {}` beside a populated `hooks/hooks.json` yielded no events, no problem,
        and tier `inert` — the loudest tier silently losing its subject to a precedence rule
        invented for it.

        The union is the fail-closed direction where the harness's real precedence is unknown: it
        can over-report an event the harness ignores; it cannot miss one the harness binds.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "both", hook_events=["Stop"])
            self.assertTrue((root / "hooks" / "hooks.json").is_file())
            # The exact real-world shape: an EMPTY inline map in the manifest, beside a populated
            # conventional file. Under manifest-wins this returned [].
            manifest = root / ".claude-plugin" / "plugin.json"
            original = manifest.read_bytes()
            manifest.write_text(json.dumps({"name": "both", "hooks": {}}), encoding="utf-8")
            self.assertNotEqual(manifest.read_bytes(), original, "fixture did not mutate")
            enable_plugins(home, {"both@fixture": root})

            rc, payload, err = self.run_json(home)

            item = payload["plugins"]["claude"]["items"][0]
            self.assertEqual(item["hook_events"], ["Stop"])
            self.assertEqual(item["tier"], "hook")
            self.assertEqual(rc, 0, err)

            # ...and where the two sources name DIFFERENT events, both survive.
            manifest.write_text(json.dumps({"name": "both", "hooks": {
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "x"}]}]}}),
                encoding="utf-8")
            _, payload, err = self.run_json(home)
            self.assertEqual(payload["plugins"]["claude"]["items"][0]["hook_events"],
                             ["Stop", "UserPromptSubmit"], err)

    def test_a_manifest_hook_path_escaping_the_plugin_root_is_refused(self) -> None:
        """This check reads a file BECAUSE a third party named it. A declaration resolving outside
        the plugin is refused and reported, not followed."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "escapee")
            manifest = root / ".claude-plugin" / "plugin.json"
            manifest.write_text(json.dumps({"name": "escapee", "hooks": "../../../outside.json"}),
                                encoding="utf-8")

            rc, payload, err = self.run_json(home)

            self.assertEqual(rc, 2, err)
            self.assertIn("resolves OUTSIDE the plugin root",
                          " ".join(f["detail"] for f in payload["findings"]))

    def test_the_codex_scan_reads_commented_lines_and_refuses_dotted_keys(self) -> None:
        """M6. The scan could UNDER-report while its docstring claimed it could only over-report,
        and the real config.toml is hand-edited and already carries `#` markers."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            config = home / ".codex" / "config.toml"

            # Comments on both the header and the value. Previously: silently dropped.
            config.write_text('# a note\n[plugins."x@mp"]  # trailing\nenabled = true  # yes\n\n'
                              '[plugins."y@mp"]\nenabled = false\n', encoding="utf-8")
            rc, payload, err = self.run_json(home)
            self.assertEqual(payload["plugins"]["codex"]["enabled_keys"], ["x@mp"], err)
            self.assertTrue(payload["plugins"]["codex"]["enumerated"])
            self.assertEqual(rc, 0, err)

            # A dotted key is not parsed — and now says so rather than dropping the plugin.
            original = config.read_bytes()
            config.write_text('plugins."z@mp".enabled = true\n', encoding="utf-8")
            self.assertNotEqual(config.read_bytes(), original, "fixture did not mutate")

            rc, payload, err = self.run_json(home)

            self.assertEqual(rc, 2, err)
            self.assertFalse(payload["plugins"]["codex"]["enumerated"])
            self.assertIn("a key this scanner does not parse",
                          " ".join(f["detail"] for f in payload["findings"]))

    def test_the_codex_scan_detects_the_remaining_unparsed_forms(self) -> None:
        """M-4. Three more silently-dropped shapes, plus a permanent unclearable exit 2.

        Each is asserted against the same green baseline, so what changed is one construct.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            config = home / ".codex" / "config.toml"

            # [plugins_cache] shares a prefix with the plugins table and is unrelated. Under the
            # prefix match it produced exit 2 that no action could ever clear.
            config.write_text('[plugins_cache]\nttl = 30\n\n[plugins."x@mp"]\nenabled = true\n',
                              encoding="utf-8")
            rc, payload, err = self.run_json(home)
            self.assertEqual(rc, 0, err)
            self.assertTrue(payload["plugins"]["codex"]["enumerated"])
            self.assertEqual(payload["plugins"]["codex"]["enabled_keys"], ["x@mp"])

            # The forms that ARE unparsed must be detected, never silently dropped.
            #
            # EVERY LABEL HERE IS ASSERTED AGAINST ITS BODY. The first case used to be labelled
            # "top-level inline table" while writing `[plugins]\n"z@mp" = { … }` — a SECTION
            # HEADER, which the header path already catches. The case the label claimed was
            # therefore untested and a genuine top-level inline table still dropped a plugin
            # silently, while a reader auditing coverage would grep the label, find it, and stop.
            # That is worse than no test. The guard below is what makes the label load-bearing:
            # a body that does not contain the construct its label names fails before it is run.
            for label, must_contain, body in (
                ("top-level inline table",
                 'plugins = {', 'plugins = { "z@mp" = { enabled = true } }\n'),
                ("[plugins] section with inline members",
                 '[plugins]\n', '[plugins]\n"z@mp" = { enabled = true }\n'),
                ("quoted dotted key",
                 '"plugins".', '"plugins"."z@mp".enabled = true\n'),
                ("bare dotted key",
                 'plugins."', 'plugins."z@mp".enabled = true\n'),
            ):
                self.assertIn(must_contain, body,
                              f"{label}: the fixture body does not contain the construct its "
                              f"label names — the label would document coverage that is absent")
                original = config.read_bytes()
                config.write_text(body, encoding="utf-8")
                self.assertNotEqual(config.read_bytes(), original,
                                    f"{label}: fixture did not mutate")

                rc, payload, err = self.run_json(home)

                self.assertEqual(rc, 2, f"{label}: {err}")
                self.assertFalse(payload["plugins"]["codex"]["enumerated"], label)
                self.assertIn("cannot be trusted",
                              " ".join(f["detail"] for f in payload["findings"]), label)

    def test_an_unreadable_agent_file_is_a_problem_not_a_stem_guess(self) -> None:
        """L-6. The `except OSError` in `registered_agent_name` was real in source and exercised by
        nothing — delete it and the suite stayed green, which makes it a claim rather than a
        behaviour. A file whose name cannot be read may be declaring any name at all."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "opaque", agents=["helper"])
            agent = root / "agents" / "helper.md"
            self.assertTrue(agent.is_file())
            agent.chmod(0o000)
            # Restored INSIDE the block: `addCleanup` fires after TemporaryDirectory has already
            # removed the tree, and an unreadable file left behind would break its teardown.
            try:
                if os.access(agent, os.R_OK):
                    self.skipTest("cannot make a file unreadable here (running as root?)")

                rc, payload, err = self.run_json(home)

                self.assertEqual(rc, 2, err)
                self.assertIn("the name this subagent registers under is unknown",
                              " ".join(f["detail"] for f in payload["findings"]))
                self.assertFalse(payload["plugins"]["claude"]["enumerated"])
            finally:
                agent.chmod(0o644)

    # ---- could-not-run is not an empty enumeration ----------------------------------------

    def test_a_malformed_manifest_is_could_not_run_and_differs_from_an_empty_surface(self) -> None:
        """THE CONTROL. The empty case and the failed case must not produce the same output.

        Both are run here and compared directly, because "an unreadable manifest yields
        could-not-run" is only meaningful against a demonstrated clean case that the failed one
        does not resemble. Asserting the failed case alone would pass for a build that returned
        could-not-run unconditionally.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))

            # EMPTY: a plugins directory with nothing in it. Zero plugins is a real answer.
            (home / ".claude" / "plugins").mkdir(parents=True)
            empty_rc, empty, err = self.run_json(home)
            self.assertEqual(empty_rc, 0, err)
            self.assertEqual(empty["status"], "clean")
            self.assertEqual(empty["plugins"]["claude"]["count"], 0)
            self.assertTrue(empty["plugins"]["claude"]["enumerated"])
            self.assertIn("plugin surface", empty["evaluated"])

            # FAILED: one manifest that is not JSON.
            root = self.install(home, "broken")
            manifest = root / ".claude-plugin" / "plugin.json"
            original = manifest.read_bytes()
            manifest.write_bytes(b"{ this is not json")
            self.assertNotEqual(manifest.read_bytes(), original, "fixture did not mutate")

            failed_rc, failed, err = self.run_json(home)

            self.assertEqual(failed_rc, 2, err)
            self.assertEqual(failed["status"], toolchain.NOT_RUN)
            self.assertFalse(failed["plugins"]["claude"]["enumerated"])
            self.assertIn("plugin surface", [n["check"] for n in failed["not_evaluated"]])
            self.assertNotIn("plugin surface", failed["evaluated"])
            self.assertIn("NOT FULLY ENUMERATED",
                          " ".join(f["detail"] for f in failed["findings"]))
            # ...and the two are not the same output, in the fields a caller reads.
            self.assertNotEqual(empty["status"], failed["status"])
            self.assertNotEqual(empty["exit"], failed["exit"])
            self.assertNotEqual(empty["plugins"]["claude"]["enumerated"],
                                failed["plugins"]["claude"]["enumerated"])
            self.assertNotEqual(empty["summary"], failed["summary"])

    def test_a_shadow_survives_a_failure_elsewhere_in_the_same_harness(self) -> None:
        """A PRESENCE claim stays true when the list is short, and must still be reported.

        THIS TEST REPLACES ITS OWN INVERSE. The version here before asserted that a failed
        enumeration emits not-run AND NOTHING ELSE — with a `reviewer` shadow planted in the same
        fixture. It passed, which means it encoded the defect as a requirement: fixing the code
        looked like breaking the suite. "X SHADOWS a judging persona" is an observation that was
        made; a broken manifest in a DIFFERENT plugin cannot unmake it.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "rogue", agents=["reviewer"])
            enable_plugins(home, {"rogue@fixture": root})
            broken = self.install(home, "broken")
            original = (broken / ".claude-plugin" / "plugin.json").read_bytes()
            (broken / ".claude-plugin" / "plugin.json").write_bytes(b"nope")
            self.assertNotEqual((broken / ".claude-plugin" / "plugin.json").read_bytes(), original,
                                "fixture did not mutate")

            rc, payload, err = self.run_json(home)

            severities = {f["severity"] for f in payload["findings"]}
            self.assertIn(toolchain.NOT_RUN, severities)     # the short list is still declared...
            self.assertIn("critical", severities)            # ...and the shadow is still reported
            shadow = [f for f in payload["findings"] if "SHADOWS" in f["detail"]]
            self.assertEqual(len(shadow), 1, payload["findings"])
            self.assertIn("`reviewer`", shadow[0]["detail"])
            # not-run outranks: the verdict is still untrustworthy, and still exits 2.
            self.assertEqual(rc, 2, err)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)

    def test_undetermined_enablement_is_not_reported_as_not_enabled(self) -> None:
        """H-1. A two-valued flag conflated "no" with "could not tell".

        settings.json says `rogue@fixture` IS enabled; installed_plugins.json is malformed, so its
        root cannot be located — an uninstall/reinstall, or a half-written file. Baseline and
        mutation are asserted together because the whole claim is that ONE fact changed.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "rogue", agents=["reviewer"])
            enable_plugins(home, {"rogue@fixture": root})

            # BASELINE: enablement resolves. Critical, exit 1, one enabled, none unknown.
            base_rc, base, err = self.run_json(home)
            self.assertEqual(base_rc, 1, err)
            self.assertEqual(base["plugins"]["claude"]["enablement"],
                             {"enabled": 1, "not-enabled": 0, "unknown": 0})
            self.assertEqual([f["severity"] for f in base["findings"]
                              if "SHADOWS" in f["detail"]], ["critical"])

            # MUTATION: installed_plugins.json unreadable. settings.json is untouched — enablement
            # was read successfully one function earlier.
            installed = home / ".claude" / "plugins" / "installed_plugins.json"
            original = installed.read_bytes()
            installed.write_bytes(b"{ half-written")
            self.assertNotEqual(installed.read_bytes(), original, "fixture did not mutate")

            rc, payload, err = self.run_json(home)
            claude = payload["plugins"]["claude"]

            # "SHADOW", not "SHADOWS" — the two variants are worded differently and matching only
            # the critical one would make this fail on the COUNT rather than on the severity, which
            # is the thing under test.
            shadow = [f for f in payload["findings"] if "SHADOW" in f["detail"]]
            self.assertEqual(len(shadow), 1, payload["findings"])
            # CRITICAL, not warn: a consumer filtering on severity must not see a possibly-live
            # shadow of a judging persona as non-gating.
            self.assertEqual(shadow[0]["severity"], "critical", shadow[0]["detail"])
            # The presence half only. The affirmatively false absence sentence must be gone.
            self.assertIn("could NOT be determined", shadow[0]["detail"])
            self.assertNotIn("Not enabled today", shadow[0]["detail"])
            self.assertNotIn("would SHADOW", shadow[0]["detail"])
            # The object no longer contradicts itself.
            self.assertEqual(claude["enablement"],
                             {"enabled": 0, "not-enabled": 0, "unknown": 1})
            self.assertEqual(claude["enabled_keys"], ["rogue@fixture"])
            self.assertEqual(claude["unresolved_enabled_keys"], ["rogue@fixture"])
            # ...and the census says so rather than printing a bare "0 enabled".
            _, human = self.run_human(home)
            self.assertIn("0 enabled, 1 of UNDETERMINED enablement", human)
            self.assertEqual(rc, 2, err)   # not-run still outranks

            # SECOND MUTATION, and the harder one: settings.json ITSELF is unreadable, so
            # `enabled_claude_plugins` returns an EMPTY dict beside a problem and there is no
            # unresolved KEY to point at. The first fix keyed `unknown` off that key list alone, so
            # a run that could not read enablement AT ALL fell through to `not-enabled` and
            # reported every plugin on disk as determined-not-enabled — the same conflation one
            # function further out. Restore installed_plugins.json first, so this isolates
            # settings.json and nothing else.
            installed.write_bytes(original)
            settings = home / ".claude" / "settings.json"
            settings_before = settings.read_bytes()
            settings.write_bytes(b"{ not json")
            self.assertNotEqual(settings.read_bytes(), settings_before, "fixture did not mutate")

            rc, payload, err = self.run_json(home)
            claude = payload["plugins"]["claude"]

            self.assertEqual(claude["enablement"],
                             {"enabled": 0, "not-enabled": 0, "unknown": 1}, claude)
            # There is no key to list — that is exactly why the key list was the wrong trigger.
            self.assertEqual(claude["enabled_keys"], [])
            self.assertEqual(claude["unresolved_enabled_keys"], [])
            shadow = [f for f in payload["findings"] if "SHADOW" in f["detail"]]
            self.assertEqual([f["severity"] for f in shadow], ["critical"],
                             [f["detail"] for f in shadow])
            self.assertIn("could NOT be determined", shadow[0]["detail"])
            self.assertNotIn("Not enabled today", shadow[0]["detail"])
            self.assertEqual(rc, 2, err)

    def test_undetermined_enablement_still_reports_the_hook_tier(self) -> None:
        """The third absence claim was by OMISSION: the hook and agent lines were gated on
        `enabled` being true, so a plugin of undetermined enablement produced no line at all —
        the loudest tier going silent about a hook that may well be executing."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "loud", hook_events=["SessionStart"])
            enable_plugins(home, {"loud@fixture": root})
            (home / ".claude" / "plugins" / "installed_plugins.json").write_bytes(b"nope")

            rc, payload, err = self.run_json(home)

            loud = [f for f in payload["findings"] if "SessionStart" in f["detail"]]
            self.assertEqual(len(loud), 1, payload["findings"])
            self.assertEqual(loud[0]["severity"], "warn")
            self.assertIn("ENABLEMENT UNDETERMINED", loud[0]["detail"])
            self.assertEqual(rc, 2, err)

    def test_a_codex_failure_does_not_suppress_a_claude_shadow(self) -> None:
        """H1, the sequence that needed no adversary. Claude-only machine, enabled rogue plugin.

        Baseline and mutation are run together here, because the proof is that the shadow finding
        is IDENTICAL either side of a Codex failure — not merely that it is present in one run.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "rogue", agents=["reviewer"])
            enable_plugins(home, {"rogue@fixture": root})

            # BASELINE: Codex config present. The shadow is critical, exit 1.
            base_rc, base_payload, err = self.run_json(home)
            base_shadow = [f for f in base_payload["findings"] if "SHADOWS" in f["detail"]]
            self.assertEqual(base_rc, 1, err)
            self.assertEqual(len(base_shadow), 1, base_payload["findings"])

            # MUTATION: no ~/.codex/config.toml at all.
            config = home / ".codex" / "config.toml"
            self.assertTrue(config.is_file())
            config.unlink()
            self.assertFalse(config.is_file(), "fixture did not mutate")

            rc, payload, err = self.run_json(home)

            # The Codex half is untrustworthy and says so...
            self.assertFalse(payload["plugins"]["codex"]["enumerated"])
            self.assertIn("unknown rather than empty",
                          " ".join(f["detail"] for f in payload["findings"]))
            self.assertEqual(rc, 2, err)
            # ...the Claude half is not, which is M4...
            self.assertTrue(payload["plugins"]["claude"]["enumerated"])
            # ...and the shadow finding is byte-identical to the baseline's.
            self.assertEqual([f["detail"] for f in payload["findings"] if "SHADOWS" in f["detail"]],
                             [base_shadow[0]["detail"]])

    def test_a_missing_persona_source_is_could_not_run(self) -> None:
        """No names, no cross-check. An enumeration that skipped the cross-check would report a
        clear result having compared a plugin agent list against nothing at all."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            self.install(home, "rogue", agents=["reviewer"])
            sync = home / ".claude" / "skills" / "agent-personas" / "scripts" / "sync_personas.py"
            self.assertTrue(sync.is_file())
            sync.unlink()

            rc, payload, err = self.run_json(home)

            self.assertEqual(rc, 2, err)
            self.assertIn("no plugin agent name was cross-checked",
                          " ".join(f["detail"] for f in payload["findings"]))

    def test_an_empty_persona_name_set_is_could_not_run(self) -> None:
        """An empty set collides with nothing, so it would make the cross-check vacuously clear."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            plant_persona_source(home / ".claude" / "skills", base=(), judging=())

            rc, payload, err = self.run_json(home)

            self.assertEqual(rc, 2, err)
            self.assertIn("EMPTY persona or judging name set",
                          " ".join(f["detail"] for f in payload["findings"]))

    def test_a_persona_source_that_exits_on_import_does_not_kill_the_run(self) -> None:
        """Observed during TC-41: `exec_module` on a body calling `sys.exit()` raises SystemExit,
        which is a BaseException — uncaught it terminated the process with an EMPTY stdout, so a
        `--json` caller got no object at all and the three-state contract was simply gone."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            sync = home / ".claude" / "skills" / "agent-personas" / "scripts" / "sync_personas.py"
            sync.write_text("import sys; sys.exit(0)\n", encoding="utf-8")

            rc, payload, err = self.run_json(home)

            self.assertIsNotNone(payload, f"stdout was empty; the process died: {err}")
            self.assertEqual(rc, 2, err)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)

    def test_the_census_marks_an_incomplete_enumeration(self) -> None:
        """L9. A count from an enumeration that did not finish is a floor, not a census, and each
        half is marked independently because after the H1 partition each can fail alone."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            self.install(home, "ok", skills=True)

            _, clean_human = self.run_human(home)
            self.assertIn("Claude 1 on disk", clean_human)
            self.assertNotIn("INCOMPLETE", clean_human)

            (home / ".codex" / "config.toml").unlink()
            _, human = self.run_human(home)

            # Codex is marked, Claude is not — the partition, visible in the human report.
            self.assertIn("Codex (INCOMPLETE — at least) 0 enabled", human)
            self.assertIn("Claude 1 on disk", human)
            self.assertNotIn("Claude (INCOMPLETE", human)

    def test_the_clean_phrase_qualifies_its_absence_claim_to_the_claude_side(self) -> None:
        """L-7. The L8 shortening removed the only wording on the summary line that qualified an
        unqualified absence claim — and the L8 test then pinned the removal.

        `CODEX_ASYMMETRY` says in as many words that whether a Codex plugin shadows a persona is
        "UNKNOWN, not known to be false", while the same summary line asserted, flat, "no plugin
        agent shadows a base persona". Shortening the notice was right; the residue is that what
        replaced it no longer says the SHADOW question specifically is open. The qualifier belongs
        on the claim, not in the exclusion — which keeps the summary short AND true.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            _, payload, err = self.run_json(home)

            self.assertEqual(payload["status"], "clean", err)
            summary = payload["summary"]
            self.assertIn("no CLAUDE plugin agent shadows a base persona", summary)
            self.assertIn("the Codex side was enumerated by name only and not classified", summary)
            # Positively above, negatively here: a rewording that dropped the qualifier again would
            # still contain the qualified substring's neighbours, so absence is asserted too.
            self.assertNotIn("; no plugin agent shadows", summary)

    def test_the_stem_fallback_is_not_claimed_to_be_the_harness_behaviour(self) -> None:
        """L-9. An unsourced factual claim about another system, in the same declarative register
        as the measured claim beside it, where a reader cannot tell the two apart.

        `hook_events` was rewritten this milestone specifically to stop doing that; the adjacent
        function still did. Structural rather than behavioural on purpose — the defect IS the
        wording, and there is no observable behaviour to pin because the loader is not reachable
        from here. The behaviour itself (stem fallback) is pinned by
        `test_the_shadow_is_the_frontmatter_name_not_the_filename`.
        """
        source = (SCRIPTS / "check_toolchain.py").read_text(encoding="utf-8")
        # Collapsed, because the sentence is wrapped across lines and a newline-sensitive match
        # would fail on a reflow rather than on the claim coming back.
        doc = " ".join(toolchain.registered_agent_name.__doc__.split())

        # `assertFalse` with a short message, not `assertNotIn`: the latter renders the whole
        # 1600-line file into the failure output, which buries the one sentence at issue.
        self.assertFalse("which is the harness's own fallback" in source,
                         "check_toolchain.py again asserts the harness's fallback behaviour as "
                         "fact; that is not observable from this file")
        self.assertIn("THIS CHECK'S CHOICE IN THE ABSENCE OF A DECLARED NAME", doc)
        self.assertIn("NOT established here", doc)
        # ...and it still says which way it errs, or the downgrade would have removed information.
        self.assertIn("OVER-reports", doc)

    def test_the_exclusion_notice_on_the_summary_line_is_short(self) -> None:
        """L8. `Run.summary` renders every exclusion inline, so the full asymmetry paragraph rode on
        every summary line this tool printed — including the clean one, at every session start, with
        no action that could clear it. The paragraph belongs in --json.

        SPLIT ON THE PLUGIN EXCLUSION BY NAME, not on `"1 excluded"`. The count moved the moment
        TC-47 declared a second standing exclusion, and a split on the count would have raised
        IndexError — or, had it been written defensively, silently stopped asserting anything. A
        guard defeated by the next change is the shape this whole class is about; the generic rule
        over every exclusion lives in `TrackedContentTest`."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            _, payload, _ = self.run_json(home)

            self.assertEqual(payload["status"], "clean")
            # The clause this exclusion contributes, isolated by its own name — the rest of the
            # summary is the clean line and the other exclusions, and is not this test's subject.
            entry, = [e for e in payload["excluded"] if e["name"] == "Codex plugin classification"]
            clause = f"{entry['name']} ({entry['why']})"
            self.assertIn(clause, payload["summary"])
            self.assertLess(len(clause), 120, clause)
            self.assertNotIn("UNKNOWN, not known to be false", payload["summary"])
            # ...and the full text is still available where a consumer reads it deliberately.
            self.assertIn("UNKNOWN, not known to be false",
                          payload["plugins"]["codex"]["why_not_classified"])

    # ---- no second copy of the roster, and no conforming set ------------------------------

    @reaches_home(
        "READS THE REAL MACHINE, and the property under test is exactly that: the checker holds no "
        "second copy of the roster. A synthetic `sync_personas.py` could not tell reading the "
        "source of truth apart from reading a literal that happens to match it. Skips when "
        "`toolchain.SYNC` is absent, which is what a replica sees.")
    def test_persona_names_come_from_sync_personas(self) -> None:
        """The names are READ, not copied. Asserted against the real module, on purpose.

        This is the one case here that touches the real `~/.claude`, because the property under
        test is precisely that this file holds no second copy of the roster — and a synthetic
        stub could not tell the difference between reading the source of truth and reading a
        literal that happens to match it.
        """
        if not toolchain.SYNC.is_file():
            self.skipTest(f"no persona source at {toolchain.SYNC}")
        real = load_module("_sync_personas_source_of_truth", toolchain.SYNC)

        base, judging, why = toolchain.persona_names()

        self.assertIsNone(why)
        self.assertEqual(base, frozenset(real.BASE_PERSONA_NAMES))
        self.assertEqual(judging, frozenset(real.JUDGING_PERSONA_NAMES))
        self.assertTrue(judging <= base)
        # A literal copy of either set anywhere in the checker is the drift this forbids.
        source = (SCRIPTS / "check_toolchain.py").read_text(encoding="utf-8")
        for name in sorted(base):
            self.assertNotIn(f'"{name}"', source,
                             f"`{name}` appears as a literal in check_toolchain.py — the persona "
                             f"names must be read from sync_personas.py, never copied")

    # Every string comparison the plugin surface performs, and why each one is not an approval.
    # THE RECORD IS THE MECHANISM. A new comparison anywhere in the plugin call graph fails the test
    # below until it is written here with a reason, which puts the question "is this an allow-list?"
    # in front of whoever reviews that diff. Adding a row is cheap and deliberate; adding one
    # silently is impossible.
    NAME_COMPARISON_RECORD = {
        ("check_plugins", "in", "protected"):
            "the persona names, READ from sync_personas.py. The only legitimate name comparison "
            "here, and its subject is our roster rather than a plugin.",
        ("check_plugins", "in", "judging"):
            "same source; selects the wording of the finding, not whether one is emitted.",
        ("plugin_roots", "in", "PLUGIN_WALK_PRUNE"):
            "DIRECTORY names pruned from the walk (node_modules/.git/__pycache__). Not plugin "
            "identity — and this is the exact module-level-frozenset idiom a future allow-list "
            "would most plausibly copy, which is why it is recorded rather than exempted.",
        ("plugin_surface", "in", "enabled_roots"):
            "resolved filesystem paths, not names.",
        ("plugin_surface", "in", "seen"):
            "resolved filesystem paths, not names.",
        ("codex_plugin_keys", "startswith", "#"): "TOML comment syntax.",
        ("codex_plugin_keys", "startswith", "["): "TOML section syntax.",
        ("codex_plugin_keys", "startswith", '[plugins."'): "TOML section syntax.",
        ("codex_plugin_keys", "startswith", "enabled="): "TOML key syntax.",
        ("codex_plugin_keys", "eq", "true"): "TOML boolean literal.",
        ("assigns_plugins_key", "eq", "plugins"):
            "a TOML key SEGMENT. Segment equality rather than a prefix match is what catches the "
            "top-level inline table without also catching `plugins_cache = 30`.",
        ("is_plugins_table", "eq", "plugins"):
            "a TOML table NAME. Distinguishes the plugins table from [plugins_cache], which the "
            "prefix match wrongly treated as an unparseable plugin section.",
        ("is_plugins_table", "startswith", "plugins."): "TOML table name.",
        ("is_plugins_table", "startswith", '"plugins"'): "TOML quoted table name.",
        ("check_plugins", "eq", "enabled"):
            "an ENABLEMENT STATE, not a plugin name — three-valued per H-1.",
        ("check_plugins", "eq", "unknown"): "an enablement state.",
        ("check_plugins", "eq", "not-enabled"): "an enablement state.",
        ("plugin_surface", "noteq", "enabled"):
            "an enablement state; orders the items list so enabled plugins sort first.",
        ("worst_enablement", "in", "states"):
            "the enablement states observed among one name's owners; not plugin names.",
        ("hook_events", "startswith", "<computed>"):
            "path containment fallback for Python 3.8 (`Path.is_relative_to` is 3.9+).",
        ("registered_agent_name", "noteq", "---"): "YAML frontmatter delimiter.",
        ("registered_agent_name", "eq", "---"): "YAML frontmatter delimiter.",
        ("registered_agent_name", "startswith", "name:"): "YAML frontmatter key.",
    }

    def plugin_call_graph(self, tree: ast.AST) -> dict:
        """Every module function reachable from `check_plugins`, by direct call.

        DERIVED, NOT LISTED, and that is the fix for the largest hole in the previous version of
        this rule: it named three functions, so `plugin_roots` — the natural place to filter plugins
        by name — was outside it, and so was any helper added later. Reachability moves with the
        code.
        """
        functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        reached: set[str] = set()
        pending = ["check_plugins"]
        while pending:
            name = pending.pop()
            if name in reached or name not in functions:
                continue
            reached.add(name)
            pending += [c.func.id for c in ast.walk(functions[name])
                        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                        and c.func.id in functions]
        return {name: functions[name] for name in reached}

    def name_comparison_sites(self, tree: ast.AST):
        """`(descriptors, literal_collection_offences)` over the whole plugin call graph.

        THREE SHAPES, AND EXACTLY THREE. The previous rule matched only the first and therefore
        matched NOTHING at all in this file — `def check_plugins(): return {}, [], []` passed it —
        so widening was the fix. But "every comparison" is not what this enumerates and claiming it
        would stop the next reviewer looking, which is the more expensive failure:

          COVERED
            `x in <thing>` / `not in`     membership, including against a module-level frozenset
            `x == "literal"` / `!=`       equality against a string constant
            `.startswith(...)` / `.endswith(...)`   prefix matching

          NOT COVERED, and a name filter written any of these ways passes silently
            a regex — `ALLOWED_RE.match(name)`
            set algebra — `set(names) & ALLOWED`, `names - DENIED`
            a dict or mapping lookup used as membership — `ALLOWED.get(name)`
            a helper in another module, or anything the call-graph walk cannot see through
              (a call through a variable, a method, or `getattr`)
            any comparison against a value computed at runtime rather than written here

        This is a TRIPWIRE ON THE OBVIOUS WAYS, not a semantic analyser. It exists so that the
        cheapest and most likely reintroduction — a literal or module-level name list — cannot land
        unnoticed. It is not evidence that no allow-list exists.
        """
        descriptors: set[tuple[str, str, str]] = set()
        offences: list[str] = []
        literal_call = ("set", "frozenset", "list", "tuple", "dict")
        for fname, node in sorted(self.plugin_call_graph(tree).items()):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Compare):
                    for op, right in zip(sub.ops, sub.comparators):
                        if isinstance(op, (ast.In, ast.NotIn)):
                            if isinstance(right, (ast.Set, ast.List, ast.Tuple, ast.Dict)) or (
                                    isinstance(right, ast.Call)
                                    and isinstance(right.func, ast.Name)
                                    and right.func.id in literal_call):
                                offences.append(f"{fname}:{sub.lineno} membership test against an "
                                                f"inline literal collection")
                                continue
                            key = right.id if isinstance(right, ast.Name) else "<computed>"
                            descriptors.add((fname, "in", key))
                        elif isinstance(op, (ast.Eq, ast.NotEq)):
                            for side in (sub.left, right):
                                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                                    descriptors.add((fname,
                                                     "eq" if isinstance(op, ast.Eq) else "noteq",
                                                     side.value))
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                        and sub.func.attr in ("startswith", "endswith"):
                    arg = sub.args[0] if sub.args else None
                    key = arg.value if isinstance(arg, ast.Constant) \
                        and isinstance(arg.value, str) else "<computed>"
                    descriptors.add((fname, sub.func.attr, key))
        return descriptors, offences

    def test_no_plugin_is_approved_or_rejected_by_name(self) -> None:
        """THERE IS NO CONFORMING SET. A named allow- or deny-list here would be wrong on the first
        new plugin, and the founder would learn to skip the report.

        WHAT THIS CAN AND CANNOT ASSERT, stated because the difference is the whole value.

        ASSERTED: every comparison OF THE THREE SHAPES `name_comparison_sites` enumerates, within
        the call graph reachable from `check_plugins`, is either refused (an inline literal
        collection) or recorded in `NAME_COMPARISON_RECORD` — so one of those cannot be added
        without a diff a reviewer sees.

        NOT ASSERTED, two ways, and neither is a detail:
          * the three shapes are not every way to filter by name. See `name_comparison_sites` for
            the list of what passes silently — a regex, set algebra, a mapping lookup.
          * the recorded REASONS are not verified. A human writing "TOML syntax" beside a genuine
            allow-list would pass. That needs a semantics this file does not have.

        So the honest summary is: this is a tripwire on the obvious reintroductions, and its value
        is that adding one becomes visible. It is not proof that no allow-list exists.
        """
        tree = ast.parse((SCRIPTS / "check_toolchain.py").read_text(encoding="utf-8"))

        # GUARD THE GUARD, which the previous version had and its two siblings at :1399/:1462 both
        # do. It matched nothing at all in this file, so a stubbed-out `check_plugins` passed it and
        # the rule had never been observed capable of firing.
        graph = self.plugin_call_graph(tree)
        self.assertGreaterEqual(len(graph), 8, sorted(graph))
        for required in ("check_plugins", "plugin_roots", "codex_plugin_keys", "classify"):
            self.assertIn(required, graph, "the call graph no longer reaches the plugin surface")

        found, offences = self.name_comparison_sites(tree)

        self.assertEqual(offences, [], "\n  ".join(offences))
        self.assertGreaterEqual(len(found), 12, sorted(found))
        # The specific site that proves the matcher reaches a module-level frozenset compared by
        # NAME — the shape a future `PLUGIN_ALLOWED = frozenset({...})` would take, and the shape
        # the previous rule was blind to.
        self.assertIn(("plugin_roots", "in", "PLUGIN_WALK_PRUNE"), found)

        unrecorded = sorted(found - set(self.NAME_COMPARISON_RECORD))
        stale = sorted(set(self.NAME_COMPARISON_RECORD) - found)
        self.assertEqual(unrecorded, [], f"a string comparison in the plugin surface that is not "
                                         f"recorded: {unrecorded}. If it decides which plugins are "
                                         f"acceptable, this check has started approving. If it does "
                                         f"not, add it to NAME_COMPARISON_RECORD with the reason.")
        self.assertEqual(stale, [], f"recorded but gone: {stale}")

    def test_the_codex_asymmetry_is_stated_rather_than_silently_thinner(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            plant_codex_config(home, keys=["a@mp", "b@mp"])

            rc, payload, err = self.run_json(home)

            codex = payload["plugins"]["codex"]
            self.assertEqual((codex["count"], codex["enabled_keys"]), (2, ["a@mp", "b@mp"]))
            self.assertFalse(codex["classified"])
            self.assertIn("NAME ONLY", codex["why_not_classified"])
            self.assertIn("Codex plugin classification",
                          [e["name"] for e in payload["excluded"]])
            self.assertEqual(rc, 0, err)

    # ---- the real machine -----------------------------------------------------------------

    @reaches_home(
        "READS THE REAL MACHINE, as its name says: the claim is that THIS machine's plugin surface "
        "is enumerable and that no plugin here shadows a base persona. On a synthetic surface it "
        "would assert nothing about the machine anyone actually runs on. Skips when "
        "`~/.claude/plugins` is absent, which is what a replica under a redirected HOME sees.")
    def test_the_real_machine_is_enumerable_and_its_clear_result_is_a_compared_one(self) -> None:
        """The current true answer — no plugin agent shadows a base persona — must be reported as a
        result, not as the absence of a check.

        In-process rather than through the CLI, so this reads the real plugin surface without
        spawning the real `sync_personas.py --check` and its 60-second timeout.

        THE POSITIVE CONTROL IS THE POINT. An absence claim needs one more than a presence claim
        does, so this asserts the cross-check had real names on both sides before believing that
        they did not intersect — and the presence direction is proved separately by
        `test_a_plugin_agent_shadowing_a_judging_persona_is_a_finding`.
        """
        if not toolchain.CLAUDE_PLUGINS.is_dir():
            self.skipTest("no ~/.claude/plugins on this machine")
        surface, findings, excluded = toolchain.check_plugins()
        base, judging, why = toolchain.persona_names()

        self.assertIsNone(why)
        self.assertTrue(surface["claude"]["enumerated"],
                        [d for s, d in findings if s == toolchain.NOT_RUN])
        self.assertGreater(surface["claude"]["count"], 0)
        # Positive control: both sides of the intersection are non-empty and the plugin side really
        # did yield names, so "they do not intersect" is a comparison rather than a vacuum.
        shipped = {a for i in surface["claude"]["items"] for a in i["agents"]}
        self.assertGreater(len(base), 0)
        self.assertGreater(len(shipped), 0)
        self.assertEqual(sorted(shipped & base), [])
        self.assertEqual([d for s, d in findings if s == "critical"], [])
        self.assertEqual([n for n, _ in excluded], ["Codex plugin classification"])

    def test_agents_inside_a_skill_body_are_not_plugin_agents(self) -> None:
        """`<plugin>/skills/<skill>/agents/*.md` is a skill's own content, not the plugin's agent
        directory. Three such files exist on this machine and a naive `find` counts them as plugin
        agents; the harness does not load them as subagents and neither does this check."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            root = self.install(home, "skilly", skills=True)
            buried = root / "skills" / "inner" / "agents"
            buried.mkdir(parents=True)
            (buried / "reviewer.md").write_text("not a plugin agent\n", encoding="utf-8")
            self.assertTrue((buried / "reviewer.md").is_file(), "fixture did not mutate")

            rc, payload, err = self.run_json(home)

            self.assertEqual(payload["plugins"]["claude"]["items"][0]["agents"], [])
            self.assertEqual(rc, 0, err)
            self.assertEqual(payload["status"], "clean", payload["summary"])


class TrackedContentTest(GreenHomeMixin, unittest.TestCase):
    """TC-47, sweep one. Authored content that git would not commit, and nothing noticed.

    THREE MEASURED INSTANCES IN ONE MILESTONE, all the same mechanism: `docs/decisions.md`
    untracked while the renderer read it at startup; `docs/fleet-lessons.md` invisible to git for
    two days while `git status` reported clean; and an entire new skill directory whose commit
    would have silently dropped it. Each was fixed by a human remembering to add one line to an
    allow-list. Nothing asked.

    Every case mutates the SHARED green baseline and asserts the mutation landed before concluding
    anything from it, and every not-run case is asserted to produce output DIFFERENT from the clean
    one — a failure that renders identically to a pass is the defect this whole file is about.
    """

    def skills(self, home: Path) -> Path:
        return home / ".claude" / "skills"

    def write_gitignore(self, home: Path, body: str) -> Path:
        """Plant `skills/.gitignore` and assert git's answer actually changed because of it."""
        path = self.skills(home) / ".gitignore"
        before = path.read_text(encoding="utf-8") if path.is_file() else None
        path.write_text(body, encoding="utf-8")
        self.assertNotEqual(path.read_text(encoding="utf-8"), before, "fixture did not mutate")
        return path

    def allow_everything_but(self, home: Path, *extra_allowed: str) -> str:
        """The real shape of `skills/.gitignore`: `/*` and then a negation per owned entry.

        Reproduced rather than simplified, because the negation is exactly what makes
        `git check-ignore` answer the wrong question — see the trap test below.

        `!/.gitignore` IS EMITTED, and leaving it out was a real defect this fixture carried until
        TC-49's per-entry sweep reported it. The real `skills/.gitignore` names itself on its second
        negation line; a replica that omits it describes an allow-list that would not survive its
        own commit — the invisible-authored-work state, planted by accident, in the fixture for a
        test about something else. The old version excluded the name because it enumerated the
        directory it was about to write into; it is now added back explicitly.
        """
        entries = sorted(p.name for p in self.skills(home).iterdir() if p.name != ".gitignore")
        return "/*\n" + "".join(f"!/{name}\n"
                                for name in (".gitignore", *entries, *extra_allowed))

    # ---- the state that occurred three times ----------------------------------------------

    def test_an_ignored_skill_directory_is_a_finding_naming_it(self) -> None:
        """THE ONE. A skill directory git will not commit, absent from the allow-list.

        Baseline and mutation printed together: the same tree answers `clean` with the directory
        trackable and `findings` with it ignored, so the finding is attributable to the state and
        not to the fixture.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))

            # BASELINE: the new skill exists and git would commit it. Nothing to report.
            (self.skills(home) / "brand-new-skill").mkdir()
            (self.skills(home) / "brand-new-skill" / "SKILL.md").write_text("x\n", encoding="utf-8")
            base_rc, base_payload, err = self.run_json(home)
            self.assertEqual(base_rc, 0, err)
            self.assertEqual(base_payload["status"], "clean", base_payload["summary"])

            # MUTATION: one line of .gitignore, and the whole skill becomes invisible.
            self.write_gitignore(home, "/brand-new-skill\n")
            rc, payload, err = self.run_json(home)

            self.assertNotEqual(payload["summary"], base_payload["summary"],
                                "the ignored state renders identically to the trackable one")
            hits = [f for f in payload["findings"] if "brand-new-skill" in f["detail"]]
            self.assertEqual(len(hits), 1, payload["findings"])
            self.assertEqual(hits[0]["severity"], "warn", hits[0])
            self.assertIn("MACHINE-GLOBAL", hits[0]["detail"])
            self.assertIn("would NOT be committed", hits[0]["detail"])
            self.assertEqual(payload["status"], "findings")
            # TC-06: visible, not fatal. The severity ruling is argued on the card and in
            # `check_tracking`; this pins it so a later raise to critical is a deliberate diff.
            self.assertEqual(rc, 0, err)
            # ...and structured, so `project-conformance` never parses the prose above.
            self.assertEqual(payload["tracking"]["claude"]["results"]["brand-new-skill"], "ignored")

    # ---- the trap the card exists to avoid inheriting ---------------------------------------

    def test_a_path_a_negation_matched_is_reported_trackable_not_ignored(self) -> None:
        """PROOF THE CHECK-IGNORE TRAP IS ABSENT, by constructing the state it fires on.

        `git check-ignore` exits 0 both for "this path is excluded" and for "a NEGATION matched
        it", and only the second is the wanted answer. Under the real allow-list shape — `/*` then
        `!/<name>` per owned skill — EVERY owned skill is a negation match, so a check built on
        `check-ignore`'s exit code answers 0 for all of them and cannot tell the published skills
        from the dropped one.

        This test does not take that on trust. It runs `check-ignore` itself, asserts it exits 0
        with a negation as the matching rule, and then asserts this check calls the same path
        TRACKABLE. The second half plants a directory that is genuinely excluded, so the first half
        cannot pass by the check having simply stopped reporting anything.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            claude = home / ".claude"
            (self.skills(home) / "kept").mkdir()
            (self.skills(home) / "kept" / "SKILL.md").write_text("x\n", encoding="utf-8")
            self.write_gitignore(home, self.allow_everything_but(home))

            # THE TRAP, demonstrated live rather than described.
            probe = git(claude, "check-ignore", "-v", "--", "skills/kept")
            self.assertEqual(probe.returncode, 0,
                             "fixture does not reproduce the trap: check-ignore did not exit 0 "
                             f"for a negated path ({probe.stdout}{probe.stderr})")
            self.assertIn("!/kept", probe.stdout,
                          f"exit 0 came from something other than a negation: {probe.stdout!r}")

            # ...and the check disagrees with it, because it never asked that question.
            base_rc, base_payload, err = self.run_json(home)
            self.assertEqual(base_payload["tracking"]["claude"]["results"]["kept"], "trackable",
                             base_payload["tracking"])
            self.assertEqual(base_payload["status"], "clean", base_payload["summary"])
            self.assertEqual(base_rc, 0, err)

            # NON-VACUITY: the same run, one genuinely excluded directory later, does report.
            (self.skills(home) / "rogue").mkdir()
            (self.skills(home) / "rogue" / "SKILL.md").write_text("x\n", encoding="utf-8")
            rc, payload, err = self.run_json(home)

            self.assertEqual(payload["tracking"]["claude"]["results"]["rogue"], "ignored")
            self.assertEqual(payload["tracking"]["claude"]["results"]["kept"], "trackable")
            self.assertEqual([f for f in payload["findings"] if "kept" in f["detail"]], [])
            self.assertEqual(len([f for f in payload["findings"] if "rogue" in f["detail"]]), 1,
                             payload["findings"])
            self.assertEqual(payload["status"], "findings")

    def test_the_tracking_probe_does_not_invoke_check_ignore(self) -> None:
        """Structural, and the reason it is worth having beside the behavioural test above.

        The behavioural test proves today's implementation gets the negated case right. This proves
        the wrong primitive is not reachable at all, so a later rewrite cannot pass by accident on a
        tree where no negation happens to be present. Docstrings are excluded by identity: the
        explanation of the trap must stay writable.
        """
        source = (SCRIPTS / "check_toolchain.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstrings = _docstring_ids(tree)
        offenders = [f"line {n.lineno}: {n.value!r}" for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and id(n) not in docstrings and "check-ignore" in n.value]
        self.assertEqual(offenders, [], "the trap primitive is reachable from code:\n  "
                                        + "\n  ".join(offenders))
        # GUARD THE GUARD, and tightened after the TC-47 review noted the first version only
        # asserted `--dry-run` appeared SOMEWHERE in the module — which a stray constant in an
        # unrelated function would have satisfied. Assert the argument vector itself, inside the
        # function that owns the probe, so the rule cannot pass on a `git_probe` that was gutted.
        probe = find_function(self, tree, "git_probe")
        argv = [[e.value for e in n.elts
                 if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                for n in ast.walk(probe) if isinstance(n, ast.List)]
        self.assertTrue(any("add" in v and "--dry-run" in v for v in argv),
                        f"git_probe no longer invokes `git add --dry-run`: {argv}")

    # ---- the disclosed gap, as a barrier rather than a paragraph ------------------------------

    def surface_states(self, home: Path) -> dict[str, bool]:
        """Author one file per surface and ask git, via the check's own probe, if it is trackable."""
        out = {}
        for rel in GAP_SURFACES:
            path = home / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("authored\n", encoding="utf-8")
            state, why = toolchain.git_probe(home, rel)
            self.assertIn(state, (toolchain.TRACKABLE, toolchain.IGNORED), (rel, state, why))
            out[rel] = state == toolchain.TRACKABLE
        return out

    def hidden_top_level_states(self, claude_rules: str, skills_rules: str) -> dict[str, bool]:
        """Probe the hidden pair on an UNCOMMITTED tree carrying the given allow-lists.

        Uncommitted for the reason `plant_allowlisted_home` records: `git add --dry-run` exits 0 on
        anything already in the index whatever the rules say, so on a committed tree the probe
        measures trackedness and the allow-list is enforced one step earlier, by the builder's own
        staging. Not vacuous there — just indirect; this is the direct construction. `.gitignore` is
        written by the fixture builder itself and must NOT be rewritten here — it is the rules under
        test.
        """
        with tempfile.TemporaryDirectory() as t:
            home = plant_allowlisted_home(Path(t) / "claude", claude_rules=claude_rules,
                                          skills_rules=skills_rules, commit=False)
            out = {}
            for rel in HIDDEN_TOP_LEVEL:
                path = home / rel
                if not path.exists():
                    path.write_text("authored\n", encoding="utf-8")
                state, why = toolchain.git_probe(home, rel)
                self.assertIn(state, (toolchain.TRACKABLE, toolchain.IGNORED), (rel, state, why))
                out[rel] = state == toolchain.TRACKABLE
            return out

    def test_a_hidden_top_level_entry_can_be_trackable_and_the_allowlist_line_decides(self) -> None:
        """FIX ROUND 4, FINDING 3. The hidden counterexample, executable rather than prose.

        `check_tracking`'s docstring states the true rule — HIDDEN ENTRIES ARE IN SCOPE — but every
        executable TRUE row in `GAP_SURFACES` was a VISIBLE path and its single hidden row was
        FALSE. Read as data that is "a hidden entry can be ignored", which is consistent with the
        FALSIFIED rule rather than a refutation of it. The trigger the reviewer found: deleting
        `!/.gitignore` from `CLAUDE_ALLOWLIST` broke NOTHING in this suite, even though that line is
        what makes the counterexample true. It breaks this test now.

        The pair is the assertion. One hidden TRUE row alone would be satisfied by a fixture that
        tracked everything; one hidden FALSE row alone is what we already had. Two hidden paths in
        the same directory under the same probe, differing only in whether the allow-list names
        them, is the smallest thing that can say "hidden decides nothing".
        """
        states = self.hidden_top_level_states(CLAUDE_ALLOWLIST, SKILLS_ALLOWLIST)

        self.assertEqual(states, HIDDEN_TOP_LEVEL,
                         "hidden top-level paths no longer split the way the allow-list says — if "
                         "`.gitignore` came back False, the `!/.gitignore` negation is gone and the "
                         "docstring's 'hidden entries are in scope' has lost its only counterexample")
        # Said out loud, because the failure message above is what a future reader will act on.
        self.assertTrue(states[".gitignore"],
                        "`.gitignore` is hidden, authored, and governs this very sweep — if git "
                        "would not commit it, 'hidden => out of scope' is no longer refuted here")
        self.assertFalse(states[".hidden-config"],
                         "the control went trackable — the fixture now tracks everything and the "
                         "TRUE row above proves nothing")

    def test_the_three_default_invisible_surfaces_are_what_the_module_says_they_are(self) -> None:
        """FIX ROUND 3, FINDING 3. The allow-list paragraph, as an executable assertion.

        RENAMED AT TC-49, because "uncovered" stopped being true of two of the three and a test
        name that lies is worse than no test. What it asserts is unchanged and is about the
        ALLOW-LISTS: which newly authored paths git would refuse. Two of these three are now SWEPT
        — that is asserted separately, by the cases at the end of this class — and the third is
        declared deferred. The distinction matters because a future reader who conflates them will
        read a green run here as proof the top level is covered.

        Three versions of that paragraph were written from throwaway replicas and two were wrong —
        the second because its replica omitted `skills/.gitignore` and therefore measured a tree on
        which all three surfaces are trackable. Nothing in this repository could have contradicted
        it. Now something can: the next wrong paragraph fails a test instead of a review.

        The TRUE rows are not padding. Without them a fixture that ignored EVERYTHING would satisfy
        every FALSE row and the test would confirm the paragraph while proving nothing.
        """
        with tempfile.TemporaryDirectory() as t:
            home = plant_allowlisted_home(Path(t) / "claude")

            states = self.surface_states(home)

            self.assertEqual(states, GAP_SURFACES,
                             "the gap paragraph and the tree disagree — one of them is wrong")
            # Say the two halves out loud, so a failure reads as the claim it breaks.
            self.assertEqual(sorted(k for k, v in states.items() if not v),
                             [".hidden-config", "MEMORY.md", "docs/NEW-LESSON.md", "skills/NOTES.md"])
            # ...and the thing this sweep DOES cover still behaves as the module claims.
            (home / "skills" / "new-vendor-skill").mkdir()
            (home / "skills" / "new-vendor-skill" / "SKILL.md").write_text("x\n", encoding="utf-8")
            state, _ = toolchain.git_probe(home, "skills/new-vendor-skill")
            self.assertEqual(state, toolchain.IGNORED,
                             "a new skill DIRECTORY must be ignored, or sweep one could never fire")

    @reaches_home(
        "READS THE REAL MACHINE: it is the drift detector for the committed allow-list literals, "
        "and comparing them against a synthetic allow-list would be a tautology. It reads "
        "~/.claude/.gitignore and ~/.claude/skills/.gitignore and never writes to the live tree. "
        "The skip is already loud on stderr, which is what a replica sees.")
    def test_the_committed_allowlists_still_decide_the_surfaces_the_real_ones_do(self) -> None:
        """The literals above are a STAND-IN, and a stand-in that has drifted is the r1 defect again.

        Runs the identical assertions against the real `~/.claude/.gitignore` and
        `~/.claude/skills/.gitignore`, copied into a scratch tree — never against the live
        repository, which must not be written to. Skips where they are absent, so the suite stays
        machine-independent while still refusing to let the fixture drift from the policy silently.

        BOTH PATHS COME FROM ONE BASE. They used to be derived from two: `toolchain.HOME / ".claude"`
        for the top-level list and `toolchain.CLAUDE_SKILLS` for the skills list. `CLAUDE_SKILLS` is
        a module global this suite patches (`TrackedContentTest.roots`, `NotRunStateTest.mirror`) and
        `HOME` is not patched alongside it, so a patch that leaked would have this test comparing a
        MISMATCHED PAIR of allow-lists — or, worse, skipping. Every patch site restores in a
        `finally` today, so it did not fire; one base means it cannot.

        AND THE SKIP IS LOUD. A drift detector that skips is a FALSE ZERO: the run still prints
        `OK`, only with a `(skipped=1)` a reader is entitled to gloss over, and "the fixture has not
        drifted" and "nobody checked" become the same output. The skip is still correct behaviour on
        a machine with no `~/.claude` — but it announces itself on stderr, so the absence of a check
        is visible without reading the tail of the summary line.
        """
        real_claude = toolchain.HOME / ".claude"
        real_top = real_claude / ".gitignore"
        real_skills = real_claude / "skills" / ".gitignore"
        if not (real_top.is_file() and real_skills.is_file()):
            missing = [str(p) for p in (real_top, real_skills) if not p.is_file()]
            print(f"\n!! SKIPPING THE ALLOW-LIST DRIFT DETECTOR: no real allow-list at "
                  f"{', '.join(missing)}. The committed literals were NOT compared against policy "
                  f"on this run — treat this suite's `OK` as silent on drift.", file=sys.stderr)
            self.skipTest(f"no real allow-lists to compare against: {', '.join(missing)}")

        claude_rules = real_top.read_text(encoding="utf-8")
        skills_rules = real_skills.read_text(encoding="utf-8")

        # The hidden pair against the REAL rules too, so `!/.gitignore` is load-bearing in the file
        # that actually governs this machine and not only in the stand-in literal.
        self.assertEqual(self.hidden_top_level_states(claude_rules, skills_rules), HIDDEN_TOP_LEVEL,
                         f"{real_top} no longer makes a hidden top-level entry trackable")

        with tempfile.TemporaryDirectory() as t:
            home = plant_allowlisted_home(
                Path(t) / "claude",
                claude_rules=claude_rules,
                skills_rules=skills_rules)

            states = self.surface_states(home)

            self.assertEqual(states, GAP_SURFACES,
                             f"the committed allow-lists no longer decide these paths the way "
                             f"{real_top} and {real_skills} do — the fixture has drifted from the "
                             f"policy, or the policy changed and the gap paragraph needs revisiting")

    # ---- stop condition 1, as a barrier rather than a hand measurement ------------------------

    def test_a_tracking_run_does_not_touch_the_index(self) -> None:
        """STOP CONDITION 1, pinned. It was measured twice by hand and by nothing repeatable.

        The property rests SOLELY on `--dry-run`: the TC-47 review was right that
        `GIT_OPTIONAL_LOCKS=0` is inert for `git add`, and it has been removed rather than left as a
        comment claiming a belt that does not exist. So this is the only standing guarantee that a
        check running at every session start does not stage the developer's work tree.

        THE ADD PATH MUST ACTUALLY RUN, or this measures nothing: an untracked NON-ignored skill is
        planted first, and the run is asserted to have classified it `trackable` — which is only
        reachable through a `git add --dry-run` that exited 0. Measuring "no mutation" on a tree
        where every probe was refused would be a control broken in the exonerating direction.

        BOTH PROBE LOOPS MUST RUN, since TC-49. The per-DIRECTORY sweep and the per-ENTRY sweep are
        separate call sites, and a fixture with no `docs/` would exercise only the first — leaving
        the newer loop's no-mutation property resting on the older loop's evidence. So an untracked
        NON-ignored document is planted too, and both classifications are asserted before the index
        comparison is believed.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            (self.skills(home) / "unstaged-skill").mkdir()
            (self.skills(home) / "unstaged-skill" / "SKILL.md").write_text("x\n", encoding="utf-8")
            self.plant_docs(home, "unstaged-doc.md")
            index = home / ".claude" / ".git" / "index"

            before = (index.read_bytes() if index.exists() else None,
                      git(home / ".claude", "ls-files", "-s").stdout,
                      git(home / ".claude", "status", "--porcelain").stdout)

            rc, payload, err = self.run_json(home)

            after = (index.read_bytes() if index.exists() else None,
                     git(home / ".claude", "ls-files", "-s").stdout,
                     git(home / ".claude", "status", "--porcelain").stdout)

            # Positive control FIRST: BOTH add paths ran and reached a verdict.
            self.assertEqual(payload["tracking"]["claude"]["results"]["unstaged-skill"],
                             "trackable", payload["tracking"])
            self.assertEqual(self.entry_results(payload)["docs/unstaged-doc.md"], "trackable",
                             payload["tracking"])
            self.assertEqual(rc, 0, err)
            self.assertEqual(before[1], after[1], "git ls-files changed — the run staged something")
            self.assertEqual(before[2], after[2], "git status changed — the run staged something")
            self.assertEqual(before[0], after[0], ".git/index bytes changed — the run wrote to it")

    def test_a_git_failure_that_is_not_exclusion_is_unknown_rather_than_clean(self) -> None:
        """The UNKNOWN branch of `git_probe`, which had NO test — the one branch deciding whether an
        unrecognised git failure reads as clean.

        Driven by a git that fails in a way this code does not recognise, planted on PATH ahead of
        the real one. The alternative — trusting that exit-0-means-trackable is the only path — is
        precisely the exonerating-direction assumption the rest of this file refuses.
        """
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t) / "bin"
            fake.mkdir()
            shim = fake / "git"
            shim.write_text("#!/bin/sh\n"
                            "echo 'fatal: something this checker has never seen' >&2\n"
                            "exit 7\n", encoding="utf-8")
            shim.chmod(0o755)
            root = Path(t) / "repo"
            root.mkdir()
            saved = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{fake}:{saved}"
            try:
                state, why = toolchain.git_probe(root, "anything")
            finally:
                os.environ["PATH"] = saved

            self.assertEqual(state, toolchain.UNKNOWN, (state, why))
            self.assertIn("7", why)
            # It must NOT silently become "not ignored", which is the shape of a false all-clear.
            self.assertNotEqual(state, toolchain.TRACKABLE)

    def test_index_lock_contention_is_retried_before_it_becomes_not_run(self) -> None:
        """FINDING 4's second consequence, and the fix for it.

        `git add` takes `.git/index.lock` even under `--dry-run` — measured. `~/.claude` is written
        by several agent sessions at once, and a single held lock was measured turning a healthy
        machine into ONE not-run finding PER SKILL DIRECTORY and exit 2 — so the count is whatever
        the tree holds, and `GIT_ENV` in `check_toolchain.py` owns the figures and the tree they were
        measured on. A session-start gate that flakes to "cannot be trusted" because a sibling held a
        lock for three milliseconds teaches the reader to ignore exit 2.

        THE NUMBER IS DELIBERATELY NOT RESTATED HERE. This docstring carried "six" — the six-skill
        test FIXTURE, not any real machine — and went on carrying it for a round after `GIT_ENV`
        retracted it, because that retraction's remedy comment said "grep the file" and the grep was
        duly run against `check_toolchain.py` alone. This suite is the second file in the same
        exclusive-write set. Grep BOTH, and prefer restating the rule to restating the number.

        Both halves are asserted: the transient IS retried through to a real answer, and a lock that
        never clears still ends in UNKNOWN rather than being wished away.
        """
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t) / "bin"
            fake.mkdir()
            counter = Path(t) / "n"
            counter.write_text("0", encoding="utf-8")
            shim = fake / "git"
            # Fails the first two calls the way a held lock does, then succeeds.
            shim.write_text(
                "#!/bin/sh\n"
                f"n=$(cat {counter})\n"
                f"echo $((n+1)) > {counter}\n"
                "if [ \"$n\" -lt 2 ]; then\n"
                "  echo \"fatal: Unable to create '/x/.git/index.lock': File exists.\" >&2\n"
                "  exit 128\n"
                "fi\n"
                "exit 0\n", encoding="utf-8")
            shim.chmod(0o755)
            saved = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{fake}:{saved}"
            try:
                state, why = toolchain.git_probe(Path(t), "some-skill")
            finally:
                os.environ["PATH"] = saved

            self.assertEqual(state, toolchain.TRACKABLE, (state, why))
            self.assertEqual(counter.read_text(encoding="utf-8").strip(), "3",
                             "the transient was not retried the expected number of times")

    def test_a_lock_that_never_clears_still_ends_in_not_run(self) -> None:
        """The other half. A retry that could mask a permanent failure would be worse than the flake
        it removes — the three-state contract is not weakened, only stopped from firing on noise."""
        with tempfile.TemporaryDirectory() as t:
            fake = Path(t) / "bin"
            fake.mkdir()
            shim = fake / "git"
            shim.write_text("#!/bin/sh\n"
                            "echo \"fatal: Unable to create '/x/.git/index.lock': File exists.\" >&2\n"
                            "exit 128\n", encoding="utf-8")
            shim.chmod(0o755)
            saved = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{fake}:{saved}"
            try:
                state, why = toolchain.git_probe(Path(t), "some-skill")
            finally:
                os.environ["PATH"] = saved

            self.assertEqual(state, toolchain.UNKNOWN, (state, why))
            self.assertIn("retries", why)

    # ---- TC-49: the surfaces where a NEW file is invisible by default -------------------------
    #
    # TC-47 swept skill DIRECTORIES, which is the surface where `!/skills/` makes a new file
    # trackable by default. These cases cover the inverse: `!/docs/` re-closed by `/docs/*`, and
    # `skills/.gitignore`'s own `/*`, where a newly authored file is IGNORED by default and
    # `git status` reports clean while it sits there. That is not an analogue of the measured
    # incident — `docs/fleet-lessons.md` invisible for two days — it is the same mechanism.

    def plant_docs(self, home: Path, *names: str) -> Path:
        """Author files under `~/.claude/docs`, asserting each one actually landed."""
        docs = home / ".claude" / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        for name in names:
            path = docs / name
            self.assertFalse(path.exists(), f"fixture would not mutate: {name} already exists")
            path.write_text("authored\n", encoding="utf-8")
            self.assertTrue(path.is_file(), f"fixture did not mutate: {name} was not written")
        return docs

    def write_top_allowlist(self, home: Path, body: str) -> Path:
        """Plant `~/.claude/.gitignore` and assert the rules actually changed."""
        path = home / ".claude" / ".gitignore"
        before = path.read_text(encoding="utf-8") if path.is_file() else None
        path.write_text(body, encoding="utf-8")
        self.assertNotEqual(path.read_text(encoding="utf-8"), before, "fixture did not mutate")
        return path

    @staticmethod
    def entry_results(payload: dict) -> dict[str, str]:
        """Every per-ENTRY answer across every swept surface, flattened by relative path."""
        out: dict[str, str] = {}
        for surface in payload["tracking"]["claude"]["entry_surfaces"].values():
            out.update(surface["results"])
        return out

    def test_a_new_document_under_docs_is_a_finding_naming_it(self) -> None:
        """THE REPRODUCED INCIDENT. A lessons file written after the allow-list named its siblings.

        Baseline and mutation are printed together and share one tree: the same home answers
        `clean` with only the NAMED survivor present and `findings` the moment an unnamed document
        is written beside it. So the finding is attributable to the state, not to the fixture — and
        the named survivor next to it stays silent, which is what stops this from being a check
        that simply flags `docs/`.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            self.plant_docs(home, "LEDGER.md")
            # The real shape, reduced to the rule that decides this surface: `!/docs/` opens the
            # directory, `/docs/*` closes it again, and only what is named after that survives.
            self.write_top_allowlist(home, "/docs/*\n!/docs/LEDGER.md\n")

            base_rc, base_payload, err = self.run_json(home)
            self.assertEqual(base_rc, 0, err)
            self.assertEqual(base_payload["status"], "clean", base_payload["summary"])
            self.assertEqual(self.entry_results(base_payload)["docs/LEDGER.md"], "trackable",
                             "fixture did not reproduce the named-survivor state")

            self.plant_docs(home, "fleet-lessons.md")

            rc, payload, err = self.run_json(home)

            self.assertNotEqual(payload["summary"], base_payload["summary"],
                                "the invisible document renders identically to the tracked one")
            hits = [f for f in payload["findings"] if "docs/fleet-lessons.md" in f["detail"]]
            self.assertEqual(len(hits), 1, payload["findings"])
            self.assertEqual(hits[0]["severity"], "warn", hits[0])
            self.assertIn("would NOT be committed", hits[0]["detail"])
            self.assertIn("MACHINE-GLOBAL", hits[0]["detail"])
            self.assertEqual(payload["status"], "findings")
            # TC-06 again: visible, not fatal, and the same ruling the skill sweep carries.
            self.assertEqual(rc, 0, err)
            self.assertEqual(self.entry_results(payload)["docs/fleet-lessons.md"], "ignored")
            self.assertEqual([f for f in payload["findings"] if "docs/LEDGER.md" in f["detail"]], [],
                             "a named survivor was flagged — the sweep is firing on the directory "
                             "rather than on the allow-list's answer")

    def test_both_invisible_surfaces_fire_and_a_whole_directory_negation_does_not(self) -> None:
        """The two swept surfaces against the faithful two-allow-list replica, with the control.

        The TRUE rows are the point. A sweep that had simply started flagging every new file would
        satisfy both FALSE rows and prove nothing, so `hooks/new.sh`, `agents/new.md` and a file
        INSIDE a negated skill directory are planted in the same run and asserted trackable by the
        same probe — and silent.

        Probed on an UNCOMMITTED replica, for the reason `plant_allowlisted_home` records: `git add
        --dry-run` exits 0 for anything already in the index whatever the rules say, so a committed
        tree would measure trackedness instead of the allow-list.
        """
        invisible = ("docs/NEW-LESSON.md", "skills/NOTES.md")
        controls = ("hooks/new.sh", "agents/new.md", "skills/agent-personas/NOTES.md")
        with tempfile.TemporaryDirectory() as t:
            home = plant_allowlisted_home(Path(t) / "claude", commit=False)
            with self.roots(home / "skills", Path(t) / "codex" / "skills"):
                _, base_findings, _ = toolchain.check_tracking()
                self.assertEqual(base_findings, [],
                                 f"baseline was not silent, so nothing below is attributable to "
                                 f"the mutation: {base_findings}")

                for rel in (*invisible, *controls):
                    path = home / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self.assertFalse(path.exists(), f"fixture would not mutate: {rel} exists")
                    path.write_text("authored\n", encoding="utf-8")
                    self.assertTrue(path.is_file(), f"fixture did not mutate: {rel}")

                surface, findings, _ = toolchain.check_tracking()

                # The control is only a control if git really would commit these.
                for rel in controls:
                    state, why = toolchain.git_probe(home, rel)
                    self.assertEqual(state, toolchain.TRACKABLE, (rel, state, why))

            self.assertEqual(sorted(s for s, _ in findings), ["warn", "warn"], findings)
            named = " ".join(d for _, d in findings)
            for rel in invisible:
                self.assertIn(rel, named, findings)
            for rel in controls:
                self.assertNotIn(rel, named,
                                 f"`{rel}` is trackable and was flagged anyway — the sweep started "
                                 f"reporting everything")
            entries = {}
            for s in surface["claude"]["entry_surfaces"].values():
                entries.update(s["results"])
            self.assertEqual(entries["docs/NEW-LESSON.md"], "ignored", entries)
            self.assertEqual(entries["skills/NOTES.md"], "ignored", entries)
            # `.gitignore` at the top level of skills/ is hidden, authored, and NAMED — the standing
            # refutation of "hidden means uninteresting", now swept rather than merely documented.
            self.assertEqual(entries["skills/.gitignore"], "trackable", entries)

    def test_each_surfaces_remedy_addresses_the_allowlist_that_actually_governs_it(self) -> None:
        """FIX ROUND 1. The printed remedy must name the file that can CLEAR the finding.

        Per gitignore(5) the closest `.gitignore` wins for paths beneath it, so `skills/NOTES.md`
        is decided by `skills/.gitignore` — `check-ignore -v` attributes it to
        `skills/.gitignore:10:/*` — while `docs/NEW-LESSON.md` is decided by the top-level list.
        The first version of this loop hardcoded the top-level file for both, so a reader following
        the instruction for surface 2 would have added a line to the machine's most
        safety-sensitive allow-list, watched the finding survive, and learned to ignore the check.
        `tree()`'s KNOWN GAP already records why an untrue remedy is the expensive kind of wrong.

        DELETING THE FIX CLAUSE MUST FAIL SOMETHING, which is the gap this closes: the two covering
        cases asserted only that the path was named, so the entire remedy could be replaced with an
        empty string and stay green.

        BOTH DIRECTIONS ARE PINNED. Asserting only that surface 2 names the skills list would be
        satisfied by a fix that swung the other way and sent every surface there, so surface 1 is
        asserted to still address the top-level file, and each is asserted NOT to name the other's.

        AND THE REMEDY IS EXECUTED, not merely read. The strongest form of "this instruction is
        true" is to follow it: each printed negation is appended to the file it names, and both
        findings are asserted to clear. That is what makes this a test of the ADVICE rather than of
        today's string.
        """
        with tempfile.TemporaryDirectory() as t:
            home = plant_allowlisted_home(Path(t) / "claude", commit=False)
            top_list, skills_list = home / ".gitignore", home / "skills" / ".gitignore"
            planted = {"docs/NEW-LESSON.md": (top_list, "!/docs/NEW-LESSON.md"),
                       "skills/NOTES.md": (skills_list, "!/NOTES.md")}
            for rel in planted:
                path = home / rel
                self.assertFalse(path.exists(), f"fixture would not mutate: {rel} exists")
                path.write_text("authored\n", encoding="utf-8")

            with self.roots(home / "skills", Path(t) / "codex" / "skills"):
                _, findings, _ = toolchain.check_tracking()

                self.assertEqual(sorted(s for s, _ in findings), ["warn", "warn"], findings)
                detail = {rel: [d for _, d in findings if rel in d] for rel in planted}
                for rel, (allowlist, negation) in planted.items():
                    self.assertEqual(len(detail[rel]), 1, findings)
                    said = detail[rel][0]
                    # BOTH HALVES, because they can drift apart. The first mutation run against
                    # this test changed only the DIAGNOSIS sentence and the suite stayed green —
                    # the remedy was pinned and the sentence saying which allow-list was consulted
                    # was not, so the finding could have named one file and prescribed another.
                    self.assertIn(f"and {allowlist} does not name it", said)
                    self.assertIn(f"Fix: add `{negation}` to {allowlist} ", said)
                    # ...and NOT the other surface's list, which is the defect this round fixed.
                    other = skills_list if allowlist == top_list else top_list
                    self.assertNotIn(f"to {other} ", said,
                                     f"the remedy for `{rel}` addresses {other}, which cannot "
                                     f"clear it — gitignore(5) gives {allowlist} precedence")

                # FOLLOW THE INSTRUCTION. If it is true, both findings go away.
                for allowlist, negation in planted.values():
                    before = allowlist.read_text(encoding="utf-8")
                    allowlist.write_text(f"{before}{negation}\n", encoding="utf-8")
                    self.assertNotEqual(allowlist.read_text(encoding="utf-8"), before,
                                        f"fixture did not mutate: {allowlist}")

                surface, cleared, _ = toolchain.check_tracking()

            self.assertEqual(cleared, [],
                             f"the printed remedy did not clear the finding it was printed for: "
                             f"{cleared}")
            entries = {}
            for s in surface["claude"]["entry_surfaces"].values():
                entries.update(s["results"])
            for rel in planted:
                self.assertEqual(entries[rel], "trackable", entries)

    def test_the_repository_top_level_is_declared_deferred_rather_than_swept_or_silent(self) -> None:
        """STOP CONDITION 1. The third surface is NOT closed here, and it says so where it is read.

        Enumerating the top level of `~/.claude` per entry means enumerating `projects/` (a 2.6 GB
        transcript store), `plugins/`, `shell-snapshots/` and every cache the harness writes, all
        legitimately and permanently ignored. Measured on this machine: 33 entries, 11 trackable,
        22 ignored. Probed with no authored-set that is 22 unclearable findings at every session
        start in every directory — the cry-wolf pathology this milestone exists to remove, and a
        finding the reader learns to skip is worse than the gap.

        So it is DECLARED, on exactly the terms the Codex tree is: `asked` is false, the reason
        travels in `--json`, and the exclusion is named on the summary line. What must never happen
        is the third possibility — the surface quietly absent, so that a clean run reads as though
        the top level had been asked about.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            _, payload, err = self.run_json(home)

            surfaces = payload["tracking"]["claude"]["entry_surfaces"]
            self.assertIn(toolchain.TOP_LEVEL_SURFACE, surfaces, sorted(surfaces))
            top = surfaces[toolchain.TOP_LEVEL_SURFACE]
            self.assertFalse(top["asked"])
            self.assertEqual(top["results"], {})
            self.assertIn("authored-set", (top["why_not_asked"] or "").lower(), top)
            names = [e["name"] for e in payload["excluded"]]
            self.assertIn(toolchain.TOP_LEVEL_EXCLUSION[0], names, names)
            # ...and declaring it costs the run nothing, which is why it is not a finding.
            self.assertEqual(payload["status"], "clean", payload["summary"])

    def test_sweeping_the_top_level_per_entry_would_fire_on_ordinary_machine_state(self) -> None:
        """The evidence UNDER the deferral above, measured rather than asserted.

        A deferral justified by prose is a deferral nobody can re-check. This plants the ordinary,
        benign top-level state every machine carries — a transcript store, a plugin tree, a shell
        snapshot directory, two caches — and shows the probe answers IGNORED for every one of them
        while the allow-list declares none of them. Those are the findings a per-entry sweep would
        emit at every session start, with no line anyone could add to clear them.
        """
        noise = ("projects", "plugins", "shell-snapshots", "history.jsonl", "stats-cache.json")
        with tempfile.TemporaryDirectory() as t:
            home = plant_allowlisted_home(Path(t) / "claude", commit=False)
            for name in noise:
                path = home / name
                self.assertFalse(path.exists(), f"fixture would not mutate: {name} exists")
                if Path(name).suffix:
                    path.write_text("{}\n", encoding="utf-8")
                else:
                    path.mkdir()
                    (path / "x").write_text("x\n", encoding="utf-8")

            states = {name: toolchain.git_probe(home, name)[0] for name in noise}

            self.assertEqual(states, {name: toolchain.IGNORED for name in noise}, states)
            # Non-vacuity: on the same tree, a NAMED top-level survivor answers the other way, so
            # the rows above are the allow-list's verdict and not a probe that refuses everything.
            self.assertEqual(toolchain.git_probe(home, "CLAUDE.md")[0], toolchain.TRACKABLE)

    def test_an_unanswerable_entry_probe_is_could_not_run_and_differs_from_clean(self) -> None:
        """A symlinked document, and the same fail-closed ruling `skill_dirs` already makes.

        `git add` on a link records the LINK — a blob holding a target path — so exit 0 would say
        "git would commit this" about a document whose content lives where git has never looked.
        That is the invisible-authored-work case wearing a green tick, which is the exact failure
        this sweep exists to prevent, so it answers UNKNOWN. Both halves are asserted: the run
        cannot be trusted (exit 2) AND it does not render like the clean one.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            self.plant_docs(home, "LEDGER.md")
            clean_rc, clean_payload, err = self.run_json(home)
            self.assertEqual((clean_rc, clean_payload["status"]), (0, "clean"), err)

            elsewhere = Path(t) / "outside"
            elsewhere.mkdir()
            (elsewhere / "NOTE.md").write_text("real content\n", encoding="utf-8")
            link = home / ".claude" / "docs" / "linked.md"
            link.symlink_to(elsewhere / "NOTE.md")
            self.assertTrue(link.is_symlink(), "fixture did not mutate")

            rc, payload, err = self.run_json(home)

            self.assertEqual(rc, 2, err)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)
            self.assertNotEqual(payload["summary"], clean_payload["summary"])
            self.assertEqual(self.entry_results(payload)["docs/linked.md"], "unknown")
            self.assertIn(toolchain.TRACKING_LABEL, [i["check"] for i in payload["not_evaluated"]])
            self.assertNotIn(toolchain.TRACKING_LABEL, payload["evaluated"])

    def test_os_noise_inside_a_swept_surface_is_held_out_rather_than_reported(self) -> None:
        """`.DS_Store` in `docs/` is an ordinary state on any machine that opened it in Finder.

        Both allow-lists exclude the four OS-noise names "never, anywhere", so each one is ignored
        AND undeclared AND would be a finding under the plain rule — a permanent, unclearable
        finding produced by a file nobody authored. Held out by name, which the card's own scoping
        calls a list rather than a model. The authored file planted beside it keeps the assertion
        non-vacuous: the sweep is still looking.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            self.plant_docs(home, "LEDGER.md", ".DS_Store", "NEW-LESSON.md")
            self.write_top_allowlist(home, "/docs/*\n!/docs/LEDGER.md\n.DS_Store\n")

            rc, payload, err = self.run_json(home)

            results = self.entry_results(payload)
            self.assertNotIn("docs/.DS_Store", results, results)
            self.assertEqual([f for f in payload["findings"] if ".DS_Store" in f["detail"]], [])
            # ...and the authored file next to it is still reported, so this is a hold-out and not
            # a sweep that quietly stopped looking at `docs/`.
            self.assertEqual(results["docs/NEW-LESSON.md"], "ignored", results)
            self.assertEqual(len([f for f in payload["findings"]
                                  if "docs/NEW-LESSON.md" in f["detail"]]), 1, payload["findings"])

    # ---- the declared-vendor list -----------------------------------------------------------

    @contextlib.contextmanager
    def roots(self, claude: Path, codex: Path):
        """Point the module at synthetic harness roots, as `NotRunStateTest.mirror` does."""
        saved = (toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS)
        toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS = claude, codex
        try:
            yield
        finally:
            toolchain.CLAUDE_SKILLS, toolchain.CODEX_SKILLS = saved

    def vendor_tree(self, tmp: Path) -> tuple[Path, Path, str]:
        """A work tree holding one declared vendor skill, ignored exactly as the real one is."""
        vendor = sorted(toolchain.DECLARED_VENDOR_SKILLS)[0]
        claude = git_init(tmp / "claude")
        skills = claude / "skills"
        (skills / vendor).mkdir(parents=True)
        (skills / vendor / "SKILL.md").write_text("vendor\n", encoding="utf-8")
        (skills / ".gitignore").write_text(f"/{vendor}\n", encoding="utf-8")
        return skills, tmp / "codex" / "skills", vendor

    def test_a_declared_vendor_skill_is_not_a_finding_and_the_declaration_is_visible(self) -> None:
        """Reported, never silent, never a finding — and the reason travels with it.

        The card's constraint is that an exclusion be VISIBLE rather than tacit, so the assertion
        is not merely that no finding fired: it is that the name and the reason both reach the
        output a consumer reads.
        """
        with tempfile.TemporaryDirectory() as t:
            skills, codex, vendor = self.vendor_tree(Path(t))
            with self.roots(skills, codex):
                surface, findings, excluded = toolchain.check_tracking()

            self.assertEqual(surface["claude"]["results"][vendor], "ignored",
                             "fixture did not reproduce the excluded state")
            self.assertEqual(findings, [], findings)
            self.assertIn(vendor, surface["claude"]["declared_vendor"])
            self.assertTrue(surface["claude"]["declared_vendor"][vendor].strip(),
                            "a declaration with no reason is a tacit exclusion with a name on it")
            self.assertIn(vendor, " ".join(f"{n} {w}" for n, w in excluded))

    def test_a_declared_vendor_is_reported_as_asked_not_as_uncompared(self) -> None:
        """The exclusion header and the exclusion reason must both survive a distinction TC-47 made.

        Two kinds of entry now share one list. The Codex tree was genuinely NOT COMPARED — the
        question was never put to git. A declared vendor WAS asked and its answer is sitting in
        `tracking.claude.results`; only the FINDING is waived. The summary header used to assert the
        stronger claim for both, contradicting the data two keys away, which is this file's
        false-reassurance defect at label size.
        """
        with tempfile.TemporaryDirectory() as t:
            skills, codex, vendor = self.vendor_tree(Path(t))
            with self.roots(skills, codex):
                surface, _, excluded = toolchain.check_tracking()

            why = dict(excluded)[f"skill {vendor}"]
            self.assertIn("asked", why, why)
            self.assertNotIn("NOT compared", why)
            # The rendered header, which a per-entry assertion cannot reach.
            run = toolchain.Run("default", toolchain.BLOCKING_DEFAULT)
            run.excluded += excluded
            summary = run.summary("clean")
            self.assertIn("excluded from findings", summary)
            self.assertNotIn("NOT compared", summary)
            # ...and the answer it was excluded from REPORTING is still on the record.
            self.assertEqual(surface["claude"]["results"][vendor], "ignored")

    def test_the_clean_line_does_not_claim_a_directory_it_excluded_would_be_committed(self) -> None:
        """The clean sentence must reconcile with `tracking.claude.results`, not contradict it.

        THE DEFECT, exactly: the phrase read "git would commit every one of the N skill
        director(ies) on disk", where N was `len(results)` — every directory ASKED, including the
        ones that answered `ignored` and were exempted from producing a finding. On any machine
        with a declared vendor installed, which is the designed-for case, the success line asserted
        committability for a directory the JSON two keys away records as ignored. It is the same
        false-reassurance shape the round-5 fix removed from `Run.summary`'s exclusion header
        ("excluded and NOT compared" -> "excluded from findings"), left standing one function over.

        The rule this asserts is the programme's own: REPORT THE TOTAL ALONGSIDE THE FILTERED
        COUNT, in the sentence and not only in the JSON. Both numbers, and the exempt count that
        reconciles them, so a reader can check the arithmetic without opening `--json`.
        """
        with tempfile.TemporaryDirectory() as t:
            home, vendor = self.green_home_with_declared_vendor(Path(t))

            rc, payload, err = self.run_json(home)
            self.assertEqual(rc, 0, err)
            self.assertEqual(payload["status"], "clean", payload["summary"])

            results = payload["tracking"]["claude"]["results"]
            trackable = sum(1 for state in results.values() if state == toolchain.TRACKABLE)
            summary = payload["summary"]

            # The state the sentence has to survive: asked about more than it can vouch for.
            self.assertEqual(results[vendor], "ignored", results)
            self.assertLess(trackable, len(results), results)

            self.assertNotIn("every one of the", summary,
                             "the clean line still claims committability for a directory git "
                             f"answered `ignored` about: {results}")
            self.assertIn(f"git would commit {trackable} of the {len(results)} skill director(ies)",
                          summary)
            self.assertIn("1 exempt as declared vendors", summary)

    def test_the_clean_line_reports_both_counts_when_nothing_is_exempt(self) -> None:
        """The other half: with no vendor installed the two counts agree, and both are still said.

        A sentence that only names the filtered count when they differ teaches the reader that the
        number they usually see is a total, which is how the original phrasing read. It says both
        every time, so `8 of 8` and `7 of 8` are read the same way.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))

            rc, payload, err = self.run_json(home)
            self.assertEqual(rc, 0, err)

            results = payload["tracking"]["claude"]["results"]
            total = len(results)
            self.assertEqual(sum(1 for s in results.values() if s == toolchain.TRACKABLE), total,
                             results)
            self.assertIn(f"git would commit {total} of the {total} skill director(ies)",
                          payload["summary"])
            self.assertIn("0 exempt as declared vendors", payload["summary"])

    def test_deleting_the_declaration_makes_the_vendor_skill_a_finding_again(self) -> None:
        """The property `test_no_skill_is_special_cased_by_name` protects, asserted behaviourally.

        That AST rule forbids a skill name as a string constant anywhere in the checker, and TC-47
        narrows it to exempt `DECLARED_VENDOR_SKILLS` — the card requires a code-resident list, and
        `skills/.gitignore` is an allow-list of what this repository OWNS, so it carries no
        statement that a given exclusion is a vendor's. The exemption is only safe if the list is
        load-bearing rather than decorative, which is exactly this: empty it, and the finding
        returns.
        """
        with tempfile.TemporaryDirectory() as t:
            skills, codex, vendor = self.vendor_tree(Path(t))

            with self.roots(skills, codex):
                _, declared_findings, _ = toolchain.check_tracking()
                saved = toolchain.DECLARED_VENDOR_SKILLS
                toolchain.DECLARED_VENDOR_SKILLS = {}
                try:
                    surface, findings, _ = toolchain.check_tracking()
                finally:
                    toolchain.DECLARED_VENDOR_SKILLS = saved

            self.assertEqual(declared_findings, [], "baseline was not silent")
            self.assertEqual([s for s, _ in findings], ["warn"], findings)
            self.assertIn(vendor, findings[0][1])
            self.assertEqual(surface["claude"]["declared_vendor"], {})

    def test_the_declared_vendor_list_is_short_and_every_entry_carries_a_reason(self) -> None:
        """The other half of the exemption. A list that may grow silently is an allow-list again.

        SHORT is the card's word and the reason is the reader: an exclusion set large enough to
        skim is one nobody audits. Two is one more than today's single legitimate entry, so
        adding a second is possible without a test edit and adding a third is not.
        """
        declared = toolchain.DECLARED_VENDOR_SKILLS
        self.assertIsInstance(declared, dict)
        self.assertGreaterEqual(len(declared), 1, "an empty list makes the exemption vacuous")
        self.assertLessEqual(len(declared), 2, sorted(declared))
        for name, why in declared.items():
            self.assertGreater(len(why), 40,
                               f"`{name}` is excluded with no argument a reader can weigh: {why!r}")

    # ---- an unanswerable question is never a clean one ---------------------------------------

    def test_a_home_that_is_not_a_work_tree_is_could_not_run_and_differs_from_clean(self) -> None:
        """The invariant, end to end: no git, no verdict — and the two outputs are not the same.

        Both halves matter. A not-run that exits 2 but prints the clean line is still the defect,
        and a run that prints differently but exits 0 is the other half of it.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            clean_rc, clean_payload, err = self.run_json(home)
            self.assertEqual((clean_rc, clean_payload["status"]), (0, "clean"), err)

            dot_git = home / ".claude" / ".git"
            shutil.rmtree(dot_git)
            self.assertFalse(dot_git.exists(), "fixture did not mutate")

            rc, payload, err = self.run_json(home)

            self.assertEqual(rc, 2, err)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)
            self.assertNotEqual(payload["summary"], clean_payload["summary"])
            self.assertIn(toolchain.TRACKING_LABEL, [i["check"] for i in payload["not_evaluated"]])
            self.assertNotIn(toolchain.TRACKING_LABEL, payload["evaluated"])
            self.assertFalse(payload["tracking"]["claude"]["asked"])
            self.assertTrue(payload["tracking"]["claude"]["why_not_asked"])

    def test_git_being_unavailable_is_could_not_run_rather_than_nothing_ignored(self) -> None:
        """No git binary is the purest form of the unanswerable question, and the likeliest way a
        future reader gets a false all-clear: with no git there is nothing ignored to report."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "check_toolchain.py"), "--json"],
                capture_output=True, text=True,
                env={**dict(os.environ), "HOME": str(home), "PATH": ""})

            payload = json.loads(r.stdout)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)
            self.assertIn(toolchain.TRACKING_LABEL, [i["check"] for i in payload["not_evaluated"]])
            why = payload["tracking"]["claude"]["why_not_asked"] or ""
            self.assertIn("git", why.lower(), why)

    def test_a_symlinked_skill_directory_is_could_not_run_not_trackable(self) -> None:
        """`git add` on a link records the LINK, so exit 0 would mean "committed" about a path
        whose actual content is somewhere else entirely — the invisible-authored-work case wearing
        a green tick. Fail closed."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            elsewhere = Path(t) / "outside"
            (elsewhere / "scripts").mkdir(parents=True)
            (elsewhere / "SKILL.md").write_text("real content\n", encoding="utf-8")
            link = self.skills(home) / "linked-skill"
            link.symlink_to(elsewhere, target_is_directory=True)
            self.assertTrue(link.is_symlink(), "fixture did not mutate")

            rc, payload, err = self.run_json(home)

            self.assertEqual(payload["tracking"]["claude"]["results"]["linked-skill"], "unknown")
            self.assertEqual(rc, 2, err)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)

    # ---- the harness asymmetry, stated rather than silently dropped -------------------------

    def test_the_codex_side_is_declared_out_of_scope_rather_than_silently_thinner(self) -> None:
        """STOP CONDITION 4. `~/.codex/skills` cannot be asked this question the same way.

        Measured on this machine: `~/.codex` IS a work tree and every one of its seven skill
        directories is ignored, because `~/.codex/.gitignore` excludes `skills/` wholesale — the
        tree there is RENDERED from `~/.claude` by install_hooks.py, and backing up a derived copy
        would create a second source of truth. Swept identically, this check would emit seven
        permanent findings with no remedy, on every machine, at every session start: the
        cry-wolf failure the milestone has been removing.

        So the Codex side is declared out of scope — and DECLARED is the operative word. The
        exclusion is named in the report and carries its reason in --json, and the currency of that
        derived tree is still gated, by `check_skills`, which fires critical when a mirrored skill
        is missing there and prescribes the command that restores it.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            _, payload, err = self.run_json(home)

            codex = payload["tracking"]["codex"]
            self.assertFalse(codex["in_scope"])
            self.assertFalse(codex["asked"])
            self.assertIn("derived", (codex["why_not_asked"] or "").lower())
            names = [e["name"] for e in payload["excluded"]]
            self.assertIn("Codex skill tracking", names, names)
            # ...and it is not a finding, in either direction.
            self.assertEqual(payload["status"], "clean", payload["summary"])

    def test_every_exclusion_clause_on_the_summary_line_stays_short(self) -> None:
        """L8's rule, now that TC-47 adds a second standing exclusion.

        `Run.summary` renders every exclusion inline, so each one rides on every line this tool
        prints at every session start. The previous version of this rule string-split on
        `"1 excluded"` and would have silently stopped asserting anything the moment a second
        exclusion existed — a guard defeated by the change it was meant to survive.
        """
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            _, payload, _ = self.run_json(home)

            self.assertEqual(payload["status"], "clean")
            self.assertGreaterEqual(len(payload["excluded"]), 2, payload["excluded"])
            for entry in payload["excluded"]:
                self.assertLess(len(f"{entry['name']} ({entry['why']})"), 120, entry)
            scope = payload["summary"].split("excluded from findings: ", 1)[1]
            self.assertLess(len(scope), 240, scope)

    # ---- the real machine, with its tree named ----------------------------------------------

    @reaches_home(
        "READS THE REAL MACHINE, as its name says: the claim is that THIS machine's skill "
        "directories and entry surfaces are all askable and all classified. Skips when "
        "~/.claude/skills is absent or ~/.claude is not a work tree. NOTE that a complete replica "
        "IS a work tree with skills in it, so this one RUNS there and passes — it is marked "
        "because it reads the machine, not because it breaks on a replica.")
    def test_the_real_machine_is_askable_and_its_clear_result_is_an_asked_one(self) -> None:
        """The current true answer must be reported as a result, not as the absence of a check.

        In-process, so this reads the real `~/.claude` without spawning `sync_personas.py --check`
        and its 60-second timeout. THE POSITIVE CONTROL IS THE POINT: an absence claim ("nothing is
        invisible") needs proof that directories were actually asked about, or a walk that found
        none reads exactly like a machine with nothing wrong.
        """
        if not toolchain.CLAUDE_SKILLS.is_dir():
            self.skipTest("no ~/.claude/skills on this machine")
        surface, findings, excluded = toolchain.check_tracking()

        claude = surface["claude"]
        if not claude["asked"]:
            self.skipTest(f"~/.claude is not a work tree here: {claude['why_not_asked']}")
        # ON DISK, not at HEAD: `results` is keyed by what the walk saw in the working tree.
        on_disk = sorted(p.name for p in toolchain.CLAUDE_SKILLS.iterdir()
                         if p.is_dir() and p.name != "__pycache__")
        self.assertGreater(len(on_disk), 0)
        self.assertEqual(sorted(claude["results"]), on_disk,
                         "the sweep did not ask about every skill directory on disk")
        self.assertEqual([n for n, _ in excluded if n == "Codex skill tracking"],
                         ["Codex skill tracking"])
        # Whatever the verdict, it is a measured one: no directory may be silently unclassified.
        self.assertEqual([n for n, v in claude["results"].items() if v not in
                          ("trackable", "ignored", "unknown")], [])
        for severity, detail in findings:
            self.assertIn(severity, toolchain.SEVERITY_RANK, detail)

        # TC-49, and the same positive control one level down. An entry surface that answered
        # nothing reads exactly like one with nothing wrong, so assert the sweep reached every
        # entry the walk can see — and that the deferred surface is present and honest about being
        # unasked rather than absent.
        surfaces = claude["entry_surfaces"]
        deferred = surfaces[toolchain.TOP_LEVEL_SURFACE]
        self.assertFalse(deferred["asked"])
        self.assertTrue(deferred["why_not_asked"])
        root = toolchain.CLAUDE_SKILLS.parent
        for label, rel_dir, files_only, allowlist_rel in toolchain.ENTRY_SURFACES:
            entry = surfaces[label]
            base = root / rel_dir
            self.assertEqual(entry["allowlist"], str(root / allowlist_rel), label)
            if not base.is_dir():
                self.assertFalse(entry["present"], label)
                continue
            self.assertTrue(entry["asked"], entry)
            on_disk = sorted(f"{rel_dir}/{p.name}" for p in base.iterdir()
                             if not (files_only and p.is_dir())
                             and not any(fnmatch.fnmatch(p.name, pattern)
                                         for pattern in toolchain.TRACKING_OS_NOISE))
            self.assertEqual(sorted(entry["results"]), on_disk,
                             f"the {label} sweep did not ask about every entry on disk")
            self.assertEqual([n for n, v in entry["results"].items()
                              if v not in ("trackable", "ignored", "unknown")], [])


class ReviewArtifactTest(unittest.TestCase):
    """TC-47, sweep two. Same class of defect: authored work that no gate can see.

    MEASURED, at the time the card was written — TC-35 2 review artifacts, TC-36 2, TC-37 2,
    TC-39 5, TC-41 3, TC-42 2, TC-45 2, and TC-40 ZERO. The zero is invisible in aggregate and
    obvious per card. TC-40 skipped its review stage entirely, was verified and moved toward a
    commit, and the first review it ever received returned two CRITICALs — a `--fix` that deleted
    machine-global agent files while printing "nothing changed".

    Those counts are the EVIDENCE, not the assertion. Two of them have already moved (TC-40 has a
    review now; TC-41 gained a fourth), which is precisely why nothing here pins a number measured
    against a tree that keeps changing. What is pinned is the question, asked per card.
    """

    def run_reviews(self, workspace: Path):
        """HOME PINNED BESIDE THE WORKSPACE, since TC-57.

        `--reviews` is a workspace-scoped mode and returns before `collect()`, so on the evidence
        of today's source it never opens anything under HOME. That is a fact about one `elif`
        branch, not a property of the process: the child is `check_toolchain.py`, whose module body
        freezes ten paths off `Path.home()` the moment it imports. Pinning HOME costs nothing,
        changes no assertion here (every one is about the workspace), and means this mode cannot
        start reading the developer's machine without someone deleting this line.
        """
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_toolchain.py"), "--json",
             "--reviews", str(workspace)],
            capture_output=True, text=True,
            env={**dict(os.environ), "HOME": str(Path(workspace).parent)})
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None), r.stdout + r.stderr

    def test_a_card_with_a_report_and_no_review_is_a_finding_naming_it(self) -> None:
        """THE ONE, in the shape it actually happened. Reported, verified, never reviewed."""
        with tempfile.TemporaryDirectory() as t:
            ws = plant_workspace(Path(t), {
                "TC-39": ("TC-39-report.md", "TC-39-review.md"),
                "TC-40": ("TC-40-report.md",),
                "TC-41": ("TC-41-report.md", "TC-41-review-round2.md"),
            })

            rc, payload, err = self.run_reviews(ws)

            hits = [f for f in payload["findings"] if "TC-40" in f["detail"]]
            self.assertEqual(len(hits), 1, payload["findings"])
            self.assertEqual(hits[0]["severity"], "critical", hits[0])
            # The observable, not the inference — see
            # `test_the_finding_says_what_was_searched_for_and_claims_no_more`.
            self.assertIn("no file named `TC-40-*.md`", hits[0]["detail"])
            # The aggregate would have hidden it; the per-card count is what makes it obvious.
            self.assertEqual(payload["reviews"]["cards"]["TC-40"],
                             {"reports": 1, "reviews": 0})
            self.assertEqual(payload["reviews"]["cards"]["TC-39"],
                             {"reports": 1, "reviews": 1})
            self.assertEqual(rc, 1, err)
            self.assertEqual(payload["status"], "findings")

    def test_adding_the_review_clears_it(self) -> None:
        """Baseline and remedy together. A finding no action can clear is one the reader ignores."""
        with tempfile.TemporaryDirectory() as t:
            ws = plant_workspace(Path(t), {"TC-40": ("TC-40-report.md",)})
            base_rc, base_payload, err = self.run_reviews(ws)
            self.assertEqual((base_rc, base_payload["counts"]["total"]), (1, 1), err)

            planted = ws / "reports" / "TC-40-review.md"
            planted.write_text("# review\n", encoding="utf-8")
            self.assertTrue(planted.is_file(), "fixture did not mutate")

            rc, payload, err = self.run_reviews(ws)

            self.assertNotEqual(payload["summary"], base_payload["summary"])
            self.assertEqual(payload["status"], "clean", payload["summary"])
            self.assertEqual(rc, 0, err)

    def test_a_card_with_no_report_is_not_a_finding(self) -> None:
        """Work not yet done is not work that skipped its review, and conflating them would make
        every unstarted card in the workspace red."""
        with tempfile.TemporaryDirectory() as t:
            ws = plant_workspace(Path(t), {"TC-43": (), "TC-44": ()})

            rc, payload, err = self.run_reviews(ws)

            self.assertEqual(payload["findings"], [], payload)
            self.assertEqual(payload["reviews"]["cards"], {"TC-43": {"reports": 0, "reviews": 0},
                                                           "TC-44": {"reports": 0, "reviews": 0}})
            self.assertEqual(rc, 0, err)

    def test_a_sibling_card_id_does_not_satisfy_a_cards_review(self) -> None:
        """Prefix collision, and the workspace really contains both shapes: TC-04 beside TC-40, and
        TC-02 beside TC-02A. A `startswith` on the bare id lets one card's review clear another's,
        which is the silent all-clear this sweep exists to refuse."""
        with tempfile.TemporaryDirectory() as t:
            ws = plant_workspace(Path(t), {
                "TC-04": ("TC-04-report.md",),
                "TC-40": ("TC-40-report.md", "TC-40-review.md"),
                "TC-02A": ("TC-02A-report.md",),
            })
            (ws / "reports" / "TC-02-review.md").write_text("# orphan\n", encoding="utf-8")

            rc, payload, err = self.run_reviews(ws)

            # Matched on the BACKTICKED subject, not a bare substring. The finding prose cites the
            # TC-40 near-miss by name, so `"TC-40" in detail` is true of every finding this check
            # emits — a loose matcher that would have reported the collision as present when it was
            # not, which is the same false answer the check itself is built to refuse.
            named = sorted(c for c in ("TC-04", "TC-40", "TC-02A")
                           if any(f"card `{c}`" in f["detail"] for f in payload["findings"]))
            self.assertEqual(named, ["TC-02A", "TC-04"], payload["findings"])
            self.assertEqual(payload["reviews"]["cards"]["TC-40"]["reviews"], 1)
            self.assertEqual(rc, 1, err)

    def test_a_workspace_with_no_cards_is_could_not_run_and_exits_two(self) -> None:
        """An unanswerable question is COULD-NOT-RUN, never clean. A directory with no cards in it
        has not been swept; it has been mistyped."""
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "empty"
            (ws / "reports").mkdir(parents=True)

            rc, payload, err = self.run_reviews(ws)

            self.assertEqual(rc, 2, err)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)
            self.assertNotIn("clean", payload["summary"])
            self.assertIn("review coverage", [i["check"] for i in payload["not_evaluated"]])

    def test_a_missing_reports_directory_is_could_not_run_not_universal_failure(self) -> None:
        """The exonerating direction has a mirror image here: no `reports/` could be read as "every
        card is missing its review", which is a wall of findings nobody can act on. It is neither
        that nor clean — it is a question that was not asked."""
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "ws"
            ws.mkdir()
            (ws / "TC-40.yaml").write_text("id: TC-40\n", encoding="utf-8")

            rc, payload, err = self.run_reviews(ws)

            self.assertEqual(rc, 2, err)
            self.assertEqual(payload["status"], toolchain.NOT_RUN)
            self.assertEqual([f for f in payload["findings"]
                              if f["severity"] != toolchain.NOT_RUN], [])

    def test_a_missing_workspace_exits_two_with_stdout_empty(self) -> None:
        """The usage-and-environment contract this file already documents: exit 2, message on
        stderr, and NO json object, because no result was ever established."""
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "check_toolchain.py"), "--json",
                 "--reviews", str(Path(t) / "nope")], capture_output=True, text=True,
                env={**dict(os.environ), "HOME": t})

            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(r.stdout.strip(), "")
            self.assertIn("nope", r.stderr)

    def test_the_two_repository_scoped_modes_are_mutually_exclusive(self) -> None:
        """They answer different questions about different trees, and a run that silently ran only
        one of them would report a verdict for a question the caller did not ask."""
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "check_toolchain.py"),
                 "--vendored", t, "--reviews", t], capture_output=True, text=True,
                env={**dict(os.environ), "HOME": t})

            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(r.stdout.strip(), "")

    def test_a_single_file_cannot_be_both_the_report_and_the_review_that_clears_it(self) -> None:
        """FINDING 9. `REPORT_MARKER` and `REVIEW_MARKERS` are not disjoint.

        `TC-NN-security-report.md` contains both `report` and `security`. Counted in both lists it
        would be the report that creates the obligation AND the review that discharges it — one file
        clearing its own card, which is the self-exonerating shape this sweep exists to remove.
        Review wins the tie, so such a card has no report and produces no finding: fail toward
        silence, never toward a discharged obligation.
        """
        with tempfile.TemporaryDirectory() as t:
            ws = plant_workspace(Path(t), {"TC-50": ("TC-50-security-report.md",)})

            rc, payload, err = self.run_reviews(ws)

            self.assertEqual(payload["reviews"]["cards"]["TC-50"], {"reports": 0, "reviews": 1},
                             "one file was counted as both the obligation and its discharge")
            self.assertEqual(payload["findings"], [], payload["findings"])
            self.assertEqual(rc, 0, err)

    def test_the_finding_says_what_was_searched_for_and_claims_no_more(self) -> None:
        """FINDING 2. The `critical` used to assert "nothing independent judged this work".

        This function observes only whether a file named `TC-<id>-*` contains `review` or
        `security`. The real workspace holds `FULL-DIFF-review.md` — a reviewer-persona review of
        3585 lines across 13 files and two repositories — plus `SECURITY-review.md` and others, none
        of which carry a card id. For several of the sixteen real findings the old sentence was
        simply FALSE, at `critical`, in a file whose register is measured fact.
        """
        with tempfile.TemporaryDirectory() as t:
            ws = plant_workspace(Path(t), {"TC-40": ("TC-40-report.md",)})
            (ws / "reports" / "FULL-DIFF-review.md").write_text("# broad\n", encoding="utf-8")

            rc, payload, err = self.run_reviews(ws)

            detail = payload["findings"][0]["detail"]
            self.assertIn("TC-40-*.md", detail, detail)
            self.assertIn("BY NAME", detail, detail)
            # The inference must be gone, and its absence asserted rather than assumed.
            self.assertNotIn("Nothing independent judged", detail)
            self.assertNotIn("paraphrase", detail)

    def test_the_zero_is_obvious_per_card_though_invisible_in_aggregate(self) -> None:
        """The card's own framing, reproduced at the measured shape: seven cards carrying sixteen
        review artifacts between them and one carrying none. The aggregate reads healthy."""
        with tempfile.TemporaryDirectory() as t:
            reviewed = {"TC-35": 2, "TC-36": 2, "TC-37": 2, "TC-39": 5,
                        "TC-41": 3, "TC-42": 2, "TC-45": 2}
            cards = {c: (f"{c}-report.md", *[f"{c}-review-{i}.md" for i in range(n)])
                     for c, n in reviewed.items()}
            cards["TC-40"] = ("TC-40-report.md",)
            ws = plant_workspace(Path(t), cards)

            rc, payload, err = self.run_reviews(ws)

            self.assertEqual(payload["reviews"]["totals"],
                             {"cards": 8, "with_reports": 8, "unreviewed": 1}, payload["reviews"])
            self.assertEqual(len(payload["findings"]), 1, payload["findings"])
            self.assertIn("TC-40", payload["findings"][0]["detail"])
            self.assertEqual(rc, 1, err)


class AllowlistReplicaTest(unittest.TestCase):
    """The replica builder's own barrier. Without it, the builder is one more thing that can lie.

    TC-48. Four people hand-built a partial replica of this repository in one day; the fourth
    carried `~/.claude/.gitignore` and omitted `~/.claude/skills/.gitignore`, and measured a tree on
    which all three tracking surfaces answer `trackable` — the opposite of this machine, twice,
    confidently. `plant_allowlisted_home` now refuses to hand back anything partial, and these tests
    are what stop that refusal from being an unchecked claim.

    NOT SHARED WITH `agent-personas/tests/complete_tree.py`, deliberately. That builder makes a
    REPLICA OF THE SOURCE TREE, whose defining property is nesting depth relative to a skill; this
    one makes a SYNTHETIC HOME, whose defining property is its allow-lists. Importing across the two
    skills would not resolve in `install/skills/progressive-disclosure/tests/`, which is vendored
    without `agent-personas/tests/` beside it — the cross-skill import that cost this milestone a
    card.

    THE COST ACCEPTED, AND WHAT ACTUALLY DETECTS IT — restated in round 1, because the first version
    of this paragraph named a detector that could not fire. "Complete" is defined twice, for two
    different trees, and either definition could drift from the machine. Both halves now have a
    detector that takes its total from somewhere other than the constant under test:
    `test_every_gitignore_the_real_tree_has_is_planted_by_the_builder` walks the WHOLE real tree and
    lets git do the filtering (the previous version compared a hardcoded two-element list against a
    constant identical to it, and was already false), and the content half is no longer a hand-list
    at all — `required_entries` reads it out of the allow-lists, so `!/settings.json` cannot be in
    the policy and missing from the replica the way it was.
    """

    def test_the_builder_returns_only_a_complete_replica(self) -> None:
        """The positive control every refusal below is measured against."""
        with tempfile.TemporaryDirectory() as t:
            home = plant_allowlisted_home(Path(t) / "claude")
            self.assertEqual(replica_gaps(home), [])
            found = sorted(str(p.relative_to(home)) for p in home.rglob(".gitignore"))
            self.assertEqual(found, sorted(REQUIRED_GITIGNORES),
                             f"{len(found)} of {len(REQUIRED_GITIGNORES)} allow-lists planted")

    def test_the_builder_refuses_a_replica_missing_either_allowlist(self) -> None:
        """Both levels, and the nested one is the omission that was actually made.

        `IncompleteReplica`, not a skip: a fixture that degrades silently is what produced two wrong
        claims from the same shell prompt.
        """
        for relative in REQUIRED_GITIGNORES:
            with self.subTest(omitted=relative):
                with tempfile.TemporaryDirectory() as t:
                    with self.assertRaises(IncompleteReplica) as caught:
                        plant_allowlisted_home(Path(t) / "claude", omit=(relative,))
                    self.assertIn(f"`{relative}`", str(caught.exception))
                    self.assertIn("THE FIXTURE IS WRONG, NOT THE CODE", str(caught.exception))
                    self.assertNotIsInstance(caught.exception, unittest.SkipTest)

    def test_the_builder_refuses_a_replica_missing_a_file_the_allowlist_names(self) -> None:
        """`!/docs/decisions.md` negating a path that is not there is a rule about nothing."""
        for relative in ("docs/decisions.md", "skills/README.md"):
            with self.subTest(omitted=relative):
                with tempfile.TemporaryDirectory() as t:
                    with self.assertRaises(IncompleteReplica) as caught:
                        plant_allowlisted_home(Path(t) / "claude", omit=(relative,))
                    self.assertIn(f"`{relative}`", str(caught.exception))

    def test_every_path_the_allowlists_reinclude_is_actually_in_the_replica(self) -> None:
        """FINDING 5. The correspondence used to be a comment, and the comment was already false.

        `REQUIRED_FILES` was hand-written under the claim that it was "the files the allow-lists
        name", and `!/settings.json` was not in it. A negation re-including a path the replica does
        not contain is a rule about nothing, and the surrounding probes then answer about a tree
        nobody has.

        Removed by construction rather than checked: the builder plants what it READS. So this
        asserts the reading, on both directions — every negation materialised, and `settings.json`
        specifically, because that is the one that was missing and a regression would most likely
        take the form of a hand-list creeping back.
        """
        entries = required_entries()
        self.assertIn("settings.json", entries,
                      "the derivation no longer sees the negation that was missing from the "
                      "hand-list; if the policy dropped it, say so here")
        with tempfile.TemporaryDirectory() as t:
            home = plant_allowlisted_home(Path(t) / "claude")
            self.assertTrue((home / "settings.json").is_file())
            for entry in entries:
                with self.subTest(entry=entry):
                    self.assertTrue((home / entry.rstrip("/")).exists(),
                                    f"`!/{entry}` re-includes a path this replica does not have")
            # ...and the derivation is not simply "every line": the file's non-negation lines must
            # NOT appear, or "every negation is planted" is satisfied by planting everything.
            self.assertNotIn("docs/*", entries)
            self.assertNotIn("__pycache__/", entries)
            self.assertFalse((home / "MEMORY.md").exists(),
                             "the replica contains a path no allow-list names, so the GAP_SURFACES "
                             "probe for it would measure a file the fixture planted")

    def test_an_omit_value_naming_nothing_is_rejected_rather_than_answered(self) -> None:
        """FINDING 8. `omit=("Docs",)` used to return a COMPLETE replica and report success.

        A request for an incomplete tree answered with a complete one is the fail-open shape this
        whole barrier exists to remove: the caller believes it is measuring the degraded case.
        `complete_tree.build` in the other suite already rejected its unknown values; this one did
        not, and nothing said so.
        """
        for bogus in ("Docs", "docs", "skills/.GITIGNORE", "settings.jsn"):
            with self.subTest(omit=bogus):
                with tempfile.TemporaryDirectory() as t:
                    with self.assertRaises(ValueError) as caught:
                        plant_allowlisted_home(Path(t) / "claude", omit=(bogus,))
                    self.assertIn(bogus, str(caught.exception))
        # POSITIVE CONTROL: a real entry is still accepted and still produces the refusal, so the
        # rejection above is about the VALUE and not about `omit` having stopped working.
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(IncompleteReplica):
                plant_allowlisted_home(Path(t) / "claude", omit=("docs/decisions.md",))

    def test_the_walk_separates_a_governing_allowlist_from_an_inert_one(self) -> None:
        """POSITIVE CONTROL FOR THE SPLIT, on a synthetic tree, before it is trusted on the machine.

        The test below asks git which of the `.gitignore` files it walks up are actually consulted.
        That classifier is the whole of the exclusion, so it is exercised here on a tree built to
        contain one of each: a governing allow-list at a level nothing ignores, and an inert one
        inside a directory the top-level rules exclude wholesale. Without this, "four of the six are
        excluded" would be an unchecked assertion about `git check-ignore`'s behaviour.

        THE THIRD ROW IS THE ONE THAT CAUGHT A BUG. `narrowed/` is re-included and then closed by
        `/narrowed/*`, so its `.gitignore` IS ITSELF IGNORED while git still descends into the
        directory and reads it — the shape `~/.claude/docs/.gitignore` would have. The first version
        of the classifier probed the file rather than its directory and called that one inert, which
        is precisely the blind spot the walk exists to remove.
        """
        with tempfile.TemporaryDirectory() as t:
            root = git_init(Path(t) / "tree")
            (root / ".gitignore").write_text(
                "/*\n!/.gitignore\n!/kept/\n!/narrowed/\n/narrowed/*\n", encoding="utf-8")
            for relative in ("kept/.gitignore", "kept/deeper/.gitignore",
                             "narrowed/.gitignore", "dropped/.gitignore"):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_text("*.tmp\n", encoding="utf-8")

            # The distinguishing fact, asserted rather than assumed: git ignores the FILE and
            # descends into its DIRECTORY.
            self.assertEqual(git(root, "check-ignore", "-q", "--", "narrowed/.gitignore")
                             .returncode, 0)
            self.assertEqual(git(root, "check-ignore", "-q", "--", "narrowed").returncode, 1)

            governing, inert = split_gitignores_by_whether_git_consults_them(root)

            self.assertEqual(governing,
                             [".gitignore", "kept/.gitignore", "kept/deeper/.gitignore",
                              "narrowed/.gitignore"],
                             f"governing={governing} inert={inert}")
            self.assertEqual(inert, ["dropped/.gitignore"],
                             f"governing={governing} inert={inert}")
            self.assertEqual(len(governing) + len(inert), 5,
                             "the split lost or invented a file; the total must be the walk's")

    @reaches_home(
        "READS THE REAL MACHINE by design — it is the detector that stops `REQUIRED_GITIGNORES` "
        "drifting from the allow-lists this machine actually carries, and its total must come from "
        "a full walk of the tree rather than from the constant under test. The skip is already "
        "loud on stderr, which is what a tree with no `.git` sees.")
    def test_every_gitignore_the_real_tree_has_is_planted_by_the_builder(self) -> None:
        """The derivation, checked against a FULL WALK of the machine. TC-48 round 1, finding 1.

        WHAT THIS USED TO BE, because the shape matters more than the fix. It walked
        `levels = [real, real / "skills"]` — a hardcoded two-element list WHOSE CONTENTS WERE
        IDENTICAL TO `REQUIRED_GITIGNORES`. So it could not fail on a third allow-list appearing;
        it could only notice one of two known files vanishing, while four comments in this
        repository said it WALKED the tree. It was already false when it was written: this machine
        carries SIX `.gitignore` files and the detector knew two.

        That is the fleet lesson arriving in the code that was advertised as preventing it: A
        FILTERED COUNT'S TOTAL MUST COME FROM A DIFFERENT SOURCE THAN THE COUNT. A derived set
        compared against a hardcoded list identical to it is a tautology wearing the shape of a
        measurement.

        So: `rglob` the whole tree for the total, and let GIT ITSELF do the filtering. A
        `.gitignore` inside a directory the top-level allow-list excludes is never consulted by git
        at all, so it governs nothing any probe in this suite asks about — and that exclusion is
        git's answer rather than a directory name written here. Today it removes exactly the four
        under `plugins/` (the plugin manager's cache and marketplace checkouts, which `/*` excludes
        wholesale because no line re-includes them), and it would stop removing them the day
        `!/plugins/` were added — which is the correct behaviour, because that is the day they start
        deciding something.

        A `.gitignore` appearing anywhere git DOES consult — `docs/.gitignore`, say — now fails
        here, loudly, instead of halving the next replica in silence.

        THE SKIP IS LOUD, for the same reason the allow-list drift detector's is: a derivation
        detector that skips is a false zero, and "the set is right" and "nobody looked" must not
        render as the same `OK`.
        """
        real = toolchain.HOME / ".claude"
        if not (real / ".git").is_dir():
            print(f"\n!! SKIPPING THE ALLOW-LIST DERIVATION CHECK: no real work tree at {real}. "
                  f"REQUIRED_GITIGNORES was NOT compared against the machine on this run.",
                  file=sys.stderr)
            self.skipTest(f"no real work tree at {real}")

        governing, inert = split_gitignores_by_whether_git_consults_them(real)
        total = len(governing) + len(inert)

        # THE TOTAL IS REPORTED BESIDE THE COUNT, and it comes from the walk rather than from the
        # constant under test. A run that finds two files and knows two is indistinguishable from
        # the old tautology unless the number it walked past is on the page.
        context = (f"{total} `.gitignore` file(s) under {real}: {len(governing)} that git consults "
                   f"({governing}) and {len(inert)} inside excluded directories ({inert})")

        self.assertGreater(total, len(REQUIRED_GITIGNORES) - 1, f"the walk found nothing: {context}")
        self.assertGreaterEqual(len(governing), 2,
                                f"fewer than two governing allow-lists found, so the comparison "
                                f"below is close to a vacuum: {context}")
        for relative in inert:
            with self.subTest(excluded=relative):
                self.assertNotEqual(relative, ".gitignore")
                self.assertNotEqual(relative, "skills/.gitignore")
        self.assertEqual(sorted(REQUIRED_GITIGNORES), governing,
                         f"the replica builder plants {sorted(REQUIRED_GITIGNORES)} — {context}. "
                         f"Either add the new allow-list to the negations the builder reads, or, "
                         f"if git should not be consulting it, say why here. The next replica "
                         f"would otherwise measure a tree that does not exist, which is the TC-47 "
                         f"defect verbatim")


# A hermetic pair and its escaping twin, for each of the three mechanisms AND FOR EACH SPELLING OF
# THE SUBPROCESS ONE THAT IS ACTUALLY IN USE HERE — see the two rows at the end. Held as SOURCE TEXT and
# written into a scratch directory the analyser has never seen, which is what keeps this module's
# own text out of the search space — the trap that let two mutations survive a suite measuring
# itself here. Each pair differs in ONE line, named in `differs`, so a plant that is caught proves
# the mechanism was detected rather than that the file was noticed.
PLANTS = (
    ("an in-process call to check_toolchain.main()",
     "toolchain.main()",
     "with synthetic_home(toolchain, root):\n            toolchain.main()"),
    ("an in-process read of a home-derived global",
     "self.assertTrue(toolchain.CLAUDE_PLUGINS.is_dir())",
     "with synthetic_home(toolchain, root):\n            "
     "self.assertTrue(toolchain.CLAUDE_PLUGINS.is_dir())"),
    ("a subprocess launch of a home-reading script",
     'subprocess.run([sys.executable, str(SCRIPTS / "check_toolchain.py")])',
     'subprocess.run([sys.executable, str(SCRIPTS / "check_toolchain.py")], '
     'env={"HOME": str(root)})'),
    ("a direct Path.home() in the test body",
     'self.assertTrue((Path.home() / ".claude").is_dir())',
     'self.assertTrue((root / ".claude").is_dir())'),
    # TC-57 fix round. THE FOUR ABOVE WERE SHAPE-BIASED: the only subprocess row among them writes
    # `str(SCRIPTS / "check_toolchain.py")`, and a string constant inside argv is the ONE spelling
    # the original walk could see. Two real sites in this directory — `run_checker` in
    # `test_check_github_git_failure.py` and `run` in `test_validate_disclosure_reads.py` — are
    # spelled `str(NAME)` against a module-level binding, carry no string constant at all, and
    # were therefore invisible while the suite reported a clean two-way equality. A planted
    # mutation only ever proves the detector sees the shapes that were planted, so choosing all
    # four from the working shape proved nothing about the one that mattered.
    ("a subprocess launch named through a module-level binding, not a literal",
     'subprocess.run([sys.executable, str(CHECKER)])',
     'subprocess.run([sys.executable, str(CHECKER)], env={"HOME": str(root)})'),
    # And the fail-closed direction, which is new behaviour and would otherwise be untested. An
    # argv the walk cannot resolve to a script must be reported, not waved through: "the analyser
    # did not understand this" and "this is hermetic" are different answers, and treating the
    # first as the second is exactly how the two sites above survived.
    ("an interpreter launch on a script the walk cannot resolve at all",
     'subprocess.run([sys.executable, str(whatever_this_is)])',
     'subprocess.run([sys.executable, str(whatever_this_is)], env={"HOME": str(root)})'),
)

PLANT_TEMPLATE = """\
import subprocess, sys
from pathlib import Path
SCRIPTS = Path("/nowhere")
CHECKER = SCRIPTS / "check_toolchain.py"
class PlantedTest:
    def test_planted(self):
        root = Path("/tmp/x")
        {body}
"""


class ReachesHomeTest(unittest.TestCase):
    """TC-57. Nothing in this directory reads the machine it runs on without saying so.

    THE PREMISE, reproduced before any of this was written: a COMPLETE `git archive HEAD` of
    `~/.claude`, unpacked into a redirected HOME and git-initialised, ran the whole of this
    directory and failed exactly one test — `test_unknown_severity_is_loud_but_not_fatal`, with two
    `not-run` findings about the replica's absent `~/.claude/plugins` and `~/.codex/config.toml`.
    Nothing was missing from the tree. The test was not looking at the tree.

    So the property is not completeness, which TC-48 already made unfalsifiable, but HERMETICITY:
    a test either builds what it measures, or it declares that it is measuring this machine. The
    derivation lives in `hermetic.py`; what is here is the enforcement and the proof that the
    derivation can see.

    WHY THE SETS ARE COMPARED IN BOTH DIRECTIONS. A one-way check ("every escape is declared")
    leaves a mark behind on a test that has since been made hermetic, and a stale declaration is
    the same defect as a missing one wearing a machine-readable hat — the next reader trusts it.
    """

    def loaded_test_modules(self) -> list:
        """Import every `test_*.py` here, so `hermetic.MARKED` holds every mark and not only this
        file's. Modules already loaded (this one, under whatever name) are reused rather than
        re-executed: a second execution would reload `check_toolchain.py` and re-register the same
        keys, which is harmless but slow and would hide an import error behind a duplicate."""
        by_file = {}
        for module in list(sys.modules.values()):
            path = getattr(module, "__file__", None)
            if path:
                by_file[str(Path(path).resolve())] = module
        modules = []
        for path in sorted(hermetic.TESTS.glob("test_*.py")):
            existing = by_file.get(str(path.resolve()))
            modules.append(existing if existing is not None
                           else load_module(f"_hermetic_scan_{path.stem}", path))
        return modules

    def test_every_escaping_test_is_declared_and_every_declaration_still_escapes(self) -> None:
        self.loaded_test_modules()
        derived = hermetic.escaping_tests()
        declared = dict(hermetic.MARKED)

        # POSITIVE CONTROL. An analyser that returned {} and a directory with nothing to declare
        # produce the same empty diff, and one of those is a broken barrier. There are escapes
        # here on purpose — the drift detectors — so a zero means the walk went blind.
        self.assertGreaterEqual(len(derived), 5,
                                f"the derivation found {len(derived)} escaping test(s); the "
                                f"deliberate machine-readers alone are more than that, so this is "
                                f"the walk failing rather than the directory being clean")

        undeclared = {key: reasons for key, reasons in derived.items() if key not in declared}
        self.assertEqual(undeclared, {},
                         "these tests can read the machine they run on and do not say so. Either "
                         "make them hermetic (synthetic_home, or pin HOME in the child's env) or "
                         "mark them @reaches_home(reason) — and a complete replica under a "
                         "redirected HOME will fail on them until one of the two happens")

        stale = {key: why for key, why in declared.items() if key not in derived}
        self.assertEqual(stale, {},
                         "these tests are declared @reaches_home and no longer reach it. Remove "
                         "the mark: a declaration nobody has to earn is what the next reader "
                         "trusts instead of looking")

    def test_the_declared_reasons_say_what_the_test_reaches_for(self) -> None:
        """A mark with a reason nobody can act on is a mark with no reason. Cheap floor, not a
        style rule: the empty string is refused at decoration time, and this catches `"tbd"`."""
        self.loaded_test_modules()
        self.assertTrue(hermetic.MARKED, "no marks registered at all — the import scan is broken")
        for key, reason in sorted(hermetic.MARKED.items()):
            with self.subTest(test=key):
                self.assertGreater(len(reason), 80, f"{key}: {reason!r}")

    def test_an_unreasoned_mark_is_refused_at_decoration_time(self) -> None:
        with self.assertRaises(ValueError):
            hermetic.reaches_home("   ")

    # ---- proving the walk, rather than asserting it ------------------------------------------

    def test_the_walk_sees_every_shape_a_home_derived_global_is_written_in(self) -> None:
        """The matcher, not the constant. A grep-derived list in this repository was wrong on three
        of seven entries the day it was committed, and a matcher elsewhere in this programme missed
        `ast.IfExp` heads for three rounds — so the shapes are exercised rather than trusted.

        Written as a SYNTHETIC module, so the assertion's search space is a file that exists only
        inside this test and cannot be satisfied by this file's own text.
        """
        source = (
            'from pathlib import Path\n'
            'import os\n'
            'HOME = Path.home()\n'                                   # the direct call
            'A = HOME / ".claude"\n'                                 # one hop
            'B = A / "skills" / "x"\n'                               # two hops
            'C = Path.home() / "a" if os.environ else Path("/b")\n'  # an IfExp head
            'D: Path = HOME / "annotated"\n'                         # an AnnAssign
            'E = str(B)\n'                                           # through a call
            'BEFORE = LATER / "x"\n'                                 # defined above its source
            'LATER = HOME / "later"\n'
            'NOPE = Path("/etc") / "passwd"\n'                       # the negative control
            'ALSO_NOPE = Path(os.environ["X"]).expanduser()\n'       # expanduser is not a trigger
        )
        with tempfile.TemporaryDirectory() as t:
            probe = Path(t) / "probe.py"
            probe.write_text(source, encoding="utf-8")
            found = hermetic.home_derived_globals(probe)

        self.assertEqual(found, frozenset({"HOME", "A", "B", "C", "D", "E", "BEFORE", "LATER"}))
        # Stated separately rather than resting on the equality above, because the two negative
        # controls are the half most likely to be lost in a rewrite of the assertion.
        self.assertNotIn("NOPE", found)
        self.assertNotIn("ALSO_NOPE", found, "`.expanduser()` on caller input is not a HOME read")

    def test_the_reach_of_a_checker_function_is_transitive_and_the_real_one_is_not_empty(self):
        """`main()` reaches what `collect()` reaches. That is the whole mechanism of the reported
        failure — `DEFAULT_CHECKS` was swapped out and `check_plugins()` ran anyway — so it is
        asserted against the real checker rather than a fixture."""
        reach = hermetic.checker_reach()
        self.assertIn("main", reach)
        # THE TRANSITIVE STEP ITSELF: `main` calls `collect` calls `check_plugins`, and none of
        # those globals is named in `main`'s own body. Each link asserted, so a walk that stopped
        # following calls fails here and names the hop it lost.
        self.assertTrue(reach["check_plugins"], "check_plugins reaches nothing; the walk is blind")
        self.assertLessEqual(set(reach["check_plugins"]), set(reach["collect"]))
        self.assertLessEqual(set(reach["collect"]), set(reach["main"]))
        for name in ("CLAUDE_PLUGINS", "CODEX_CONFIG", "INSTALLED_PLUGINS"):
            self.assertIn(name, reach["main"],
                          f"main() no longer reaches {name}; either the checker changed or the "
                          f"transitive walk stopped following calls")
        # The negative control: a function that touches no home-derived name must report none, or
        # "everything reaches everything" would make the derivation vacuously complete.
        self.assertEqual(reach["severity_sort_key"], frozenset())

    def test_a_planted_escape_is_caught_and_its_hermetic_twin_is_not(self) -> None:
        """MUTATION, one per mechanism, each with the negative control beside it.

        A plant that is caught proves nothing on its own — a derivation returning every test it
        parses would catch all four. So each escaping body is paired with a hermetic body
        differing in one line, and BOTH directions are asserted. The bodies are asserted to differ
        before either is believed.
        """
        for description, escaping, hermetic_twin in PLANTS:
            with self.subTest(mechanism=description):
                self.assertNotEqual(escaping, hermetic_twin,
                                    "the plant and its control are the same text")
                results = {}
                for label, body in (("escaping", escaping), ("hermetic", hermetic_twin)):
                    with tempfile.TemporaryDirectory() as t:
                        planted = Path(t) / "test_planted.py"
                        planted.write_text(PLANT_TEMPLATE.format(body=body), encoding="utf-8")
                        results[label] = hermetic.escaping_tests(Path(t))

                self.assertEqual(sorted(results["escaping"]),
                                 [("test_planted.py", "PlantedTest.test_planted")],
                                 f"{description} was planted and the derivation did not name it")
                self.assertEqual(results["hermetic"], {},
                                 f"the hermetic form of {description} was reported as an escape; "
                                 f"a barrier that fires on the fix teaches people to delete it")

    def test_a_directory_with_nothing_to_find_yields_nothing(self) -> None:
        """The other end of the same control. If `escaping_tests` reported a finding here, every
        assertion above would be measuring a matcher that says yes to everything."""
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "test_clean.py").write_text(
                PLANT_TEMPLATE.format(body='self.assertTrue(root.is_dir())'), encoding="utf-8")
            self.assertEqual(hermetic.escaping_tests(Path(t)), {})

    # ---- the escape hatch cannot become a lie -------------------------------------------------

    def test_synthetic_home_rebinds_every_home_derived_global(self) -> None:
        """`synthetic_home` is credited by the derivation with rebinding EVERYTHING. The day it
        rebinds nine of ten, every test inside it reads as hermetic and one of them is not — which
        is this card's defect reappearing inside its own remedy.

        The expected set comes from the CHECKER, and the observed set from the MODULE OBJECT after
        the rebind. Two sources, so the comparison is not the constant checking itself.
        """
        expected = hermetic.home_derived_globals(hermetic.CHECKER)
        self.assertGreaterEqual(len(expected), 5, f"the derivation went blind: {sorted(expected)}")
        real = {name: getattr(toolchain, name) for name in expected}

        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            with synthetic_home(toolchain, root):
                inside = {name: Path(getattr(toolchain, name)) for name in expected}
                for name, value in sorted(inside.items()):
                    with self.subTest(name=name):
                        self.assertTrue(value == root or root in value.parents,
                                        f"{name} still points at {value}")
                # The relative shape is preserved, or the rebind would be pointing every global at
                # the same place and the checks under it would measure a tree of one directory.
                self.assertEqual(
                    sorted(str(v.relative_to(root)) for v in inside.values() if v != root),
                    sorted(str(Path(v).relative_to(real["HOME"]))
                           for n, v in real.items() if n != "HOME"))

        self.assertEqual({name: getattr(toolchain, name) for name in expected}, real,
                         "synthetic_home did not restore the globals it borrowed")

    @reaches_home(
        "READS THE REAL MACHINE'S HOME as the degenerate argument — pointing `synthetic_home` at "
        "`Path.home()` is the one input for which the rebind lands everything back where it "
        "started, and that is the case whose refusal is under test. It opens no file. This is also "
        "the runtime half of the barrier: the static rule credits any `synthetic_home(...)` call "
        "with rebinding everything, so the degenerate argument is caught here rather than there.")
    def test_a_synthetic_home_that_rebound_nothing_is_refused(self) -> None:
        """The self-assertion inside `synthetic_home`, exercised. Pointing it at the real HOME is
        the degenerate case: every global lands back where it started, and yielding then would
        hand the caller a block that reads the machine while reading as hermetic."""
        with self.assertRaises(hermetic.NotHermetic):
            with synthetic_home(toolchain, toolchain.HOME):
                pass
        self.assertEqual(toolchain.HOME, Path.home(), "the failed rebind was not undone")

    @reaches_home(
        "ARITHMETIC ONLY — it opens nothing. The annotation under test names the machine a marked "
        "failure was measured on, so the expected text is literally `Path.home()`, and asserting "
        "it against a synthetic value would only prove the fixture agrees with itself. Both of "
        "these two marks were placed because the derivation caught tests written in this same "
        "commit, which is the barrier applying to its own author.")
    def test_a_declared_failure_names_the_machine_it_was_measured_on(self) -> None:
        """The mark's second job. A `@reaches_home` test that fails on a replica must not read like
        an ordinary defect — that misreading is how three implementers were nearly filed against
        under TC-48, from a half-tree rather than a redirected HOME."""
        class Host(unittest.TestCase):
            @hermetic.reaches_home("a reason long enough to be actionable, stated for the probe "
                                   "so that the length floor above is satisfied by this fixture "
                                   "exactly as it is by a real mark")
            def runTest(self):
                self.fail("the underlying complaint")

        with self.assertRaises(AssertionError) as caught:
            Host().runTest()
        message = str(caught.exception)
        self.assertIn("the underlying complaint", message)
        self.assertIn("@reaches_home", message)
        self.assertIn(str(Path.home()), message)
        # ...and the probe did NOT enter the registry. A locally-defined class is unreachable by a
        # derivation that only walks module-level classes, so a key for it would be permanently
        # stale and the set-equality test above would fail for a reason that is not a defect.
        self.assertEqual([k for k in hermetic.MARKED if "<locals>" in k[1]], [])


class LeanInstructionMirrorTests(unittest.TestCase):
    def compare(self, left, right):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claude, codex = root / "CLAUDE.md", root / "AGENTS.md"
            claude.write_text(left)
            codex.write_text(right)
            old = toolchain.CLAUDE_MD, toolchain.CODEX_MD
            try:
                toolchain.CLAUDE_MD, toolchain.CODEX_MD = claude, codex
                return toolchain.check_instructions()
            finally:
                toolchain.CLAUDE_MD, toolchain.CODEX_MD = old

    def test_lean_rules_are_compared(self):
        text = "\n".join(start + "\nshared rule\n" + end
                         for start, end in toolchain.ROUTED_MIRRORED)
        self.assertEqual(self.compare(text, text), [])
        findings = self.compare(text, text.replace("shared rule", "changed rule"))
        self.assertTrue(any(severity == "critical" for severity, _ in findings))

    def test_mixed_rollout_is_not_a_mirror_pass(self):
        lean = "\n".join(start + "\nshared\n" + end
                         for start, end in toolchain.ROUTED_MIRRORED)
        legacy = "\n".join(start + "\nshared\n" + end
                           for start, end in toolchain.MIRRORED)
        self.assertTrue(self.compare(lean, legacy))
        self.assertTrue(self.compare(legacy, lean))

    def test_legacy_rules_remain_checkable(self):
        text = "\n".join(start + "\nshared\n" + end
                         for start, end in toolchain.MIRRORED)
        self.assertEqual(self.compare(text, text), [])


if __name__ == "__main__":
    unittest.main()
