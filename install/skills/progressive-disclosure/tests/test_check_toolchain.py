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

import contextlib
import importlib.util
import io
import os
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
            self.assertEqual(len(payload), 1, payload)
            self.assertEqual(payload[0]["severity"], "critical")
            self.assertIn("stale published content", payload[0]["detail"])

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
                findings = toolchain.check_vendored(vendored)
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
            toolchain.check_vendored = lambda _root: [("warn", "synthetic non-critical finding")]
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

            self.assertIn(r.returncode, (0, 1))
            if r.stdout:
                self.assertTrue(r.stdout.startswith("AGENT CONTEXT:"), r.stdout)
                # The default header, not the repository-scoped one: this mode IS machine-global.
                self.assertIn("affects every project", r.stdout)

    def test_json_mode_is_parseable(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as t:
            r = self.run_default(Path(t), "--json")

            payload = json.loads(r.stdout)
            self.assertIsInstance(payload, list)
            for item in payload:
                self.assertEqual(sorted(item), ["detail", "severity"])


if __name__ == "__main__":
    unittest.main()
