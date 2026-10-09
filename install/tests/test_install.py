"""install.sh against a temporary HOME and CODEX_HOME.

Every test builds its own scratch home; nothing here reads or writes the real ~/.claude or ~/.codex.
The retired names are read from install.sh's own retire-v5 list (the lines between its markers are
evaluated by bash), so this file adds no second copy of the set verify.sh's dangling-name scan
looks for.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INSTALL = Path(__file__).resolve().parents[1]
SCRIPT = INSTALL / "install.sh"
SKILLS = INSTALL / "skills"
SKILL = "execution-methodology"
GOAL_STOP = f"skills/{SKILL}/scripts/goal.py stop-hook"  # the v6- and T7-era global registration
RUN_SH = f"skills/{SKILL}/scripts/run.sh"
GLOBAL = (INSTALL / "global.md").read_text(encoding="utf-8")


def retire_list() -> dict[str, list[str] | str]:
    text = SCRIPT.read_text(encoding="utf-8")
    block = text.split("# BEGIN retire-v5 list", 1)[1].split("# END retire-v5 list", 1)[0]
    names = ("RETIRED_SKILLS", "RETIRED_PERSONAS", "RETIRED_HOOKS", "RETIRED_FILES", "GENERATED_MARK")
    out = subprocess.run(["bash", "-c", block + "".join(f'\nprintf "%s\\0" "${n}"' for n in names)],
                         capture_output=True, text=True, check=True).stdout.split("\0")
    lists = {n: v.split() for n, v in zip(names, out)}
    return {**lists, "GENERATED_MARK": out[4]}


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def commands(file: Path, event: str = "Stop") -> list[str]:
    hooks = json.loads(file.read_text()).get("hooks", {})
    return [h["command"] for e in hooks.get(event, []) for h in e["hooks"]]


class E2ERunTests(unittest.TestCase):
    """e2e_run.sh and run.sh with neither the claude nor the codex CLI on PATH: a stub directory
    holding git and python3 comes first and only the system directories follow. No network."""

    E2E = SKILLS / SKILL / "tests" / "e2e_run.sh"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="e2e-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        stubs = self.tmp / "bin"
        stubs.mkdir()
        (stubs / "git").symlink_to(shutil.which("git"))
        (stubs / "python3").symlink_to(sys.executable)
        path = f"{stubs}:/usr/bin:/bin:/usr/sbin:/sbin"
        for cli in ("claude", "codex"):
            self.assertIsNone(shutil.which(cli, path=path), cli)
        (self.tmp / "home").mkdir()
        self.env = {**os.environ, "PATH": path, "HOME": str(self.tmp / "home"), "PYTHONDONTWRITEBYTECODE": "1",
                    "GIT_CONFIG_NOSYSTEM": "1", "RUN_NO_NOTIFY": "1",
                    "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                    "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
        for var in ("CODEX_HOME", "CODEX_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY",
                    "E2E_CODEX_AUTH_JSON", "E2E_KEEP", "E2E_FAKE_NO_STOP_HOOK", "RUN_HARNESS_CMD", "RUN_PROMPT"):
            self.env.pop(var, None)

    def e2e(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.E2E), *args], env={**self.env, **env}, capture_output=True,
                              text=True, timeout=300, cwd=self.tmp)

    def test_e2e_requires_every_requested_live_harness(self):
        for args, names in ((["--harness", "codex"], ["codex"]), (["--live"], ["claude", "codex"])):
            r = self.e2e(*args)
            out = r.stdout + r.stderr
            self.assertNotEqual(r.returncode, 0, out)
            for name in names:
                self.assertRegex(out, rf"e2e_run: {name} +FAIL: a live run was requested", out)
            self.assertNotIn("fake harness", out)
            self.assertNotIn("run.sh", out)

    def test_e2e_rejects_missing_session_stop_hook(self):
        r = self.e2e(E2E_FAKE_NO_STOP_HOOK="1")
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 1, out)
        for harness in ("claude", "codex"):
            self.assertRegex(out, rf"e2e_run: {harness} session stop hook +FAIL: .*Stop hook never ran", out)
        self.assertIn("e2e_run: FAIL", out.splitlines()[-1])

    def test_codex_session_denies_local_transport_push(self):
        sys.path.insert(0, str(SKILLS / SKILL / "tests"))
        from fixtures.goal_fixture import Repo  # noqa: E402
        repo = Repo()
        self.addCleanup(repo.cleanup)
        origin, log = self.tmp / "origin.git", self.tmp / "pushes.log"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, env=self.env)
        subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=repo.dir, check=True, env=self.env)
        stub = self.tmp / "session.sh"  # the session: a local-transport push four ways, exit codes logged
        stub.write_text(f"""for cmd in "git push --dry-run origin HEAD" "git push origin HEAD" \\
           "git push --no-verify origin HEAD" "git -c remote.origin.pushurl={origin} push origin HEAD"; do
  $cmd >/dev/null 2>&1; echo "$? $cmd" >> '{log}'
done
""")
        r = subprocess.run(["bash", str(SKILLS / SKILL / "scripts" / "run.sh"), "F-9", "--harness", "codex",
                            "--sessions", "1"], cwd=repo.dir, capture_output=True, text=True, timeout=120,
                           env={**self.env, "RUN_HARNESS_CMD": f"bash {stub}"})
        attempts = log.read_text().splitlines()
        self.assertEqual(len(attempts), 4, r.stdout + r.stderr)
        for attempt in attempts:
            self.assertNotEqual(attempt.split(" ", 1)[0], "0", attempt)
        refs = subprocess.run(["git", "for-each-ref"], cwd=origin, capture_output=True, text=True, env=self.env)
        self.assertEqual(refs.stdout, "")
        left = subprocess.run(["git", "config", "--local", "--get-regexp", r"pushinsteadof|hookspath"],
                              cwd=repo.dir, capture_output=True, text=True, env=self.env)
        self.assertEqual(left.stdout, "", "run.sh did not restore the repository's git config")


class InstallCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="t7-home-")).resolve()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.claude, self.codex = self.home / ".claude", self.home / ".codex"
        self.codex.mkdir()
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.codex),
                    "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                    "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
        for var in ("CLAUDE_PROJECT_DIR", "GOAL_ROLE"):
            self.env.pop(var, None)

    def install(self, *args, ok=True):
        r = subprocess.run(["bash", str(SCRIPT), *args], env=self.env, capture_output=True, text=True,
                           cwd=self.home)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def stop_registrations(self, file: Path) -> list[str]:
        return [c for c in commands(file) if "goal.py stop-hook" in c] if file.is_file() else []


class InstallTest(InstallCase):
    def test_installs_global_file_and_skill_and_registers_no_hook_in_either_harness(self):
        self.install()
        for root, name, hooks in ((self.claude, "CLAUDE.md", "settings.json"), (self.codex, "AGENTS.md", "hooks.json")):
            self.assertEqual((root / name).read_text(encoding="utf-8"), GLOBAL)
            self.assertEqual({p.name for p in (root / "skills").iterdir()}, {SKILL})
            installed = root / "skills" / SKILL
            self.assertEqual({p.name for p in installed.iterdir()}, {"SKILL.md", "references", "agents", "scripts"})
            self.assertTrue(os.access(root / RUN_SH, os.X_OK), root / RUN_SH)
            # run.sh registers the Stop hook per session; the installer never does (S-1 decision).
            self.assertFalse((root / hooks).exists(), root / hooks)
        self.assertFalse((self.claude / "agents").exists())

    def test_a_differing_global_file_is_backed_up_and_an_equal_one_is_left_alone(self):
        mine = self.write(self.claude / "CLAUDE.md", "my own rules\n")
        self.write(self.codex / "AGENTS.md", GLOBAL)
        out = self.install().stdout
        backups = list(self.claude.glob("CLAUDE.md.bak-*"))
        self.assertEqual(len(backups), 1, out)
        self.assertEqual(backups[0].read_text(), "my own rules\n")
        self.assertIn(f"backup: {backups[0]}", out)
        self.assertEqual(mine.read_text(encoding="utf-8"), GLOBAL)
        self.assertFalse(list(self.codex.glob("AGENTS.md.bak-*")))
        self.assertIn(f"unchanged {self.codex / 'AGENTS.md'}", out)

    def test_codex_is_skipped_when_its_home_is_absent(self):
        self.codex.rmdir()
        out = self.install().stdout
        self.assertIn(f"no {self.codex}: Codex is not installed here", out)
        self.assertFalse(self.codex.exists())
        self.assertTrue((self.claude / "skills" / SKILL / "SKILL.md").is_file())

    def test_python_3_9_is_refused_because_the_floor_is_3_10(self):
        stub = self.home / "stub-bin"
        self.write(stub / "python3", '#!/bin/sh\ncase "$2" in *"print("*) echo 3.9; exit 0;; esac\nexit 1\n')
        (stub / "python3").chmod(0o755)
        self.env["PATH"] = f"{stub}{os.pathsep}{self.env['PATH']}"
        r = self.install(ok=False)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("python3 3.9 found; 3.10 or newer is required", r.stderr)
        self.assertFalse(self.claude.exists(), "a refused install wrote files")

    def test_dry_run_writes_nothing_and_a_second_install_changes_nothing(self):
        self.write(self.claude / "CLAUDE.md", "mine\n")
        before = snapshot(self.home)
        out = self.install("--dry-run").stdout
        self.assertEqual(snapshot(self.home), before)
        self.assertIn(f"would: copy {SKILLS / SKILL} (without tests/) to {self.claude / 'skills' / SKILL}", out)
        self.assertNotIn("registered", out)
        self.install()
        first = snapshot(self.home)
        second = self.install().stdout
        self.assertEqual(snapshot(self.home), first)
        self.assertNotIn("would", second)
        self.assertEqual(second.count("unchanged "), 4, second)

    def test_existing_settings_and_hook_files_are_left_byte_for_byte(self):
        self.write(self.claude / "settings.json", json.dumps(
            {"theme": "dark — mine", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}],
                                               "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}))
        self.write(self.codex / "hooks.json", json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "user-stop"}]}]}}))
        before = {f: f.read_bytes() for f in (self.claude / "settings.json", self.codex / "hooks.json")}
        self.install()
        self.assertEqual({f: f.read_bytes() for f in before}, before)
        self.assertFalse(list(self.claude.glob("settings.json.bak-*")) + list(self.codex.glob("hooks.json.bak-*")))

    def test_malformed_or_misshapen_hook_files_are_refused_and_left_alone(self):
        for text, why in (("{not json", "is not valid JSON"), (json.dumps({"hooks": {"Stop": {"a": 1}}}), "hooks shape")):
            bad = self.write(self.claude / "settings.json", text)
            r = self.install(ok=False)
            self.assertEqual(r.returncode, 1)
            self.assertIn(why, r.stdout + r.stderr)
            self.assertIn("stop hook:", r.stderr)
            self.assertNotIn("Traceback", r.stdout + r.stderr)
            self.assertEqual(bad.read_text(), text)


class UninstallTest(InstallCase):
    def test_uninstall_removes_what_install_added_and_restores_the_backup(self):
        self.write(self.claude / "CLAUDE.md", "my own rules\n")
        self.write(self.claude / "settings.json", json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}))
        self.install()
        self.assertTrue(list(self.claude.glob("CLAUDE.md.bak-*")))

        before = snapshot(self.home)
        dry = self.install("--uninstall", "--dry-run").stdout
        self.assertEqual(snapshot(self.home), before)
        self.assertIn(f"would: rm -rf {self.claude / 'skills' / SKILL}", dry)

        out = self.install("--uninstall").stdout
        self.assertEqual((self.claude / "CLAUDE.md").read_text(), "my own rules\n")
        self.assertFalse(list(self.claude.glob("CLAUDE.md.bak-*")), "the restored backup is consumed")
        self.assertFalse((self.codex / "AGENTS.md").exists())
        for root in (self.claude, self.codex):
            self.assertFalse((root / "skills" / SKILL).exists(), root)
        self.assertEqual(commands(self.claude / "settings.json"), ["mine"])
        self.assertFalse((self.codex / "hooks.json").exists(), "a hook file holding only our entry was ours")
        self.assertIn(f"restored {self.claude / 'CLAUDE.md'}", out)

        after = snapshot(self.home)
        again = self.install("--uninstall").stdout
        self.assertEqual(snapshot(self.home), after, again)
        self.assertIn(f"left in place (differs from global.md): {self.claude / 'CLAUDE.md'}", again)

    def test_install_and_uninstall_drop_an_earlier_global_stop_entry(self):
        v6 = f'[ -n "${{GOAL_HARNESS:-}}" ] || python3 ~/.claude/{GOAL_STOP}'
        self.write(self.claude / "settings.json", json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": v6}]}],
                       "SessionStart": [{"hooks": [{"type": "command", "command": "keep-me"}]}]}}))
        self.install()  # the v6 (and T7-era) global Stop registration goes; run.sh owns the hook now
        hooks = json.loads((self.claude / "settings.json").read_text())["hooks"]
        self.assertEqual(hooks, {"SessionStart": [{"hooks": [{"type": "command", "command": "keep-me"}]}]})
        self.install("--uninstall")
        hooks = json.loads((self.claude / "settings.json").read_text())["hooks"]
        self.assertEqual(hooks, {"SessionStart": [{"hooks": [{"type": "command", "command": "keep-me"}]}]})


class RetireTest(InstallCase):
    def plant(self) -> tuple[dict[str, Path], set[Path]]:
        """A machine as v5.1 and v6 left it, plus things this installer does not know.
        Returns (everything planted, the paths --retire-v5 must delete)."""
        r, planted, expected = retire_list(), {}, set()
        render = f"---\n{r['GENERATED_MARK']} — edit the persona, not this.\n"
        for root, ext in ((self.claude, "md"), (self.codex, "toml")):
            for s in r["RETIRED_SKILLS"]:
                planted[f"{root}/skill/{s}"] = self.write(root / "skills" / s / "SKILL.md", "old\n")
                expected.add(root / "skills" / s)
            for p in r["RETIRED_PERSONAS"]:
                planted[f"{root}/agent/{p}"] = self.write(root / "agents" / f"{p}.{ext}", render + f"name: {p}\n")
                expected.add(root / "agents" / f"{p}.{ext}")
            for h in r["RETIRED_HOOKS"]:
                planted[f"{root}/hook/{h}"] = self.write(root / "hooks" / h, "old\n")
                expected.add(root / "hooks" / h)
            for rel in r["RETIRED_FILES"]:
                leaf = root / "skills" / SKILL / rel
                planted[f"{root}/file/{rel}"] = self.write(leaf / "test_old.py" if rel.endswith("/") else leaf, "old\n")
                if rel.endswith("/"):
                    self.write(leaf / "fixtures" / "deep.py", "old\n")
                expected.add(leaf)
        planted["unknown-in-skill"] = self.write(self.claude / "skills" / SKILL / "scripts" / "my_local_tool.py", "mine\n")
        planted["unknown-skill"] = self.write(self.claude / "skills" / "someone-elses" / "SKILL.md", "x\n")
        planted["unknown-hook"] = self.write(self.claude / "hooks" / "my-hook.sh", "x\n")
        planted["unknown-agent"] = self.write(self.codex / "agents" / "my-own-worker.toml", render)
        planted["bundle"] = self.write(self.codex / "approved-runtimes" / "proj" / "recovery.json", "{}\n")
        self.write(self.claude / "settings.json", json.dumps({"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": f"bash ~/.claude/hooks/{r['RETIRED_HOOKS'][2]} || true"}]},
            {"hooks": [{"type": "command", "command": "mine"}]}]}}))
        self.write(self.codex / "hooks.json", json.dumps({"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": f"bash {self.codex}/hooks/{r['RETIRED_HOOKS'][0]}"}]}]}}))
        return planted, expected

    def test_a_plain_install_removes_nothing(self):
        planted, _ = self.plant()
        contents = {k: p.read_bytes() for k, p in planted.items()}
        out = self.install().stdout
        for key, path in planted.items():
            self.assertEqual(path.read_bytes(), contents[key], key)
        self.assertIn(f"kept {self.claude / 'skills' / SKILL / 'scripts' / 'my_local_tool.py'} (not in this package)", out)
        self.assertEqual((self.claude / "skills" / SKILL / "SKILL.md").read_bytes(), (SKILLS / SKILL / "SKILL.md").read_bytes())

    def test_retire_v5_deletes_exactly_the_named_set_and_reports_the_rest(self):
        planted, expected = self.plant()
        hand = self.write(self.claude / "agents" / f"{retire_list()['RETIRED_PERSONAS'][0]}.md", "---\nname: hand\n---\n")
        expected.discard(hand)

        dry = self.install("--retire-v5", "--dry-run").stdout
        self.assertEqual({Path(l.split("would delete ", 1)[1]) for l in dry.splitlines() if "would delete " in l}, expected)
        self.assertTrue(all(p.exists() for p in planted.values()))

        out = self.install("--retire-v5").stdout
        self.assertEqual({Path(l.split("deleted ", 1)[1]) for l in out.splitlines() if l.strip().startswith("deleted ")},
                         expected)
        for path in expected:
            self.assertFalse(path.exists(), path)
        for key in ("unknown-in-skill", "unknown-skill", "unknown-hook", "unknown-agent", "bundle"):
            self.assertTrue(planted[key].exists(), key)
            self.assertIn("left in place (not in the retire list): ", out)
        self.assertIn(f"left in place (not in the retire list): {planted['unknown-in-skill']}", out)
        self.assertIn(f"left in place (not in the retire list): {planted['unknown-skill'].parent}", out)
        self.assertIn(f"left in place (not in the retire list): {planted['unknown-agent']}", out)
        self.assertIn(f"left in place (not in the retire list): {self.codex / 'approved-runtimes'}", out)
        self.assertTrue(hand.exists())
        self.assertIn(f"kept {hand}", out)
        # The retired hooks' registrations go; the founder's stay, and no Stop hook is added.
        self.assertEqual(commands(self.claude / "settings.json", "SessionStart"), ["mine"])
        self.assertEqual(self.stop_registrations(self.claude / "settings.json"), [])
        # The planted Codex file held only retired entries, so with no Stop hook added it goes whole.
        self.assertFalse((self.codex / "hooks.json").exists())
        for root in (self.claude, self.codex):
            self.assertTrue((root / "skills" / SKILL / "SKILL.md").is_file())

    def test_retire_is_skipped_when_an_install_step_failed(self):
        planted, _ = self.plant()
        self.write(self.claude / "settings.json", "{not json")
        r = self.install("--retire-v5", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("SKIPPED: an install step above failed", r.stdout)
        self.assertTrue(all(p.exists() for p in planted.values()))


class GuardTest(InstallCase):
    def git(self, repo, *args, ok=True):
        r = subprocess.run(["git", *args], cwd=repo, env=self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_installed_pre_push_hook_blocks_a_planted_secret(self):
        self.install()
        repo, remote = self.home / "work", self.home / "remote.git"
        repo.mkdir()
        self.git(self.home, "init", "-q", "--bare", str(remote))
        self.git(repo, "init", "-q", "-b", "main")
        self.write(repo / "README.md", "fixture\n")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "init")
        self.git(repo, "remote", "add", "origin", str(remote))
        scripts = self.claude / "skills" / SKILL / "scripts"
        r = subprocess.run(["bash", str(scripts / "git-hooks.sh"), str(repo)], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(str(scripts / "guard.py"), (repo / ".git" / "hooks" / "pre-push").read_text())
        # The installed pre-commit hook needs a private-name list; a synthetic one, never the real.
        names = self.write(self.home / "names.txt", "zarquon-widget\n")
        self.env["PD_PRIVATE_IDENTIFIERS"] = str(names)

        self.git(repo, "checkout", "-q", "-b", "clean")
        self.write(repo / "notes.txt", "nothing secret\n")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "clean")
        self.git(repo, "push", "-q", "origin", "clean")  # the control: the hook lets this through

        self.git(repo, "checkout", "-q", "-b", "leak")
        key = "AKIA" + "Q7RZM2XK4PLD9WTE"
        self.write(repo / "config.py", f'AWS_KEY = "{key}"\n')
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", "leak", "--no-verify")  # reach pre-push past pre-commit
        r = self.git(repo, "push", "origin", "leak", ok=False)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("guard BLOCKED", r.stdout + r.stderr)
        self.assertIn("AWS access key id", r.stdout + r.stderr)
        self.assertNotIn("leak", self.git(remote, "branch").stdout)

    def tree_scan_guard(self, files: dict[str, str], links: dict[str, str]):
        """Build a fixture repo (files committed with -f, then symlinks added), stage it the way
        verify.sh does, and return the guard's result over the scratch tree."""
        repo = self.home / f"fixture{len(list(self.home.glob('fixture*')))}"
        repo.mkdir()
        self.git(repo, "init", "-q", "-b", "main")
        self.write(repo / ".gitignore", "*.log\n")
        for rel, text in files.items():
            self.write(repo / rel, text)
        for rel, target in links.items():
            os.symlink(target, repo / rel)
        self.git(repo, "add", "-A", "-f")
        self.git(repo, "commit", "-q", "-m", "init")
        names = self.write(self.home / "names.txt", "zarquon-widget\n")
        env = {**self.env, "PD_PRIVATE_IDENTIFIERS": str(names)}
        scan = self.home / (repo.name + "-scan")
        r = subprocess.run(["python3", str(INSTALL / "tests" / "tree_scan.py"), str(repo), str(scan)],
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        guard = SKILLS / SKILL / "scripts" / "guard.py"
        return subprocess.run(["python3", str(guard), "--staged"], cwd=scan, env=env,
                              capture_output=True, text=True)

    def test_tree_guard_scans_ignored_tracked_files_and_symlinks(self):
        control = self.tree_scan_guard({"notes.txt": "nothing secret\n"}, {})
        self.assertEqual(control.returncode, 0, control.stdout + control.stderr)
        ignored = self.tree_scan_guard({"build.log": "see zarquon-widget\n"}, {})
        self.assertNotEqual(ignored.returncode, 0, "a tracked file an ignore rule matches went unscanned")
        link = self.tree_scan_guard({"notes.txt": "nothing secret\n"}, {"pointer": "/srv/zarquon-widget/data"})
        self.assertNotEqual(link.returncode, 0, "a symlink's link text went unscanned")


class LinkCheckTest(InstallCase):
    def links(self, *anchors: str) -> list[str]:
        sys.path.insert(0, str(INSTALL / "tests"))
        from link_check import check_links
        repo = self.home / "docsrepo"
        self.write(repo / "docs" / "decisions" / "decisions.md",
                   "# Decisions\n\n## D17 — Zeta rule\n\n## D18: Other (thing)\n")
        self.write(repo / "AGENTS.md", "root\n")
        self.write(repo / "README.md", "".join(f"[x](docs/decisions/decisions.md#{a})\n" for a in anchors))
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        return check_links(str(repo))

    def test_link_check_rejects_missing_decision_slug(self):
        self.assertEqual(self.links("d17", "d17--zeta-rule", "d18-other-thing"), [])
        bad = self.links("d17--nonexistent", "d99")
        self.assertEqual(len(bad), 2, bad)


class GoalStopHookTest(InstallCase):
    """Nothing registers a Stop hook globally; the installed goal.py, run as run.sh registers it per
    session, blocks a stop while a goal is not done in each harness home."""

    def test_each_harness_blocks_an_unfinished_goal(self):
        sys.path.insert(0, str(SKILLS / SKILL / "tests"))
        from fixtures.goal_fixture import Repo  # noqa: E402
        self.install()
        repo = Repo()
        self.addCleanup(repo.cleanup)
        for harness, root, file in (("claude", self.claude, self.claude / "settings.json"),
                                    ("codex", self.codex, self.codex / "hooks.json")):
            self.assertEqual(self.stop_registrations(file), [], file)
            hook = ["python3", str(root / "skills" / SKILL / "scripts" / "goal.py"), "--goal", "F-9", "stop-hook"]
            r = subprocess.run(hook, cwd=repo.dir, env=self.env, capture_output=True,
                               text=True, input=json.dumps({"session_id": harness}))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["decision"], "block", harness)


class M2InstallFixes(InstallCase):
    """The M2 diff review's installer findings, one closing test each."""

    def test_install_and_parity_support_spaces_in_harness_homes(self):
        self.codex.rmdir()  # the fixture's own Codex home; this test uses the spaced one only
        spaced = self.home / "my home"
        claude, codex = spaced / ".claude", spaced / ".codex"
        codex.mkdir(parents=True)
        self.env.update(HOME=str(spaced), CODEX_HOME=str(codex))
        self.install()
        # A split path would land beside "my home" (an absolute "<home>/my") or under the cwd ("home/...").
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["my home"])
        for root, name in ((claude, "CLAUDE.md"), (codex, "AGENTS.md")):
            self.assertEqual((root / name).read_text(encoding="utf-8"), GLOBAL)
            self.assertTrue((root / "skills" / SKILL / "SKILL.md").is_file(), root)
        r = subprocess.run(["bash", str(INSTALL / "verify.sh"), "--installed-only"], env=self.env,
                           capture_output=True, text=True, cwd=self.home)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("verify: installed_parity ok", r.stdout)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "verify: PASS")
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ["my home"])

    def test_uninstall_preserves_preexisting_unknown_skill_files(self):
        skill = self.claude / "skills" / SKILL
        mine = self.write(skill / "scripts" / "my_local_tool.py", "mine\n")
        notes = self.write(skill / "notes" / "todo.md", "mine too\n")
        self.install()
        dry = self.install("--uninstall", "--dry-run").stdout
        self.assertIn(f"left in place (not in this package): {mine}", dry)
        out = self.install("--uninstall").stdout
        self.assertEqual(mine.read_text(), "mine\n")
        self.assertEqual(notes.read_text(), "mine too\n")
        self.assertIn(f"left in place (not in this package): {mine}", out)
        self.assertIn(f"left in place (not in this package): {notes}", out)
        # Only the foreign files and the directories holding them remain; every shipped file is gone.
        left = sorted(str(p.relative_to(skill)) for p in skill.rglob("*"))
        self.assertEqual(left, ["notes", "notes/todo.md", "scripts", "scripts/my_local_tool.py"])
        self.assertFalse((self.codex / "skills").exists(), "a skill holding only shipped files goes whole")

    def test_global_instruction_symlink_target_survives_install_and_uninstall(self):
        target = self.write(self.home / "dotfiles" / "CLAUDE.md", "my own rules\n")
        same = self.write(self.home / "dotfiles" / "AGENTS.md", GLOBAL)
        self.claude.mkdir()
        link, same_link = self.claude / "CLAUDE.md", self.codex / "AGENTS.md"
        link.symlink_to(target)
        same_link.symlink_to(same)

        self.install()
        self.assertEqual(target.read_text(), "my own rules\n", "install wrote through the symlink")
        self.assertFalse(link.is_symlink())
        self.assertEqual(link.read_text(encoding="utf-8"), GLOBAL)
        backups = list(self.claude.glob("CLAUDE.md.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].is_symlink(), "the link itself is the backup")
        self.assertEqual(os.readlink(backups[0]), str(target))
        # Equal content behind a symlink: no write, no backup.
        self.assertTrue(same_link.is_symlink())
        self.assertFalse(list(self.codex.glob("AGENTS.md.bak-*")))

        self.install("--uninstall")
        self.assertTrue(link.is_symlink(), "uninstall restores the link")
        self.assertEqual(os.readlink(link), str(target))
        self.assertEqual(target.read_text(), "my own rules\n")
        self.assertFalse(list(self.claude.glob("CLAUDE.md.bak-*")))
        self.assertTrue(same_link.is_symlink(), "a symlink the installer did not write stays")
        self.assertEqual(same.read_text(encoding="utf-8"), GLOBAL)


if __name__ == "__main__":
    unittest.main()
