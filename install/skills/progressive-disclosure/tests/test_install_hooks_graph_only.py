"""F-5 T7: the graph hooks install without a graph in the main checkout, and `--graph-only`.

Each worktree keeps its own graph and the guard makes the shared blocks no-ops wherever none
exists, so the installer no longer requires the main checkout to have one. `--graph-only` runs only
that step for goal setup, leaving pre-commit, commit-msg and pre-push to migration.

Real git, a temporary HOME and global config, and a stub `graphify` that renders fixed blocks into
whatever repository it runs in and logs where it ran. Nothing reads the real HOME.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
INSTALLER = SKILL / "scripts" / "install_hooks.py"
STUB = {
    "post-commit": "# graphify-hook-start\necho stub post-commit refresh\n# graphify-hook-end",
    "post-checkout": ("# graphify-checkout-hook-start\necho stub post-checkout refresh\n"
                      "# graphify-checkout-hook-end"),
}
OURS = {  # existing content of the hooks --graph-only must not touch; no trailing newline on one
    "pre-commit": "#!/bin/sh\n# someone else's pre-commit\nexit 0\n",
    "commit-msg": "#!/bin/bash\necho msg   \n",
    "pre-push": "#!/bin/sh\necho push",
}
REFUSED = "--graph-only cannot be combined with"
INSTALLED = "post-commit graph refresh installed"


def guard_text() -> str:
    spec = importlib.util.spec_from_file_location("install_hooks_graph_only_under_test", INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.GRAPH_GUARD


GUARD = guard_text()


class GraphOnlyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hooks-graph-only-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        shutil.copytree(SKILL / "scripts",
                        self.home / ".claude" / "skills" / "progressive-disclosure" / "scripts")
        self.gitconfig = self.tmp / "gitconfig"
        self.gitconfig.write_text("[user]\n\tname = Fixture\n\temail = fixture@example.invalid\n"
                                  "[init]\n\tdefaultBranch = main\n", encoding="utf-8")
        fake_bin = self.tmp / "bin"
        fake_bin.mkdir()
        self.log = self.tmp / "graphify.log"
        lines = ["#!/bin/sh", f"printf '%s\\t%s\\n' \"$(pwd -P)\" \"$*\" >> '{self.log}'",
                 "[ \"$1 $2\" = 'hook install' ] || exit 0"]
        for name, block in STUB.items():
            lines.append(f"printf '#!/bin/sh\\n%s\\n' '{block}' > .git/hooks/{name}")
        (fake_bin / "graphify").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (fake_bin / "graphify").chmod(0o755)
        self.fake_bin = fake_bin
        self.path = f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"
        self.repo = self.tmp / "repo"
        self.git("init", "-q", str(self.repo), cwd=self.tmp)

    # -- fixture ------------------------------------------------------------------------------

    def env(self, **extra: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GRAPHIFY_"))}
        env.update(HOME=str(self.home), GIT_CONFIG_GLOBAL=str(self.gitconfig),
                   GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1", PATH=self.path)
        env.update(extra)
        return env

    def git(self, *args: str, cwd: Path) -> str:
        return subprocess.run(["git", *args], cwd=cwd, env=self.env(), check=True,
                              capture_output=True, text=True, timeout=60).stdout

    def invoke(self, *flags: str, root: Path | None = None, cwd: Path | None = None,
               **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(INSTALLER), str(root or self.repo), *flags],
                              cwd=cwd or self.tmp, env=self.env(**extra), capture_output=True,
                              text=True, timeout=180)

    def hook(self, name: str, repo: Path | None = None) -> Path:
        return (repo or self.repo) / ".git" / "hooks" / name

    def graph(self, base: Path) -> None:
        (base / "graphify-out").mkdir(parents=True, exist_ok=True)
        (base / "graphify-out" / "graph.json").write_text("{}\n", encoding="utf-8")

    def write_ours(self) -> None:
        for name, text in OURS.items():
            self.hook(name).write_text(text, encoding="utf-8")
            self.hook(name).chmod(0o755)

    def unguarded(self, body: str = "") -> dict[str, str]:
        """graphify blocks already present without our guard; returns their guarded form."""
        for name, block in STUB.items():
            self.hook(name).write_text("#!/bin/sh\necho mine\n\n" + (body or block) + "\n",
                                       encoding="utf-8")
            self.hook(name).chmod(0o755)
        return {name: "#!/bin/sh\necho mine\n\n" + GUARD + "\n" + block + "\n"
                for name, block in STUB.items()}

    def snapshot(self, *dirs: Path) -> dict[str, tuple[bytes, int, int, int]]:
        """Bytes, mode, inode and mtime of every file: an unchanged entry was not rewritten."""
        out = {}
        for base in dirs or (self.repo,):
            for p in sorted(base.rglob("*")):
                if p.is_file() and not p.is_symlink() and (".git" not in p.relative_to(base).parts
                                                           or "hooks" in p.parts):
                    st = p.stat()
                    out[str(p)] = (p.read_bytes(), st.st_mode, st.st_ino, st.st_mtime_ns)
        return out

    def calls(self) -> list[list[str]]:
        text = self.log.read_text(encoding="utf-8") if self.log.exists() else ""
        return [line.split("\t") for line in text.splitlines()]

    def assert_rendered_only_outside(self, project: Path) -> None:
        self.assertTrue(self.calls())
        for cwd, _args in self.calls():
            self.assertNotIn(project.resolve(), [Path(cwd), *Path(cwd).parents], cwd)

    def assert_guarded_blocks(self, repo: Path | None = None, prefix: str = "#!/bin/sh\n") -> None:
        for name, block in STUB.items():
            self.assertEqual(self.hook(name, repo).read_text(encoding="utf-8"),
                             prefix + GUARD + "\n" + block + "\n", name)
            self.assertTrue(os.access(self.hook(name, repo), os.X_OK), name)

    def without_graphify_on_path(self) -> None:
        self.path = os.pathsep.join(d for d in self.path.split(os.pathsep)
                                    if d and not (Path(d) / "graphify").exists())

    # -- the dropped graph requirement --------------------------------------------------------

    def test_install_without_a_graph_writes_the_guarded_blocks(self) -> None:
        for flags in ((), ("--graph-only",)):
            with self.subTest(flags=flags):
                for name in STUB:
                    self.hook(name).unlink(missing_ok=True)
                proc = self.invoke(*flags)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn(INSTALLED, proc.stdout)
                self.assertNotIn("no graphify-out/graph.json", proc.stdout)
                self.assertFalse((self.repo / "graphify-out").exists())
                self.assert_guarded_blocks()
                self.assert_rendered_only_outside(self.repo)

    def test_child_graph_still_installs_nothing(self) -> None:
        self.graph(self.repo / "sub")
        for flags in ((), ("--graph-only",)):
            with self.subTest(flags=flags):
                proc = self.invoke(*flags)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("skipped — the graph is under sub/", proc.stdout)
                self.assertNotIn(INSTALLED, proc.stdout)
                for name in STUB:
                    self.assertFalse(self.hook(name).exists(), name)
                self.assertEqual(self.calls(), [])

    def test_graph_only_with_a_root_graph_installs(self) -> None:
        self.graph(self.repo)
        proc = self.invoke("--graph-only")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assert_guarded_blocks()

    # -- --graph-only touches no other hook ---------------------------------------------------

    def test_graph_only_leaves_other_hooks_byte_for_byte(self) -> None:
        self.write_ours()
        self.hook("post-commit").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        others = {k: v for k, v in self.snapshot(self.hook("x").parent).items()
                  if Path(k).name not in STUB}
        proc = self.invoke("--graph-only")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        after = {k: v for k, v in self.snapshot(self.hook("x").parent).items()
                 if Path(k).name not in STUB}
        self.assertEqual(after, others)
        for name in OURS:
            self.assertNotIn(f"  {name} ", proc.stdout)
        self.assertEqual(self.hook("post-commit").read_text(encoding="utf-8"),
                         "#!/bin/sh\necho mine\n\n" + GUARD + "\n" + STUB["post-commit"] + "\n")
        self.assertEqual(self.hook("post-checkout").read_text(encoding="utf-8"),
                         "#!/bin/sh\n" + GUARD + "\n" + STUB["post-checkout"] + "\n")

    def test_graph_only_creates_no_other_hook(self) -> None:
        proc = self.invoke("--graph-only")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in OURS:
            self.assertFalse(self.hook(name).exists(), name)
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_graph_only_guards_an_existing_unguarded_block_in_place(self) -> None:
        self.write_ours()
        expected = self.unguarded(body="# graphify-hook-start\nold body\n# graphify-hook-end")
        self.hook("post-checkout").write_text(
            "#!/bin/sh\necho mine\n\n" + STUB["post-checkout"] + "\n", encoding="utf-8")
        before = {name: self.hook(name).read_bytes() for name in OURS}
        proc = self.invoke("--graph-only")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in STUB:
            text = self.hook(name).read_text(encoding="utf-8")
            self.assertEqual(text, expected[name], name)
            self.assertEqual(text.count("# graph-guard-start"), 1, name)
        self.assertEqual({name: self.hook(name).read_bytes() for name in OURS}, before)
        again = self.snapshot()
        self.assertEqual(self.invoke("--graph-only").returncode, 0)
        self.assertEqual({k: v[0] for k, v in self.snapshot().items()},
                         {k: v[0] for k, v in again.items()})

    def test_graph_only_with_no_graph_flag_only_guards_existing_blocks(self) -> None:
        self.write_ours()
        expected = self.unguarded()
        before = {name: self.hook(name).read_bytes() for name in OURS}
        proc = self.invoke("--graph-only", "--no-graph")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("skipped (--no-graph)", proc.stdout)
        self.assertNotIn(INSTALLED, proc.stdout)
        for name in STUB:
            self.assertEqual(self.hook(name).read_text(encoding="utf-8"), expected[name])
        self.assertEqual({name: self.hook(name).read_bytes() for name in OURS}, before)
        self.assertEqual(self.calls(), [])
        fresh = self.tmp / "fresh"
        self.git("init", "-q", str(fresh), cwd=self.tmp)
        proc = self.invoke("--graph-only", "--no-graph", root=fresh)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in (*STUB, *OURS):
            self.assertFalse(self.hook(name, fresh).exists(), name)

    def test_graph_only_without_graphify_writes_nothing_new(self) -> None:
        self.without_graphify_on_path()
        proc = self.invoke("--graph-only")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("graphify is not installed", proc.stdout)
        for name in (*STUB, *OURS):
            self.assertFalse(self.hook(name).exists(), name)
        expected = self.unguarded()
        self.assertEqual(self.invoke("--graph-only").returncode, 0)
        for name in STUB:  # still guarded in place: the guard needs no graphify
            self.assertEqual(self.hook(name).read_text(encoding="utf-8"), expected[name])

    def test_graph_only_render_failure_exits_nonzero_and_writes_nothing(self) -> None:
        (self.fake_bin / "graphify").write_text("#!/bin/sh\necho broken >&2\nexit 3\n",
                                                encoding="utf-8")
        self.write_ours()
        before = self.snapshot()
        proc = self.invoke("--graph-only")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("post-commit graph refresh FAILED", proc.stdout)
        self.assertEqual(self.snapshot(), before)

    # -- core.hooksPath: install only when unset ----------------------------------------------

    def test_graph_only_with_hooks_path_configured_writes_nothing(self) -> None:
        (self.repo / ".hooks").mkdir()
        only = self.tmp / "only.gitconfig"
        only.write_text("[core]\n\thooksPath = .hooks\n", encoding="utf-8")
        cases = {
            "default dir": (".git/hooks", {}),
            "relative": (".hooks", {}),
            "own absolute": (str(self.repo / ".git" / "hooks"), {}),
            "empty": ("", {}),
            "GIT_CONFIG_PARAMETERS": (None, {"GIT_CONFIG_PARAMETERS": "'core.hooksPath'='.hooks'"}),
            "GIT_CONFIG_COUNT": (None, {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath",
                                        "GIT_CONFIG_VALUE_0": ".hooks"}),
            "GIT_CONFIG shadowing a set value": (".hooks", {"GIT_CONFIG": str(self.gitconfig)}),
        }
        self.write_ours()
        for label, (value, extra) in cases.items():
            with self.subTest(label):
                cfg = ["config", "--unset-all", "core.hooksPath"]
                subprocess.run(["git", *cfg], cwd=self.repo, env=self.env())
                if value is not None:
                    self.git("config", "core.hooksPath", value, cwd=self.repo)
                self.unguarded()
                before = self.snapshot()
                proc = self.invoke("--graph-only", **extra)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("core.hooksPath is configured", proc.stdout)
                self.assertNotIn("guarded the existing", proc.stdout)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(list((self.repo / ".hooks").iterdir()), [])
                self.assertEqual(self.calls(), [])

    def test_git_config_file_alone_is_not_what_git_runs(self) -> None:
        """GIT_CONFIG is read only by `git config`, never by the git that runs hooks: unset."""
        only = self.tmp / "only.gitconfig"
        only.write_text("[core]\n\thooksPath = .hooks\n", encoding="utf-8")
        proc = self.invoke("--graph-only", GIT_CONFIG=str(only))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(INSTALLED, proc.stdout)
        self.assert_guarded_blocks()

    # -- refused combinations -----------------------------------------------------------------

    def test_refused_combinations_exit_nonzero_and_write_nothing(self) -> None:
        self.write_ours()
        self.unguarded()
        self.graph(self.repo)
        (self.repo / "AGENTS.md").write_text("# Fixture\n", encoding="utf-8")
        before = self.snapshot()
        combos = {
            "--uninstall": ("--uninstall",), "--check": ("--check",),
            "--scope": ("--scope", "project"), "--public": ("--public",),
            "--standard": ("--standard",),
            "--scope --preview": ("--scope", "project", "--preview"),
            "--check --uninstall": ("--check", "--uninstall"),
        }
        for label, flags in combos.items():
            for extra in ((), ("--no-graph",)):
                with self.subTest(label, no_graph=bool(extra)):
                    proc = self.invoke("--graph-only", *flags, *extra)
                    self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                    self.assertIn(REFUSED, proc.stderr)
                    self.assertEqual(proc.stdout, "")
                    self.assertEqual(self.snapshot(), before)
                    self.assertEqual(self.calls(), [])
        for flags in (("--preview",), ("--preview", "--json"), ("--json",)):
            with self.subTest(flags=flags):  # refused by the existing --scope/--preview rules
                proc = self.invoke("--graph-only", *flags)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertEqual(self.snapshot(), before)

    # -- worktrees ----------------------------------------------------------------------------

    def commit(self, cwd: Path, name: str) -> None:
        (cwd / name).write_text("x = 1\n", encoding="utf-8")
        self.git("add", name, cwd=cwd)
        self.git("-c", f"core.hooksPath={self.tmp / 'no-hooks'}", "commit", "-q", "-m", name,
                 cwd=cwd)

    def test_graph_only_from_a_linked_worktree_whose_main_checkout_has_no_graph(self) -> None:
        self.commit(self.repo, "a.py")
        linked = self.tmp / "linked"
        self.git("worktree", "add", "-q", "-b", "side", str(linked), cwd=self.repo)
        self.graph(linked)
        graph_before = (linked / "graphify-out" / "graph.json").read_bytes()
        common = Path(self.git("rev-parse", "--path-format=absolute", "--git-common-dir",
                               cwd=linked).strip())
        main = common.parent
        self.assertEqual(main, self.repo)
        self.write_ours()
        before = {name: self.hook(name).read_bytes() for name in OURS}
        # As setup runs it: cwd in the linked worktree, the main checkout as ROOT, and the
        # linked worktree's repository-location variables inherited, which must not redirect it.
        linked_git = self.git("rev-parse", "--absolute-git-dir", cwd=linked).strip()
        proc = self.invoke("--graph-only", root=main, cwd=linked, GIT_DIR=linked_git,
                           GIT_WORK_TREE=str(linked))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(INSTALLED, proc.stdout)
        self.assert_guarded_blocks()
        hooks = Path(self.git("rev-parse", "--path-format=absolute", "--git-path", "hooks",
                              cwd=linked).strip())
        self.assertEqual(hooks, self.repo / ".git" / "hooks")
        self.assertEqual({name: self.hook(name).read_bytes() for name in OURS}, before)
        self.assertFalse((self.repo / "graphify-out").exists())
        self.assertEqual((linked / "graphify-out" / "graph.json").read_bytes(), graph_before)
        self.assert_rendered_only_outside(self.repo)
        self.assert_rendered_only_outside(linked)

    def test_graph_only_given_the_linked_worktree_itself_writes_nothing(self) -> None:
        """A linked worktree's .git is a file; the installer needs the main checkout as ROOT."""
        self.commit(self.repo, "a.py")
        linked = self.tmp / "linked"
        self.git("worktree", "add", "-q", "-b", "side", str(linked), cwd=self.repo)
        before = self.snapshot(self.hook("x").parent)
        proc = self.invoke("--graph-only", root=linked)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("not a git repository", proc.stdout)
        self.assertEqual(self.snapshot(self.hook("x").parent), before)
        self.assertEqual(self.calls(), [])

    # -- symlinked destinations (the existing _destination_error path) ------------------------

    def test_graph_only_refuses_a_symlinked_hooks_directory(self) -> None:
        external = self.tmp / "external-hooks"
        external.mkdir()
        (external / "post-commit").write_text("#!/bin/sh\necho theirs\n", encoding="utf-8")
        shutil.rmtree(self.repo / ".git" / "hooks")
        (self.repo / ".git" / "hooks").symlink_to(external, target_is_directory=True)
        before = self.snapshot(external)
        proc = self.invoke("--graph-only")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("REFUSED", proc.stdout)
        self.assertEqual(self.snapshot(external), before)
        self.assertEqual(sorted(p.name for p in external.iterdir()), ["post-commit"])
        self.assertEqual(self.calls(), [])

    def test_graph_only_refuses_a_symlinked_hook_file(self) -> None:
        for name in ("post-commit", "post-checkout", "pre-commit"):
            with self.subTest(name):
                target = self.tmp / f"outside-{name}"
                target.write_text("#!/bin/sh\necho outside\n", encoding="utf-8")
                for hook in self.hook("x").parent.iterdir():
                    if hook.is_symlink():
                        hook.unlink()
                self.hook(name).symlink_to(target)
                proc = self.invoke("--graph-only")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn("REFUSED", proc.stdout)
                self.assertEqual(target.read_text(encoding="utf-8"), "#!/bin/sh\necho outside\n")
                for other in STUB:
                    if other != name:
                        self.assertFalse(self.hook(other).exists(), other)
                self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
