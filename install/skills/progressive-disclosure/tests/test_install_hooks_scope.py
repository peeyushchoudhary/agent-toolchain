from __future__ import annotations

import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


SOURCE_SKILLS = Path(__file__).resolve().parents[2]


class ScopedHooksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hooks-scope-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.codex_home = self.tmp / "codex-home"
        self.bundle = self.tmp / "bundle" / "skills"
        self.repo = self.tmp / "repo"
        shutil.copytree(SOURCE_SKILLS / "progressive-disclosure",
                        self.bundle / "progressive-disclosure")
        scripts = self.home / ".claude" / "skills" / "progressive-disclosure" / "scripts"
        scripts.parent.mkdir(parents=True)
        shutil.copytree(SOURCE_SKILLS / "progressive-disclosure" / "scripts", scripts)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "docs" / "agents").mkdir(parents=True)
        (self.repo / "docs" / "agents" / "README.md").write_text(
            '# Agents\n\n<!-- agent-personas: {"mode":"base-only","reason":"fixture"} -->\n',
            encoding="utf-8")
        (self.repo / "AGENTS.md").write_text("# Fixture\n", encoding="utf-8")
        self.session = self.home / ".claude" / "hooks" / "disclosure-check.sh"
        self.session.parent.mkdir(parents=True)
        self.session.write_text('#!/bin/sh\nnotes=""\n[ -n "$notes" ] || exit 0\n', encoding="utf-8")

    @property
    def installer(self) -> Path:
        return self.bundle / "progressive-disclosure" / "scripts" / "install_hooks.py"

    def invoke(self, *flags: str, **extra_env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.installer), str(self.repo), *flags],
            capture_output=True, text=True, timeout=60,
            env={**{k: v for k, v in os.environ.items() if not k.startswith("GRAPHIFY_")},
                 "HOME": str(self.home), "CODEX_HOME": str(self.codex_home),
                 "PYTHONDONTWRITEBYTECODE": "1", **extra_env})

    def snapshot(self) -> dict[str, bytes]:
        out = {}
        for base in (self.home, self.codex_home, self.repo):
            for path in sorted(base.rglob("*")):
                if path.is_file() and "/.git/" not in str(path):
                    out[str(path)] = path.read_bytes()
        return out

    def load_installer_module(self):
        spec = importlib.util.spec_from_file_location("install_hooks_under_test", self.installer)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        return module

    def test_project_preview_is_json_and_writes_nothing(self) -> None:
        before = self.snapshot()
        proc = self.invoke("--scope", "project", "--preview", "--json", "--no-graph")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = json.loads(proc.stdout)
        self.assertEqual(plan["schema_version"], 1)
        self.assertEqual(plan["scope"], "project")
        self.assertEqual(plan["findings"], [])
        self.assertTrue(plan["operations"])
        self.assertTrue(all(Path(op["path"]).is_absolute() for op in plan["operations"]))
        allowed = (self.repo.resolve() / ".git" / "hooks",)
        self.assertTrue(all(any(Path(op["path"]).is_relative_to(root) for root in allowed)
                            for op in plan["operations"]), plan)
        self.assertEqual(self.snapshot(), before)

    def test_project_apply_matches_preview_and_repeats_as_noop(self) -> None:
        preview = json.loads(self.invoke("--scope", "project", "--preview", "--json",
                                      "--no-graph").stdout)
        proc = self.invoke("--scope", "project", "--no-graph")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for op in preview["operations"]:
            self.assertTrue(Path(op["path"]).exists(), op)
        second = self.invoke("--scope", "project", "--preview", "--json", "--no-graph")
        self.assertEqual(json.loads(second.stdout)["operations"], [])

    def test_project_scope_never_touches_global_state(self) -> None:
        before_session = self.session.read_bytes()
        proc = self.invoke("--scope", "project", "--no-graph")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.session.read_bytes(), before_session)
        self.assertFalse((self.home / ".claude" / "agents").exists())
        self.assertFalse((self.codex_home / "skills").exists())

    def test_project_scope_rejects_symlinked_hooks_directory(self) -> None:
        external = self.tmp / "external-hooks"
        external.mkdir()
        sentinel = external / "pre-commit"
        sentinel.write_text("outside\n", encoding="utf-8")
        hooks = self.repo / ".git" / "hooks"
        shutil.rmtree(hooks)
        hooks.symlink_to(external, target_is_directory=True)

        preview = self.invoke("--scope", "project", "--preview", "--json", "--no-graph")
        self.assertEqual(preview.returncode, 2, preview.stdout + preview.stderr)
        findings = json.loads(preview.stdout)["findings"]
        self.assertTrue(any(item["code"] == "unsafe-file-destination" for item in findings), findings)
        applied = self.invoke("--scope", "project", "--no-graph")
        self.assertEqual(applied.returncode, 2, applied.stdout + applied.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")

    def test_project_scope_rejects_symlinked_hook_leaf(self) -> None:
        external = self.tmp / "external-pre-commit"
        external.write_text("outside\n", encoding="utf-8")
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.symlink_to(external)

        preview = self.invoke("--scope", "project", "--preview", "--json", "--no-graph")
        self.assertEqual(preview.returncode, 2, preview.stdout + preview.stderr)
        findings = json.loads(preview.stdout)["findings"]
        self.assertTrue(any(item["code"] == "unsafe-file-destination" for item in findings), findings)
        self.assertEqual(external.read_text(encoding="utf-8"), "outside\n")

    def test_plain_install_and_uninstall_refuse_symlinked_hooks_directory(self) -> None:
        """The unscoped path is what agents are told to run; it gets the same destination rule."""
        external = self.tmp / "plain-external-hooks"
        external.mkdir()
        hooks = self.repo / ".git" / "hooks"
        shutil.rmtree(hooks)
        hooks.symlink_to(external, target_is_directory=True)
        for flags in ((), ("--uninstall",)):
            proc = self.invoke("--no-graph", *flags)
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(list(external.iterdir()), [], flags)

    def test_plain_install_and_uninstall_refuse_symlinked_hook_leaf(self) -> None:
        external = self.tmp / "plain-external-pre-commit"
        original = "#!/bin/sh\necho mine\n\n# >>> progressive-disclosure >>>\n# <<< progressive-disclosure <<<\n"
        external.write_text(original, encoding="utf-8")
        (self.repo / ".git" / "hooks" / "pre-commit").symlink_to(external)
        for flags in ((), ("--uninstall",)):
            proc = self.invoke("--no-graph", *flags)
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(external.read_text(encoding="utf-8"), original, flags)

    # What the stub renders: the real installer's markers around a fixed body.
    STUB_BLOCKS = {
        "post-commit": "# graphify-hook-start\necho stub post-commit refresh\n# graphify-hook-end",
        "post-checkout": ("# graphify-checkout-hook-start\necho stub post-checkout refresh\n"
                          "# graphify-checkout-hook-end"),
    }

    def stub_graphify(self) -> Path:
        """A graphify stand-in that behaves like the real installer: it resolves the hooks directory
        from its cwd's repository through git, so it honours GIT_DIR and core.hooksPath, appends or
        strips the marked blocks, and logs its cwd and the git environment it was given."""
        fake_bin = self.tmp / "bin"; fake_bin.mkdir()
        log = self.tmp / "graphify.log"
        stub = fake_bin / "graphify"
        lines = ["#!/bin/sh",
                 f"printf '%s\\t%s\\t%s\\t%s\\n' \"$(pwd -P)\" \"${{GIT_DIR-unset}}\" "
                 f"\"${{GIT_CONFIG_GLOBAL-unset}}\" \"$*\" >> '{log}'",
                 "[ \"$1\" = hook ] || exit 0",
                 "hooks=$(git rev-parse --git-path hooks) || exit 1",
                 "case \"$hooks\" in /*) ;; *) hooks=\"$(pwd -P)/$hooks\";; esac",
                 "mkdir -p \"$hooks\""]
        for name, block in self.STUB_BLOCKS.items():
            start, end = block.splitlines()[0], block.splitlines()[-1]
            lines += [f"f=\"$hooks/{name}\"",
                      "if [ \"$2\" = install ] && ! grep -qx '" + start + "' \"$f\" 2>/dev/null; then",
                      "  [ -f \"$f\" ] || printf '#!/bin/sh\\n' > \"$f\"",
                      "  printf '%s\\n' '" + block.replace("\n", "' '") + "' >> \"$f\"; chmod 755 \"$f\"",
                      "elif [ \"$2\" = uninstall ] && [ -f \"$f\" ]; then",
                      f"  awk '$0==\"{start}\"{{s=1}} !s{{print}} $0==\"{end}\"{{s=0}}' \"$f\" > \"$f.t\"",
                      "  mv \"$f.t\" \"$f\"",
                      "fi"]
        stub.write_text("\n".join(lines) + "\n", encoding="utf-8")
        stub.chmod(0o755)
        env_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{fake_bin}:{env_path}"
        self.addCleanup(os.environ.__setitem__, "PATH", env_path)
        return log

    def graphify_calls(self, log: Path) -> list[list[str]]:
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        return [line.split("\t") for line in text.splitlines()]

    def assert_never_ran_in_project(self, log: Path) -> None:
        for cwd, git_dir, config_global, _args in self.graphify_calls(log):
            self.assertFalse(Path(cwd).resolve() == self.repo.resolve()
                             or self.repo.resolve() in Path(cwd).resolve().parents, cwd)
            self.assertEqual(git_dir, "unset")
            self.assertNotEqual(config_global, "unset")

    def assert_graphify_blocks(self, present: bool) -> None:
        for name, block in self.STUB_BLOCKS.items():
            hook = self.repo / ".git" / "hooks" / name
            text = hook.read_text(encoding="utf-8") if hook.exists() else ""
            if present:
                self.assertEqual(text.count(block.splitlines()[0]), 1, text)
                self.assertIn(block + "\n", text)
                self.assertTrue(text.startswith("#!/bin/sh\n"), text)
                self.assertTrue(hook.stat().st_mode & 0o111)
            else:
                self.assertNotIn("graphify", text)

    def tree(self, base: Path) -> dict[str, bytes]:
        return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*"))
                if p.is_file()}

    def test_inherited_git_dir_cannot_redirect_graphify(self) -> None:
        """Round 3: a GIT_DIR inherited from the caller pointed delegated graphify at another
        repository's hooks. graphify now renders in a sandbox and we write the blocks."""
        log = self.stub_graphify()
        outside = self.tmp / "outside-git-dir"
        subprocess.run(["git", "init", "-q", str(outside)], check=True)
        before = self.tree(outside / ".git" / "hooks")
        graph = self.repo / "graphify-out" / "graph.json"
        graph.parent.mkdir(); graph.write_text("{}\n", encoding="utf-8")
        env = {"GIT_DIR": str(outside / ".git")}

        proc = self.invoke(**env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("post-commit graph refresh installed", proc.stdout)
        self.assertEqual(self.tree(outside / ".git" / "hooks"), before)
        self.assert_graphify_blocks(present=True)
        graph_hooks = [self.repo / ".git" / "hooks" / name for name in self.STUB_BLOCKS]
        hooks = [p.read_bytes() for p in graph_hooks]
        again = self.invoke(**env)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual([p.read_bytes() for p in graph_hooks], hooks)

        proc = self.invoke("--uninstall", **env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.tree(outside / ".git" / "hooks"), before)
        self.assert_graphify_blocks(present=False)
        self.assertFalse((self.repo / ".git" / "hooks" / "post-checkout").exists())
        self.assertTrue(self.graphify_calls(log))
        self.assert_never_ran_in_project(log)
        self.assertFalse(any("uninstall" in call[3] for call in self.graphify_calls(log)))

    def test_graphify_block_replaces_in_place_and_preserves_other_content(self) -> None:
        self.stub_graphify()
        graph = self.repo / "graphify-out" / "graph.json"
        graph.parent.mkdir(); graph.write_text("{}\n", encoding="utf-8")
        hook = self.repo / ".git" / "hooks" / "post-checkout"
        hook.write_text("#!/bin/sh\necho mine\n\n# graphify-checkout-hook-start\nold\n"
                        "# graphify-checkout-hook-end\necho after\n", encoding="utf-8")
        proc = self.invoke()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assert_graphify_blocks(present=True)
        text = hook.read_text(encoding="utf-8")
        self.assertNotIn("\nold\n", text)
        self.assertIn("echo mine", text); self.assertIn("echo after", text)
        self.assertEqual(self.invoke("--uninstall").returncode, 0)
        self.assertEqual(hook.read_text(encoding="utf-8"), "#!/bin/sh\necho mine\necho after\n")

    def test_graphify_failure_writes_nothing(self) -> None:
        fake_bin = self.tmp / "bin"; fake_bin.mkdir()
        (fake_bin / "graphify").write_text("#!/bin/sh\necho broken >&2\nexit 3\n", encoding="utf-8")
        (fake_bin / "graphify").chmod(0o755)
        env_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{fake_bin}:{env_path}"
        self.addCleanup(os.environ.__setitem__, "PATH", env_path)
        graph = self.repo / "graphify-out" / "graph.json"
        graph.parent.mkdir(); graph.write_text("{}\n", encoding="utf-8")
        proc = self.invoke()
        self.assertIn("post-commit graph refresh FAILED", proc.stdout)
        self.assertTrue((self.repo / ".git" / "hooks" / "pre-commit").is_file())
        for name in self.STUB_BLOCKS:
            self.assertFalse((self.repo / ".git" / "hooks" / name).exists(), name)

    def test_graphify_delegation_refuses_symlinked_post_checkout(self) -> None:
        log = self.stub_graphify()
        graph = self.repo / "graphify-out" / "graph.json"
        graph.parent.mkdir(); graph.write_text("{}\n", encoding="utf-8")
        external = self.tmp / "external-post-checkout"
        original = "#!/bin/sh\necho mine\n"
        external.write_text(original, encoding="utf-8")
        (self.repo / ".git" / "hooks" / "post-checkout").symlink_to(external)
        for flags in ((), ("--uninstall",)):
            proc = self.invoke(*flags)
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("post-checkout", proc.stdout)
            self.assertEqual(external.read_text(encoding="utf-8"), original, flags)
        scoped = self.invoke("--scope", "project", "--preview", "--json")
        self.assertEqual(scoped.returncode, 2, scoped.stdout + scoped.stderr)
        self.assertIn("unsafe-file-destination",
                      [f["code"] for f in json.loads(scoped.stdout)["findings"]])
        self.assertEqual(self.graphify_calls(log), [])
        self.assertEqual(external.read_text(encoding="utf-8"), original)

    def test_graph_discovery_ignores_symlinked_child_and_runs_at_root(self) -> None:
        log = self.stub_graphify()
        outside = self.tmp / "outside-repo"
        subprocess.run(["git", "init", "-q", str(outside)], check=True)
        (outside / "graphify-out").mkdir()
        (outside / "graphify-out" / "graph.json").write_text("{}\n", encoding="utf-8")
        outside_hooks = sorted(p.name for p in (outside / ".git" / "hooks").iterdir())
        (self.repo / "linked").symlink_to(outside, target_is_directory=True)
        proc = self.invoke()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # No graph of its own is no skip (F-5 AC-7): the guarded blocks go into the root's hooks.
        self.assertNotIn("the graph is under linked/", proc.stdout)
        self.assert_never_ran_in_project(log)
        self.assertEqual(sorted(p.name for p in (outside / ".git" / "hooks").iterdir()), outside_hooks)
        self.assert_graphify_blocks(present=True)
        for name in self.STUB_BLOCKS:
            (self.repo / ".git" / "hooks" / name).unlink()
        log.unlink()
        # A real child's graph is found but not claimed: the hook runs at the worktree root, so it
        # could never refresh it (M4 fix 5). The skip names it; nothing is written or run.
        (self.repo / "sub" / "graphify-out").mkdir(parents=True)
        (self.repo / "sub" / "graphify-out" / "graph.json").write_text("{}\n", encoding="utf-8")
        proc = self.invoke()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("the graph is under sub/", proc.stdout)
        self.assert_graphify_blocks(present=False)
        self.assertEqual(self.graphify_calls(log), [])
        self.assert_never_ran_in_project(log)
        self.assertEqual(sorted(p.name for p in (outside / ".git" / "hooks").iterdir()), outside_hooks)

    def test_core_hooks_path_skips_graph_hook_and_uninstall_still_strips(self) -> None:
        """git runs core.hooksPath, not .git/hooks, so blocks written to .git/hooks would never
        run. The plain install skips the graph hook without running graphify; --uninstall still
        strips our blocks from .git/hooks and never writes the configured directory."""
        log = self.stub_graphify()
        graph = self.repo / "graphify-out" / "graph.json"
        graph.parent.mkdir(); graph.write_text("{}\n", encoding="utf-8")
        (self.repo / ".hooks").mkdir()
        subprocess.run(["git", "-C", str(self.repo), "config", "core.hooksPath", ".hooks"],
                       check=True)
        proc = self.invoke()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("graph refresh skipped \u2014 core.hooksPath is configured", proc.stdout)
        self.assertNotIn("graph refresh installed", proc.stdout)
        self.assert_graphify_blocks(present=False)
        self.assertEqual(self.graphify_calls(log), [])
        for hook in (self.repo / ".hooks").iterdir():
            self.assertNotIn("graphify", hook.read_text(encoding="utf-8"))
        for name, block in self.STUB_BLOCKS.items():
            hook = self.repo / ".git" / "hooks" / name
            hook.write_text("#!/bin/sh\n" + block + "\n", encoding="utf-8")
        proc = self.invoke("--uninstall")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assert_graphify_blocks(present=False)
        self.assertEqual(list((self.repo / ".hooks").iterdir()), [])
        self.assertEqual(self.graphify_calls(log), [])

    def test_graph_hook_installs_only_when_hooks_path_is_unset_everywhere(self) -> None:
        """Any core.hooksPath, empty or spelled to look like .git/hooks, skips; no path
        comparison. An inherited GIT_DIR or a global-only value must not change the decision."""
        log = self.stub_graphify()
        graph = self.repo / "graphify-out" / "graph.json"
        graph.parent.mkdir(); graph.write_text("{}\n", encoding="utf-8")
        (self.repo / ".hooks").mkdir()
        other = self.tmp / "other"
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        subprocess.run(["git", "-C", str(other), "config", "core.hooksPath", "elsewhere"],
                       check=True)
        gcfg = self.tmp / "global.gitconfig"
        own = str(self.repo / ".git" / "hooks")
        # GIT_CONFIG changes what `git config` reads, not what a running git applies.
        empty_cfg, only_cfg = self.tmp / "empty.gitconfig", self.tmp / "only.gitconfig"
        empty_cfg.write_text("", encoding="utf-8")
        only_cfg.write_text("[core]\n\thooksPath = .hooks\n", encoding="utf-8")
        shadow = {"GIT_CONFIG": str(empty_cfg), "GIT_CONFIG_COUNT": "1",
                  "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": ".hooks"}
        cases = [("unset", None, {}, True),
                 ("inherited-git-dir", None, {"GIT_DIR": str(other / ".git")}, True),
                 ("empty", "", {}, False), ("relative", ".hooks", {}, False),
                 ("trailing-space", ".git/hooks ", {}, False),
                 ("missing-component", ".git/missing/../hooks", {}, False),
                 ("case-variant", ".git/HOOKS", {}, False),
                 ("own-absolute", own, {}, False),
                 ("global-only", None, {"GIT_CONFIG_GLOBAL": str(gcfg)}, False),
                 ("config-env", None, {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath",
                                       "GIT_CONFIG_VALUE_0": ".hooks"}, False),
                 ("inherited-git-dir-empty", "", {"GIT_DIR": str(other / ".git")}, False),
                 ("git-config-shadows-env", None, shadow, False),
                 ("git-config-file-only", None, {"GIT_CONFIG": str(only_cfg)}, True)]
        for label, value, extra, installed in cases:
            with self.subTest(label):
                cfg = ["git", "-C", str(self.repo), "config"]
                subprocess.run(cfg + ["--unset-all", "core.hooksPath"])
                if value is not None:
                    subprocess.run(cfg + ["core.hooksPath", value], check=True)
                if label == "global-only":
                    gcfg.write_text("[core]\n\thooksPath = /nonexistent-hooks\n", encoding="utf-8")
                else:
                    gcfg.write_text("", encoding="utf-8")
                log.unlink(missing_ok=True)
                if label.startswith("git-config-"):  # what a running git would use
                    hooks_dir = subprocess.run(
                        ["git", "rev-parse", "--git-path", "hooks"], cwd=self.repo, check=True,
                        capture_output=True, text=True,
                        env={**{k: v for k, v in os.environ.items()
                                if not k.startswith("GRAPHIFY_")}, **extra}).stdout.strip()
                    self.assertEqual(hooks_dir == ".git/hooks", installed, hooks_dir)
                proc = self.invoke(**extra)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                if installed:
                    self.assertIn("graph refresh installed", proc.stdout)
                    self.assert_graphify_blocks(present=True)
                    self.assert_never_ran_in_project(log)
                else:
                    self.assertIn("graph refresh skipped \u2014 core.hooksPath is configured",
                                  proc.stdout)
                    self.assertNotIn("graph refresh installed", proc.stdout)
                    self.assert_graphify_blocks(present=False)
                    self.assertEqual(self.graphify_calls(log), [])
                    for hook in (self.repo / ".hooks").iterdir():
                        self.assertNotIn("graphify", hook.read_text(encoding="utf-8"))
                for name in self.STUB_BLOCKS:  # reset for the next case
                    hook = self.repo / ".git" / "hooks" / name
                    if hook.exists():
                        hook.unlink()

    def test_commit_time_hooks_directory_swap_cannot_touch_external_target(self) -> None:
        module = self.load_installer_module()
        files, findings = module._scoped_plan(
            self.repo.resolve(), uninstall=False, standard=False,
            public_flag=False, no_graph=True)
        self.assertEqual(findings, [])
        external = self.tmp / "commit-swap-external"
        external.mkdir()
        sentinel = external / "pre-commit"
        sentinel.write_text("outside\n", encoding="utf-8")
        sentinel.chmod(0o600)
        hooks = self.repo / ".git" / "hooks"
        real_open = module.os.open
        swapped = False

        def swap_before_hooks_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "hooks" and kwargs.get("dir_fd") is not None and not swapped:
                swapped = True
                shutil.rmtree(hooks)
                hooks.symlink_to(external, target_is_directory=True)
            return real_open(path, flags, *args, **kwargs)

        with unittest.mock.patch.object(module.os, "open", side_effect=swap_before_hooks_open):
            with self.assertRaises(OSError):
                module._apply_files(files, module._scope_file_roots(self.repo.resolve(), "project"))
        self.assertTrue(swapped)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")
        self.assertEqual(sentinel.stat().st_mode & 0o777, 0o600)

    def test_commit_time_uninstall_swap_cannot_delete_external_target(self) -> None:
        self.assertEqual(self.invoke("--scope", "project", "--no-graph").returncode, 0)
        module = self.load_installer_module()
        files, findings = module._scoped_plan(
            self.repo.resolve(), uninstall=True, standard=False,
            public_flag=False, no_graph=True)
        self.assertEqual(findings, [])
        self.assertTrue(any(item.action == "delete" for item in files), files)
        external = self.tmp / "delete-swap-external"
        external.mkdir()
        sentinel = external / "pre-commit"
        sentinel.write_text("outside\n", encoding="utf-8")
        hooks = self.repo / ".git" / "hooks"
        real_open = module.os.open
        swapped = False

        def swap_before_hooks_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "hooks" and kwargs.get("dir_fd") is not None and not swapped:
                swapped = True
                shutil.rmtree(hooks)
                hooks.symlink_to(external, target_is_directory=True)
            return real_open(path, flags, *args, **kwargs)

        with unittest.mock.patch.object(module.os, "open", side_effect=swap_before_hooks_open):
            with self.assertRaises(OSError):
                module._apply_files(files, module._scope_file_roots(self.repo.resolve(), "project"))
        self.assertTrue(swapped)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")

    def test_authority_root_replacement_after_plan_cannot_redirect_commit(self) -> None:
        module = self.load_installer_module()
        authorities = module._scope_file_roots(self.repo.resolve(), "project")
        files, findings = module._scoped_plan(
            self.repo.resolve(), uninstall=False, standard=False,
            public_flag=False, no_graph=True, roots=authorities)
        self.assertEqual(findings, [])
        parked = self.tmp / "repo-parked"
        self.repo.rename(parked)
        external = self.tmp / "replacement-root"
        (external / ".git" / "hooks").mkdir(parents=True)
        sentinel = external / ".git" / "hooks" / "pre-commit"
        sentinel.write_text("outside\n", encoding="utf-8")
        self.repo.symlink_to(external, target_is_directory=True)

        with self.assertRaises(OSError):
            module._apply_files(files, authorities)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside\n")

    def test_plain_install_no_longer_touches_machine_global_state(self) -> None:
        """The plain path once mirrored skills into ~/.codex/skills and rendered global personas.
        install.sh owns the skill trees and sync_personas.py owns personas, so it writes neither."""
        session_before = self.session.read_bytes()
        (self.home / ".codex" / "skills").mkdir(parents=True)
        proc = self.invoke("--no-graph")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.session.read_bytes(), session_before)
        self.assertFalse((self.home / ".claude" / "agents").exists())
        self.assertEqual(list((self.home / ".codex" / "skills").iterdir()), [])
        self.assertTrue((self.repo / ".git" / "hooks" / "pre-commit").is_file())

    def test_only_the_project_scope_exists(self) -> None:
        for scope in ("global", "all"):
            proc = self.invoke("--scope", scope, "--preview", "--json", "--no-graph")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("invalid choice", proc.stderr)

    def test_explicit_check_uses_same_plan_without_writing(self) -> None:
        before = self.snapshot()
        stale = self.invoke("--scope", "project", "--check", "--no-graph")
        self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.invoke("--scope", "project", "--no-graph").returncode, 0)
        current = self.invoke("--scope", "project", "--check", "--no-graph")
        self.assertEqual(current.returncode, 0, current.stdout + current.stderr)

    def test_public_declaration_is_previewed_and_applied_with_its_guards(self) -> None:
        route = self.repo / "docs" / "agents" / "README.md"
        before = route.read_text(encoding="utf-8")
        preview = self.invoke("--scope", "project", "--public", "--preview", "--json",
                              "--no-graph")
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        plan = json.loads(preview.stdout)
        self.assertIn(str(route.resolve()), [op["path"] for op in plan["operations"]])
        self.assertEqual(route.read_text(encoding="utf-8"), before)
        applied = self.invoke("--scope", "project", "--public", "--no-graph")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        self.assertIn("public-exception", route.read_text(encoding="utf-8"))
        self.assertIn("identifier_guard.py", (self.repo / ".git" / "hooks" /
                                               "pre-commit").read_text(encoding="utf-8"))
        self.assertIn("identifier_guard.py", (self.repo / ".git" / "hooks" /
                                               "commit-msg").read_text(encoding="utf-8"))

    def test_uninstall_preview_and_apply_preserve_unmanaged_hook(self) -> None:
        self.assertEqual(self.invoke("--scope", "project", "--no-graph").returncode, 0)
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho mine\n\n" + hook.read_text().split("\n", 1)[1],
                        encoding="utf-8")
        preview = self.invoke("--scope", "project", "--uninstall", "--preview", "--json",
                           "--no-graph")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn(str(hook.resolve()), [op["path"] for op in json.loads(preview.stdout)["operations"]])
        self.assertEqual(self.invoke("--scope", "project", "--uninstall", "--no-graph").returncode, 0)
        self.assertEqual(hook.read_text(encoding="utf-8"), "#!/bin/sh\necho mine\n")

    def test_unpreviewable_graph_operation_is_rejected_before_writes(self) -> None:
        graph = self.repo / "graphify-out" / "graph.json"
        graph.parent.mkdir(); graph.write_text("{}\n", encoding="utf-8")
        fake_bin = self.tmp / "bin"; fake_bin.mkdir()
        graphify = fake_bin / "graphify"
        graphify.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8"); graphify.chmod(0o755)
        env_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{fake_bin}:{env_path}"
        self.addCleanup(os.environ.__setitem__, "PATH", env_path)
        proc = self.invoke("--scope", "project", "--preview", "--json")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        plan = json.loads(proc.stdout)
        self.assertEqual(plan["findings"][0]["code"], "graph-operation-unpreviewable")
        self.assertFalse((self.repo / ".git" / "hooks" / "pre-commit").exists())

if __name__ == "__main__":
    unittest.main(verbosity=2)
