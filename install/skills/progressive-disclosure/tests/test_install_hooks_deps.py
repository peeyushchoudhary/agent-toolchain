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

from hermetic import reaches_home


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

    # -- the declaration, as the repository records it -----------------------------------------

    ROUTE = Path("docs") / "agents" / "README.md"

    def declare(self, root: Path, body: str = '{"reason":"a docs repo","date":"2026-01-02"}') -> None:
        """Write a public-exception marker by hand, at column zero, outside any code block."""
        p = root / self.ROUTE
        p.write_text(p.read_text(encoding="utf-8").rstrip("\n")
                     + f"\n\n<!-- public-exception: {body} -->\n", encoding="utf-8")

    def undeclare(self, root: Path) -> None:
        """The deliberate removal: delete the marker line from the tracked file."""
        p = root / self.ROUTE
        p.write_text("\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines()
                               if "public-exception" not in ln) + "\n", encoding="utf-8")

    def markers(self, root: Path) -> int:
        return (root / self.ROUTE).read_text(encoding="utf-8").count("public-exception")

    def guard(self, root: Path) -> tuple[bool, bool]:
        """(pre-commit has the identifier stanza, commit-msg has it) — read off disk, not inferred."""
        def has(name: str) -> bool:
            p = root / ".git" / "hooks" / name
            return p.is_file() and "identifier_guard.py" in p.read_text(encoding="utf-8")
        return has("pre-commit"), has("commit-msg")

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


class DeclarationTest(ScratchHomeMixin, unittest.TestCase):
    """PUBLIC IS STATE THE REPOSITORY DECLARES. The measured defect, and the four behaviours.

    Reproduced on a scratch repository, exit codes taken from the process:

        $ install_hooks.py REPO --public   ->  EXIT=0, identifier guard PRESENT in both hooks
        $ install_hooks.py REPO            ->  EXIT=0, identifier guard ABSENT from both hooks
          pre-commit updated (existing hook preserved)      <- no mention of the guard it removed

    The second command is the one every document tells you to run. That is what makes this the worst
    shape in the class the earlier tests in this file pin: not a restore in the wrong order or a
    renamed script, but FOLLOWING THE INSTRUCTIONS silently stripping the leak guard off a public
    repository and reporting success.

    The remedy is the deny-list-opt-out shape — removal by construction, not validation. The guard
    now follows from a `public-exception` marker in the repository's own routed contract, read by
    `check_github.py`'s parser (the same one, imported, never a second copy), so taking the guard
    away requires deleting a line from a tracked file.
    """

    # -- behaviour 2: --public WRITES the declaration -------------------------------------------

    def test_public_writes_the_declaration_once_and_says_where(self):
        home, root = self.scratch_home(), self.scratch_repo()
        self.assertEqual(self.markers(root), 0)
        rc, out = self.install(home, root, "--public")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.markers(root), 1, out)
        self.assertIn("public declaration: recorded in docs/agents/README.md", out)
        self.assertEqual(self.guard(root), (True, True), out)

    def test_public_twice_does_not_write_a_second_marker(self):
        """The parser rejects two markers outright, so idempotence here is not a nicety."""
        home, root = self.scratch_home(), self.scratch_repo()
        self.assertEqual(self.install(home, root, "--public")[0], 0)
        rc, out = self.install(home, root, "--public")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.markers(root), 1, out)
        self.assertIn("already declared", out)

    def test_the_written_marker_is_honoured_by_check_githubs_own_parser(self):
        """Written by one tool, read by the other. If these ever disagree the declaration is a
        decoration: this repository would be guarded locally and still CRITICAL in the report."""
        home, root = self.scratch_home(), self.scratch_repo()
        self.assertEqual(self.install(home, root, "--public")[0], 0)
        cg = load_module("cg_written", SCRIPTS / "check_github.py")
        self.assertEqual(cg.public_exception(root)["state"], "active",
                         (root / self.ROUTE).read_text(encoding="utf-8"))

    # -- behaviour 1 and 3: the declaration installs the guard, the flag does not -----------------

    def test_the_red_sequence_public_then_plain_no_longer_removes_the_guard(self):
        """THE DEFECT. Second command is the documented remedy; it used to disarm the repository."""
        home, root = self.scratch_home(), self.scratch_repo()
        rc, out = self.install(home, root, "--public")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.guard(root), (True, True), out)

        rc, out = self.install(home, root)                     # NO --public
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.guard(root), (True, True), out)  # was (False, False)
        # And it says why, rather than keeping it by accident.
        self.assertIn("REQUIRED by this repository's own declaration", out)
        self.assertIn("docs/agents/README.md", out)

    def test_a_declaring_repo_gets_the_guard_with_no_flag_ever_passed(self):
        """The marker written by a human, --public never used. State, not a remembered flag."""
        home, root = self.scratch_home(), self.scratch_repo()
        self.declare(root)
        rc, out = self.install(home, root)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.guard(root), (True, True), out)

    def test_no_re_run_can_remove_the_guard_from_a_declaring_repo(self):
        home, root = self.scratch_home(), self.scratch_repo()
        self.declare(root)
        for flags in ((), ("--standard",), (), ("--no-graph",), ()):
            with self.subTest(flags=flags):
                rc, out = self.install(home, root, *flags)
                self.assertEqual(rc, 0, out)
                self.assertEqual(self.guard(root), (True, True), out)

    # -- the unchanged case, and deliberate removal ----------------------------------------------

    def test_no_declaration_and_no_flag_still_gets_no_guard(self):
        home, root = self.scratch_home(), self.scratch_repo()
        rc, out = self.install(home, root)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.guard(root), (False, False), out)
        self.assertEqual(self.markers(root), 0, out)

    def test_removing_the_declaration_removes_the_guard(self):
        """Deliberate removal still works — it just costs a visible edit to a tracked file."""
        home, root = self.scratch_home(), self.scratch_repo()
        self.assertEqual(self.install(home, root, "--public")[0], 0)
        self.assertEqual(self.guard(root), (True, True))
        self.undeclare(root)
        rc, out = self.install(home, root)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.guard(root), (False, False), out)
        self.assertIn("removing the private-identifier guard", out)

    def test_uninstall_still_takes_everything_even_from_a_declaring_repo(self):
        home, root = self.scratch_home(), self.scratch_repo()
        self.assertEqual(self.install(home, root, "--public")[0], 0)
        rc, out = self.install(home, root, "--uninstall")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.guard(root), (False, False), out)
        # An explicit request is honoured, but it must not read as "this repo is now private".
        self.assertIn("declares itself PUBLIC", out)

    # -- behaviour 4: the disagreement is never silent -------------------------------------------

    def test_declaration_present_and_guard_absent_is_a_finding_in_check(self):
        home, root = self.scratch_home(), self.scratch_repo()
        self.assertEqual(self.install(home, root, "--public")[0], 0)
        for name in ("pre-commit", "commit-msg"):
            (root / ".git" / "hooks" / name).unlink()
        rc, out = self.install(home, root, "--check")
        self.assertEqual(rc, 1, out)                       # was 0
        self.assertIn("FINDING", out)
        self.assertIn("repository declares itself PUBLIC: YES", out)

    def test_the_finding_is_read_back_off_disk_not_inferred(self):
        """A declaring repo whose pre-commit could not be written must still report the gap.

        With `validate_disclosure.py` absent the pre-commit hook is refused, so a declaring
        repository ends the run with no staged-content scan. The run must say that in the
        declaration's own terms, not only as a refused hook.
        """
        home = self.scratch_home(remove=("validate_disclosure.py",))
        root = self.scratch_repo()
        self.declare(root)
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertIn("DECLARES itself public and the private-identifier", out)
        self.assertIn("guard is NOT in place after this run", out)

    def test_a_healthy_declaring_install_reports_no_disagreement(self):
        home, root = self.scratch_home(), self.scratch_repo()
        self.declare(root)
        rc, out = self.install(home, root)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FINDING", out)
        self.assertNotIn("NOT DETERMINED", out)

    # -- fail-closed, and by the same parser -----------------------------------------------------

    def test_a_malformed_declaration_is_refused_by_the_same_parser_and_never_disarms(self):
        """Same parser, so the same verdict AND the same words. The assertion is the equality.

        Not "the installer also rejects it" — that could be a second implementation agreeing by
        luck today. The detail string printed by the installer is `check_github.public_exception`'s
        own, so a divergence between the two is a test failure rather than a discovery.

        And refusing the marker is NOT deciding the repository is private. The guard stays exactly
        where it was and the run exits non-zero; `UnhonouredMarkerTest` pins the full class.
        """
        cg = load_module("cg_malformed", SCRIPTS / "check_github.py")
        cases = [
            '{"reason":"","date":"2026-01-02"}',            # empty reason
            '{"reason":"x","date":"nope"}',                 # not a date
            '{"reason":"x","date":"2099-01-01"}',           # dated in the future
            'not json at all',                              # not one JSON object
        ]
        for body in cases:
            with self.subTest(body=body):
                home, root = self.scratch_home(), self.scratch_repo()
                self.declare(root, body)
                verdict = cg.public_exception(root)
                self.assertNotEqual(verdict["state"], "active", verdict)
                rc, out = self.install(home, root)
                self.assertEqual(rc, 1, out)
                self.assertEqual(self.guard(root), (False, False), out)  # unchanged, not removed
                self.assertIn(verdict["detail"], out)
                self.assertIn("NOT HONOURED", out)

    def test_a_marker_inside_a_code_fence_declares_nothing_and_denies_nothing(self):
        """The carrier the parser's column-zero anchor and fence stripper exist for.

        A repository that DOCUMENTS the mechanism must not thereby claim to be public — and must
        not be recorded as having declared itself PRIVATE either. Both are answers the parser did
        not give. The guard is left alone and the run says the marker needs resolving.
        """
        home, root = self.scratch_home(), self.scratch_repo()
        p = root / self.ROUTE
        p.write_text(p.read_text(encoding="utf-8")
                     + '\n```\n<!-- public-exception: {"reason":"an example","date":"2026-01-02"} -->\n```\n',
                     encoding="utf-8")
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.guard(root), (False, False), out)
        self.assertIn("NOT HONOURED", out)
        # It must NOT assert the repository is private — that was the false claim.
        self.assertNotIn("treated as PRIVATE", out)

    def test_public_on_a_repo_with_an_unhonoured_marker_writes_nothing_and_guards_nothing(self):
        """Two markers are what the parser rejects, so a second one would make the repo undeclarable.

        And the guard is NOT rendered as a consolation: an unbacked guard is removed again by the
        next ordinary run, which is the defect wearing a different hat.
        """
        home, root = self.scratch_home(), self.scratch_repo()
        self.declare(root, '{"reason":"","date":"2026-01-02"}')
        rc, out = self.install(home, root, "--public")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.markers(root), 1, out)
        self.assertEqual(self.guard(root), (False, False), out)
        self.assertIn("Writing a second one would", out)

    def test_public_with_no_routed_file_to_declare_in_is_refused_not_faked(self):
        home = self.scratch_home()
        root = Path(tempfile.mkdtemp(prefix="pd-hookdeps-bare-"))
        self.addCleanup(shutil.rmtree, root, True)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        rc, out = self.install(home, root, "--public")
        self.assertEqual(rc, 1, out)
        self.assertIn("no routed file to record the decision in", out)
        self.assertEqual(self.guard(root), (False, False), out)


class UnhonouredMarkerTest(ScratchHomeMixin, unittest.TestCase):
    """A MARKER THE PARSER REFUSES IS NOT A DECISION TO BECOME PRIVATE.

    The first cut of TC-35 moved the guard from a flag to a declaration and then collapsed three
    parser verdicts into one `else` that set `public = False`. Measured on a declaring repository
    with the guard in both hooks, running the plain documented `install_hooks.py <repo>`:

        variant                                    verdict        rc   pre-commit   commit-msg
        two markers across MARKER_FILES            invalid        0    no           NO-FILE
        marker indented under a bullet             none+detail    0    no           NO-FILE
        marker inside a code fence                 none+detail    0    no           NO-FILE
        marker inside an enclosing HTML comment    none+detail    0    no           NO-FILE
        a date that is not a date                  invalid        0    no           NO-FILE
        a date in the future                       invalid        0    no           NO-FILE
        a control character in the reason          invalid        0    no           NO-FILE
        a body that is not JSON                    invalid        0    no           NO-FILE
        an unclosed fence EARLIER in the file      none+detail    0    no           NO-FILE
        the marker file is a symlink outside       none+detail    0    no           NO-FILE

    Ten shapes, every one disarming a public repository and reporting success, and the first is
    reachable by the NEXT QUEUED ACTION on the real public repo — onboarding creates
    `docs/agents/README.md` and carries the contract's marker across, so two exist for one commit.

    Two of these ten were in nobody's list and are ordinary typos rather than mistakes about the
    marker: an unclosed ```python fence anywhere above it, and a docs restructure that turns a
    marker file into a symlink. That is why this is written as a matrix over shapes rather than as
    a test per reported instance — the reported instance is never the class.

    THE CONTROL IS PART OF THE TEST. Deliberate deletion must still disarm, at rc=0. Without it
    this suite would pass just as well against an installer that never removes the guard at all,
    which is a different broken thing.
    """

    GOOD = '{"reason":"a deliberately public docs repo","date":"2026-07-30"}'

    def declaring_repo(self, home: Path) -> Path:
        """A repo that declares itself public and has the guard in BOTH hooks. Asserted, not hoped."""
        root = self.scratch_repo()
        p = root / "AGENTS.md"
        p.write_text(p.read_text(encoding="utf-8").rstrip("\n")
                     + f"\n\n<!-- public-exception: {self.GOOD} -->\n", encoding="utf-8")
        rc, out = self.install(home, root)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.guard(root), (True, True), out)
        return root

    # Each mutator turns a valid declaration into one shape the parser will not honour.
    def _sub(self, root: Path, old: str, new: str, where: str = "AGENTS.md") -> None:
        p = root / where
        before = p.read_text(encoding="utf-8")
        after = before.replace(old, new)
        # A fixture that did not change proves nothing, and a silently-failing `replace` is the
        # easiest way to write ten tests that all pass against anything.
        self.assertNotEqual(after, before, f"fixture not mutated in {where}: {old!r} not found")
        p.write_text(after, encoding="utf-8")

    def mutate(self, root: Path, kind: str) -> None:
        marker = f"<!-- public-exception: {self.GOOD} -->"
        if kind == "two markers":
            p = root / self.ROUTE
            before = p.read_text(encoding="utf-8")
            p.write_text(before + f"\n{marker}\n", encoding="utf-8")
            self.assertNotEqual(p.read_text(encoding="utf-8"), before)
        elif kind == "bullet indented":
            self._sub(root, marker, f"  - {marker}")
        elif kind == "code fence":
            self._sub(root, marker, f"```\n{marker}\n```")
        elif kind == "enclosing html comment":
            self._sub(root, marker, f"<!--\n{marker}\n-->")
        elif kind == "bad date":
            self._sub(root, '"date":"2026-07-30"', '"date":"last tuesday"')
        elif kind == "future date":
            self._sub(root, '"date":"2026-07-30"', '"date":"2099-01-01"')
        elif kind == "control character":
            self._sub(root, "a deliberately public docs repo", "public\\u001b[2J INJECTED")
        elif kind == "not json":
            self._sub(root, self.GOOD, "{just prose}")
        elif kind == "unclosed fence above":
            self._sub(root, "# Fixture", "# Fixture\n\n```python\nx = 1\n")
        elif kind == "symlink out":
            outside = Path(tempfile.mkdtemp(prefix="pd-hookdeps-outside-"))
            self.addCleanup(shutil.rmtree, outside, True)
            (outside / "AGENTS.md").write_text(f"# elsewhere\n\n{marker}\n", encoding="utf-8")
            (root / "AGENTS.md").unlink()
            (root / "AGENTS.md").symlink_to(outside / "AGENTS.md")
        elif kind == "deliberately deleted":
            p = root / "AGENTS.md"
            before = p.read_text(encoding="utf-8")
            p.write_text("\n".join(ln for ln in before.splitlines()
                                   if "public-exception" not in ln) + "\n", encoding="utf-8")
            self.assertNotEqual(p.read_text(encoding="utf-8"), before)
        else:  # pragma: no cover
            raise AssertionError(f"unknown mutation {kind}")

    UNHONOURED = ("two markers", "bullet indented", "code fence", "enclosing html comment",
                  "bad date", "future date", "control character", "not json",
                  "unclosed fence above", "symlink out")

    def test_no_unhonoured_marker_shape_can_disarm_a_declaring_repository(self):
        cg = load_module("cg_shapes", SCRIPTS / "check_github.py")
        for kind in self.UNHONOURED:
            with self.subTest(shape=kind):
                home = self.scratch_home()
                root = self.declaring_repo(home)
                self.mutate(root, kind)

                # The parser must genuinely refuse this shape, or the case is testing nothing.
                self.assertNotEqual(cg.public_exception(root)["state"], "active", kind)

                rc, out = self.install(home, root)          # the plain documented command
                self.assertEqual(self.guard(root), (True, True),
                                 f"{kind} disarmed a public repository\n{out}")
                self.assertEqual(rc, 1, f"{kind} reported success while refusing the marker\n{out}")
                self.assertIn("NOT RESOLVED", out)

    def test_the_installer_never_contradicts_its_own_diagnostic(self):
        """The tell that gave the defect away: "2 markers found" three lines above "no declaration".

        Whatever else it prints, a run that reports marker text must not also assert that the
        repository does not declare itself public or that no declaration exists.
        """
        for kind in self.UNHONOURED:
            for want in self.HALF_STATES:
                with self.subTest(shape=kind, halves=want):
                    home = self.scratch_home()
                    root = self.declaring_repo(home)
                    self.force_guard_state(root, want)
                    self.mutate(root, kind)
                    _, out = self.install(home, root)
                    for lie in ("does not declare itself", "no public-exception declaration",
                                "treated as PRIVATE", "no `public-exception` marker exists",
                                "nothing was taken away"):
                        self.assertNotIn(lie, out, f"{kind} {want}: contradicts itself\n{out}")

    # The four ways the two halves can sit on disk. The asymmetric pair is not hypothetical: it is
    # the END STATE of `test_the_finding_is_read_back_off_disk_not_inferred` in this same file, so a
    # fixture built only from `declaring_repo()` — which asserts (True, True) — can never reach the
    # state in which the round-1 code stripped a surviving half while printing that it had not.
    HALF_STATES = ((True, True), (True, False), (False, True), (False, False))

    def force_guard_state(self, root: Path, want: tuple[bool, bool]) -> None:
        """Put the two hooks into `want`, starting from a fully guarded repo. Verified, not assumed."""
        for present, name in zip(want, ("pre-commit", "commit-msg")):
            if not present:
                (root / ".git" / "hooks" / name).unlink(missing_ok=True)
        self.assertEqual(self.guard(root), want, f"could not force guard state {want}")

    def test_an_unresolved_declaration_moves_neither_half_from_any_starting_state(self):
        """FINDING 1. `guard_on_disk` read pre-commit ONLY, so with the stanza in commit-msg alone
        the run stripped the surviving half while printing "left exactly as it was (absent) …
        nothing was taken away" — three false statements about an action as it was taken.

        The property is per-half preservation from EVERY starting state, not only the symmetric
        ones, and the run must also refuse to call itself clean.
        """
        for want in self.HALF_STATES:
            for kind in ("bad date", "two markers", "code fence"):
                with self.subTest(halves=want, shape=kind):
                    home = self.scratch_home()
                    root = self.declaring_repo(home)
                    self.force_guard_state(root, want)
                    self.mutate(root, kind)
                    rc, out = self.install(home, root)
                    self.assertEqual(self.guard(root), want,
                                     f"unresolved declaration moved the guard from {want}\n{out}")
                    self.assertEqual(rc, 1, out)

    def test_the_preservation_claim_is_verified_against_disk_not_asserted(self):
        """The round-1 message was an intention printed beside the opposite action.

        `main()` now re-reads both hooks after the run and reports a mismatch as a finding. This
        pins the two halves of the mechanism that make the claim checkable: the per-hook message,
        and a summary that says the state was verified rather than merely intended.
        """
        home = self.scratch_home()
        root = self.declaring_repo(home)
        self.force_guard_state(root, (False, True))
        self.mutate(root, "bad date")
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertIn("commit-msg identifier guard left untouched (present)", out)
        self.assertIn("verified against the disk", out)
        self.assertEqual(self.guard(root), (False, True), out)

    def test_the_run_that_demonstrates_the_fix_does_not_contradict_itself(self):
        """FINDING 3. Correcting `(--public)` to `(this repo declares itself public)` reproduced the
        original defect's own signature: "public declaration NOT HONOURED" and then, three lines
        later, "blocks: … (this repo declares itself public)". In ten passing tests.

        A `blocks:` line is derived from the rendered block, which records THAT the stanza is there
        and never WHY, so no provenance belongs in it.
        """
        for kind in self.UNHONOURED:
            with self.subTest(shape=kind):
                home = self.scratch_home()
                root = self.declaring_repo(home)
                self.mutate(root, kind)
                _, out = self.install(home, root)
                if "NOT HONOURED" not in out and "NOT DETERMINED" not in out:
                    continue
                for line in out.splitlines():
                    if "blocks:" in line or line.strip().startswith("private identifiers"):
                        self.assertNotIn("declares itself public", line, f"{kind}\n{out}")
                        self.assertNotIn("--public", line, f"{kind}\n{out}")

    def test_the_disarm_message_claims_only_what_the_parser_promises(self):
        """FINDING 2, the half that IS mechanisable from this write set.

        The fix for the unreadable-candidate hole needs `check_github.py` and is escalated. What is
        enforceable here is that this file never again writes as though it were closed: the disarm
        message must not claim that no marker EXISTS, only that no honoured marker was found in a
        file the parser could READ.
        """
        home = self.scratch_home()
        root = self.declaring_repo(home)
        self.mutate(root, "deliberately deleted")
        _, out = self.install(home, root)
        self.assertIn("could read", out)
        for absolute in ("no `public-exception` marker exists",
                         "looked and there was nothing there",
                         "read every routed file", "read every candidate file"):
            self.assertNotIn(absolute, out, f"disarm message overclaims: {absolute!r}\n{out}")

    def test_finding_two_is_still_open_so_the_comments_denying_it_stay_honest(self):
        """A TRIPWIRE ON AN ESCALATION, not a test of desired behaviour.

        `install_hooks.py` now carries several comments saying the unreadable-candidate hole is real
        and still open. Those comments are claims about `check_github.py`, so they rot the moment
        somebody fixes it — and a comment describing a closed hole as open is the same defect as the
        one this round is correcting, pointing the other way.

        So the hole itself is asserted. When Finding 2 is fixed this test FAILS, which is the
        intended signal: come back and correct the comments in the disarm branch, the module
        docstring, `remove_hook_block`, and the PRE_COMMIT_IDENTIFIER note.

        Read-only on the shared parser: it imports and calls it, and writes nothing.
        """
        cg = load_module("cg_finding2", SCRIPTS / "check_github.py")
        home = self.scratch_home()
        root = self.declaring_repo(home)
        marker_file = root / "AGENTS.md"
        self.assertEqual(cg.public_exception(root)["state"], "active")

        before = marker_file.stat().st_mode
        os.chmod(marker_file, 0o000)
        self.addCleanup(os.chmod, marker_file, 0o644)
        self.assertNotEqual(marker_file.stat().st_mode, before, "fixture not mutated")
        if os.access(marker_file, os.R_OK):
            self.skipTest("running as a user that can read a 000 file (root?) — "
                          "the unreadable-candidate path is unreachable here")

        verdict = cg.public_exception(root)
        self.assertEqual(
            (verdict["state"], verdict["detail"]), ("none", ""),
            "check_github.py now distinguishes an unreadable candidate from an absent marker. "
            "FINDING 2 IS FIXED — go and correct install_hooks.py's comments, which currently say "
            "it is open, and route the new state into the `unresolved` branch.")

    def test_the_control_deliberate_deletion_still_disarms_and_exits_zero(self):
        """Without this the suite would pass against an installer that never removes anything."""
        home = self.scratch_home()
        root = self.declaring_repo(home)
        self.mutate(root, "deliberately deleted")
        rc, out = self.install(home, root)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.guard(root), (False, False), out)
        self.assertIn("removing the private-identifier guard", out)

    def test_check_mode_reports_the_same_class_and_exits_non_zero(self):
        home = self.scratch_home()
        root = self.declaring_repo(home)
        self.mutate(root, "two markers")
        rc, out = self.install(home, root, "--check")
        self.assertEqual(rc, 1, out)
        self.assertIn("NOT RESOLVED", out)

    def test_an_unhonoured_marker_does_not_conjure_a_guard_either(self):
        """Conservative means UNCHANGED, not "install it to be safe". A repo with no guard and a
        marker nobody can read gets no guard — it gets a message and a non-zero code."""
        home, root = self.scratch_home(), self.scratch_repo()
        self.declare(root, '{"reason":"x","date":"not-a-date"}')
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.guard(root), (False, False), out)


class DeclarationDependencyTest(ScratchHomeMixin, unittest.TestCase):
    """The declaration path's dependency, enumerated the same way the hooks' dependencies are.

    This is the TC-30 argument applied one level out. The hook blocks name their scripts in shell
    and `block_dependencies` reads them out of the rendered text; the DECLARATION is read by a
    sibling Python import instead, so its dependency is `check_github.py` and the resolver that
    finds it is `script_dependencies` — TC-30's own, unchanged, pointed at the installer.

    The failure being closed is the same one: a script absent from `~/.claude` (a restore in the
    wrong order, `install_tree` replacing the skill directory) turning into a confident report. Here
    it would be worse than a false claim, because the natural fallback — "no declaration found" —
    silently REMOVES the guard from a public repository.
    """

    def test_the_declaration_parser_is_visible_to_the_dependency_resolver(self):
        deps = {p.name for p in installer.script_dependencies(INSTALLER)}
        self.assertIn("check_github.py", deps,
                      "install_hooks.py must read the public declaration through a sibling import "
                      "of check_github.py that script_dependencies() can see — a dynamic or dotted "
                      "import would hide the dependency from every check in this file")

    def test_every_sibling_the_installer_imports_is_really_there(self):
        missing = [p for p in installer.script_dependencies(INSTALLER) if not p.is_file()]
        self.assertEqual(missing, [], f"installer imports scripts that are not on disk: {missing}")

    def test_without_the_parser_the_guard_is_kept_and_the_run_is_not_clean(self):
        """Fail closed. Visibility unknown is not "not public"."""
        home, root = self.scratch_home(), self.scratch_repo()
        self.assertEqual(self.install(home, root, "--public")[0], 0)
        self.assertEqual(self.guard(root), (True, True))

        (home / ".claude" / "skills" / "progressive-disclosure" / "scripts"
         / "check_github.py").unlink()
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.guard(root), (True, True), out)   # kept, not removed
        self.assertIn("NOT DETERMINED", out)
        self.assertIn("check_github.py", out)

    def test_without_the_parser_an_undeclared_repo_gains_no_guard_either(self):
        """"Unknown" leaves the state alone in BOTH directions — it is not an excuse to install."""
        home, root = self.scratch_home(remove=("check_github.py",)), self.scratch_repo()
        rc, out = self.install(home, root)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.guard(root), (False, False), out)
        self.assertIn("NOT DETERMINED", out)

    def test_check_mode_also_refuses_to_call_an_unread_declaration_clean(self):
        home, root = self.scratch_home(remove=("check_github.py",)), self.scratch_repo()
        rc, out = self.install(home, root, "--check")
        self.assertEqual(rc, 1, out)
        self.assertIn("NOT DETERMINED", out)


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

    @reaches_home(
        "ARITHMETIC ONLY — it opens nothing under HOME. `block_dependencies()` returns absolute "
        "paths rooted at `Path.home()`, and this test strips that root to compare them against the "
        "`$HOME/...` literals in the template. Both sides use the same base, so the comparison is "
        "identical on every machine; declaring it is how the derivation stays exact rather than "
        "gaining an exemption for a shape that is genuinely fine.")
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

    def test_there_is_no_second_marker_parser(self):
        """One fact, one parser. The marker is a SECURITY decision — the worst thing to duplicate.

        A regex here that mentions `public-exception` would be a second reader of the same marker,
        and the hardening the shared one carries (column-zero anchoring, the line-state fence pass,
        enclosing-comment stripping, the symlink rule, the unicode refusals) would have to be
        rediscovered in it one bug at a time. Reading a marker is not the same as MENTIONING it: the
        docstring and the printed guidance say the word, and must.

        Named for compilation, it used to CHECK only for compilation — `ast.Call` whose func is an
        attribute named `compile`. `re.search(pat, text)`, `re.findall`, a bare
        `"public-exception" in text` or `text.find("public-exception")` all passed it, and every one
        of those is a second reader. Matching, not compiling, is the thing being forbidden, so the
        check now covers the whole `re` surface plus the string operations that do the same job
        without importing anything.
        """
        MATCHERS = {"compile", "search", "match", "fullmatch", "findall", "finditer", "split",
                    "sub", "subn", "scanner"}
        STR_TESTS = {"find", "rfind", "index", "startswith", "endswith", "count", "partition",
                     "rpartition", "split", "rsplit", "replace"}

        def literals_of(node) -> str:
            return " ".join(n.value for n in ast.walk(node)
                            if isinstance(n, ast.Constant) and isinstance(n.value, str)).lower()

        offenders = []
        for node in ast.walk(self.tree):
            # 1. any re.* matcher, however spelled, and any bare call to one of those names
            if isinstance(node, ast.Call):
                fn = (node.func.attr if isinstance(node.func, ast.Attribute)
                      else node.func.id if isinstance(node.func, ast.Name) else "")
                if fn in MATCHERS | STR_TESTS and "public-exception" in literals_of(node):
                    offenders.append(f"line {node.lineno}: {fn}(...) over a public-exception literal")
            # 2. `"public-exception" in text` / `not in` — no call, same effect
            if isinstance(node, ast.Compare) and any(
                    isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                if "public-exception" in literals_of(node):
                    offenders.append(f"line {node.lineno}: membership test on a public-exception "
                                     f"literal")
        self.assertEqual(offenders, [],
                         "install_hooks.py parses the marker itself instead of importing the one "
                         "parser:\n  " + "\n  ".join(offenders)
                         + "\n  Import check_github.public_exception instead.")

    def test_the_second_parser_check_actually_catches_a_second_parser(self):
        """A guard on the guard. The previous version of the test above passed against four
        different real second-parsers, so its passing carried no information. These synthetic
        sources stand in for each, and the detector must reject every one.
        """
        MATCHERS = {"compile", "search", "match", "fullmatch", "findall", "finditer", "split",
                    "sub", "subn", "scanner"}
        STR_TESTS = {"find", "rfind", "index", "startswith", "endswith", "count", "partition",
                     "rpartition", "split", "rsplit", "replace"}

        def detects(src: str) -> bool:
            tree = ast.parse(src)

            def lits(n):
                return " ".join(c.value for c in ast.walk(n)
                                if isinstance(c, ast.Constant) and isinstance(c.value, str)).lower()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = (node.func.attr if isinstance(node.func, ast.Attribute)
                          else node.func.id if isinstance(node.func, ast.Name) else "")
                    if fn in MATCHERS | STR_TESTS and "public-exception" in lits(node):
                        return True
                if isinstance(node, ast.Compare) and any(
                        isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                    if "public-exception" in lits(node):
                        return True
            return False

        for src in ('re.compile(r"<!--\\s*public-exception:")',
                    're.search(r"public-exception", text)',
                    're.findall("public-exception", text)',
                    'x = "public-exception" in text',
                    'i = text.find("<!-- public-exception:")',
                    'b = text.startswith("public-exception")'):
            with self.subTest(src=src):
                self.assertTrue(detects(src), f"detector misses a real second parser: {src}")
        # And it must not fire on merely NAMING the marker, which the docstrings and the printed
        # guidance both do and must keep doing.
        for src in ('print("record a public-exception marker in your contract")',
                    'REASON = "declared via the public-exception marker"'):
            with self.subTest(src=src):
                self.assertFalse(detects(src), f"detector fires on a mere mention: {src}")

    def test_the_declaration_is_read_through_check_githubs_function(self):
        """The positive half of the rule above: the shared parser is actually the thing called."""
        self.assertRegex(self.source, r"import\s+check_github\b")
        self.assertIn("public_exception(root)", self.source)

    def _main_node(self) -> ast.FunctionDef:
        for node in self.tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                return node
        raise AssertionError("main() not found in install_hooks.py")

    def _tainted_by_flag(self) -> set[str]:
        """Names in `main()` whose value derives, transitively, from `args.public`.

        A counting test cannot express this invariant and never could: `flag = args.public` then
        `public = flag` keeps the count at two and restores the coupling completely. So the check
        follows the DATA rather than counting mentions. Fixed-point over simple assignments, which
        is all this function contains and all an author would need to defeat a literal match.
        """
        def mentions_flag(node) -> bool:
            return any(isinstance(n, ast.Attribute) and n.attr == "public"
                       and isinstance(n.value, ast.Name) and n.value.id == "args"
                       for n in ast.walk(node))

        tainted: set[str] = set()
        for _ in range(20):                      # fixed point; depth here is 1-2 in practice
            grew = False
            for node in ast.walk(self._main_node()):
                if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    continue
                value = node.value
                if value is None:
                    continue
                src_names = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
                if not (mentions_flag(value) or (src_names & tainted)):
                    continue
                targets = (node.targets if isinstance(node, ast.Assign) else [node.target])
                for t in targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name) and n.id not in tainted:
                            tainted.add(n.id)
                            grew = True
            if not grew:
                break
        return tainted

    def test_the_guard_is_not_decided_by_the_flag(self):
        """`args.public` may only WRITE the declaration.

        If it also gated the render, the flag would be back in the decision and dropping it could
        once again take the guard away. Asserted by DATA FLOW, not by counting: the value handed to
        `render_pre_commit(public=...)` must not derive from `args.public` through any chain of
        assignments.
        """
        uses = [n.lineno for n in ast.walk(self.tree)
                if isinstance(n, ast.Attribute) and n.attr == "public"
                and isinstance(n.value, ast.Name) and n.value.id == "args"]
        self.assertTrue(uses, "args.public is not read at all — the flag no longer does anything")

        tainted = self._tainted_by_flag()
        calls = [n for n in ast.walk(self._main_node())
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "render_pre_commit"]
        self.assertTrue(calls, "main() no longer calls render_pre_commit — rewrite this test")
        for call in calls:
            kw = next((k for k in call.keywords if k.arg == "public"), None)
            self.assertIsNotNone(kw, f"render_pre_commit at line {call.lineno} without public=")
            names = {n.id for n in ast.walk(kw.value) if isinstance(n, ast.Name)}
            flagged = names & tainted
            direct = any(isinstance(n, ast.Attribute) and n.attr == "public"
                         and isinstance(n.value, ast.Name) and n.value.id == "args"
                         for n in ast.walk(kw.value))
            self.assertFalse(flagged or direct,
                             f"render_pre_commit(public=...) at line {call.lineno} derives from "
                             f"args.public (via {sorted(flagged) or 'a direct read'}). The identifier "
                             f"guard must follow the DECLARATION; routing the flag back into it "
                             f"restores the defect this card exists to remove.")

    def test_the_flag_taint_check_catches_the_indirection_that_defeats_counting(self):
        """A guard on the guard. The counting version passed against `flag = args.public;
        public = flag`, so this pins that the replacement does not."""
        src = ("def main():\n"
               "    flag = args.public\n"
               "    public = flag\n"
               "    render_pre_commit(standard=args.standard, public=public)\n")
        saved_tree, saved_source = self.tree, self.source
        try:
            self.tree, self.source = ast.parse(src), src
            with self.assertRaises(AssertionError):
                self.test_the_guard_is_not_decided_by_the_flag()
        finally:
            self.tree, self.source = saved_tree, saved_source

    def test_there_is_no_opt_out(self):
        """No flag, no environment variable. 'Install it anyway' is a request to be told a guard is
        there when nobody knows whether it is."""
        lowered = self.source.lower()
        for forbidden in ("--force", "--skip-dep", "--no-dep-check", "--allow-missing",
                          "pd_skip_dep_check", "pd_allow_missing"):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
