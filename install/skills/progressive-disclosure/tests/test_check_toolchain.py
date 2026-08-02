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
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            installed = tmp / "home" / ".claude" / "skills"
            (installed / "alpha").mkdir(parents=True)
            (tmp / "repo" / "install" / "skills" / "alpha").mkdir(parents=True)

            saved_skills, saved_argv = toolchain.CLAUDE_SKILLS, sys.argv
            toolchain.CLAUDE_SKILLS = installed
            saved_check = toolchain.check_vendored
            toolchain.check_vendored = (
                lambda _root, _rules=(): ([("warn", "synthetic non-critical finding")], []))
            sys.argv = ["check_toolchain.py", "--vendored", str(tmp / "repo")]
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    rc = toolchain.main()
            finally:
                toolchain.CLAUDE_SKILLS = saved_skills
                toolchain.check_vendored = saved_check
                sys.argv = saved_argv

            self.assertEqual(rc, 1, buffer.getvalue())
            self.assertIn("synthetic non-critical finding", buffer.getvalue())
            self.assertNotIn("clean", buffer.getvalue())


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
            # Four, not three: TC-41's plugin surface joined them, and an empty HOME cannot
            # enumerate it either — ~/.codex/config.toml is absent, so the Codex plugin surface is
            # UNKNOWN rather than empty. Updated to the new value rather than widened to a subset
            # check, for the reason `test_hook_mode_emits_no_stray_output_shape` gives about
            # widening an assertion to accommodate a new value.
            self.assertEqual({item["check"] for item in payload["not_evaluated"]},
                             {"personas", "instruction mirror", "Codex skill mirror",
                              "plugin surface"})

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
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / ".claude").mkdir()
            saved = (toolchain.DEFAULT_CHECKS, sys.argv)
            toolchain.DEFAULT_CHECKS = (
                ("synthetic", "synthetic fine", lambda: [("advisory", "a brand new level"),
                                                         ("critical", "a known one")]),
            )
            sys.argv = ["check_toolchain.py"]
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    rc = toolchain.main()
            finally:
                toolchain.DEFAULT_CHECKS, sys.argv = saved

            out = buffer.getvalue()
            self.assertEqual(rc, 1, out)  # from the critical, never from the unknown level
            self.assertLess(out.index("a brand new level"), out.index("a known one"),
                            "an unrecognised severity must sort loudest, above critical")

            # And alone, it must not be fatal.
            toolchain.DEFAULT_CHECKS = (
                ("synthetic", "synthetic fine", lambda: [("advisory", "a brand new level")]),
            )
            sys.argv = ["check_toolchain.py"]
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    rc = toolchain.main()
            finally:
                toolchain.DEFAULT_CHECKS, sys.argv = saved
            self.assertEqual(rc, 0, buffer.getvalue())


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
            self.assertIn("1 excluded and NOT compared: vendorskill", r.stdout)
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
            self.assertIn("excluded and NOT compared", after.stdout)

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
            self.assertIn("1 excluded and NOT compared: vendorskill", r.stdout)


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
        """
        tree = ast.parse(self.SOURCE)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) \
                        and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))
        offenders = [f"line {n.lineno}: {n.value!r}" for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and id(n) not in docstrings and "graphify" in n.value.lower()]
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
        """
        tree = ast.parse(self.SOURCE)
        emitted: dict[str, int] = {}

        # Module-level data is not an emission. Collect the whole subtree of every top-level
        # assignment so `MIRRORED`'s entries cannot be mistaken for findings.
        module_data: set[int] = set()
        for stmt in tree.body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and stmt.value is not None:
                module_data.update(id(n) for n in ast.walk(stmt.value))

        def record(node: ast.AST) -> None:
            if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
                return
            head = node.elts[0]
            if isinstance(head, ast.Constant) and isinstance(head.value, str):
                emitted.setdefault(head.value, node.lineno)
            elif isinstance(head, ast.Name):
                # A severity emitted through a module constant — `NOT_RUN` — is still an emitted
                # severity. Resolving it is what makes the third state covered by this rule rather
                # than invisible to it, which is how the previous whitelist came to hold only two.
                value = getattr(toolchain, head.id, None)
                if isinstance(value, str):
                    emitted.setdefault(value, node.lineno)

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
        # Three, because the file emits exactly `critical`, `warn` and `not-run` today and the
        # not-run emissions are the ones a naive matcher loses.
        self.assertGreaterEqual(len(emitted), 3, emitted)
        self.assertIn(toolchain.NOT_RUN, emitted,
                      "the matcher no longer reaches the not-run emission sites")
        unranked = {s: line for s, line in emitted.items() if s not in toolchain.SEVERITY_RANK}
        self.assertEqual(unranked, {}, f"emitted but unranked (visibility and blocking are both "
                                       f"undefined for these): {unranked}")


class PluginSurfaceTest(unittest.TestCase):
    """TC-41. The plugin surface: enumerated, classified, never approved.

    THE CARD'S DEFECT, in one sentence: a plugin shipping `agents/reviewer.md` replaces a judging
    persona from a directory that the roster, the judging allow-list and `sync_personas.py --check`
    all do not look at. Everything below either proves that is now seen, or proves that a failed
    look cannot be mistaken for a clear one.

    Every case runs against a GREEN BASELINE built by `green_home` and then mutated, and every
    mutation is asserted to have taken effect before anything is concluded from it — a fixture that
    silently failed to apply produces a pass that proves nothing.
    """

    # ---- fixture construction -------------------------------------------------------------

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

        rc, payload, err = self.run_json(home)
        self.assertEqual(rc, 0, err)
        self.assertEqual(payload["status"], "clean", payload["summary"])
        return home

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
        no action that could clear it. The paragraph belongs in --json."""
        with tempfile.TemporaryDirectory() as t:
            home = self.green_home(Path(t))
            _, payload, _ = self.run_json(home)

            self.assertEqual(payload["status"], "clean")
            # The clause the exclusion contributes, isolated — the rest of the summary is the
            # clean line and is not this test's subject.
            clause = payload["summary"].split("1 excluded and NOT compared: ", 1)[1]
            self.assertLess(len(clause), 120, clause)
            self.assertNotIn("UNKNOWN, not known to be false", payload["summary"])
            # ...and the full text is still available where a consumer reads it deliberately.
            self.assertIn("UNKNOWN, not known to be false",
                          payload["plugins"]["codex"]["why_not_classified"])

    # ---- no second copy of the roster, and no conforming set ------------------------------

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


if __name__ == "__main__":
    unittest.main()
