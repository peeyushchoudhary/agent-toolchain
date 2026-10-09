"""git-hooks.sh against throwaway repositories with a redirected HOME."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HOOKS_SH = SCRIPTS / "git-hooks.sh"
MARKER = "# swe-agent guard"
NAMES = ("pre-commit", "commit-msg", "pre-push")


class GitHooksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="git-hooks-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(HOME=str(self.tmp / "home"), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CEILING_DIRECTORIES=str(self.tmp))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.guard = self.tmp / "skill dir" / "guard.py"  # a space, so the hook's quoting is tested
        self.guard.parent.mkdir()
        shutil.copy(SCRIPTS / "guard.py", self.guard)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def hooks(self, *args):
        return subprocess.run(["bash", str(HOOKS_SH), *args, str(self.repo)], env=self.env,
                              capture_output=True, text=True)

    def test_writes_three_marked_hooks_that_run_the_guard(self):
        r = self.hooks("--guard", str(self.guard))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hooks = self.repo / ".git" / "hooks"
        for name in NAMES:
            text = (hooks / name).read_text()
            self.assertIn(MARKER, text.splitlines())
            self.assertIn(str(self.guard), text)
            self.assertTrue(os.access(hooks / name, os.X_OK))
        self.assertIn('--message "$1"', (hooks / "commit-msg").read_text())
        p = subprocess.run([str(hooks / "pre-push"), "origin", "url"], cwd=self.repo, env=self.env,
                           input="", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)  # the guard ran on an empty payload
        self.assertEqual(self.hooks("--guard", str(self.guard)).returncode, 0)  # idempotent

    def test_core_hooks_path_is_honoured(self):
        self.git("config", "core.hooksPath", "custom-hooks")
        r = self.hooks("--guard", str(self.guard))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in NAMES:
            self.assertTrue((self.repo / "custom-hooks" / name).is_file(), name)
            self.assertFalse((self.repo / ".git" / "hooks" / name).exists(), name)

    def test_an_absent_guard_is_refused_and_nothing_is_written(self):
        before = sorted(p.name for p in (self.repo / ".git" / "hooks").iterdir())
        for args in (["--guard", str(self.tmp / "missing.py")], []):  # [] is the default under HOME
            with self.subTest(args):
                r = self.hooks(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(len((r.stdout + r.stderr).strip().splitlines()), 1)
                self.assertEqual(sorted(p.name for p in (self.repo / ".git" / "hooks").iterdir()),
                                 before)

    def test_a_guard_removed_after_install_blocks_rather_than_skips(self):
        self.hooks("--guard", str(self.guard))
        self.guard.unlink()
        (self.repo / "a.txt").write_text("x\n")
        self.git("add", "-A")
        r = subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=f@example.invalid",
                            "commit", "-qm", "x"], cwd=self.repo, env=self.env, capture_output=True,
                           text=True)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_foreign_hook_is_left_alone_and_uninstall_removes_only_marked_files(self):
        hooks = self.repo / ".git" / "hooks"
        foreign = "#!/bin/sh\necho mine\n"
        (hooks / "pre-push").write_text(foreign)
        r = self.hooks("--guard", str(self.guard))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("left alone", r.stderr)
        self.assertEqual((hooks / "pre-push").read_text(), foreign)
        self.assertIn(MARKER, (hooks / "pre-commit").read_text())
        r = self.hooks("--uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((hooks / "pre-commit").exists())
        self.assertFalse((hooks / "commit-msg").exists())
        self.assertEqual((hooks / "pre-push").read_text(), foreign)
        self.assertTrue(any(p.name.endswith(".sample") for p in hooks.iterdir()))


if __name__ == "__main__":
    unittest.main()
