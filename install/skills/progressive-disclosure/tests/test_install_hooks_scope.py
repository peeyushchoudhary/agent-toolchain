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


def _is_under(path: Path, root: Path) -> bool:
    path = path.resolve(); root = root.resolve()
    return path == root or root in path.parents


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
        self.install_persona_stub()

    @property
    def installer(self) -> Path:
        return self.bundle / "progressive-disclosure" / "scripts" / "install_hooks.py"

    def install_persona_stub(self, malformed: bool = False) -> None:
        path = self.bundle / "agent-personas" / "scripts" / "sync_personas.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        if malformed:
            path.write_text("import sys\nprint('not-json')\nsys.exit(0)\n", encoding="utf-8")
            return
        path.write_text(
            """import argparse, json
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--scope', required=True); p.add_argument('--repo')
p.add_argument('--preview', action='store_true'); p.add_argument('--json', action='store_true')
p.add_argument('--check', action='store_true'); a=p.parse_args()
repo=Path(a.repo).resolve() if a.repo else None
target=(repo/'.claude/agents/demo.md') if repo else (Path.home()/'.claude/agents/demo.md')
action='update' if target.exists() and target.read_text()!='demo\\n' else ('create' if not target.exists() else None)
ops=[] if action is None else [{'action':action,'path':str(target)}]
if a.preview:
 print(json.dumps({'schema_version':1,'scope':a.scope,'operations':ops,'findings':[]})); raise SystemExit(0)
if a.check: raise SystemExit(1 if ops else 0)
if action:
 target.parent.mkdir(parents=True, exist_ok=True); target.write_text('demo\\n')
print('personas synchronized')
""", encoding="utf-8")

    def install_real_persona_owner(self) -> None:
        target = self.bundle / "agent-personas"
        shutil.rmtree(target)
        shutil.copytree(SOURCE_SKILLS / "agent-personas", target,
                        ignore=shutil.ignore_patterns("__pycache__"))
        sources = self.repo / "docs" / "agents" / "personas"
        sources.mkdir(parents=True)
        (sources / "domain-validator.md").write_text(
            """---
name: domain-validator
description: Use for domain validation.
writes: no
claude.model: opus
claude.effort: high
claude.disallowedTools: Write, Edit, NotebookEdit, Bash
codex.model: gpt-5.6-sol
codex.effort: high
codex.sandbox: read-only
---
Validate the domain.
""", encoding="utf-8")

    def invoke(self, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.installer), str(self.repo), *flags],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.codex_home),
                 "PYTHONDONTWRITEBYTECODE": "1"})

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
        allowed = tuple(path.resolve() for path in (
            self.repo / ".git" / "hooks", self.repo / ".claude" / "agents",
            self.repo / ".codex" / "agents"))
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

    def test_commit_time_hooks_directory_swap_cannot_touch_external_target(self) -> None:
        module = self.load_installer_module()
        files, _, findings = module._scoped_plan(
            self.repo.resolve(), scope="project", uninstall=False, standard=False,
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
        files, _, findings = module._scoped_plan(
            self.repo.resolve(), scope="project", uninstall=True, standard=False,
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
        files, _, findings = module._scoped_plan(
            self.repo.resolve(), scope="project", uninstall=False, standard=False,
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

    def test_historical_default_still_demonstrates_the_global_side_effect(self) -> None:
        """The red observation: a project install also entered three machine-global paths."""
        legacy = self.home / ".claude" / "skills" / "agent-personas" / "scripts" / "sync_personas.py"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(
            "import argparse\nfrom pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--repo'); a=p.parse_args()\n"
            "target=Path.home()/'.claude/agents/legacy.md'; target.parent.mkdir(parents=True)\n"
            "target.write_text('legacy\\n'); print('legacy personas')\n", encoding="utf-8")
        legacy_codex = self.home / ".codex" / "skills"
        legacy_codex.mkdir(parents=True)
        proc = self.invoke("--no-graph")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("execution-methodology adoption", self.session.read_text(encoding="utf-8"))
        self.assertTrue((self.home / ".claude" / "agents" / "legacy.md").is_file())
        self.assertTrue((legacy_codex / "progressive-disclosure" / "scripts" /
                         "install_hooks.py").is_file())

    def test_global_preview_and_apply_never_visit_project(self) -> None:
        before_repo = self.snapshot()
        preview = self.invoke("--scope", "global", "--preview", "--json", "--no-graph")
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        plan = json.loads(preview.stdout)
        self.assertTrue(plan["operations"])
        self.assertTrue(all(not _is_under(Path(op["path"]), self.repo)
                            for op in plan["operations"]), plan)
        self.assertEqual(self.snapshot(), before_repo)
        applied = self.invoke("--scope", "global", "--no-graph")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        self.assertFalse((self.repo / ".git" / "hooks" / "pre-commit").exists())
        self.assertIn("execution-methodology adoption", self.session.read_text(encoding="utf-8"))
        self.assertTrue((self.codex_home / "skills" / "progressive-disclosure" /
                         "scripts" / "install_hooks.py").is_file())
        second = self.invoke("--scope", "global", "--preview", "--json", "--no-graph")
        self.assertEqual(json.loads(second.stdout)["operations"], [])

    def test_global_mirror_preserves_unmanaged_content(self) -> None:
        unmanaged = self.codex_home / "skills" / "progressive-disclosure" / "mine.txt"
        unmanaged.parent.mkdir(parents=True)
        unmanaged.write_text("keep\n", encoding="utf-8")
        proc = self.invoke("--scope", "global", "--no-graph")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(unmanaged.read_text(encoding="utf-8"), "keep\n")

    def test_all_preview_enumerates_project_and_global_operations(self) -> None:
        proc = self.invoke("--scope", "all", "--preview", "--json", "--no-graph")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        paths = [Path(op["path"]) for op in json.loads(proc.stdout)["operations"]]
        self.assertTrue(any(_is_under(path, self.repo) for path in paths), paths)
        self.assertTrue(any(_is_under(path, self.home) or _is_under(path, self.codex_home)
                            for path in paths), paths)

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

    def test_malformed_persona_preview_blocks_before_hook_writes(self) -> None:
        self.install_persona_stub(malformed=True)
        proc = self.invoke("--scope", "project", "--no-graph")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertFalse((self.repo / ".git" / "hooks" / "pre-commit").exists())

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

    def test_real_sibling_persona_owner_project_integration(self) -> None:
        self.install_real_persona_owner()
        session_before = self.session.read_bytes()
        preview = self.invoke("--scope", "project", "--preview", "--json", "--no-graph")
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        plan = json.loads(preview.stdout)
        self.assertEqual(plan["findings"], [])
        planned = {(op["action"], Path(op["path"])) for op in plan["operations"]}
        claude_agent = (self.repo / ".claude" / "agents" / "domain-validator.md").resolve()
        codex_agent = (self.repo / ".codex" / "agents" / "domain-validator.toml").resolve()
        self.assertIn(("create", claude_agent), planned)
        self.assertIn(("create", codex_agent), planned)
        self.assertEqual(self.session.read_bytes(), session_before)
        self.assertFalse((self.home / ".claude" / "agents").exists())
        self.assertFalse((self.codex_home / "agents").exists())

        applied = self.invoke("--scope", "project", "--no-graph")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        self.assertTrue(claude_agent.is_file())
        self.assertTrue(codex_agent.is_file())
        checked = self.invoke("--scope", "project", "--check", "--no-graph")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        repeated = self.invoke("--scope", "project", "--preview", "--json", "--no-graph")
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)["operations"], [])
        self.assertEqual(self.session.read_bytes(), session_before)
        self.assertFalse((self.home / ".claude" / "agents").exists())
        self.assertFalse((self.codex_home / "agents").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
