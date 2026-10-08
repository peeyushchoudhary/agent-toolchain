"""The graph refresh runs only where an existing graph sits at the hook's worktree root.

git runs a hook from the root of the worktree that ran the command, and linked worktrees share the
hooks directory. graphify's post-commit block never checks that a graph exists, so without our guard
a commit in a graphless worktree builds a partial graph that every consumer reads as current.

The oracle tests render real graphify blocks and run the installed hook file directly with `sh`, so
they observe the guard's decision without waiting on graphify's detached rebuild.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
INSTALLER = SKILL / "scripts" / "install_hooks.py"
LAUNCH = "[graphify hook] launching background rebuild"


def load_installer():
    spec = importlib.util.spec_from_file_location("install_hooks_guard_under_test", INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


class HermeticRepo(unittest.TestCase):
    """A temporary HOME, global git config and repository; no inherited GIT_* variable."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hooks-guard-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        scripts = self.home / ".claude" / "skills" / "progressive-disclosure" / "scripts"
        shutil.copytree(SKILL / "scripts", scripts)
        self.gitconfig = self.tmp / "gitconfig"
        self.gitconfig.write_text("[user]\n\tname = Fixture\n\temail = fixture@example.invalid\n"
                                  "[init]\n\tdefaultBranch = main\n", encoding="utf-8")
        self.path = os.environ.get("PATH", "")
        self.repo = self.tmp / "repo"
        self.git("init", "-q", str(self.repo), cwd=self.tmp)

    def env(self, **extra: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(HOME=str(self.home), GIT_CONFIG_GLOBAL=str(self.gitconfig),
                   GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1", PATH=self.path)
        env.update(extra)
        return env

    def git(self, *args: str, cwd: Path) -> str:
        return subprocess.run(["git", *args], cwd=cwd, env=self.env(), check=True,
                              capture_output=True, text=True, timeout=60).stdout

    def commit(self, cwd: Path, name: str) -> None:
        """Commit one file with every hook disabled, so setup never runs the hook under test."""
        (cwd / name).write_text(f"def {name.split('.')[0]}():\n    return 1\n", encoding="utf-8")
        no_hooks = self.tmp / "no-hooks"
        no_hooks.mkdir(exist_ok=True)
        self.git("add", name, cwd=cwd)
        self.git("-c", f"core.hooksPath={no_hooks}", "commit", "-q", "-m", name, cwd=cwd)

    def invoke(self, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(INSTALLER), str(self.repo), *flags],
                              env=self.env(), capture_output=True, text=True, timeout=180)

    def hook(self, name: str) -> Path:
        return self.repo / ".git" / "hooks" / name

    def run_hook(self, name: str, cwd: Path, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["sh", str(self.hook(name))], cwd=cwd, env=self.env(**extra),
                              capture_output=True, text=True, timeout=60)


@unittest.skipUnless(shutil.which("graphify"), "graphify is not on PATH; the oracle tests need the "
                     "real `graphify hook install` and `graphify update`")
class RealGraphifyGuardTest(HermeticRepo):
    def setUp(self) -> None:
        super().setUp()
        self.commit(self.repo, "alpha.py")
        self.commit(self.repo, "beta.py")
        subprocess.run(["graphify", "update", "."], cwd=self.repo, env=self.env(), check=True,
                       capture_output=True, text=True, timeout=120)
        self.assertTrue((self.repo / "graphify-out" / "graph.json").is_file())
        proc = self.invoke()
        self.assertIn("post-commit graph refresh installed", proc.stdout, proc.stdout + proc.stderr)
        self.worktree = self.tmp / "worktree"
        self.git("worktree", "add", "-q", "-b", "side", str(self.worktree), cwd=self.repo)
        self.commit(self.worktree, "gamma.py")
        self.assertFalse((self.worktree / "graphify-out").exists())
        self.addCleanup(self.settle)

    def settle(self) -> None:
        """Before cleanup only: let a launched detached rebuild finish writing into the tree."""
        log = self.home / ".cache" / "graphify-rebuild.log"
        deadline, size, stable = time.monotonic() + 30, -1, 0
        while log.is_file() and time.monotonic() < deadline and stable < 5:
            now = log.stat().st_size
            stable = stable + 1 if now == size else 0
            size = now
            time.sleep(0.2)

    def test_graphless_worktree_skips_and_creates_no_graph(self) -> None:
        proc = self.run_hook("post-commit", self.worktree)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(LAUNCH, proc.stdout + proc.stderr)
        self.assertFalse((self.worktree / "graphify-out").exists())
        checkout = self.run_hook("post-checkout", self.worktree)
        self.assertEqual(checkout.returncode, 0, checkout.stderr)
        self.assertFalse((self.worktree / "graphify-out").exists())

    def test_main_checkout_with_its_graph_reaches_the_launch(self) -> None:
        proc = self.run_hook("post-commit", self.repo)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(LAUNCH, proc.stdout)

    def test_graphify_root_pointing_elsewhere_skips(self) -> None:
        (self.repo / "graphify-out" / ".graphify_root").write_text("elsewhere", encoding="utf-8")
        proc = self.run_hook("post-commit", self.repo)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(LAUNCH, proc.stdout + proc.stderr)

    def test_installed_hooks_parse_as_sh(self) -> None:
        for name in ("post-commit", "post-checkout"):
            text = self.hook(name).read_text(encoding="utf-8")
            self.assertEqual(text.count("# graph-guard-start"), 1, name)
            r = subprocess.run(["sh", "-n", str(self.hook(name))], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


class StubGraphifyGuardTest(HermeticRepo):
    STUB = {
        "post-commit": "# graphify-hook-start\necho stub post-commit refresh\n# graphify-hook-end",
        "post-checkout": ("# graphify-checkout-hook-start\necho stub post-checkout refresh\n"
                          "# graphify-checkout-hook-end"),
    }

    def setUp(self) -> None:
        super().setUp()
        self.guard = load_installer().GRAPH_GUARD
        fake_bin = self.tmp / "bin"
        fake_bin.mkdir()
        self.log = self.tmp / "graphify.log"
        lines = ["#!/bin/sh", f"echo \"$*\" >> '{self.log}'", "[ \"$1 $2\" = 'hook install' ] || exit 0"]
        for name, block in self.STUB.items():
            lines.append(f"printf '#!/bin/sh\\n%s\\n' '{block}' > .git/hooks/{name}")
        (fake_bin / "graphify").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (fake_bin / "graphify").chmod(0o755)
        self.path = f"{fake_bin}:{self.path}"

    def root_graph(self, base: Path | None = None, out: str = "graphify-out") -> Path:
        graph = (base or self.repo) / out / "graph.json"
        graph.parent.mkdir(parents=True, exist_ok=True)
        graph.write_text("{}\n", encoding="utf-8")
        return graph

    def test_guard_sits_immediately_before_each_block_byte_for_byte(self) -> None:
        self.root_graph()
        proc = self.invoke()
        self.assertIn("post-commit graph refresh installed", proc.stdout, proc.stdout)
        for name, block in self.STUB.items():
            text = self.hook(name).read_text(encoding="utf-8")
            self.assertEqual(text, "#!/bin/sh\n" + self.guard + "\n" + block + "\n", name)

    def test_reinstall_replaces_in_place(self) -> None:
        self.root_graph()
        self.invoke()
        first = {name: self.hook(name).read_bytes() for name in self.STUB}
        self.invoke()
        for name in self.STUB:
            self.assertEqual(self.hook(name).read_bytes(), first[name], name)
            text = first[name].decode("utf-8")
            self.assertEqual(text.count("# graph-guard-start"), 1)
            self.assertEqual(text.count(self.STUB[name].splitlines()[0]), 1)

    def test_existing_unguarded_block_gains_its_guard(self) -> None:
        self.root_graph()
        for name, block in self.STUB.items():
            self.hook(name).write_text("#!/bin/sh\necho mine\n\n" + block + "\n", encoding="utf-8")
        self.invoke()
        for name, block in self.STUB.items():
            self.assertEqual(self.hook(name).read_text(encoding="utf-8"),
                             "#!/bin/sh\necho mine\n\n" + self.guard + "\n" + block + "\n", name)

    def test_uninstall_strips_guards_with_the_blocks(self) -> None:
        self.root_graph()
        self.hook("post-checkout").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        self.invoke()
        self.assertIn("graph-guard-start", self.hook("post-checkout").read_text(encoding="utf-8"))
        proc = self.invoke("--uninstall")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(self.hook("post-commit").exists())
        self.assertEqual(self.hook("post-checkout").read_text(encoding="utf-8"),
                         "#!/bin/sh\necho mine\n")

    def test_child_graph_is_skipped_honestly(self) -> None:
        self.root_graph(self.repo / "sub")
        proc = self.invoke()
        self.assertIn("post-commit graph refresh skipped — the graph is under sub/ and git hooks "
                      "run at the repository root; refresh by hand with: graphify update sub",
                      proc.stdout)
        self.assertNotIn("graph refresh installed", proc.stdout)
        self.assertFalse(self.log.exists())
        for name in self.STUB:
            self.assertFalse(self.hook(name).exists(), name)

    GUARDED_LINE = ("guarded the existing graphify hook blocks; they refresh only an existing graph "
                    "at the worktree root")

    def existing_unguarded(self) -> dict[str, str]:
        """graphify blocks already in the hooks without our guard, as graphify itself writes them."""
        for name, block in self.STUB.items():
            self.hook(name).write_text("#!/bin/sh\necho mine\n\n" + block + "\n", encoding="utf-8")
            self.hook(name).chmod(0o755)
        return {name: "#!/bin/sh\necho mine\n\n" + self.guard + "\n" + block + "\n"
                for name, block in self.STUB.items()}

    def without_graphify_on_path(self) -> None:
        self.path = os.pathsep.join(d for d in self.path.split(os.pathsep)
                                    if d and not (Path(d) / "graphify").exists())

    def test_skipping_runs_still_guard_existing_blocks(self) -> None:
        cases = {
            "no root graph": ((), None, "no graphify-out/graph.json in this repo"),
            "child graph": ((), "sub", "the graph is under sub/"),
            "--no-graph": (("--no-graph",), ".", "skipped (--no-graph)"),
            "graphify absent": ((), ".", "graphify is not installed"),
        }
        for case, (flags, graph, skip_line) in cases.items():
            with self.subTest(case):
                shutil.rmtree(self.repo / "graphify-out", True)
                shutil.rmtree(self.repo / "sub", True)
                if graph:
                    self.root_graph(self.repo / graph)
                if case == "graphify absent":
                    self.without_graphify_on_path()
                expected = self.existing_unguarded()
                proc = self.invoke(*flags)
                self.assertIn(skip_line, proc.stdout)
                self.assertIn(self.GUARDED_LINE, proc.stdout)
                self.assertNotIn("graph refresh installed", proc.stdout)
                for name in self.STUB:
                    self.assertEqual(self.hook(name).read_text(encoding="utf-8"), expected[name])
                self.assertFalse(self.log.exists())

    def test_hooks_path_leaves_existing_unguarded_block_untouched(self) -> None:
        self.git("config", "core.hooksPath", ".hooks", cwd=self.repo)
        self.existing_unguarded()
        before = {name: self.hook(name).read_bytes() for name in self.STUB}
        proc = self.invoke("--no-graph")
        self.assertNotIn(self.GUARDED_LINE, proc.stdout)
        self.assertEqual({name: self.hook(name).read_bytes() for name in self.STUB}, before)

    def test_already_guarded_block_is_not_rewritten(self) -> None:
        self.existing_unguarded()
        self.invoke("--no-graph")
        before = {name: (self.hook(name).read_bytes(), self.hook(name).stat().st_ino,
                         self.hook(name).stat().st_mtime_ns) for name in self.STUB}
        proc = self.invoke("--no-graph")
        self.assertNotIn(self.GUARDED_LINE, proc.stdout)
        self.assertEqual({name: (self.hook(name).read_bytes(), self.hook(name).stat().st_ino,
                                 self.hook(name).stat().st_mtime_ns) for name in self.STUB}, before)

    def test_guard_honours_graphify_out_and_graphify_root(self) -> None:
        self.root_graph()
        self.invoke()
        site = self.tmp / "site"
        site.mkdir()
        reached = "stub post-commit refresh"
        self.assertNotIn(reached, self.run_hook("post-commit", site).stdout)
        self.root_graph(site, "custom-out")
        self.assertNotIn(reached, self.run_hook("post-commit", site).stdout)
        self.assertIn(reached, self.run_hook("post-commit", site, GRAPHIFY_OUT="custom-out").stdout)
        marker = site / "custom-out" / ".graphify_root"
        for content, runs in ((".", True), (".\n", True), (".\n\n", False), ("sub", False),
                              ("", False)):
            marker.write_text(content, encoding="utf-8")
            out = self.run_hook("post-commit", site, GRAPHIFY_OUT="custom-out").stdout
            self.assertEqual(reached in out, runs, repr(content))


if __name__ == "__main__":
    unittest.main()
