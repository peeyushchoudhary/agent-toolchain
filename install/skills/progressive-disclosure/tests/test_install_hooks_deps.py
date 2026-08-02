"""Every git hook install_hooks.py writes, and the one thing none of them may do: claim a guard
that is not there.

THE DEFECT THESE TESTS PIN. With `push_guard.py` absent from `~/.claude` and everything else
present, measured twice, independently:

    install_hooks rc=0
      pre-push installed
        blocks: credentials in the pushed range, files over 10 MB (not configurable),
        direct pushes to main.

    $ wc -c .git/hooks/pre-push  ->  419
    $ grep -c push_guard .git/hooks/pre-push  ->  1

Exit 0, a hook on disk, three claims, and every one of the three false. That is worse than no guard
at all, because the report is what anyone would check — a machine restored in the wrong order says
it is protected.

WHAT IS ACTUALLY BEING TESTED, and it is not "the pre-push branch got a check". Two other blocks in
that file already handled their own absence, the identifier guard twice and loudly, and the pre-push
branch did not; nothing made the asymmetry visible, so a fourth hook would have been written the
same way. The class is that a hook can be DECLARED INSTALLED without anything verifying the thing it
invokes exists. So, as with `read_doc` in validate_disclosure.py, the remedy is the removal of the
bypass, and the tests come in two layers:

  1. Behavioural — for each hook, with its dependency absent, the hook is refused, no success line
     is printed, the summary does not claim it, and the process exits non-zero.
  2. Structural — `ChokepointTest` enumerates the hook templates FROM THE SOURCE and asserts each
     one's dependency is visible to the dependency resolver, that no hook is written outside
     `install_hook`, and that no success or claims line is printed outside it. That layer covers
     the hook someone adds next year without having read any of this.

Run: python3 skills/progressive-disclosure/tests/test_install_hooks_deps.py
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
INSTALLER = SCRIPTS / "install_hooks.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


installer = load_module("install_hooks_deps_test", INSTALLER)


# ------------------------------------------------------------------------------------------------
# Fixture: a scratch HOME, so no test can read, write or install into the real one.
# ------------------------------------------------------------------------------------------------

class ScratchHomeMixin:
    """A complete copy of the skill under a throwaway HOME, with knobs to remove one script.

    A copy rather than a stub, because the thing under test resolves `$HOME/.claude/...` paths and
    reads module constants out of the real scripts to derive its claims. A stubbed tree would test
    the stub. Nothing here ever touches the developer's own ~/.claude or any project repository.
    """

    def scratch_home(self, *, remove: tuple[str, ...] = ()) -> Path:
        home = Path(tempfile.mkdtemp(prefix="pd-hookdeps-home-"))
        self.addCleanup(shutil.rmtree, home, True)
        dest = home / ".claude" / "skills" / "progressive-disclosure"
        dest.parent.mkdir(parents=True)
        shutil.copytree(SKILL, dest, ignore=shutil.ignore_patterns("__pycache__"))
        for name in remove:
            (dest / "scripts" / name).unlink(missing_ok=True)
        return home

    def scratch_repo(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="pd-hookdeps-repo-"))
        self.addCleanup(shutil.rmtree, root, True)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        (root / "docs" / "agents").mkdir(parents=True)
        (root / "docs" / "agents" / "README.md").write_text(
            '# Agents index\n\n<!-- agent-personas: {"mode":"base-only","reason":"fixture"} -->\n',
            encoding="utf-8")
        (root / "AGENTS.md").write_text(
            "# Fixture\n\nRoute: [index](docs/agents/README.md)\n", encoding="utf-8")
        return root

    def install(self, home: Path, root: Path, *flags: str) -> tuple[int, str]:
        """Run the real CLI under the scratch HOME and return (exit code, combined output).

        A subprocess, and the code is taken from the process itself. Never from the tail of a
        pipeline — `cmd | tail; echo $?` reports tail's status, and the exit code IS the finding
        here: rc=0 was half of what made the measured defect dangerous.
        """
        script = home / ".claude" / "skills" / "progressive-disclosure" / "scripts" / "install_hooks.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(root), *flags],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return proc.returncode, proc.stdout + proc.stderr


# ------------------------------------------------------------------------------------------------
# 1. Behavioural
# ------------------------------------------------------------------------------------------------

class RedFixtureTest(ScratchHomeMixin, unittest.TestCase):
    """The exact reproduction and its fix, in one class so neither can drift from the other."""

    def test_pre_push_without_its_guard_is_refused_not_claimed(self):
        """The whole defect. Before the fix: rc=0, a 419-byte hook, three false claims."""
        home = self.scratch_home(remove=("push_guard.py",))
        root = self.scratch_repo()
        rc, out = self.install(home, root)

        self.assertEqual(rc, 1, out)                              # was 0
        self.assertNotIn("pre-push installed", out)               # was printed
        self.assertNotIn("pre-push updated", out)
        self.assertIn("pre-push NOT INSTALLED", out)
        self.assertIn("push_guard.py", out)
        self.assertIn("NOT INSTALLED: pre-push", out)             # the summary

        # Not one of the three false claims survives.
        self.assertNotIn("credentials in the pushed range", out)
        self.assertNotIn("10 MB", out)
        self.assertNotIn("direct pushes to main", out)

        # And no wrapper around nothing was left on disk.
        self.assertFalse((root / ".git" / "hooks" / "pre-push").exists(), out)

    def test_an_existing_pre_push_hook_is_left_exactly_as_it_was(self):
        """Refusing must not be a downgrade: the hook already there is the better of the states."""
        home = self.scratch_home(remove=("push_guard.py",))
        root = self.scratch_repo()
        hook = root / ".git" / "hooks" / "pre-push"
        hook.parent.mkdir(parents=True, exist_ok=True)
        original = "#!/bin/sh\necho mine\n"
        hook.write_text(original, encoding="utf-8")

        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertEqual(hook.read_text(encoding="utf-8"), original, out)

    def test_one_missing_dependency_does_not_cost_the_hooks_that_are_fine(self):
        home = self.scratch_home(remove=("push_guard.py",))
        root = self.scratch_repo()
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertIn("pre-commit installed", out)
        self.assertTrue((root / ".git" / "hooks" / "pre-commit").is_file(), out)


class EveryHookTest(ScratchHomeMixin, unittest.TestCase):
    """Not only pre-push. Each hook, with its own dependency absent, must be refused the same way."""

    def test_pre_commit_without_the_validator(self):
        home = self.scratch_home(remove=("validate_disclosure.py",))
        root = self.scratch_repo()
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertIn("pre-commit NOT INSTALLED", out)
        self.assertNotIn("pre-commit installed", out)
        self.assertFalse((root / ".git" / "hooks" / "pre-commit").exists(), out)

    def test_commit_msg_without_the_identifier_guard(self):
        home = self.scratch_home(remove=("identifier_guard.py",))
        root = self.scratch_repo()
        rc, out = self.install(home, root, "--public")
        self.assertEqual(rc, 1, out)
        self.assertIn("commit-msg NOT INSTALLED", out)
        self.assertNotIn("commit-msg installed", out)
        # --public renders the identifier stanza into pre-commit too, so that hook is refused as
        # well rather than installed as a half-guard.
        self.assertIn("pre-commit NOT INSTALLED", out)
        self.assertFalse((root / ".git" / "hooks" / "commit-msg").exists(), out)

    def test_pre_push_when_the_guards_own_import_is_missing(self):
        """push_guard.py imports SECRET_PATTERNS from validate_disclosure.py at module scope.

        Present-but-broken-chain is the case a naive `is_file()` on the direct dependency passes.
        Without that import the guard exits 2 on every push, so claiming the pushed range is
        scanned for credentials would be false in a second, quieter way.
        """
        home = self.scratch_home(remove=("validate_disclosure.py",))
        root = self.scratch_repo()
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertIn("pre-push NOT INSTALLED", out)
        self.assertIn("validate_disclosure.py", out)


class RegressionTest(ScratchHomeMixin, unittest.TestCase):
    """A complete install must still install every hook, and its claims must be true."""

    def test_complete_install_installs_everything_and_exits_zero(self):
        home = self.scratch_home()
        root = self.scratch_repo()
        rc, out = self.install(home, root)
        self.assertEqual(rc, 0, out)
        self.assertIn("pre-commit installed", out)
        self.assertIn("pre-push installed", out)
        self.assertNotIn("NOT INSTALLED", out)
        for name in ("pre-commit", "pre-push"):
            hook = root / ".git" / "hooks" / name
            self.assertTrue(hook.is_file(), f"{name} missing\n{out}")
            self.assertIn(installer.BEGIN, hook.read_text(encoding="utf-8"))

    def test_the_printed_claims_match_the_guard_that_was_installed(self):
        """Derived, not recited: the number and the branch names come from push_guard.py itself."""
        home = self.scratch_home()
        root = self.scratch_repo()
        rc, out = self.install(home, root)
        self.assertEqual(rc, 0, out)
        guard = home / ".claude" / "skills" / "progressive-disclosure" / "scripts" / "push_guard.py"
        mb = installer._module_constant(guard, "MAX_FILE_MB")
        branches = installer._module_constant(guard, "DEFAULT_BRANCHES")
        self.assertIsNotNone(mb, "MAX_FILE_MB is no longer a source literal in push_guard.py")
        self.assertIn(f"files over {mb:g} MB", out)
        for ref in branches:
            self.assertIn(ref.rsplit("/", 1)[-1], out)

    def test_a_changed_limit_changes_the_printed_claim(self):
        """The claim tracks the guard. A literal beside the install would not have moved."""
        home = self.scratch_home()
        guard = home / ".claude" / "skills" / "progressive-disclosure" / "scripts" / "push_guard.py"
        guard.write_text(
            guard.read_text(encoding="utf-8").replace("MAX_FILE_MB = 10.0", "MAX_FILE_MB = 42.0", 1),
            encoding="utf-8")
        rc, out = self.install(home, self.scratch_repo())
        self.assertEqual(rc, 0, out)
        self.assertIn("files over 42 MB", out)
        self.assertNotIn("files over 10 MB", out)

    def test_public_install_is_complete_and_claims_both_halves(self):
        home = self.scratch_home()
        root = self.scratch_repo()
        rc, out = self.install(home, root, "--public")
        self.assertEqual(rc, 0, out)
        self.assertIn("commit-msg installed", out)
        self.assertIn("STAGED CONTENT", out)
        self.assertIn("private-identifiers.txt", out)

    def test_check_and_uninstall_still_work(self):
        home = self.scratch_home()
        root = self.scratch_repo()
        self.assertEqual(self.install(home, root)[0], 0)
        rc, out = self.install(home, root, "--check")
        self.assertEqual(rc, 0, out)
        self.assertIn("pre-push secret/size/main guard: present", out)
        rc, out = self.install(home, root, "--uninstall")
        self.assertEqual(rc, 0, out)
        self.assertFalse((root / ".git" / "hooks" / "pre-push").exists(), out)

    def test_a_non_git_directory_is_still_a_clean_zero(self):
        home = self.scratch_home()
        plain = Path(tempfile.mkdtemp(prefix="pd-hookdeps-plain-"))
        self.addCleanup(shutil.rmtree, plain, True)
        rc, out = self.install(home, plain)
        self.assertEqual(rc, 0, out)
        self.assertIn("not a git repository", out)

    def test_help_still_works(self):
        rc, out = self.install(self.scratch_home(), Path("."), "--help")
        self.assertEqual(rc, 0, out)


class PreCommitTailTest(ScratchHomeMixin, unittest.TestCase):
    """The rendered pre-commit hook must not report a finding the validator never made.

    Riding along because it is the same class in the same file: prose overstating the check. Since
    validate_disclosure.py started distinguishing 1 (the route is broken) from 2 (the route could
    not be read), the single tail line "the route is broken" has been asserting a finding for a run
    that reached no verdict.
    """

    def rendered(self) -> str:
        return installer.render_pre_commit()

    def test_exit_one_still_says_the_route_is_broken(self):
        self.assertIn("the agent disclosure route is broken", self.rendered())

    def test_a_non_one_failure_says_not_checked_instead(self):
        body = self.rendered()
        self.assertIn("NOT CHECKED", body)
        self.assertIn("not a clean result", body)

    def test_the_two_are_actually_distinguished_by_the_shell(self):
        """Run the rendered block against a stub validator that exits 2, then one that exits 1."""
        for code, expect_broken in ((2, False), (1, True)):
            with self.subTest(code=code):
                home = Path(tempfile.mkdtemp(prefix="pd-hookdeps-tail-"))
                self.addCleanup(shutil.rmtree, home, True)
                scripts = home / ".claude" / "skills" / "progressive-disclosure" / "scripts"
                scripts.mkdir(parents=True)
                (scripts / "validate_disclosure.py").write_text(
                    f"import sys\nprint('stub output')\nsys.exit({code})\n", encoding="utf-8")
                repo = self.scratch_repo()
                hook = repo / "hook.sh"
                hook.write_text("#!/bin/sh\n" + self.rendered(), encoding="utf-8")
                proc = subprocess.run(["sh", str(hook)], cwd=repo, capture_output=True, text=True,
                                      env={**os.environ, "HOME": str(home)}, timeout=60)
                out = proc.stdout + proc.stderr
                self.assertEqual(proc.returncode, code, out)
                self.assertEqual("the agent disclosure route is broken" in out, expect_broken, out)
                if not expect_broken:
                    self.assertIn("NOT CHECKED", out)


# ------------------------------------------------------------------------------------------------
# 2. Structural — the layer that covers the hook nobody has written yet.
# ------------------------------------------------------------------------------------------------

class ChokepointTest(unittest.TestCase):
    """Asserted against the source, not against behaviour.

    A behavioural suite pins the hooks that exist today. This pins the RULE. Three properties, and
    together they make it impossible to declare a hook installed without verifying what it invokes:

      1. Every hook template in the file names its dependency in a form the resolver can see.
      2. No hook is written outside `install_hook`.
      3. No success or claims line is printed outside `install_hook`.
    """

    def setUp(self):
        self.source = INSTALLER.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    # -- 1 -----------------------------------------------------------------------------------

    def hook_templates(self) -> list[tuple[str, str]]:
        """Module-level string constants that invoke a script under $HOME. Enumerated, not listed.

        This is the half that covers a hook added later: the template cannot be added to the file
        without appearing here, and if it names its script in a form `HOOK_SCRIPT_REF` cannot read,
        the assertion below fails and the author finds out at test time rather than at restore time.
        """
        found = []
        for node in self.tree.body:
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(node, ast.AnnAssign) else [])
            if not (len(targets) == 1 and isinstance(targets[0], ast.Name)):
                continue
            if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                continue
            text = node.value.value
            if ".claude/" in text and ".py" in text:
                found.append((targets[0].id, text))
        return found

    def test_there_are_hook_templates_to_check(self):
        """A guard on the guard: if the enumeration silently found nothing, everything below passes
        vacuously and the whole structural layer would be theatre."""
        self.assertGreaterEqual(len(self.hook_templates()), 4, self.hook_templates())

    def test_every_hook_template_names_its_dependency_where_the_resolver_can_see_it(self):
        offenders = []
        for name, text in self.hook_templates():
            # Every `$HOME/.claude/....py` mention in the template, however it is written.
            mentioned = set(re.findall(r"\$HOME/(\.claude/[A-Za-z0-9._/+-]+\.py)", text))
            seen = {str(p.relative_to(Path.home())) for p in installer.block_dependencies(text)}
            for miss in sorted(mentioned - seen):
                offenders.append(
                    f"{name}: invokes {miss} but block_dependencies() does not see it — it must be "
                    f'a double-quoted "$HOME/..." literal, or the installer will claim this hook '
                    f"installed without checking that script exists")
            if mentioned and not seen:
                offenders.append(f"{name}: no dependency resolved at all")
        self.assertEqual(offenders, [], "hook dependencies invisible to the chokepoint:\n  "
                                        + "\n  ".join(offenders))

    def test_a_missing_dependency_is_detected_for_every_template(self):
        """End of the same argument, from the other side: point HOME at an empty directory and
        every template must report at least one missing script."""
        empty = Path(tempfile.mkdtemp(prefix="pd-hookdeps-empty-"))
        self.addCleanup(shutil.rmtree, empty, True)
        real_home = Path.home
        try:
            Path.home = staticmethod(lambda: empty)          # type: ignore[assignment]
            for name, text in self.hook_templates():
                with self.subTest(template=name):
                    self.assertTrue(installer.missing_dependencies(text),
                                    f"{name} reports no missing dependency under an empty HOME")
        finally:
            Path.home = real_home                            # type: ignore[assignment]

    # -- 2 and 3 ---------------------------------------------------------------------------------

    def _enclosing_function(self, target) -> str:
        best = "<module>"
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.lineno <= target.lineno <= getattr(node, "end_lineno", node.lineno):
                best = node.name
        return best

    def test_no_git_hook_is_written_outside_the_chokepoint(self):
        """`write_hook` still does the surgery; it may only be reached through `install_hook`.

        `remove_hook_block` is the uninstall path and writes nothing new, so it is not a way to
        declare a hook installed.
        """
        offenders = []
        for node in ast.walk(self.tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "write_hook":
                continue
            fn = self._enclosing_function(node)
            if fn != "install_hook":
                offenders.append(f"{fn}() line {node.lineno}")
        self.assertEqual(offenders, [], "write_hook() called outside install_hook():\n  "
                                        + "\n  ".join(offenders))

    # The one function allowed to print a success line without going through `install_hook`, with
    # its reason. Adding a second means editing this dict in a diff a reviewer sees, rather than
    # adding a print at the bottom of `main` — which is exactly how the three false claims got in.
    CLAIMS_OUTSIDE_THE_CHOKEPOINT = {
        "install_graph_hook": "its dependency is the `graphify` BINARY on PATH, not a script named "
                              "inside a hook block, so block_dependencies() cannot see it — "
                              "graphify_available() is the equivalent check and it runs first",
    }

    # A print may say the word without making the claim. These are the negations, listed rather
    # than pattern-matched so that "installed" in a NEW phrasing trips the test and has to be
    # thought about — the failure mode being guarded is exactly a reassuring sentence nobody read.
    NEGATIONS = ("not installed", "cannot be installed", "is not installed", "never installed",
                 "does not have")

    def test_no_success_or_claims_line_is_printed_outside_the_chokepoint(self):
        marks = ("installed", "blocks:")
        offenders = []
        for node in ast.walk(self.tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "print"):
                continue
            fn = self._enclosing_function(node)
            if fn in ("install_hook", *self.CLAIMS_OUTSIDE_THE_CHOKEPOINT):
                continue
            literals = " ".join(
                n.value for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)).lower()
            cleaned = literals
            for negation in self.NEGATIONS:
                cleaned = cleaned.replace(negation, "")
            for mark in marks:
                if mark in cleaned:
                    offenders.append(f"{fn}() line {node.lineno}: prints {mark!r}")
        self.assertEqual(offenders, [], "success/claims lines outside install_hook():\n  "
                                        + "\n  ".join(offenders))

    def test_there_is_no_opt_out(self):
        """No flag, no environment variable. 'Install it anyway' is a request to be told a guard is
        there when nobody knows whether it is."""
        lowered = self.source.lower()
        for forbidden in ("--force", "--skip-dep", "--no-dep-check", "--allow-missing",
                          "pd_skip_dep_check", "pd_allow_missing"):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
