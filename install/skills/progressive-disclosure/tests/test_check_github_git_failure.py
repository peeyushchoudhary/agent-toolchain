"""Every `git()` call in check_github.py, and the one thing none of them may do: read as an answer.

THE DEFECT THESE TESTS PIN. `git()` returned `""` on both "git said no" and "git never answered",
and `local_state()` turned that `""` into a positive fact. Measured on the fixture rebuilt in
`RedFixtureTest` below — a repo with 3 commits, an origin, and no upstream:

    baseline, git working      ->  rc=2, "3 unpushed commit(s), oldest 0 day(s) old"
    the same repo, git exits 128 ->  rc=1, and the unpushed line is GONE

Genuinely unpushed work vanished from the one report whose job is to name work that exists on a
single machine. The audit named that call site. It was not the only one: the same run also invented
a CRITICAL "no git remote — this repository exists only on this laptop", with instructions to create
one, about a repository that has an origin. Two false assertions and a dropped warning, from one
swallowed exit code.

WHAT IS ACTUALLY BEING TESTED, and it is not "the unpushed branch was patched". Absent and unknown
are different states, and the remedy is that `git()` can no longer produce the first when it means
the second: it takes the exit codes that constitute an ANSWER for that specific command and raises
`GitUnanswered` on anything else. One handler, in `local_state()`. So the tests come in two layers:

  1. Behavioural — every call site, failed one at a time through a real PATH shim, exercised end to
     end through the real CLI. None may assert absence; all must reach the `unable` state.
  2. Structural — `NoSwallowTest` asserts by source inspection that no call site can be added
     without declaring what a legitimate "no" looks like for it, and that the handler stays single.
     A behavioural test covers the call sites someone thought of; this one covers the fifth.

WHAT `answers` IS, and why it is measured rather than guessed. A non-zero exit is sometimes a real
answer: `git remote get-url origin` exits 2 when there is no origin, and that is the input to the
CRITICAL finding this tool exists for. Measured on this machine, git 2.x:

    command                                     no-origin / empty repo     not a repo
    remote get-url origin                       2                          128
    log --branches --not --remotes --format=%ct 0                          128
    for-each-ref ... refs/heads                 0                          128
    status --porcelain                          0                          128

Two of the seven real repositories under the projects directory exit 2 on `remote get-url`, so
`answers` for that one call is (0, 2) and narrowing it to (0,) would flip them from CRITICAL to
NOT CHECKED. `LegitimateNoTest` pins that.

Run: python3 skills/progressive-disclosure/tests/test_check_github_git_failure.py
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hermetic import reaches_home


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
CHECKER = SCRIPTS / "check_github.py"
HOOKS = Path.home() / ".claude" / "hooks"

REAL_GIT = shutil.which("git")

# The phrase the `unable` finding must carry when GIT is what could not answer. Asserted rather
# than inferred from "UNABLE", because the remote half also produces `unable` — three of these
# tests passed against the UNPATCHED checker on that ambiguity alone, which is the same mistake the
# audit made about the exit code. A git unknown and a gh unknown must not be mistakable.
GIT_UNKNOWN = "git could not answer"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gh = load_module("check_github_git_failure_test", CHECKER)


# Every `git()` call site in `local_state()`, keyed by a token unique to its argv. The shim below
# fails exactly one of them and lets the rest through to real git, which is what makes "audit every
# call site" a test rather than a claim. Adding a fifth call site without adding it here is caught
# by `NoSwallowTest.test_every_call_site_is_covered_behaviourally`.
CALL_SITES = {
    "remote": "git remote get-url origin",
    "log": "git log --branches --not --remotes",
    "for-each-ref": "git for-each-ref refs/heads",
    "status": "git status --porcelain",
}


class FixtureMixin:
    """A repo with 3 commits, an origin, and no upstream — the controller's measured fixture."""

    def repo(self, *, commits: int = 3, origin: bool = True) -> Path:
        root = Path(tempfile.mkdtemp(prefix="pd-gitfail-"))
        self.addCleanup(shutil.rmtree, root, True)
        self._git(root, "init", "-q", "-b", "main", ".")
        self._git(root, "config", "user.email", "t@e.x")
        self._git(root, "config", "user.name", "T")
        for i in range(commits):
            (root / f"f{i}.txt").write_text(str(i), encoding="utf-8")
            self._git(root, "add", f"f{i}.txt")
            self._git(root, "commit", "-qm", f"c{i}")
        if origin:
            self._git(root, "remote", "add", "origin",
                      "https://github.com/example-owner/example-repo.git")
        return root

    def _git(self, root: Path, *args: str) -> None:
        subprocess.run([REAL_GIT, "-C", str(root), *args], check=True,
                       capture_output=True, text=True, timeout=60)

    def shim_dir(self, *, fail_token: str | None, git_rc: int = 128) -> Path:
        """A PATH directory holding a `git` that fails one subcommand, and a `gh` that always fails.

        `gh` is neutralised in every run so the remote half is a constant (`unreachable`) and the
        suite needs no network and no GitHub account — the card forbids a fix that needs either.
        `fail_token=None` leaves git entirely intact, which is the baseline arm.
        """
        d = Path(tempfile.mkdtemp(prefix="pd-shim-"))
        self.addCleanup(shutil.rmtree, d, True)
        if fail_token is None:
            body = f'#!/bin/sh\nexec {REAL_GIT} "$@"\n'
        else:
            # Exact-token match against argv, so `--remotes` never matches the `remote` subcommand.
            body = (f'#!/bin/sh\n'
                    f'for a in "$@"; do\n'
                    f'  [ "$a" = "{fail_token}" ] && exit {git_rc}\n'
                    f'done\n'
                    f'exec {REAL_GIT} "$@"\n')
        self._write_exe(d / "git", body)
        self._write_exe(d / "gh", "#!/bin/sh\nexit 1\n")
        return d

    def _write_exe(self, path: Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def run_checker(self, root: Path, shim: Path, *flags: str) -> tuple[int, str]:
        """The real CLI in a subprocess. The exit CODE is under test, so it is read from the
        process itself and never from the tail of a pipeline.

        `HOME` IS REDIRECTED, AND A FRESH ONE PER CALL. `check_github.py` builds
        `CACHE_DIR = Path.home() / ".claude" / "cache" / "github-state"` and `remote_state()`
        does `CACHE_DIR.mkdir(parents=True, exist_ok=True)` — so without this these tests CREATED
        A DIRECTORY IN THE REAL `$HOME`, and a cache entry younger than 24h short-circuits the
        `unreachable` answer that `test_a_failed_git_never_erases_the_unpushed_work`,
        `test_each_call_site_reaches_unable_rather_than_emptying` and
        `test_the_hook_line_says_so_rather_than_going_quiet` assert with `"NOT determined"` and
        `rc == 2`. The sibling suite already knew: `test_check_github.py`'s end-to-end says
        verbatim "`HOME` is redirected so the 24h cache cannot answer from a previous successful
        run." Fresh per call rather than per test, because two calls in one test would let the
        first one's cache answer the second.
        """
        home = Path(tempfile.mkdtemp(prefix="pd-gitfail-home-"))
        self.addCleanup(shutil.rmtree, home, True)
        proc = subprocess.run(
            [sys.executable, str(CHECKER), str(root), *flags],
            capture_output=True, text=True, timeout=180,
            env={**os.environ, "PATH": f"{shim}:{os.environ['PATH']}",
                 "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return proc.returncode, proc.stdout + proc.stderr


@unittest.skipIf(REAL_GIT is None, "git is not installed")
class RedFixtureTest(FixtureMixin, unittest.TestCase):
    """The controller's exact fixture and its exact two runs."""

    def test_baseline_reports_the_unpushed_work(self) -> None:
        """The arm that must not change. Recorded verbatim so the GREEN arm has something to be
        compared against rather than merely asserted about."""
        root = self.repo()
        rc, out = self.run_checker(root, self.shim_dir(fail_token=None))
        self.assertIn("3 unpushed commit(s), oldest 0 day(s) old", out)
        self.assertIn("branch `main` has no upstream", out)
        self.assertEqual(rc, 2, out)  # `gh` is neutralised, so the remote half is `unable`

    def test_a_failed_git_never_erases_the_unpushed_work(self) -> None:
        """THE DEFECT. With git broken the report said nothing about three unpushed commits."""
        root = self.repo()
        rc, out = self.run_checker(root, self.shim_dir(fail_token="log"))
        self.assertNotIn("no git remote", out)
        self.assertIn(GIT_UNKNOWN, out)
        self.assertIn("NOT determined", out)
        self.assertEqual(rc, 2, out)

    def test_a_failed_git_never_invents_a_missing_remote(self) -> None:
        """The second false assertion in the same run, which the audit did not name. The fixture
        HAS an origin; the broken-git run called it a repository that exists only on this laptop
        and told the human to create a remote."""
        root = self.repo()
        rc, out = self.run_checker(root, self.shim_dir(fail_token="remote"))
        self.assertNotIn("this repository exists only on this laptop", out)
        self.assertNotIn("gh repo create", out)
        self.assertIn(GIT_UNKNOWN, out)
        self.assertEqual(rc, 2, out)

    def test_a_totally_broken_git_asserts_nothing_at_all(self) -> None:
        """Every call site down at once — the controller's `exit 128` shim."""
        root = self.repo()
        rc, out = self.run_checker(root, self.shim_dir(fail_token="-C"))
        # The assertions, named exactly. A blunt `"pushed" not in out` would also forbid the word
        # inside the unknown finding's own text, which is where it belongs.
        for lie in ("no git remote", "unpushed commit(s)", "has no upstream", "clean —",
                    # The report HEADER, which `or 'no GitHub remote'` made assert an absence out
                    # of a missing key. The findings list was already correct when this was still
                    # printing one line above it.
                    "no GitHub remote"):
            self.assertNotIn(lie, out)
        self.assertIn(GIT_UNKNOWN, out)
        self.assertEqual(rc, 2, out)


@unittest.skipIf(REAL_GIT is None, "git is not installed")
class EveryCallSiteTest(FixtureMixin, unittest.TestCase):
    """Each call site failed on its own. The audit named one; TC-29 found fifteen."""

    def test_each_call_site_reaches_unable_rather_than_emptying(self) -> None:
        root = self.repo()
        for token, human in CALL_SITES.items():
            with self.subTest(call_site=human):
                rc, out = self.run_checker(root, self.shim_dir(fail_token=token))
                self.assertIn(GIT_UNKNOWN, out, f"{human} emptied silently:\n{out}")
                self.assertIn("NOT determined", out, out)
                self.assertEqual(rc, 2, out)

    def test_no_call_site_leaves_a_fabricated_field_in_the_json(self) -> None:
        """A caller must not be able to read a degraded report as a complete one. `unpushed: 0`
        in the JSON is indistinguishable from "measured, and there are none"."""
        root = self.repo()
        for token, human in CALL_SITES.items():
            with self.subTest(call_site=human):
                rc, out = self.run_checker(root, self.shim_dir(fail_token=token), "--json")
                blob = json.loads(out)
                local = blob["local"]
                self.assertTrue(local.get("unknown"), f"{human}: no unknown marker in {local}")
                for fabricated in ("unpushed", "unpushed_age_days", "remote", "no_upstream",
                                   "dirty"):
                    self.assertNotIn(fabricated, local,
                                     f"{human}: `{fabricated}` present despite git failing")
                self.assertEqual(rc, 2, out)

    def test_the_hook_line_says_so_rather_than_going_quiet(self) -> None:
        """`--hook` is silent when healthy. An unmeasurable repository is not healthy, and session
        start is the only mode that runs by itself."""
        root = self.repo()
        for token, human in CALL_SITES.items():
            with self.subTest(call_site=human):
                rc, out = self.run_checker(root, self.shim_dir(fail_token=token), "--hook")
                self.assertIn("AGENT CONTEXT", out, f"{human} was silent at session start")
                self.assertIn(GIT_UNKNOWN, out, out)
                self.assertEqual(rc, 0, out)  # --hook must never fail a session


@unittest.skipIf(REAL_GIT is None, "git is not installed")
class LegitimateNoTest(FixtureMixin, unittest.TestCase):
    """A non-zero exit that IS an answer must keep answering. This is the fleet-impact guard.

    Two of the real project repositories have no origin, where `git remote get-url origin` exits 2.
    If `answers` for that call were narrowed to (0,) they would silently change from CRITICAL to
    NOT CHECKED — a fleet-wide change, and not this card's to make.
    """

    def test_no_origin_is_still_a_critical_and_not_an_unknown(self) -> None:
        root = self.repo(origin=False)
        rc, out = self.run_checker(root, self.shim_dir(fail_token=None))
        self.assertIn("no git remote", out)
        self.assertNotIn(GIT_UNKNOWN, out)
        self.assertEqual(rc, 1, out)

    def test_git_reports_the_measured_answer_codes(self) -> None:
        """Pins the table in the module docstring against the git on this machine, so a future git
        that changes an exit code fails here instead of silently reclassifying a repository."""
        root = self.repo(origin=False)
        self.assertEqual(gh.git_probe(root, "remote", "get-url", "origin")[0], 2)
        for args in (("log", "--branches", "--not", "--remotes", "--format=%ct"),
                     ("for-each-ref", "--format=%(refname:short) %(upstream)", "refs/heads"),
                     ("status", "--porcelain")):
            self.assertEqual(gh.git_probe(root, *args)[0], 0, args)


@unittest.skipIf(REAL_GIT is None, "git is not installed")
class HealthyRepoRegressionTest(FixtureMixin, unittest.TestCase):
    """A working repo reports exactly what it reported before the change."""

    def test_findings_and_exit_code_are_unchanged(self) -> None:
        root = self.repo()
        rc, out = self.run_checker(root, self.shim_dir(fail_token=None))
        self.assertEqual(rc, 2, out)
        self.assertIn("3 unpushed commit(s), oldest 0 day(s) old — that work exists on one machine "
                      "only.", out)
        self.assertIn("branch `main` has no upstream; it will not be pushed by `git push`.", out)
        self.assertIn("GitHub state could not be read", out)
        self.assertNotIn(GIT_UNKNOWN, out)

    def test_a_clean_pushed_repo_still_reads_as_clean_locally(self) -> None:
        """No commits, no origin is a different shape; what matters is that nothing here is an
        unknown. `local_state` must produce real fields whenever git answers."""
        root = self.repo(commits=0, origin=False)
        st = gh.local_state(root)
        self.assertEqual(st.get("unknown", ""), "")
        self.assertEqual(st["unpushed"], 0)
        self.assertEqual(st["remote"], "")


class NoSwallowTest(unittest.TestCase):
    """The durable half. Asserted against the source, not against behaviour.

    A behavioural suite pins the call sites that exist today. This pins the RULE, so the call site
    someone adds next year is covered by a test written before it.
    """

    def setUp(self) -> None:
        self.source = CHECKER.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def _git_calls(self) -> list[ast.Call]:
        return [n for n in ast.walk(self.tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "git"]

    def test_every_git_call_declares_its_answer_codes(self) -> None:
        """`answers` has no default, so this cannot be forgotten — but a default could be
        reintroduced, and then forgetting becomes silent again. Both are pinned."""
        offenders = [f"line {c.lineno}" for c in self._git_calls()
                     if not any(k.arg == "answers" for k in c.keywords)]
        self.assertEqual(offenders, [],
                         "git() calls not declaring answers=:\n  " + "\n  ".join(offenders))

        fn = self._function("git")
        self.assertIsNotNone(fn, "git() has gone missing")
        kwonly = {a.arg: d for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults)}
        self.assertIn("answers", kwonly, "answers must be keyword-only on git()")
        self.assertIsNone(kwonly["answers"],
                          "answers must have NO default — a default is a swallow with a nicer name")

    def test_git_raises_rather_than_returning_a_placeholder(self) -> None:
        fn = self._function("git")
        self.assertTrue(any(isinstance(n, ast.Raise) for n in ast.walk(fn)),
                        "git() no longer raises; a failure is being turned into a value again")

    # The handler is single by construction, and that is the property rather than a style rule: a
    # second handler is a second policy, and one of the two will be the lenient one.
    ALLOWED_HANDLERS = {"local_state"}

    def test_the_unanswered_handler_stays_single(self) -> None:
        offenders = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            names = self._exception_names(node.type)
            if "GitUnanswered" not in names and "Exception" not in names:
                continue
            fn = self._enclosing_function(node)
            if "GitUnanswered" in names and fn in self.ALLOWED_HANDLERS:
                continue
            if "GitUnanswered" in names:
                offenders.append(f"{fn}() line {node.lineno}: a second GitUnanswered handler")
                continue
            # A bare `except Exception` inside local_state would swallow GitUnanswered too.
            if fn in self.ALLOWED_HANDLERS:
                offenders.append(f"{fn}() line {node.lineno}: catches Exception, which would "
                                 f"absorb GitUnanswered into the wrong branch")
        self.assertEqual(offenders, [], "handler leaks:\n  " + "\n  ".join(offenders))

    def test_every_call_site_is_covered_behaviourally(self) -> None:
        """A fifth `git()` call whose subcommand is not in CALL_SITES is a call site the
        behavioural suite never fails. Fail here, at authoring time, instead."""
        subcommands = set()
        for c in self._git_calls():
            args = [a.value for a in c.args[1:]
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            self.assertTrue(args, f"git() at line {c.lineno} has no literal subcommand")
            subcommands.add(args[0])
        self.assertEqual(subcommands, set(CALL_SITES),
                         "CALL_SITES is out of step with the call sites in check_github.py")

    def test_the_git_unknown_is_distinguishable_from_the_gh_unknown(self) -> None:
        """Both produce `unable`. A reader who cannot tell them apart cannot tell "your remote is
        unreachable" from "this checker learned nothing about your repository at all"."""
        self.assertIn(GIT_UNKNOWN, self.source)

    def test_there_is_no_opt_out(self) -> None:
        """No flag, no environment variable. 'Assume git worked' is a request to be told a
        repository is backed up when nobody knows whether it is."""
        lowered = self.source.lower()
        for forbidden in ("--assume-git", "--ignore-git-errors", "--skip-unknown",
                          "--no-unknown", "pd_assume_git", "pd_ignore_git"):
            self.assertNotIn(forbidden, lowered)

    def test_the_absent_means_absent_claim_is_not_restated(self) -> None:
        """The false comment is why nobody checked. It claimed every field of `local_state()` was
        absent-means-absent while `unpushed` was unknown-means-zero."""
        self.assertNotIn("absent means absent", self.source.lower())

    def _function(self, name: str):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        return None

    def _exception_names(self, node) -> set[str]:
        if node is None:
            return {"Exception"}
        return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}

    def _enclosing_function(self, target) -> str:
        best = "<module>"
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.lineno <= target.lineno <= getattr(node, "end_lineno", node.lineno):
                best = node.name
        return best


class SessionStartTest(unittest.TestCase):
    """`disclosure-check.sh` must still emit one valid JSON object. It is in this card's gate risk
    because the hook swallows stderr, so a checker that crashes there is indistinguishable from a
    checker that found nothing."""

    @reaches_home(
        "READS THE REAL MACHINE, deliberately: it runs the hook AS INSTALLED at "
        "~/.claude/hooks/disclosure-check.sh. Copying it into a fixture would test the copy, and "
        "the property under test — the hook swallows stderr, so a checker that crashes there is "
        "indistinguishable from one that found nothing — belongs to the installed file. It already "
        "skips when the hook is absent, which is what a replica under a redirected HOME sees.")
    def test_the_hook_emits_a_single_json_object(self) -> None:
        script = HOOKS / "disclosure-check.sh"
        if not script.is_file():
            self.skipTest("disclosure-check.sh is not installed")
        root = Path(tempfile.mkdtemp(prefix="pd-hookjson-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        proc = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=240,
                              cwd=root, env={**os.environ, "CLAUDE_PROJECT_DIR": str(root),
                                             "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.strip()
        if not out:
            self.skipTest("hook was silent for this fixture")
        blob = json.loads(out)  # single object, or this raises
        self.assertIn("hookSpecificOutput", blob)
        self.assertNotIn("\n", out.strip().rstrip("\n"), "more than one JSON document emitted")


if __name__ == "__main__":
    unittest.main(verbosity=2)
