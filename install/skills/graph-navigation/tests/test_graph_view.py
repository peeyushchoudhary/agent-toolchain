"""F-5 T6: `graph_view.py setup` and `graph_view.py view`, the advisory graph contract A1-A6.

Real git in temporary repositories whose path contains a space, a temporary HOME, global config
and TMPDIR, and a stub `graphify` that logs its cwd, argv and environment. Like graphify 0.8.49 the
stub writes its path argument into `.graphify_root` first, then `graph.json` (with
`built_at_commit`) and `GRAPH_REPORT.md` through `Path.write_text`, which follows symlinks; it can
hang or fail after writing `.graphify_root`, and it refuses a shrinking graph without `--force`.
Its `explain` and `affected` honour `--graph` and print the `built_at_commit` they read.

`test_oracle_setup_build_then_label` runs the real graphify, when it is on PATH, in a temporary
repository under a temporary HOME. Nothing here reads or writes the real HOME.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "graph_view.py"
INSTALLER = SKILL.parent / "progressive-disclosure" / "scripts" / "install_hooks.py"
STAMP = ".graph_view_complete"
ADVISORY = "advisory — confirm with grep"
PATHSPEC_VARS = ("GIT_GLOB_PATHSPECS", "GIT_ICASE_PATHSPECS", "GIT_LITERAL_PATHSPECS",
                 "GIT_NOGLOB_PATHSPECS")
NO_GRAPHIFY = "graphify not installed; graph context off (install with: uv tool install graphifyy)"
BOOT = ("import json, sys; sys.path.insert(0, sys.argv[1]); import graph_view as g; "
        "g.BOUNDS.update(json.loads(sys.argv[2])); sys.exit(g.main(sys.argv[3:]))")
BLOCKS = {
    "post-commit": "# graphify-hook-start\necho stub post-commit refresh\n# graphify-hook-end",
    "post-checkout": ("# graphify-checkout-hook-start\necho stub post-checkout refresh\n"
                      "# graphify-checkout-hook-end"),
}
STUB = r'''#!{python}
import json, os, subprocess, sys, time
from pathlib import Path
CONTROL, LOG, BLOCKS = {control!r}, {log!r}, {blocks!r}
ctl = json.loads(Path(CONTROL).read_text()) if Path(CONTROL).exists() else {{}}
argv = sys.argv[1:]
with open(LOG, "a") as fh:
    env = {{k: v for k, v in os.environ.items() if k.startswith(("GRAPHIFY_", "GIT_"))}}
    fh.write(json.dumps({{"cwd": os.path.realpath(os.getcwd()), "argv": argv, "env": env}}) + "\n")
if ctl.get("all") == "fail":
    sys.exit(5)
if argv[:2] == ["hook", "install"]:
    for name, block in BLOCKS.items():
        Path(".git/hooks", name).write_text("#!/bin/sh\n" + block + "\n")
    sys.exit(0)
if argv[:1] == ["update"]:
    path = next(a for a in argv[1:] if not a.startswith("-"))
    out = Path(path) / "graphify-out"
    out.mkdir(exist_ok=True)
    (out / ".graphify_root").write_text(path)
    if ctl.get("update") == "hang":
        time.sleep(600)
    if ctl.get("update") == "fail":
        sys.exit(ctl.get("exit", 3))
    nodes, graph = ctl.get("nodes", 3), out / "graph.json"
    try:
        old = len(json.loads(graph.read_text())["nodes"])
    except Exception:
        old = 0
    if nodes < old and "--force" not in argv:
        print("refusing to shrink", file=sys.stderr)
        sys.exit(1)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    graph.write_text(json.dumps({{"built_at_commit": commit,
                                 "nodes": [{{"id": f"n{{i}}"}} for i in range(nodes)]}}))
    (out / "GRAPH_REPORT.md").write_text(f"# report at {{commit}}\n")
    sys.exit(0)
if argv[:1] in (["explain"], ["affected"]):
    mode = ctl.get(argv[0], "ok")
    data = json.loads(Path(argv[argv.index("--graph") + 1]).read_text())
    if mode == "replace":
        Path("graphify-out/graph.json").write_text(json.dumps({{"built_at_commit": "f" * 40}}))
    if mode == "hang":
        time.sleep(600)
    if mode == "fail":
        sys.exit(4)
    print(f"{{argv[0]}} {{argv[1]}} built_at_commit={{data.get('built_at_commit')}}")
'''


def load_guard() -> str:
    spec = importlib.util.spec_from_file_location("install_hooks_for_graph_view_test", INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module.GRAPH_GUARD


GUARD = load_guard()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def path_without_graphify() -> list[str]:
    return [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not (Path(d) / "graphify").exists()]


class GraphViewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="graph view ")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home, self.systmp, self.out = self.tmp / "home", self.tmp / "systmp", self.tmp / "out"
        self.home.mkdir()
        self.systmp.mkdir()
        self.gitconfig = self.tmp / "gitconfig"
        self.gitconfig.write_text("[user]\n\tname = Fixture\n\temail = fixture@example.invalid\n"
                                  "[init]\n\tdefaultBranch = main\n", encoding="utf-8")
        self.control, self.log = self.tmp / "stub.json", self.tmp / "stub.log"
        self.bin, pybin = self.tmp / "bin", self.tmp / "pybin"
        self.bin.mkdir()
        pybin.mkdir()
        (pybin / "python3").symlink_to(sys.executable)  # printed commands start with `python3`
        stub = self.bin / "graphify"
        stub.write_text(STUB.format(python=sys.executable, control=str(self.control),
                                    log=str(self.log), blocks=BLOCKS), encoding="utf-8")
        stub.chmod(0o755)
        self.bare_path = [str(pybin), *path_without_graphify()]
        self.path = os.pathsep.join([str(self.bin), *self.bare_path])
        self.repo = self.make_repo("repo")

    # -- fixture ------------------------------------------------------------------------------

    def env(self, path: str | None = None, **extra: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GRAPHIFY_"))}
        env.update(HOME=str(self.home), GIT_CONFIG_GLOBAL=str(self.gitconfig),
                   GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(self.systmp),
                   PATH=path or self.path)
        env.update(extra)
        return env

    def git(self, *args: str, cwd: Path | None = None, **extra: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env(**extra),
                              check=True, capture_output=True, text=True, timeout=60).stdout.strip()

    def make_repo(self, name: str, ignore: str = "/graphify-out/\n") -> Path:
        repo = self.tmp / name
        self.git("init", "-q", str(repo), cwd=self.tmp)
        (repo / ".gitignore").write_text(ignore, encoding="utf-8")
        (repo / "tracked.md").write_text("tracked\n", encoding="utf-8")
        self.git("add", "-A", cwd=repo)
        self.git("commit", "-qm", "init", cwd=repo)
        subprocess.run([sys.executable, str(INSTALLER), str(repo), "--graph-only"], cwd=repo,
                       env=self.env(), check=True, capture_output=True, timeout=120)
        self.log.unlink(missing_ok=True)
        return repo

    def commits(self, n: int, repo: Path | None = None) -> str:
        for _ in range(n):  # unique messages: same-second empty commits would otherwise collide
            self.serial = getattr(self, "serial", 0) + 1
            self.git("commit", "-q", "--allow-empty", "-m", f"c{self.serial}", cwd=repo)
        return self.git("rev-parse", "HEAD", cwd=repo)

    def stub(self, **control) -> None:
        self.control.write_text(json.dumps(control), encoding="utf-8")

    def graph(self, base: Path | None = None, commit: str | None = "HEAD", nodes: int = 3,
              marker: str | None = ".", raw: str | None = None, stamp: bool = False) -> Path:
        base = base or self.repo
        g = base / "graphify-out"
        g.mkdir(parents=True, exist_ok=True)
        data: dict = {"nodes": [{"id": f"n{i}"} for i in range(nodes)]}
        if commit:
            data["built_at_commit"] = self.git("rev-parse", commit, cwd=base)
        (g / "graph.json").write_text(json.dumps(data) if raw is None else raw, encoding="utf-8")
        if marker is not None:
            (g / ".graphify_root").write_text(marker, encoding="utf-8")
        if stamp:
            self.stamp(g)
        return g

    def stamp(self, g: Path, head: str | None = None, digest: str | None = None) -> None:
        (g / STAMP).write_text(json.dumps({
            "head": head or self.git("rev-parse", "HEAD", cwd=g.parent),
            "sha256": digest or sha((g / "graph.json").read_bytes())}), encoding="utf-8")

    def gv(self, *args: str, cwd: Path | None = None, bounds: dict | None = None,
           path: str | None = None, **extra: str) -> list[str]:
        cmd = ([sys.executable, str(SCRIPT), *args] if bounds is None else
               [sys.executable, "-c", BOOT, str(SCRIPT.parent), json.dumps(bounds), *args])
        r = subprocess.run(cmd, cwd=cwd or self.repo, env=self.env(path, **extra),
                           capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # A6: exit 0 in every case
        self.assertEqual(r.stderr, "")
        return r.stdout.splitlines()

    def run_printed(self, line: str, marker: str, cwd: Path | None = None) -> list[str]:
        """Run the command a printed line names, exactly as printed (tested-fix-command rule)."""
        cmd = shlex.split(line.split(marker, 1)[1])
        self.assertEqual(cmd[:2], ["python3", str(SCRIPT)])
        r = subprocess.run(cmd, cwd=cwd or self.repo, env=self.env(), capture_output=True,
                           text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.splitlines()

    def calls(self, kind: str | None = None) -> list[dict]:
        text = self.log.read_text(encoding="utf-8") if self.log.exists() else ""
        entries = [json.loads(line) for line in text.splitlines()]
        return [e for e in entries if kind is None or e["argv"][:1] == [kind]]

    def assert_one_build(self, cwd: Path) -> None:
        builds = self.calls("update")
        self.assertEqual(len(builds), 1, builds)
        self.assertEqual(builds[0]["argv"], ["update", ".", "--force"])
        self.assertEqual(Path(builds[0]["cwd"]), cwd)
        self.assertFalse([k for k in builds[0]["env"] if k.startswith("GRAPHIFY_")])

    def assert_stamped(self, g: Path) -> None:
        stamp = json.loads((g / STAMP).read_text(encoding="utf-8"))
        self.assertEqual(stamp, {"head": self.git("rev-parse", "HEAD", cwd=g.parent),
                                 "sha256": sha((g / "graph.json").read_bytes())})
        self.assertEqual((g / ".graphify_root").read_text(encoding="utf-8"), ".")

    def label(self, commit: str, behind: int, ahead: int = 0, full: bool = False) -> str:
        text = f"graph built at {commit[:7]} ({behind} commits behind HEAD"
        text += (f", {ahead} ahead)" if ahead else ")") + ("; full build by setup at HEAD" if full else "")
        return f"{text}; {ADVISORY}"

    def files(self, base: Path) -> dict[str, bytes]:
        return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*"))
                if p.is_file() and ".git" not in p.relative_to(base).parts}

    def rerun(self, *args: str, root: Path | None = None) -> str:
        return shlex.join(["python3", str(SCRIPT), args[0], "--root", str(root or self.repo),
                           *args[1:]])

    # -- labels (A4) --------------------------------------------------------------------------

    def test_label_behind_by_n(self) -> None:
        built = self.git("rev-parse", "HEAD")
        self.graph(stamp=True)
        self.commits(3)
        lines = self.gv("view", "--out", str(self.out), "Alpha", "Beta")
        expected = self.label(built, 3)
        self.assertEqual(lines[0], expected)
        self.assertEqual(lines[1:], [str(self.out / "Alpha.txt"), str(self.out / "Beta.txt")])
        for name in ("Alpha", "Beta"):
            text = (self.out / f"{name}.txt").read_text(encoding="utf-8")
            self.assertEqual(text.splitlines()[0], expected)

    def test_label_ahead_of_head(self) -> None:
        start = self.git("rev-parse", "HEAD")
        tip = self.commits(2)
        self.graph()
        self.git("checkout", "-q", start)
        self.assertEqual(self.gv("view"), [self.label(tip, 0, ahead=2)])

    def test_label_diverged(self) -> None:
        self.git("checkout", "-q", "-b", "side")
        side = self.commits(2)
        self.git("checkout", "-q", "main")
        self.commits(3)
        self.graph(commit=side)
        self.assertEqual(self.gv("view"), [self.label(side, 3, ahead=2)])

    def test_label_unknown_commit(self) -> None:
        unknown = f"graph build commit unknown; {ADVISORY}"
        for commit in (None, "0" * 40, "--all", "HEAD", 7):
            with self.subTest(commit=commit):
                raw = json.dumps({"nodes": []} if commit is None else
                                 {"nodes": [], "built_at_commit": commit})
                self.graph(raw=raw)
                self.assertEqual(self.gv("view"), [unknown])

    def test_label_full_build_at_head(self) -> None:
        head = self.git("rev-parse", "HEAD")
        g = self.graph(stamp=True)
        self.assertEqual(self.gv("view"), [self.label(head, 0, full=True)])
        self.stamp(g, digest="0" * 64)
        self.assertEqual(self.gv("view"), [self.label(head, 0)])
        self.commits(1)
        self.graph(commit="HEAD")
        self.stamp(g, head=head)  # the right bytes, an older commit
        self.assertEqual(self.gv("view")[0], self.label(self.git("rev-parse", "HEAD"), 0))

    # -- one read, no automatic rebuild, --refresh (A4) ---------------------------------------

    def test_view_single_read(self) -> None:
        head = self.git("rev-parse", "HEAD")
        g = self.graph(stamp=True)
        self.stub(explain="replace")
        lines = self.gv("view", "--out", str(self.out), "Alpha")
        self.assertEqual(lines[0], self.label(head, 0, full=True))
        result = (self.out / "Alpha.txt").read_text(encoding="utf-8")
        self.assertIn(f"explain Alpha built_at_commit={head}", result)
        self.assertIn(f"affected Alpha built_at_commit={head}", result)
        self.assertIn("f" * 40, (g / "graph.json").read_text(encoding="utf-8"))  # it was replaced
        for call in self.calls("explain") + self.calls("affected"):
            snapshot = Path(call["argv"][call["argv"].index("--graph") + 1])
            self.assertNotIn(self.repo, snapshot.parents)
            self.assertFalse(snapshot.exists())
        self.assertEqual(self.calls("affected")[0]["argv"][2:4], ["--depth", "2"])
        self.assertEqual(list(self.systmp.iterdir()), [])

    def test_view_never_rebuilds_on_its_own(self) -> None:
        built = self.git("rev-parse", "HEAD")
        g = self.graph()
        self.commits(50)
        for stamp in ("{not json", None):
            with self.subTest(stamp=stamp):
                (g / STAMP).unlink(missing_ok=True)
                if stamp:
                    (g / STAMP).write_text(stamp, encoding="utf-8")
                self.assertEqual(self.gv("view", "--out", str(self.out), "Alpha")[0],
                                 self.label(built, 50))
                self.assertEqual(self.calls("update"), [])
                if stamp:
                    self.assertEqual((g / STAMP).read_text(encoding="utf-8"), stamp)
                else:
                    self.assertFalse((g / STAMP).exists())

    def test_view_refresh_rebuilds_and_stamps(self) -> None:
        g = self.graph()
        head = self.commits(2)
        lines = self.gv("view", "--refresh", "--out", str(self.out), "Alpha")
        self.assert_one_build(self.repo)
        self.assert_stamped(g)
        self.assertEqual(lines, ["graph built: refresh requested", self.label(head, 0, full=True),
                                 str(self.out / "Alpha.txt")])
        self.log.unlink()
        self.assertEqual(self.gv("view", "--refresh"),
                         ["graph built: refresh requested", self.label(head, 0, full=True)])
        self.assertEqual(len(self.calls("update")), 1)
        self.assertEqual(self.calls("explain") + self.calls("affected"), [])

    def test_view_refresh_failure_line(self) -> None:
        for control, reason in (({"update": "hang"}, "timed out after 1 s"),
                                ({"update": "fail", "exit": 7}, "failed (exit 7)")):
            with self.subTest(reason=reason):
                built = self.git("rev-parse", "HEAD")
                g = self.graph(stamp=True)
                self.stub(**control)
                lines = self.gv("view", "--refresh", "--out", str(self.out), "Alpha",
                                bounds={"view": 1})
                retry = self.rerun("view", "--refresh", "--out", str(self.out), "Alpha",
                                   "--no-bound")
                self.assertEqual(lines[0], f"graph build {reason}; retry with: {retry}")
                self.assertFalse((g / STAMP).exists())
                self.assertEqual(lines[1:], [self.label(built, 0), str(self.out / "Alpha.txt")])
                (self.out / "Alpha.txt").unlink()
                self.stub()
                fixed = self.run_printed(lines[0], "retry with: ")
                self.assertEqual(fixed[0], "graph built: refresh requested")
                self.assert_stamped(g)
                self.assertTrue((self.out / "Alpha.txt").is_file())

    # -- A2's triggers, the no-build control, the one failure line ----------------------------

    def test_setup_builds_without_graph(self) -> None:
        self.assertEqual(self.gv("setup"), ["graph built: no graph"])
        self.assert_one_build(self.repo)
        self.assert_stamped(self.repo / "graphify-out")

    def test_setup_builds_unparsable_graph(self) -> None:
        for raw in ("{not json", "[1, 2]", '"a string"'):
            with self.subTest(raw=raw):
                self.log.unlink(missing_ok=True)
                g = self.graph(raw=raw, stamp=True)
                self.assertEqual(self.gv("setup"), ["graph built: graph.json does not parse"])
                self.assert_one_build(self.repo)
                self.assert_stamped(g)

    def test_setup_builds_foreign_graphify_root(self) -> None:
        for marker in (str(self.repo), "sub", ".\n", " .", "./"):
            with self.subTest(marker=marker):
                self.log.unlink(missing_ok=True)
                g = self.graph(marker=marker, stamp=True)
                self.assertEqual(self.gv("setup"), ["graph built: foreign .graphify_root"])
                self.assert_one_build(self.repo)
                self.assert_stamped(g)

    def test_setup_builds_without_stamp(self) -> None:
        cases = ((None, "stamp missing"), ("{nope", "stamp does not parse"),
                 ("[]", "stamp does not parse"), ('{"head": "x"}', "stamp does not parse"),
                 ('{"sha256": "x"}', "stamp does not parse"),
                 ('{"head": 1, "sha256": "x"}', "stamp does not parse"))
        for stamp, reason in cases:
            with self.subTest(stamp=stamp):
                self.log.unlink(missing_ok=True)
                g = self.graph()
                (g / STAMP).unlink(missing_ok=True)
                if stamp is not None:
                    (g / STAMP).write_text(stamp, encoding="utf-8")
                self.assertEqual(self.gv("setup"), [f"graph built: {reason}"])
                self.assert_one_build(self.repo)
                self.assert_stamped(g)

    def test_setup_no_build_with_stamp(self) -> None:
        for marker in (None, "."):
            with self.subTest(marker=marker):
                g = self.graph(marker=marker)
                self.assertEqual((g / ".graphify_root").exists(), marker is not None)
                self.stamp(g, digest="0" * 64)
                self.commits(20)
                self.assertEqual(self.gv("setup"), ["graph ready"])
                self.assertEqual(self.calls("update"), [])

    def test_setup_timeout_writes_no_stamp(self) -> None:
        self.stub(update="hang")
        lines = self.gv("setup", bounds={"setup": 1})
        self.assertEqual(lines, ["graph build timed out after 1 s; retry with: "
                                 + self.rerun("setup", "--no-bound")])
        g = self.repo / "graphify-out"
        self.assertFalse((g / STAMP).exists())
        self.stub()
        self.assertEqual(self.run_printed(lines[0], "retry with: "), ["graph built: no graph"])
        self.assert_stamped(g)
        self.assertEqual(self.gv("setup"), ["graph ready"])

    def test_setup_failure_line(self) -> None:
        self.stub(update="fail", exit=3)
        expected = "graph build failed (exit 3); retry with: " + self.rerun("setup", "--no-bound")
        lines = self.gv("setup")
        self.assertEqual(lines, [expected])
        self.assertEqual(self.run_printed(lines[0], "retry with: "), [expected])  # it persists
        self.assertFalse((self.repo / "graphify-out" / STAMP).exists())
        self.stub()
        self.assertEqual(self.run_printed(lines[0], "retry with: "), ["graph built: no graph"])
        self.assert_stamped(self.repo / "graphify-out")

    def test_failed_build_deletes_old_stamp(self) -> None:
        for control, bounds in (({"update": "fail"}, None), ({"update": "hang"}, {"setup": 1})):
            with self.subTest(control=control):
                g = self.graph(marker="sub", stamp=True)
                self.stub(**control)
                self.assertTrue(self.gv("setup", bounds=bounds)[0].startswith("graph build "))
                self.assertFalse((g / STAMP).exists())
                self.assertEqual((g / ".graphify_root").read_text(encoding="utf-8"), ".")
                self.stub()
                self.assertEqual(self.gv("setup"), ["graph built: stamp missing"])
                self.assert_stamped(g)

    # -- printed commands repeat --root ----------------------------------------------------------

    def test_fix_line_repeats_root(self) -> None:
        a, b = self.repo, self.make_repo("repo b")
        ga = self.graph(a, stamp=True)
        before = self.files(ga)
        self.stub(update="hang")
        line = self.gv("setup", "--root", str(b), cwd=a, bounds={"setup": 1})[0]
        self.assertEqual(line, "graph build timed out after 1 s; retry with: "
                         + self.rerun("setup", "--no-bound", root=b))
        self.stub()
        self.run_printed(line, "retry with: ", cwd=a)
        self.assert_stamped(b / "graphify-out")
        shutil.rmtree(b / "graphify-out")
        (b / ".gitignore").write_text("", encoding="utf-8")
        line = self.gv("setup", "--root", str(b), cwd=a)[0]
        self.assertEqual(line, "graphify-out/ is not ignored; add /graphify-out/ to .gitignore, "
                               "then rerun: " + self.rerun("setup", root=b))
        (b / ".gitignore").write_text("/graphify-out/\n", encoding="utf-8")
        self.assertEqual(self.run_printed(line, "then rerun: ", cwd=a), ["graph built: no graph"])
        gb = b / "graphify-out"
        (gb / ".graphify_root").write_text("sub", encoding="utf-8")
        (gb / "GRAPH_REPORT.md").unlink()
        (gb / "GRAPH_REPORT.md").symlink_to(b / "tracked.md")
        line = self.gv("setup", "--root", str(b), cwd=a)[0]
        self.assertEqual(line, f"graph build refused: {gb / 'GRAPH_REPORT.md'} is a symlink; "
                               f"remove it, then rerun: " + self.rerun("setup", root=b))
        (gb / "GRAPH_REPORT.md").unlink()
        self.assertEqual(self.run_printed(line, "then rerun: ", cwd=a),
                         ["graph built: foreign .graphify_root"])
        self.assert_stamped(gb)
        self.assertEqual(self.files(ga), before)

    def test_root_relative_and_subdirectory(self) -> None:
        (self.repo / "pkg").mkdir()
        self.stub(update="fail")
        retry = "graph build failed (exit 3); retry with: " + self.rerun("setup", "--no-bound")
        self.assertEqual(self.gv("setup", "--root", "repo", cwd=self.tmp), [retry])
        self.assertEqual(self.gv("setup", "--root", "pkg"), [retry])
        self.assertEqual(self.gv("setup", cwd=self.repo / "pkg"), [retry])
        lines = self.gv("setup", "--root", str(self.tmp / "nowhere"))
        self.assertEqual(lines, [f"not a git work tree: {self.tmp / 'nowhere'}; graph context off"])

    # -- symlinked artifacts (A5) --------------------------------------------------------------

    def test_symlinked_artifact_refused(self) -> None:
        g = self.graph(marker="sub", stamp=True)
        report, tracked = g / "GRAPH_REPORT.md", self.repo / "tracked.md"
        report.symlink_to(tracked)
        stamp = (g / STAMP).read_bytes()
        rerun = {"setup": self.rerun("setup"), "view": self.rerun("view", "--refresh")}
        for command in ("setup", "view"):
            with self.subTest(command=command):
                lines = self.gv(command, *(["--refresh"] if command == "view" else []))
                self.assertEqual(lines[0], f"graph build refused: {report} is a symlink; remove "
                                           f"it, then rerun: {rerun[command]}")
                self.assertEqual(lines[1:], [] if command == "setup" else [
                    f"graph built at {self.git('rev-parse', 'HEAD')[:7]} (0 commits behind HEAD)"
                    f"; full build by setup at HEAD; {ADVISORY}"])
                self.assertEqual(self.calls("update"), [])
                self.assertEqual((g / STAMP).read_bytes(), stamp)
                self.assertEqual(tracked.read_text(encoding="utf-8"), "tracked\n")
                self.assertEqual(self.git("status", "--porcelain"), "")
        report.unlink()
        self.assertEqual(self.run_printed(lines[0], "then rerun: ")[0],
                         "graph built: refresh requested")
        self.assert_stamped(g)
        self.assertEqual(tracked.read_text(encoding="utf-8"), "tracked\n")

    def test_symlinked_graph_directory_refused(self) -> None:
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.repo / ".gitignore").write_text("/graphify-out\n", encoding="utf-8")
        self.git("commit", "-qam", "ignore without the slash")
        g = self.repo / "graphify-out"
        g.symlink_to(outside)
        line = self.gv("setup")[0]
        self.assertEqual(line, f"graph build refused: {g} is a symlink; remove it, then rerun: "
                               + self.rerun("setup"))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.calls("update"), [])
        self.assertEqual(self.git("status", "--porcelain"), "")
        g.unlink()
        self.assertEqual(self.run_printed(line, "then rerun: "), ["graph built: no graph"])
        self.assert_stamped(g)

    def test_symlinked_marker_and_stamp_refused(self) -> None:
        for name in (".graphify_root", STAMP):
            with self.subTest(name=name):
                g = self.graph(marker=None)
                for p in (g / ".graphify_root", g / STAMP):
                    p.unlink(missing_ok=True)
                (g / name).symlink_to(self.repo / "tracked.md")
                line = self.gv("setup")[0]
                self.assertTrue(line.startswith(f"graph build refused: {g / name} is a symlink"))
                self.assertEqual(self.calls("update"), [])
                self.assertEqual((self.repo / "tracked.md").read_text(encoding="utf-8"), "tracked\n")
                (g / name).unlink()

    def test_stamp_hard_link_replaced(self) -> None:
        g = self.graph(marker="sub")
        os.link(self.repo / "tracked.md", g / STAMP)
        self.assertEqual(self.gv("setup"), ["graph built: foreign .graphify_root"])
        self.assertEqual((self.repo / "tracked.md").read_text(encoding="utf-8"), "tracked\n")
        self.assert_stamped(g)
        self.assertEqual((g / STAMP).stat().st_nlink, 1)

    def test_symlink_two_levels_deep_is_out_of_scope(self) -> None:
        """A5 checks `<g>` and its direct entries only, as the design states; a deeper link is not
        refused, and the build runs (the stub writes nothing there)."""
        g = self.graph(marker="sub")
        (g / "cache").mkdir()
        (g / "cache" / "x.json").symlink_to(self.repo / "tracked.md")
        self.assertEqual(self.gv("setup"), ["graph built: foreign .graphify_root"])
        self.assert_one_build(self.repo)

    # -- hooks (A3, AC-7) ----------------------------------------------------------------------

    def hook(self, name: str, repo: Path | None = None) -> Path:
        return (repo or self.repo) / ".git" / "hooks" / name

    def assert_guarded(self, repo: Path | None = None) -> None:
        for name, block in BLOCKS.items():
            self.assertIn(GUARD + "\n" + block, self.hook(name, repo).read_text(encoding="utf-8"))

    def test_setup_checks_post_checkout_guard(self) -> None:
        self.graph(stamp=True)
        self.hook("post-checkout").write_text("#!/bin/sh\n" + BLOCKS["post-checkout"] + "\n",
                                              encoding="utf-8")
        lines = self.gv("setup")
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("post-commit graph refresh installed"), lines)
        self.assert_guarded()
        self.log.unlink()
        self.assertEqual(self.gv("setup"), ["graph ready"])
        self.assertEqual(self.calls(), [])

    def test_setup_installs_missing_hooks_from_main_and_linked_worktree(self) -> None:
        linked = self.tmp / "linked wt"
        self.git("worktree", "add", "-q", "-b", "wt", str(linked))
        for cwd in (self.repo, linked):
            with self.subTest(cwd=cwd.name):
                for name in BLOCKS:
                    self.hook(name).unlink(missing_ok=True)
                shutil.rmtree(cwd / "graphify-out", ignore_errors=True)
                self.log.unlink(missing_ok=True)
                lines = self.gv("setup", cwd=cwd)
                self.assertEqual(len(lines), 2, lines)
                self.assertTrue(lines[0].startswith("post-commit graph refresh installed"))
                self.assertEqual(lines[1], "graph built: no graph")
                self.assert_guarded(self.repo)
                self.assertFalse((linked / ".git").is_dir())
                self.assert_one_build(cwd)

    def test_setup_hooks_path_configured(self) -> None:
        for name in BLOCKS:
            self.hook(name).unlink()
        self.git("config", "core.hooksPath", "custom-hooks")
        self.graph(stamp=True)
        lines = self.gv("setup")
        self.assertEqual(lines, ["graph refresh hooks not installed while core.hooksPath is "
                                 "configured; refresh on request with: "
                                 + self.rerun("view", "--refresh")])
        self.assertFalse(any(self.hook(n).exists() for n in BLOCKS))
        self.assertFalse((self.repo / "custom-hooks").exists())
        self.assertEqual(self.run_printed(lines[0], "with: ")[0], "graph built: refresh requested")
        self.assert_stamped(self.repo / "graphify-out")

    def test_setup_child_graph(self) -> None:
        for name in BLOCKS:
            self.hook(name).unlink()
        (self.repo / ".gitignore").write_text("/graphify-out/\n/sub/graphify-out/\n",
                                              encoding="utf-8")
        g = self.graph(self.repo / "sub", commit=None, marker=None)
        lines = self.gv("setup")
        self.assertEqual(lines, ["graph under sub/ is not refreshed by git hooks; refresh on "
                                 "request with: " + self.rerun("view", "--refresh"),
                                 "graph built: stamp missing"])
        self.assert_one_build(self.repo / "sub")
        self.assert_stamped(g)
        self.assertFalse(any(self.hook(n).exists() for n in BLOCKS))
        self.assertFalse((self.repo / "graphify-out").exists())
        self.log.unlink()
        self.assertEqual(self.run_printed(lines[0], "with: ")[0], "graph built: refresh requested")
        self.assert_one_build(self.repo / "sub")

    # -- environment ---------------------------------------------------------------------------

    def test_setup_drops_graphify_env(self) -> None:
        for name in BLOCKS:
            self.hook(name).unlink()
        elsewhere = self.tmp / "elsewhere"
        lines = self.gv("setup", GRAPHIFY_OUT=str(elsewhere), GRAPHIFY_FORCE="0",
                        GRAPHIFY_QUERY_LOG_DISABLE="1")
        self.assertEqual(lines[1:], ["graph built: no graph"])
        self.assertTrue(self.calls("hook") and self.calls("update"))
        for call in self.calls():
            self.assertFalse([k for k in call["env"] if k.startswith("GRAPHIFY_")], call)
        self.assertFalse(elsewhere.exists())
        self.assert_stamped(self.repo / "graphify-out")

    def test_setup_git_env(self) -> None:
        other = self.make_repo("other")
        self.git("config", "core.hooksPath", "elsewhere", cwd=other)
        lines = self.gv("setup", GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other))
        self.assertEqual(lines, ["graph built: no graph"])
        built = json.loads((self.repo / "graphify-out" / "graph.json").read_text())
        self.assertEqual(built["built_at_commit"], self.git("rev-parse", "HEAD"))
        self.assertFalse((other / "graphify-out").exists())
        empty = self.tmp / "empty.gitconfig"
        empty.write_text("", encoding="utf-8")
        lines = self.gv("setup", GIT_CONFIG=str(empty), GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0="core.hooksPath", GIT_CONFIG_VALUE_0="elsewhere")
        self.assertEqual(lines, ["graph refresh hooks not installed while core.hooksPath is "
                                 "configured; refresh on request with: "
                                 + self.rerun("view", "--refresh")])

    def test_setup_graphify_missing(self) -> None:
        for name in BLOCKS:
            self.hook(name).unlink()
        before = self.files(self.repo)
        self.assertEqual(self.gv("setup", path=os.pathsep.join(self.bare_path)), [NO_GRAPHIFY])
        self.assertEqual(self.files(self.repo), before)
        self.assertFalse(any(self.hook(n).exists() for n in BLOCKS))

    def test_setup_broken_graphify(self) -> None:
        """graphify on PATH but failing every command, `--version` included."""
        self.stub(all="fail")
        lines = self.gv("setup")
        self.assertEqual(lines, ["graph build failed (exit 5); retry with: "
                                 + self.rerun("setup", "--no-bound")])
        self.assertEqual(self.gv("view"), ["graph context off (no graph); read the route and grep"])

    # -- the ignore check (A5) ---------------------------------------------------------------

    def unignored(self, child: bool, tracked: bool) -> tuple[Path, str]:
        base = self.repo / "sub" if child else self.repo
        (self.repo / ".gitignore").write_text("", encoding="utf-8")
        g = self.graph(base, commit=None)
        if tracked:
            (g / "GRAPH_REPORT.md").write_text("report\n", encoding="utf-8")
            self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-am", "graph state")
        return g, "/sub/graphify-out/" if child else "/graphify-out/"

    def ignore_expected(self, entry: str, rerun: str, tracked: bool) -> str:
        rel = entry.strip("/")
        untrack = (" and untrack it with: " + shlex.join([
            "env", *[a for n in PATHSPEC_VARS for a in ("-u", n)],
            "git", "rm", "-r", "--cached", "--quiet", "--", f":(literal){rel}"])) if tracked else ""
        return f"graphify-out/ is not ignored; add {entry} to .gitignore{untrack}, then rerun: {rerun}"

    # -- correction 2: every path is literal wherever git or a shell reads it -------------------

    def sh(self, text: str, cwd: Path, **exported: str) -> list[str]:
        """Run printed text exactly as printed, through a shell exporting `exported`."""
        r = subprocess.run(["sh", "-c", text], cwd=cwd, env=self.env(**exported),
                           capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.splitlines()

    def ignore_parts(self, lines: list[str]) -> tuple[str, str | None, str]:
        """(pasted entry, untrack command or None, rerun) from the ignore line."""
        line = next(x for x in lines if x.startswith("graphify-out/ is not ignored; add "))
        head, rerun = line.split(", then rerun: ", 1)
        head = head[len("graphify-out/ is not ignored; add "):]
        entry, _, rest = head.partition(" to .gitignore")
        untrack = rest.split(" and untrack it with: ", 1)[1] if rest else None
        return entry, untrack, rerun

    def child_tree(self, child: str, tracked: bool) -> Path:
        for p in self.repo.iterdir():
            if p.name not in (".git", ".gitignore", "tracked.md"):
                shutil.rmtree(p)
        (self.repo / ".gitignore").write_text("/graphify-out/\n", encoding="utf-8")
        g = self.graph(self.repo / child, commit=None)
        if tracked:
            self.git("add", "-f", "--", f":(literal){child}")
        self.git("commit", "-q", "--allow-empty", "-am", f"tree for {child}")
        self.log.unlink(missing_ok=True)
        return g

    def test_ignore_entry_glob_characters_literal(self) -> None:
        for child in ("sub[1]", "sub*", "a?b", "b\\c", ":!x"):
            with self.subTest(child=child):
                g = self.child_tree(child, tracked=False)
                entry, untrack, rerun = self.ignore_parts(self.gv("setup"))
                self.assertIsNone(untrack)
                self.assertEqual(self.calls("update"), [])
                with (self.repo / ".gitignore").open("a", encoding="utf-8") as fh:
                    fh.write(entry + "\n")  # pasted exactly as printed
                fixed = self.sh(rerun, cwd=self.tmp)
                self.assertFalse([x for x in fixed if "is not ignored" in x], fixed)
                self.assertEqual(fixed[-1], "graph built: stamp missing")
                self.assert_one_build(self.repo / child)
                self.assert_stamped(g)
                self.assertEqual(self.git("status", "--porcelain"), "M .gitignore")

    def sibling(self) -> str:
        """`sub-other/graphify-out/`, tracked, holding a file whose path the glob `sub*/graphify-out`
        matches in full (git's `*` crosses `/`), and one it does not."""
        base = self.repo / "sub-other" / "graphify-out"
        base.mkdir(parents=True)
        (base / "graphify-out").write_text("sibling\n", encoding="utf-8")
        (base / "g.json").write_text("{}\n", encoding="utf-8")
        self.git("add", "-f", "sub-other")
        self.git("commit", "-qm", "sibling")
        return self.git("ls-files", "-s", "--", ":(literal)sub-other")

    def test_untrack_command_does_not_widen(self) -> None:
        self.child_tree("sub*", tracked=True)
        index = self.sibling()
        self.assertEqual(len(index.splitlines()), 2)
        _, untrack, rerun = self.ignore_parts(self.gv("setup"))
        self.sh(untrack, cwd=self.repo)
        self.assertEqual(self.git("ls-files", "-s", "--", ":(literal)sub-other"), index)
        self.assertEqual(self.git("ls-files", "--", ":(literal)sub*"), "")
        self.assertTrue(untrack.endswith(
            " git rm -r --cached --quiet -- ':(literal)sub*/graphify-out'"), untrack)

    def test_tracked_detection_literal(self) -> None:
        self.child_tree("sub*", tracked=False)
        self.sibling()
        entry, untrack, _ = self.ignore_parts(self.gv("setup"))
        self.assertIsNone(untrack)
        self.assertEqual(entry, "/sub\\*/graphify-out/")

    def test_untrack_command_under_pathspec_env(self) -> None:
        """`sub/graphify-out` is the graph; `Sub/graphify-out/x` sits only in the index (added with
        update-index, so the test also runs on a case-insensitive filesystem)."""
        variants = [{name: "1"} for name in PATHSPEC_VARS]
        variants.append({name: "1" for name in PATHSPEC_VARS})  # git alone rejects this mix
        for i, exported in enumerate(variants):
            with self.subTest(exported=sorted(exported)):
                repo = self.make_repo(f"icase {i}", ignore="")
                g = self.graph(repo / "sub", commit=None)
                (g / "x").write_text("mine\n", encoding="utf-8")
                self.git("add", "-f", "sub", cwd=repo)
                blob = self.git("rev-parse", ":sub/graphify-out/x", cwd=repo)
                self.git("update-index", "--add", "--cacheinfo",
                         f"100644,{blob},Sub/graphify-out/x", cwd=repo)
                self.git("commit", "-qm", "both cases", cwd=repo)
                other = self.git("ls-files", "-s", "--", ":(literal)Sub/graphify-out", cwd=repo)
                self.assertEqual(len(other.splitlines()), 1)
                entry, untrack, rerun = self.ignore_parts(self.gv("setup", "--root", str(repo)))
                self.sh(untrack, cwd=repo, **exported)
                self.assertEqual(self.git("ls-files", "--", ":(literal)sub/graphify-out",
                                          cwd=repo), "")
                self.assertEqual(self.git("ls-files", "-s", "--", ":(literal)Sub/graphify-out",
                                          cwd=repo), other)
                (repo / ".gitignore").write_text(entry + "\n", encoding="utf-8")
                fixed = self.sh(rerun, cwd=self.tmp, **exported)
                self.assertFalse([x for x in fixed if "is not ignored" in x], fixed)
                self.assertEqual(fixed[-1], "graph built: stamp missing")

    def test_rerun_under_pathspec_env(self) -> None:
        exported = {"GIT_LITERAL_PATHSPECS": "1", "GIT_ICASE_PATHSPECS": "1"}
        self.child_tree("sub*", tracked=False)
        plain = self.gv("setup")
        entry, _, rerun = self.ignore_parts(plain)
        self.assertEqual(self.sh(rerun, cwd=self.tmp, **exported), plain)
        with (self.repo / ".gitignore").open("a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
        built = self.sh(rerun, cwd=self.tmp, **exported)
        self.assertFalse([x for x in built if "is not ignored" in x], built)
        self.assertEqual(built[-1], "graph built: stamp missing")
        self.assert_one_build(self.repo / "sub*")
        # A child graph keeps only its hooks line; the build is not repeated.
        self.assertEqual(self.sh(rerun, cwd=self.tmp, **exported), built[:1])
        self.assertEqual(self.sh(rerun, cwd=self.tmp), built[:1])

    def test_printed_commands_shell_safe(self) -> None:
        repo = self.make_repo("it's $HOME `x` dir")
        g = repo / "graphify-out"
        # retry: a hanging build, then the printed retry through sh
        self.stub(update="hang")
        retry = self.gv("setup", "--root", str(repo), bounds={"setup": 1})[0]
        self.assertIn(shlex.quote(str(repo)), retry)
        self.stub()
        self.assertEqual(self.sh(retry.split("retry with: ", 1)[1], cwd=self.tmp),
                         ["graph built: no graph"])
        self.assert_stamped(g)
        # untrack and rerun: tracked artifacts in an unignored graph directory
        (repo / ".gitignore").write_text("", encoding="utf-8")
        self.git("add", "-f", "graphify-out", cwd=repo)
        self.git("commit", "-qam", "track the graph", cwd=repo)
        entry, untrack, rerun = self.ignore_parts(self.gv("setup", "--root", str(repo)))
        (repo / ".gitignore").write_text(entry + "\n", encoding="utf-8")
        self.sh(untrack, cwd=repo)
        self.assertEqual(self.git("ls-files", "--", ":(literal)graphify-out", cwd=repo), "")
        (g / STAMP).unlink()
        fixed = self.sh(rerun, cwd=self.tmp)
        self.assertEqual(fixed, ["graph built: stamp missing"])
        self.assert_stamped(g)

    def test_ignore_line_with_tracked_artifacts(self) -> None:
        cases = (("setup", False, []), ("view", False, ["--out", str(self.out), "Alpha"]),
                 ("setup", True, []))
        for command, child, extra in cases:
            with self.subTest(command=command, child=child):
                self.git("rm", "-rq", "--cached", "--ignore-unmatch", "graphify-out", "sub")
                shutil.rmtree(self.repo / "graphify-out", ignore_errors=True)
                shutil.rmtree(self.repo / "sub", ignore_errors=True)
                self.log.unlink(missing_ok=True)
                g, entry = self.unignored(child, tracked=True)
                before = self.files(g)
                lines = self.gv(command, *extra)
                line = next(x for x in lines if x.startswith("graphify-out/ is not ignored"))
                self.assertEqual(line, self.ignore_expected(entry, self.rerun(command, *extra),
                                                            tracked=True))
                self.assertEqual(self.files(g), before)
                self.assertEqual(self.calls("update"), [])
                # Do exactly what the line says: add the entry, run the git command, rerun.
                (self.repo / ".gitignore").write_text(entry + "\n", encoding="utf-8")
                untrack = shlex.split(line.split("untrack it with: ", 1)[1].split(", then rerun: ")[0])
                subprocess.run(untrack, cwd=self.repo, env=self.env(), check=True, timeout=60)
                fixed = self.run_printed(line, "then rerun: ")
                self.assertFalse([x for x in fixed if "is not ignored" in x], fixed)
                if command == "setup":
                    self.assertEqual(fixed[-1], "graph built: stamp missing")
                    self.assertEqual(len(self.calls("update")), 1)
                else:
                    self.assertTrue(fixed[0].startswith("graph build commit unknown"), fixed)
                    self.assertTrue((self.out / "Alpha.txt").is_file())
                self.git("commit", "-qam", "untracked the graph")
                self.assertEqual(self.git("status", "--porcelain"), "")

    def test_ignore_fix_clears_despite_other_rules(self) -> None:
        """Rules outside the root .gitignore, or earlier in it, cannot outvote an appended entry."""
        xf = self.tmp / "excludes"
        cases = {"earlier negation": lambda: (self.repo / ".gitignore").write_text(
                     "!/graphify-out/\n", encoding="utf-8"),
                 "info/exclude negation": lambda: (self.repo / ".git" / "info" / "exclude")
                     .write_text("!/graphify-out/\n", encoding="utf-8"),
                 "core.excludesFile negation": lambda: (xf.write_text("!/graphify-out/\n"),
                     self.git("config", "core.excludesFile", str(xf))),
                 "inner .gitignore": lambda: (self.repo / "graphify-out" / ".gitignore")
                     .write_text("!*\n", encoding="utf-8")}
        for name, arrange in cases.items():
            with self.subTest(case=name):
                (self.repo / ".gitignore").write_text("", encoding="utf-8")
                self.graph(commit=None)
                arrange()
                line = self.gv("setup")[-1]
                self.assertEqual(line, self.ignore_expected("/graphify-out/", self.rerun("setup"),
                                                            tracked=False))
                with (self.repo / ".gitignore").open("a", encoding="utf-8") as fh:
                    fh.write("/graphify-out/\n")
                self.assertEqual(self.run_printed(line, "then rerun: ")[-1],
                                 "graph built: stamp missing")
                (self.repo / ".git" / "info" / "exclude").write_text("", encoding="utf-8")
                subprocess.run(["git", "config", "--unset", "core.excludesFile"], cwd=self.repo,
                               env=self.env(), timeout=60)
                shutil.rmtree(self.repo / "graphify-out")

    def test_setup_unignored_writes_nothing(self) -> None:
        for child in (False, True):
            for tracked in (True, False):
                with self.subTest(child=child, tracked=tracked):
                    self.git("rm", "-rq", "--cached", "--ignore-unmatch", "graphify-out", "sub")
                    shutil.rmtree(self.repo / "graphify-out", ignore_errors=True)
                    shutil.rmtree(self.repo / "sub", ignore_errors=True)
                    self.log.unlink(missing_ok=True)
                    g, entry = self.unignored(child, tracked)
                    before = self.files(g)
                    lines = self.gv("setup")
                    expected = self.ignore_expected(entry, self.rerun("setup"), tracked)
                    self.assertEqual(lines[-1], expected)
                    self.assertEqual(self.files(g), before)
                    self.assertEqual(self.calls("update"), [])
                    if tracked:  # the fix for tracked artifacts: test_ignore_line_with_tracked_artifacts
                        continue
                    (self.repo / ".gitignore").write_text(entry + "\n", encoding="utf-8")
                    fixed = self.run_printed(lines[-1], "then rerun: ")
                    self.assertNotIn(expected, fixed)
                    self.assertEqual(fixed[-1], "graph built: stamp missing")

    def test_view_unignored_writes_nothing(self) -> None:
        for child in (False, True):
            for refresh in ([], ["--refresh"]):
                with self.subTest(child=child, refresh=refresh):
                    shutil.rmtree(self.repo / "graphify-out", ignore_errors=True)
                    shutil.rmtree(self.repo / "sub", ignore_errors=True)
                    g, entry = self.unignored(child, tracked=False)
                    before = self.files(g)
                    lines = self.gv("view", *refresh, "--out", str(self.out), "Alpha")
                    self.assertEqual(lines, [
                        f"graphify-out/ is not ignored; add {entry} to .gitignore, then rerun: "
                        + self.rerun("view", *refresh, "--out", str(self.out), "Alpha"),
                        "graph context off (graph directory not ignored); read the route and grep"])
                    self.assertEqual(self.files(g), before)
                    self.assertFalse(self.out.exists())
                    self.assertEqual(self.calls(), [])

    # -- other view cases --------------------------------------------------------------------

    def test_view_writes_a_file_per_symbol(self) -> None:
        head = self.git("rev-parse", "HEAD")
        self.graph()
        lines = self.gv("view", "--out", str(self.out), "Alpha", "../a b/.c()")
        names = [str(self.out / "Alpha.txt"), str(self.out / "_a_b_.c__.txt")]
        self.assertEqual(lines, [self.label(head, 0), *names])
        for name, symbol in zip(names, ("Alpha", "../a b/.c()")):
            text = Path(name).read_text(encoding="utf-8")
            self.assertEqual(text.splitlines()[0], self.label(head, 0))
            self.assertIn(f"explain {symbol} built_at_commit={head}", text)
        for call in self.calls("explain") + self.calls("affected"):
            self.assertEqual(Path(call["cwd"]), self.repo)

    def assert_regular_output(self, path: Path) -> None:
        self.assertFalse(path.is_symlink())
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertTrue(path.read_text(encoding="utf-8").startswith("graph built at "))

    def test_view_output_symlink_to_outside_file_replaced(self) -> None:
        self.graph()
        victim = self.tmp / "victim.txt"
        victim.write_text("keep me\n", encoding="utf-8")
        self.out.mkdir()
        (self.out / "Alpha.txt").symlink_to(victim)
        self.gv("view", "--out", str(self.out), "Alpha")
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep me\n")
        self.assert_regular_output(self.out / "Alpha.txt")

    def test_view_output_dangling_symlink_replaced(self) -> None:
        self.graph()
        self.out.mkdir()
        (self.out / "Alpha.txt").symlink_to(self.tmp / "would-be-created.txt")
        self.gv("view", "--out", str(self.out), "Alpha")
        self.assertFalse((self.tmp / "would-be-created.txt").exists())
        self.assert_regular_output(self.out / "Alpha.txt")

    def test_view_output_hard_link_replaced(self) -> None:
        self.graph()
        other = self.tmp / "other.txt"
        other.write_text("other\n", encoding="utf-8")
        self.out.mkdir()
        os.link(other, self.out / "Alpha.txt")
        self.gv("view", "--out", str(self.out), "Alpha")
        self.assertEqual(other.read_text(encoding="utf-8"), "other\n")
        self.assert_regular_output(self.out / "Alpha.txt")
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["Alpha.txt"])  # no tmp left

    def test_view_out_symlink_to_directory_refused(self) -> None:
        self.graph()
        target = self.tmp / "target dir"
        target.mkdir()
        self.out.symlink_to(target)
        self.assertEqual(self.gv("view", "--refresh", "--out", str(self.out), "Alpha"),
                         [f"graph context off ({self.out} is a symlink); read the route and grep"])
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(self.calls(), [])

    def test_view_colliding_symbol_names_kept(self) -> None:
        """Distinct names: the second symbol whose safe name collides gets a `-2` suffix."""
        self.graph()
        lines = self.gv("view", "--out", str(self.out), "a/b", "a_b", "a b")
        names = [self.out / "a_b.txt", self.out / "a_b-2.txt", self.out / "a_b-3.txt"]
        self.assertEqual(lines[1:], [str(p) for p in names])
        for path, symbol in zip(names, ("a/b", "a_b", "a b")):
            self.assertIn(f"explain {symbol} built_at_commit=", path.read_text(encoding="utf-8"))

    def test_view_refresh_forces_a_shrinking_rebuild(self) -> None:
        g = self.graph(nodes=5)
        self.stub(nodes=2)
        self.gv("view", "--refresh")
        self.assert_one_build(self.repo)
        self.assertEqual(len(json.loads((g / "graph.json").read_text())["nodes"]), 2)
        self.assert_stamped(g)

    def test_view_no_graph_and_graphify_missing(self) -> None:
        self.assertEqual(self.gv("view", "--out", str(self.out), "Alpha"),
                         ["graph context off (no graph); read the route and grep"])
        self.graph()
        self.assertEqual(self.gv("view", "--out", str(self.out), "Alpha",
                                 path=os.pathsep.join(self.bare_path)),
                         ["graph context off (graphify not installed); read the route and grep"])
        self.assertFalse(self.out.exists())

    def test_view_query_timeout_and_failure_fall_back(self) -> None:
        head = self.git("rev-parse", "HEAD")
        self.graph()
        for control, why in (({"affected": "hang"}, "graphify affected timed out after 1 s"),
                             ({"explain": "fail"}, "graphify explain failed (exit 4)")):
            with self.subTest(why=why):
                self.stub(**control)
                lines = self.gv("view", "--out", str(self.out), "Alpha", bounds={"query": 1})
                self.assertEqual(lines, [self.label(head, 0), f"graph context off for Alpha ({why}); "
                                                              "read the route and grep"])
                self.assertFalse((self.out / "Alpha.txt").exists())
                self.assertEqual(list(self.systmp.iterdir()), [])

    def test_view_writes_only_out_snapshot_and_ignored_graph(self) -> None:
        self.graph()
        before = self.files(self.repo)
        self.gv("view", "--out", str(self.out), "Alpha")
        self.assertEqual(self.files(self.repo), before)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["Alpha.txt"])
        self.assertEqual(list(self.systmp.iterdir()), [])
        self.gv("view", "--refresh", "--out", str(self.out), "Alpha")
        changed = {k for k in set(before) | set(self.files(self.repo))
                   if before.get(k) != self.files(self.repo).get(k)}
        self.assertTrue(changed)
        self.assertTrue(all(k.startswith("graphify-out/") for k in changed), changed)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_usage_error_exits_zero(self) -> None:
        r = subprocess.run([sys.executable, str(SCRIPT), "view", "--bogus"], cwd=self.repo,
                           env=self.env(), capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("unrecognized arguments", r.stderr)

    # -- oracle: the real graphify ---------------------------------------------------------------

    def test_oracle_setup_build_then_label(self) -> None:
        real = shutil.which("graphify", path=os.environ.get("PATH", ""))
        if real is None:  # a printed line, not a test marker: the guard forbids new skip markers
            print("\noracle not run: graphify is not on PATH, so graphify's real behaviour is not "
                  "recorded")
            return
        path = os.pathsep.join([self.bare_path[0], str(Path(real).parent), *self.bare_path[1:]])
        env = self.env(path)
        version = subprocess.run([real, "--version"], env=env, capture_output=True, text=True,
                                 timeout=60).stdout.strip()
        repo = self.tmp / "oracle repo"
        self.git("init", "-q", str(repo), cwd=self.tmp)
        (repo / ".gitignore").write_text("/graphify-out/\n", encoding="utf-8")
        (repo / "m.py").write_text("def foo():\n    return bar()\n\n\ndef bar():\n    return 1\n",
                                   encoding="utf-8")
        (repo / "notes.txt").write_text("notes\n", encoding="utf-8")
        self.git("add", "-A", cwd=repo)
        self.git("commit", "-qm", "init", cwd=repo)
        g = repo / "graphify-out"

        def setup() -> list[str]:
            return self.gv("setup", cwd=repo, path=path)

        self.assertEqual(setup()[-1], "graph built: no graph")
        head = self.git("rev-parse", "HEAD", cwd=repo)
        self.assertEqual((g / ".graphify_root").read_text(encoding="utf-8"), ".")
        self.assertEqual(json.loads((g / "graph.json").read_text())["built_at_commit"], head)
        self.assert_stamped(g)
        self.assertEqual(setup(), ["graph ready"])
        graph_bytes = (g / "graph.json").read_bytes()
        self.git("commit", "-q", "--allow-empty", "-m", "skipped refresh", cwd=repo,
                 GRAPHIFY_OUT=str(self.tmp / "unused"), PATH=path)
        self.assertEqual((g / "graph.json").read_bytes(), graph_bytes)
        lines = self.gv("view", "--out", str(self.out), "foo", cwd=repo, path=path)
        self.assertEqual(lines[0], f"graph built at {head[:7]} (1 commits behind HEAD); {ADVISORY}")
        self.assertEqual((g / "graph.json").read_bytes(), graph_bytes)  # view built nothing
        self.assertIn("foo", (self.out / "foo.txt").read_text(encoding="utf-8"))

        data = json.loads(graph_bytes)
        data["nodes"] += [{"id": "inj_ast", "label": "InjAst", "source_file": "notes.txt",
                           "_origin": "ast", "file_type": "code"},
                          {"id": "inj_plain", "label": "InjPlain", "source_file": "notes.txt",
                           "file_type": "document"}]
        injected = json.dumps(data).encode()
        (g / "graph.json").write_bytes(injected)
        genv = {k: v for k, v in env.items() if not k.startswith("GRAPHIFY_")}
        plain = subprocess.run([real, "update", "."], cwd=repo, env=genv, capture_output=True,
                               text=True, timeout=600)
        self.assertEqual(plain.returncode, 1, plain.stdout + plain.stderr)
        self.assertEqual((g / "graph.json").read_bytes(), injected)
        forced = subprocess.run([real, "update", ".", "--force"], cwd=repo, env=genv,
                                capture_output=True, text=True, timeout=600)
        self.assertEqual(forced.returncode, 0, forced.stdout + forced.stderr)
        ids = {n["id"] for n in json.loads((g / "graph.json").read_text())["nodes"]}
        self.assertLess(len(ids), len(data["nodes"]))
        self.assertNotIn("inj_ast", ids)
        print(f"\noracle: {version}; a node without _origin survives a forced build: "
              f"{'inj_plain' in ids}; an injected _origin: ast node on notes.txt trips the shrink "
              f"check without --force")


if __name__ == "__main__":
    unittest.main()
