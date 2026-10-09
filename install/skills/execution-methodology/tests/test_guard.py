"""guard.py against hermetic throwaway repositories.

Ported from the two guards it replaces; each test names the old case ids it carries (`id` for the
identifier guard, `push` for the push guard). Every rule is asserted in both directions, because
"block everything" passes every must-block assertion and "block nothing" every must-pass one.

Every identifier here is synthetic, and the home-path and key fixtures are split so this file does
not trip the guard it tests. Every run has `HOME` redirected to an empty directory, every `GIT_*`
variable removed, and `PD_PRIVATE_IDENTIFIERS` pointed at a fixture (or, for the default-location
case, unset under that redirected `HOME`), so nothing reads this machine's private list or git
identity.
"""
from __future__ import annotations

import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
GUARD = SCRIPTS / "guard.py"
HOOKS_SH = SCRIPTS / "git-hooks.sh"
sys.path.insert(0, str(SCRIPTS))
import guard  # noqa: E402

PROJECT = "zarquon-widget"
PROJECT_TWO = "Blorptastic Engine"
ACCOUNT = "quuxifier-labs"
EMAIL = "selftest@example.invalid"
NAME = "Grimblewort Fnordling"
HOME_PATH = "/Users" + "/hoopfrabjous"
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
ZERO = "0" * 40
REMOVED_OPT_OUT = "!no-private-" + "identifiers"


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="guard-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("GIT_") and k != "PD_ALLOW_MAIN_PUSH"}
        self.env.update(HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CEILING_DIRECTORIES=str(self.tmp), PYTHONDONTWRITEBYTECODE="1",
                        PD_PRIVATE_IDENTIFIERS=str(self.deny([PROJECT, PROJECT_TWO])))
        self.repo = self.new_repo("repo")

    def sh(self, *args, cwd=None, check=True):
        r = subprocess.run(args, cwd=cwd or self.repo, env=self.env, capture_output=True, text=True)
        if check:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def new_repo(self, name, remote=None, user_name=NAME, fmt=None):
        repo = self.tmp / name
        repo.mkdir(parents=True)
        self.sh("git", "init", "-q", "-b", "feature", *([f"--object-format={fmt}"] if fmt else []),
                cwd=repo)
        for key, value in (("user.email", EMAIL), ("user.name", user_name)):
            self.sh("git", "config", key, value, cwd=repo)
        if remote:
            self.sh("git", "remote", "add", "origin", remote, cwd=repo)
        self.commit(repo, {"README.md": "# fixture\n"}, "init")
        return repo

    def deny(self, entries=None, raw=None, name="private-identifiers.txt"):
        path = self.tmp / "lists" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw if raw is not None else
                         ("# synthetic list\n\n" + "".join(f"{e}\n" for e in entries)).encode())
        return path

    def stage(self, files, repo=None):
        repo = repo or self.repo
        for rel, content in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            data = content if isinstance(content, bytes) else content.encode()
            (repo / rel).write_bytes(data)
        self.sh("git", "add", "-A", cwd=repo)

    def commit(self, repo, files, msg="work"):
        self.stage(files, repo)
        self.sh("git", "commit", "-qm", msg, cwd=repo)

    def reset(self):
        self.sh("git", "reset", "-q", "--hard")
        self.sh("git", "clean", "-qfd")

    def run_guard(self, *args, repo=None, deny=..., env=None, stdin=None):
        e = {**self.env, **(env or {})}
        if deny is None:
            e.pop("PD_PRIVATE_IDENTIFIERS")
        elif deny is not ...:
            e["PD_PRIVATE_IDENTIFIERS"] = str(deny)
        r = subprocess.run([sys.executable, str(GUARD), *args], cwd=repo or self.repo, env=e,
                           capture_output=True, text=True, input=stdin)
        return r.returncode, r.stdout + r.stderr

    def staged(self, files, **kw):
        self.reset()
        self.stage(files)
        return self.run_guard("--staged", **kw)

    def message(self, text, **kw):
        path = self.tmp / "COMMIT_EDITMSG"
        path.write_text(text, encoding="utf-8")
        return self.run_guard("--message", str(path), **kw)

    def push(self, payload=None, remote=ZERO, argv=("origin", "git@github.com:example/repo.git"),
             repo=None, env=None):
        repo = repo or self.repo
        head = self.sh("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()
        payload = payload or f"refs/heads/feature {head} refs/heads/feature {remote}\n"
        return self.run_guard("--pre-push", *argv, repo=repo, env=env, stdin=payload)

    def shim(self, condition, message="simulated failure", code=128, action=None):
        """A PATH whose `git` fails one command (args after `-c core.quotepath=false`)."""
        d = self.tmp / f"shim{len(list(self.tmp.glob('shim*')))}"
        d.mkdir()
        (d / "git").write_text(f'#!/bin/sh\nif {condition}; then\n'
                               f'{action or f"  echo {message!r} >&2; exit {code}"}\nfi\n'
                               f'exec {shutil.which("git")} "$@"\n')
        (d / "git").chmod(0o755)
        return {"PATH": f"{d}{os.pathsep}{os.environ['PATH']}"}


class CommitRulesTest(GuardCase):
    def test_staged_content_table(self):  # id 1, 2, 4, 7, 16c, plus the secret patterns
        cases = [
            ("clean", {"app.py": "print('hello')\n"}, 0, None),
            ("home path", {"notes.md": f"run it from {HOME_PATH}/code\n"}, 1, "absolute home path"),
            ("/home path", {"n.md": "from /home" + "/hoopfrabjous/code\n"}, 1, "n.md:1"),
            ("lower-case /users", {"n.md": HOME_PATH.lower() + "/x\n"}, 1, "absolute home path"),
            ("upper-case /HOME", {"n.md": "/HOME" + "/hoopfrabjous/x\n"}, 1, "absolute home path"),
            ("placeholders", {"n.md": "/Users/<name>/code, /home/$USER/code, ~/code\n"
                                      "CI checks out under /home/runner/work and /HOME/RUNNER/w\n"},
             0, None),
            ("private name", {"docs/n.md": f"ported from the {PROJECT} loader\n"}, 1, "private name"),
            ("unrelated word", {"docs/n.md": "ported from the upstream loader\n"}, 0, None),
            ("secret", {"config.py": f'KEY = "{AWS_KEY}"\n'}, 1, "AWS access key id"),
            ("private key", {"k.pem": "-----BEGIN RSA PRIV" + "ATE KEY-----\n"}, 1,
             "private key block"),
            ("clean ++ lines", {"incr.c": "++counter;\n++total;\n"}, 0, None),
        ]
        for label, files, want, needle in cases:
            with self.subTest(label):
                code, out = self.staged(files)
                self.assertEqual(code, want, out)
                if needle:
                    self.assertIn(needle, out)
                    self.assertIn("guard BLOCKED", out)
                else:
                    self.assertNotIn("BLOCKED", out)

    def test_every_spelling_of_a_listed_name_is_caught(self):  # id 4c, 9r, 9s, 9v
        for spelling in ("blorptastic-engine", "Blorptastic_Engine", "BLORPTASTICENGINE",
                         "blorptastic.engine", "blorptastic–engine"):
            with self.subTest(spelling):
                self.assertEqual(self.staged({"n.md": f"see the {spelling} repo\n"})[0], 1)
        en_dash = self.deny([PROJECT.replace("-", "–")], name="dash.txt")
        self.assertEqual(self.staged({"n.md": f"the {PROJECT} loader\n"}, deny=en_dash)[0], 1)
        self.assertEqual(self.staged({"n.md": "the upstream loader\n"}, deny=en_dash)[0], 0)
        accented = "Zarquön-Widget"
        self.assertEqual(self.staged({"n.md": f"the {accented} loader\n"},
                                     deny=self.deny([accented], name="acc.txt"))[0], 1)

    def test_message_mode(self):  # id 1c, 3a, 3b, 3c, 5a, 5b
        self.assertEqual(self.message("feat: add a thing\n")[0], 0)
        code, out = self.message(f"fix: the loader\n\nfound it under {HOME_PATH}/src\n")
        self.assertEqual(code, 1, out)
        self.assertIn("commit message:3", out)
        self.assertEqual(self.message(f"feat: reuse the {PROJECT} approach\n")[0], 1)
        code, out = self.message("feat: a clean subject\n"
                                 "# Please enter the commit message for your changes. Lines starting\n"
                                 f"# on branch feature, the {PROJECT} template\n"
                                 "# ------------------------ >8 ------------------------\n"
                                 f"diff --git a/x b/x\n+see {PROJECT} at {HOME_PATH}\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.staged({"app.py": "print('hello')\n"})[0], 0)  # 3c: the message is not staged

    def test_message_scan_respects_retained_comments_and_scissors(self):  # review R8
        retained = (f"feat: a clean subject\n# the {PROJECT} note\n",
                    "feat: a clean subject\n# ------------------------ >8 ------------------------\n"
                    f"kept by -m: {HOME_PATH}/src\n")
        for text in retained:  # `git commit -m` cleans whitespace only: these lines are kept
            with self.subTest(text[:40]):
                self.assertEqual(self.message(text)[0], 1)
        self.sh("git", "config", "commit.cleanup", "strip")  # `#` lines go; the scissors tail stays
        self.assertEqual(self.message(retained[0])[0], 0)
        self.assertEqual(self.message(retained[1])[0], 1)
        self.sh("git", "config", "--unset", "commit.cleanup")
        self.sh("git", "config", "core.commentChar", ";")
        editor = ("feat: a clean subject\n; Please enter the commit message for your changes.\n"
                  f"; the {PROJECT} template\n# kept: {PROJECT}\n")
        code, out = self.message(editor)  # an editor template under another comment character
        self.assertEqual(code, 1, out)
        self.assertIn("commit message:4", out)
        self.sh("git", "commit", "-q", "--allow-empty", "-m", "subject",
                    "-m", f"# body {PROJECT}")
        self.assertIn(PROJECT, self.sh("git", "log", "-1", "--format=%B").stdout)  # git kept it

    def test_a_listed_name_in_a_staged_path_is_blocked(self):  # id 6
        code, out = self.staged({f"docs/{PROJECT}-migration.md": "nothing sensitive\n"})
        self.assertEqual(code, 1, out)
        self.assertIn("path docs/", out)

    def test_local_git_identity(self):  # id 7
        repo = self.new_repo("ssh", remote=f"git@github.com:{ACCOUNT}/thing.git")
        for content, rule in ((f"mail {EMAIL} about it", "git author email"),
                              (f"written by {NAME}", "git author name"),
                              (f"clone from github.com/{ACCOUNT}/other", "remote account name")):
            with self.subTest(rule):
                self.stage({"docs/contact.md": content + "\n"}, repo)
                code, out = self.run_guard("--staged", repo=repo)
                self.assertEqual(code, 1, out)
                self.assertIn(rule, out)
        https = self.new_repo("https", remote=f"https://github.com/{ACCOUNT}/thing.git")
        self.stage({"c.md": f"clone from {ACCOUNT}/thing\n"}, https)
        code, out = self.run_guard("--staged", repo=https)
        self.assertEqual(code, 1, out)
        self.assertIn("remote account name", out)
        self.stage({"docs/contact.md": "mail the maintainers about it\n"}, repo)
        self.assertEqual(self.run_guard("--staged", repo=repo)[0], 0)

    def test_history_is_not_reflagged(self):  # id 10, 16f
        self.commit(self.repo, {f"{PROJECT}-legacy.md": f"the old {PROJECT} notes\n"}, "legacy")
        self.stage({f"{PROJECT}-legacy.md": f"the old {PROJECT} notes\nplus a line\n"})
        self.assertEqual(self.run_guard("--staged")[0], 0)
        (self.repo / f"{PROJECT}-legacy.md").unlink()
        self.sh("git", "add", "-A")
        self.assertEqual(self.run_guard("--staged")[0], 0)  # a deletion is not a finding
        self.stage({"fresh.md": f"a new mention of {PROJECT}\n"})
        self.assertEqual(self.run_guard("--staged")[0], 1)

    def test_the_diff_format_cannot_disguise_content(self):  # id 16a, 16b, 16d, 16e, 16g
        code, out = self.staged({"incr.c": f"++ {HOME_PATH}/secret\n"})
        self.assertEqual(code, 1, out)
        self.assertIn("incr.c:1", out)
        patch = f"diff --git a/x b/x\n--- a/x\n+++ {HOME_PATH}/b\n@@ -0,0 +1 @@\n+hello\n"
        self.assertEqual(self.staged({"fixtures/sample.patch": patch})[0], 1)
        code, out = self.staged({"aaa-clean.md": "nothing here\n", "zzz-dirty.md": f"see {HOME_PATH}\n"})
        self.assertIn("zzz-dirty.md:1", out)
        self.assertNotIn("aaa-clean.md", out)
        for setting in ("diff.mnemonicPrefix", "diff.noprefix"):
            with self.subTest(setting):
                self.sh("git", "config", setting, "true")
                code, out = self.staged({"cfg-leak.md": f"{setting} fixture {HOME_PATH}/code\n"})
                self.assertEqual(code, 1, out)
                self.assertIn("cfg-leak.md:1", out)
                self.sh("git", "config", "--unset", setting)

    def test_repo_declared_binary_does_not_switch_the_commit_scan_off(self):  # push 17, staged side
        code, out = self.staged({".gitattributes": "* -diff\n", "config.py": f'K = "{AWS_KEY}"\n'})
        self.assertEqual(code, 1, out)
        self.assertIn("config.py", out)


class ListTest(GuardCase):
    def setUp(self):
        super().setUp()
        self.stage({"app.py": "print('hello')\n"})  # clean, so an exit 2 is never a finding

    def test_missing_list_fails_closed(self):  # id 8
        absent = self.tmp / "nowhere" / "list.txt"
        code, out = self.run_guard("--staged", deny=absent)
        self.assertEqual(code, 2, out)
        self.assertIn("not checked", out)
        self.assertIn("one name per line", out)
        self.assertIn("nowhere/list.txt", out)
        self.assertEqual(self.staged({"d.md": f"mention {PROJECT}\n"}, deny=absent)[0], 2)
        self.assertEqual(self.staged({"d.md": f"see {HOME_PATH}\n"}, deny=absent)[0], 2)
        self.assertEqual(self.message("fix: nothing\n", deny=absent)[0], 2)
        self.assertFalse((self.home / ".claude").exists())
        code, out = self.run_guard("--staged", deny=None)  # the default location, HOME redirected
        self.assertEqual(code, 2, out)
        self.assertIn("~/.claude/private-identifiers.txt", out)
        self.assertNotIn(str(self.home), out)

    def test_broken_lists_fail_closed_without_echoing_the_entry(self):  # id 9, 18
        unusable = [
            ("empty", None, b"# only a comment\n", "no usable entries"),
            ("commented directive", None, f"# {REMOVED_OPT_OUT}\n".encode(), "no usable entries"),
            ("undecodable", None, b"# list\nzarquon-\xff\xfewidget\n", "UTF-8"),
            ("too short", ["qz"], None, "under 3 characters"),
            ("backslash", [PROJECT_TWO.replace(" ", "\\ ")], None, "backslash"),
            ("separators only", ["-_-"], None, "only separators"),
            ("zero-width space", [PROJECT.replace("-", "​")], None, "U+200B"),
            ("soft hyphen", [PROJECT.replace("-", "­")], None, "U+00AD"),
            ("interior tab", [PROJECT.replace("-", "\t")], None, "U+0009"),
            ("non-leading BOM", [PROJECT + "﻿"], None, "U+FEFF"),
            ("removed directive", [REMOVED_OPT_OUT], None, "begins with `!`"),
            ("its upper case", [REMOVED_OPT_OUT.upper()], None, "begins with `!`"),
            ("a misspelling", ["!no-private-identifer"], None, "begins with `!`"),
            ("directive beside a real entry", [REMOVED_OPT_OUT, PROJECT], None, "did not run"),
        ]
        for i, (label, entries, raw, needle) in enumerate(unusable):
            with self.subTest(label):
                code, out = self.run_guard("--staged", deny=self.deny(entries, raw, f"l{i}.txt"))
                self.assertEqual(code, 2, out)
                self.assertIn(needle, out)
                self.assertNotIn("zarquon", out.lower())
                self.assertNotIn("blorptastic", out.lower())
                self.assertNotIn("no-private-ident", out)
                self.assertNotIn(" qz", out)
        self.assertNotIn("delet", self.run_guard("--staged", deny=self.deny([], name="e.txt"))[1])
        with self.subTest("a directory"):
            (self.tmp / "as-a-dir").mkdir()
            self.assertEqual(self.run_guard("--staged", deny=self.tmp / "as-a-dir")[0], 2)
        with self.subTest("unreadable"):
            locked = self.deny([PROJECT], name="locked.txt")
            locked.chmod(0)
            self.addCleanup(locked.chmod, 0o644)
            # A user who can read mode-000 files (root) cannot exercise this case; fail, never skip.
            self.assertFalse(os.access(locked, os.R_OK), "this suite must run as a non-root user")
            self.assertEqual(self.run_guard("--staged", deny=locked)[0], 2)

    def test_usable_variants_load_and_block(self):  # id 9n, 9p, 9q, 18f, 18j
        self.assertEqual(self.run_guard("--staged")[0], 0)
        for label, deny in (("bom", self.deny(raw=b"\xef\xbb\xbf" + PROJECT.encode() + b"\n",
                                              name="bom.txt")),
                            ("no bom", self.deny(raw=PROJECT.encode() + b"\n", name="plain.txt"))):
            with self.subTest(label):
                self.assertEqual(self.staged({"n.md": f"the {PROJECT} loader\n"}, deny=deny)[0], 1)
        self.assertEqual(self.staged({"n.md": f"the {PROJECT_TWO} rewrite\n"})[0], 1)

    def test_the_folded_separators_are_exactly_pd_and_zs(self):  # id 9w
        expected = {chr(c) for c in range(sys.maxunicode + 1)
                    if unicodedata.category(chr(c)) in ("Pd", "Zs")} | set("-_. ")
        self.assertEqual(set(guard.SEPARATORS), expected)

    def test_there_is_no_opt_out(self):  # id 18b
        self.assertNotIn("no-private-identifiers", GUARD.read_text(encoding="utf-8"))

    def test_a_dead_identity_rule_fails_closed(self):  # id 11d, 11f
        repo = self.new_repo("dead", user_name="_-_-")
        self.stage({"app.py": "print('hello')\n"}, repo)
        code, out = self.run_guard("--staged", repo=repo)
        self.assertEqual(code, 2, out)
        self.assertIn("matches the empty string", out)
        self.assertEqual(self.run_guard("--staged")[0], 0)


class OutputAndArgvTest(GuardCase):
    def test_output_does_not_republish_what_it_redacts(self):  # id 14
        for files in ({"docs/n.md": f"ported from the {PROJECT} loader\n"},
                      {f"docs/{PROJECT}.md": "body\n"}):
            code, out = self.staged(files)
            self.assertEqual(code, 1, out)
            self.assertNotIn(PROJECT, out)
        code, out = self.message(f"feat: from {PROJECT}\n")
        self.assertEqual(code, 1, out)
        self.assertNotIn(PROJECT, out)
        code, out = self.staged({"docs/Zarquon_Widget/notes.md": f"the {PROJECT} loader\n"})
        self.assertEqual(code, 1, out)
        self.assertNotIn("Zarquon_Widget", out)
        self.assertIn("notes.md:1", out)
        code, out = self.staged({"n.md": f"see {HOME_PATH}/code\n"})
        self.assertNotIn("hoopfrabjous", out)
        (self.home / "dir").mkdir()
        code, out = self.run_guard("--message", str(self.home / "dir"))
        self.assertEqual(code, 2, out)
        self.assertIn("~/dir", out)
        self.assertIn("was not scanned", out)
        self.assertNotIn(str(self.home), out)

    def test_argv(self):  # id 15; push 6
        self.stage({"n.md": f"see {HOME_PATH}/code\n"})
        code, out = self.run_guard("--help")
        self.assertEqual(code, 0)
        self.assertNotIn("BLOCKED", out)
        for args in (["--nonsense"], [], ["--staged", "--message", "x"], ["--pre-push", "--nonsense"],
                     ["--pre-push", "origin", "--help"], ["--message"]):
            with self.subTest(args):
                self.assertEqual(self.run_guard(*args)[0], 2)
        outside = self.tmp / "not-a-repo"
        outside.mkdir()
        self.assertEqual(self.run_guard("--staged", repo=outside)[0], 2)

    def test_self_test_passes(self):
        code, out = self.run_guard("--self-test")
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_a_crash_is_exit_2_and_does_not_print_the_home_directory(self):  # id 12a, 12b, 12e
        boom = MemoryError(f"simulated at {Path.home()}/x")
        with mock.patch.object(guard, "commit_rules", return_value=[]), \
                mock.patch.object(guard, "staged", side_effect=boom), \
                mock.patch.object(sys, "stderr", new_callable=io.StringIO) as err:
            code = guard.main(["--staged"])  # commit_rules is stubbed: no real list or identity
        self.assertEqual(code, 2)
        self.assertIn("the guard crashed (MemoryError)", err.getvalue())
        self.assertIn("Traceback", err.getvalue())
        self.assertNotIn(str(Path.home()) + "/", err.getvalue())

    def test_ctrl_c_is_exit_2(self):  # id 12c, 12d; push 14c
        marker = self.tmp / "started"
        env = {**self.env, **self.shim('[ "$3" = "diff" ] && [ "$4" = "--cached" ] && [ "$5" = "--text" ]',
                                       action=f"  touch {marker}; exec sleep 30")}
        self.stage({"app.py": "x\n"})
        p = subprocess.Popen([sys.executable, str(GUARD), "--staged"], cwd=self.repo, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 20
        while not marker.exists() and time.time() < deadline and p.poll() is None:
            time.sleep(0.05)
        p.send_signal(signal.SIGINT)
        out, _ = p.communicate(timeout=20)
        self.assertEqual(p.returncode, 2, out)
        self.assertIn("interrupted", out)


class PrePushTest(GuardCase):
    def test_ranges(self):  # push 1, 2, 6a, 6b, 8
        self.commit(self.repo, {"app.py": "print('hello')\n"})
        self.assertEqual(self.push(), (0, ""))
        self.commit(self.repo, {"latin.py": b"# caf\xe9 is not UTF-8\n", "config.py": f'K = "{AWS_KEY}"\n'})
        code, out = self.push()
        self.assertEqual(code, 1, out)
        self.assertIn("AWS access key id", out)
        self.assertIn("config.py", out)
        self.assertNotIn(AWS_KEY, out)
        self.assertNotIn("Traceback", out)

    def test_a_large_range_is_scanned_in_full(self):  # push 3
        filler = ("x" * 80 + "\n") * 115_000  # about 9 MB each, under the blob limit
        self.commit(self.repo, {**{f"bulk{i}.txt": filler for i in range(5)},
                                "leaked.py": f'KEY = "{AWS_KEY}"\n'})
        code, out = self.push()
        self.assertEqual(code, 1, out)
        self.assertIn("AWS access key id", out)
        self.assertNotIn("blob over", out)

    def test_an_oversized_blob_is_blocked_whatever_the_environment(self):  # push 4
        self.commit(self.repo, {"big.bin": "y" * (11 * 1024 * 1024)})
        code, out = self.push(env={"PD_MAX_FILE_MB": "99999"})
        self.assertEqual(code, 1, out)
        self.assertIn("limit 10 MB", out)
        self.assertIn("big.bin", out)

    def test_git_failures_are_exit_2(self):  # push 7, 9, 10, 12, 13, 19
        base = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        self.commit(self.repo, {"config.py": f'K = "{AWS_KEY}"\n'})
        head = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        code, out = self.push(remote="1" * 40)
        self.assertEqual(code, 2, out)
        self.assertIn("object store", out)
        code, out = self.push(payload=f"refs/heads/feature {head} refs/heads/feature\n")
        self.assertEqual(code, 2, out)
        self.assertIn("3 fields", out)
        shims = (('[ "$3" = "log" ]', "fatal: unable to read object"),
                 ('[ "$3" = "cat-file" ] && [ "$4" = "-e" ]', "fatal: Permission denied"),
                 ('[ "$3" = "cat-file" ] && [ "$4" != "-e" ]', "simulated cat-file failure"))
        for condition, message in shims:
            with self.subTest(condition):
                code, out = self.push(remote=base, env=self.shim(condition, message))
                self.assertEqual(code, 2, out)
                self.assertIn(message, out)
        bare = self.tmp / "bare.git"
        self.sh("git", "clone", "-q", "--bare", str(self.repo), str(bare))
        self.assertEqual(self.push(repo=bare)[0], 2)

    def test_a_corrupt_object_in_the_range_is_exit_2(self):  # push 13d, 13e
        base = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        self.commit(self.repo, {"app.py": "ok\n"})
        loose = self.repo / ".git" / "objects" / base[:2] / base[2:]
        loose.chmod(0o644)
        loose.write_bytes(b"not a zlib stream")
        code, out = self.push(remote=base)
        self.assertEqual(code, 2, out)
        self.assertIn("could not run", out)

    def test_direct_push_to_the_default_branch(self):  # push 15
        base = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        self.commit(self.repo, {"app.py": "ok\n"})
        head = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        payload = f"refs/heads/main {head} refs/heads/main {base}\n"
        code, out = self.push(payload=payload)
        self.assertEqual(code, 1, out)
        self.assertIn("pull request", out)
        self.assertIn("1/true/yes/on", out)
        self.assertIn("0, false, no, off", out)
        for value in ("1", "true", "yes", "on", "TRUE", "On", " 1 ", "\tyes\n"):
            with self.subTest(allow=value):
                self.assertEqual(self.push(payload=payload, env={"PD_ALLOW_MAIN_PUSH": value})[0], 0)
        for value in ("0", "false", "no", "off", "FALSE", "Off", "", " 0 ", "\tfalse\n", "maybe",
                      "banana", "2", "-1", "yes please", "true story", "null", "None"):
            with self.subTest(refuse=value):
                self.assertEqual(self.push(payload=payload, env={"PD_ALLOW_MAIN_PUSH": value})[0], 1)
        master = f"refs/heads/master {head} refs/heads/master {base}\n"
        self.assertEqual(self.push(payload=master)[0], 1)
        first = f"refs/heads/main {head} refs/heads/main {ZERO}\n"
        self.assertEqual(self.push(payload=first)[0], 0)  # creating main is not moving it
        self.commit(self.repo, {"creds.txt": f"aws_key = {AWS_KEY}\n"})
        tip = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        code, out = self.push(payload=f"refs/heads/main {tip} refs/heads/main {base}\n",
                              env={"PD_ALLOW_MAIN_PUSH": "1"})
        self.assertEqual(code, 1, out)
        self.assertIn("creds.txt", out)

    def test_push_blocks_merge_only_secret(self):  # review R9
        base = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        self.sh("git", "checkout", "-q", "-b", "side")
        self.commit(self.repo, {"side.md": "side work\n"})
        self.sh("git", "checkout", "-q", "feature")
        self.commit(self.repo, {"main.md": "main work\n"})
        self.sh("git", "merge", "-q", "--no-commit", "--no-ff", "side")
        self.stage({"resolved.py": f'K = "{AWS_KEY}"\n'})  # in neither parent: the merge adds it
        self.sh("git", "commit", "-q", "--no-verify", "-m", "merge side")
        code, out = self.push(remote=base)
        self.assertEqual(code, 1, out)
        self.assertIn("resolved.py", out)
        self.assertEqual(out.count("guard BLOCKED"), 1, out)  # one finding, not one per parent
        self.sh("bash", str(HOOKS_SH), "--guard", str(GUARD), str(self.repo))
        self.sh("git", "checkout", "-q", "-b", "other", base)
        self.stage({"leak.md": f"see {HOME_PATH}/code\n"})
        self.sh("git", "commit", "-q", "--no-verify", "-m", "past the hooks")
        self.sh("git", "checkout", "-q", "feature")
        r = self.sh("git", "merge", "-q", "--no-edit", "other", check=False)  # pre-merge-commit
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("absolute home path", r.stdout + r.stderr)

    def test_new_remote_push_scans_other_remote_history(self):  # review R10
        for name in ("private", "public"):
            self.sh("git", "init", "-q", "--bare", str(self.tmp / f"{name}.git"))
            self.sh("git", "remote", "add", name, str(self.tmp / f"{name}.git"))
        self.commit(self.repo, {"config.py": f'K = "{AWS_KEY}"\n'})
        self.sh("git", "push", "-q", "private", "feature")  # now reachable from refs/remotes/private
        public = ("public", str(self.tmp / "public.git"))
        code, out = self.push(argv=public)
        self.assertEqual(code, 1, out)
        self.assertIn("config.py", out)
        self.assertEqual(self.push(argv=("private", str(self.tmp / "private.git")))[0], 0)
        for argv in ((str(self.tmp / "public.git"),) * 2, ("pr*",  "url"), ()):  # unknown: all of it
            with self.subTest(argv):
                self.assertEqual(self.push(argv=argv)[0], 1)

    def test_empty_secret_rules_fail_closed(self):  # review R11, push 18
        self.commit(self.repo, {"config.py": f'K = "{AWS_KEY}"\n'})
        head = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        payload = f"refs/heads/feature {head} refs/heads/feature {ZERO}\n"
        patches = {"empty": "guard.SECRET_RULES = ()",
                   "one dropped": "guard.SECRET_RULES = guard.SECRET_RULES[1:]",
                   "one dead": "guard.SECRET_RULES[0] = (guard.SECRET_RULES[0][0], "
                               "re.compile('x^'), 'secret')",
                   "bad pattern": "guard.SECRET_PATTERNS += (('broken', '(', 'x'),); "
                                  "guard.SECRET_RULES = guard.secret_rules()"}
        for label, patch in patches.items():
            for args in (["--pre-push", "origin", "url"], ["--self-test"]):
                with self.subTest(label, mode=args[0]):
                    code = (f"import re, sys; sys.path.insert(0, {str(SCRIPTS)!r}); import guard; "
                            f"{patch}; raise SystemExit(guard.main({args!r}))")
                    r = subprocess.run([sys.executable, "-c", code], cwd=self.repo, env=self.env,
                                       input=payload, capture_output=True, text=True)
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn("not a clean result", r.stderr)
        self.assertEqual(self.push()[0], 1)  # the unpatched rule set still runs and finds it

    def test_sha256_null_oid(self):  # push 16
        repo = self.new_repo("sha256", fmt="sha256")
        code, out = self.push(remote="0" * 64, repo=repo)
        self.assertEqual(code, 0, out)
        self.assertNotIn("git fetch", out)
        self.commit(repo, {"config.py": f'K = "{AWS_KEY}"\n'})
        code, out = self.push(remote="0" * 64, repo=repo)
        self.assertEqual(code, 1, out)
        self.assertIn("AWS access key id", out)

    def test_repo_declared_binary_does_not_switch_the_scan_off(self):  # push 17
        cases = (("-diff", {".gitattributes": "* -diff\n", "config.py": f'K = "{AWS_KEY}"\n'}),
                 ("NUL", {"config.py": b"\x00\x00\x00\x00" + f'K = "{AWS_KEY}"\n'.encode()}),
                 ("NUL and \\x0b", {"config.py": b"\x00\x0b" + f'K = "{AWS_KEY}"\n'.encode()}))
        for i, (label, files) in enumerate(cases):
            with self.subTest(label):
                repo = self.new_repo(f"bin{i}")
                self.commit(repo, files)
                code, out = self.push(repo=repo)
                self.assertEqual(code, 1, out)
                self.assertIn("AWS access key id", out)
                self.assertIn("config.py", out)
                self.assertNotIn("could not run", out)


class ThroughRealHooksTest(GuardCase):
    """A real `git commit` and `git push` through hooks written by git-hooks.sh (id 13, push 11)."""

    def test_commit_and_push(self):
        r = self.sh("bash", str(HOOKS_SH), "--guard", str(GUARD), str(self.repo))
        self.assertIn("pre-push", r.stdout)
        head = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        self.stage({"app.py": "print('hello')\n"})
        self.sh("git", "commit", "-qm", "clean work")
        clean = self.sh("git", "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(clean, head)
        self.stage({"leak.md": f"see {HOME_PATH}/code\n"})
        r = self.sh("git", "commit", "-qm", "leak", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("absolute home path", r.stdout + r.stderr)
        self.reset()
        self.stage({"ok.md": "fine\n"})
        r = self.sh("git", "commit", "-qm", f"feat: from {PROJECT}", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("commit message:1", r.stdout + r.stderr)
        self.assertEqual(self.sh("git", "rev-parse", "HEAD").stdout.strip(), clean)
        self.reset()

        remote = self.tmp / "remote.git"
        self.sh("git", "init", "-q", "--bare", str(remote))
        self.sh("git", "remote", "add", "origin", str(remote))
        self.sh("git", "push", "-q", "origin", "feature")
        self.assertEqual(self.sh("git", "rev-parse", "feature", cwd=remote).stdout.strip(), clean)
        self.commit(self.repo, {"later.md": "more\n"})
        (self.repo / "config.py").write_text(f'K = "{AWS_KEY}"\n')  # committed past the hooks
        self.sh("git", "add", "-A")
        self.sh("git", "commit", "-qm", "planted", "--no-verify")
        r = self.sh("git", "push", "origin", "feature", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("AWS access key id", r.stdout + r.stderr)
        self.assertEqual(self.sh("git", "rev-parse", "feature", cwd=remote).stdout.strip(), clean)


if __name__ == "__main__":
    unittest.main()
