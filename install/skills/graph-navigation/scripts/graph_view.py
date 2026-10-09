#!/usr/bin/env python3
"""Graph setup and bounded graph views for goal runs.

  graph_view.py setup [--root <worktree>] [--no-bound]
  graph_view.py view  [--root <worktree>] [--refresh [--no-bound]] [--out <dir> <Symbol> ...]

The graph is advisory context. Nothing printed here claims it is complete or current: graphify's
post-commit hook re-extracts only HEAD~1..HEAD, so one skipped refresh leaves a gap no later state
reveals. `setup` installs the guarded refresh hooks (through `install_hooks.py --graph-only`),
checks that graphify-out/ is ignored, and runs a full forced build only when there is no graph,
graph.json does not parse, .graphify_root is neither absent nor `.`, or no parsing stamp of its own
last full build exists. `view` labels the graph with its build commit and distance from HEAD, and
rebuilds only on --refresh.

Every graphify call runs with its cwd at the graph root, `.` as its path and no inherited
GRAPHIFY_* variable. Every git query drops the repository-location variables and GIT_CONFIG and
keeps git's other config variables. Both commands exit 0 in every case: the fallback is the route
and grep. Design: docs/architecture/graph-context.md (Interfaces, A1-A6).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve()
INSTALL_HOOKS = SCRIPT.parents[2] / "progressive-disclosure" / "scripts" / "install_hooks.py"
OUT, STAMP = "graphify-out", ".graph_view_complete"
BOUNDS = {"setup": 600, "view": 120, "query": 60, "hooks": 120, "git": 5}  # seconds
REPO_LOCATION_ENV = {
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_PREFIX"}
PATHSPEC_ENV = {"GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS",
                "GIT_ICASE_PATHSPECS"}
HOOK_STARTS = {"post-commit": "# graphify-hook-start",
               "post-checkout": "# graphify-checkout-hook-start"}
GUARD_BEGIN, GUARD_END = "# graph-guard-start", "# graph-guard-end"
COMMIT_ID = re.compile(r"[0-9a-f]{4,64}")
ADVISORY = "advisory — confirm with grep"
NO_GRAPHIFY = "graphify not installed; graph context off (install with: uv tool install graphifyy)"


def run(cmd: list[str], cwd: Path, env: dict, bound: float | None,
        stderr=subprocess.DEVNULL) -> tuple[int | None, str]:
    """(exit code, stdout); None on timeout. A timeout kills the whole process group, so a
    graphify child cannot outlive the bound or hold the pipe open."""
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=stderr, text=True,
                                errors="replace", start_new_session=True)
    except OSError:
        return 127, ""
    try:
        out, _ = proc.communicate(timeout=bound)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.communicate()
        return None, ""


def git_env() -> dict:
    """Also drops the pathspec-mode variables, so `:(literal)` means literal in every query."""
    return {k: v for k, v in os.environ.items()
            if k not in REPO_LOCATION_ENV | PATHSPEC_ENV | {"GIT_CONFIG"}}


def graphify_env() -> dict:
    """The git environment without any GRAPHIFY_* variable: graphify then writes only the
    default graphify-out/ under its cwd, and records its HEAD from this repository."""
    return {k: v for k, v in git_env().items() if not k.startswith("GRAPHIFY_")}


def git(root: Path, *args: str) -> tuple[int | None, str]:
    rc, out = run(["git", *args], root, git_env(), BOUNDS["git"])
    return rc, out.strip()


def read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def as_graph(data: bytes | None) -> dict | None:
    """A graph is a JSON object; valid JSON of any other shape does not parse as one."""
    try:
        graph = json.loads(data)
    except (TypeError, ValueError):
        return None
    return graph if isinstance(graph, dict) else None


def graph_root(root: Path) -> Path:
    """Where a parsing graphify-out/graph.json is: the worktree root, else one child, else the
    root. install_hooks.graphify_root's rule, duplicated so this skill stands alone."""
    if as_graph(read_bytes(root / OUT / "graph.json")) is not None:
        return root
    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
            continue
        if as_graph(read_bytes(child / OUT / "graph.json")) is not None:
            return child
    return root


def head(root: Path) -> str | None:
    rc, out = git(root, "rev-parse", "--verify", "-q", "HEAD")
    return out if rc == 0 and out else None


def read_stamp(g: Path) -> dict | None:
    """The stamp parses only as an object with string `head` and `sha256`."""
    try:
        stamp = json.loads((g / STAMP).read_bytes())
    except (OSError, ValueError):
        return None
    ok = isinstance(stamp, dict) and all(isinstance(stamp.get(k), str) for k in ("head", "sha256"))
    return stamp if ok else None


def write_new(target: Path, text: str) -> None:
    """Every file graph_view.py writes: a new file beside `target` (mkstemp opens it O_EXCL),
    renamed over it, so a symlink or hard link already at `target` is replaced, never written
    through."""
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_stamp(g: Path, head_id: str, digest: str) -> None:
    write_new(g / STAMP, json.dumps({"head": head_id, "sha256": digest}))


def rerun(args, root: Path, *, no_bound: bool) -> str:
    """The invocation itself: absolute script and root, the same subcommand and arguments."""
    cmd = ["python3", str(SCRIPT), args.command, "--root", str(root)]
    if args.command == "view":
        cmd += ["--refresh"] if args.refresh else []
        cmd += ["--out", str(args.out_dir), *args.symbols] if args.out_dir else []
    return shlex.join(cmd + (["--no-bound"] if no_bound else []))


def ignore_line(args, root: Path, groot: Path) -> str | None:
    """None when git reports the graph directory ignored (A5), else the line naming the fix.
    A symlinked graphify-out is queried without the slash, which git refuses beyond a symlink.
    git never reports a directory holding tracked files as ignored, so the fix then also
    untracks them (run from the worktree root). Every path is literal: check-ignore matches its
    paths literally but parses a leading `:` as pathspec magic (and refuses `:(literal)`), so it
    gets `./<rel>`; tracked files are matched with `:(literal)`; the printed entry escapes
    gitignore's pattern characters; every printed command is shell-quoted."""
    g = groot / OUT
    rel = g.relative_to(root).as_posix()
    rc, _ = git(root, "check-ignore", "-q", "--", f"./{rel}" if g.is_symlink() else f"./{rel}/")
    if rc == 0:
        return None
    spec = f":(literal){rel}"
    rc, tracked = git(root, "ls-files", "--", spec)
    # The reader's shell may export pathspec-mode variables; the command clears them itself.
    clear = [arg for name in sorted(PATHSPEC_ENV) for arg in ("-u", name)]
    command = ["env", *clear, "git", "rm", "-r", "--cached", "--quiet", "--", spec]
    untrack = f" and untrack it with: {shlex.join(command)}" if rc == 0 and tracked else ""
    entry = "/" + re.sub(r"([\\*?\[])", r"\\\1", rel) + "/"  # starts and ends with `/`, so a
    # leading `!` or `#` and trailing spaces cannot occur
    return (f"graphify-out/ is not ignored; add {entry} to .gitignore{untrack}, then rerun: "
            f"{rerun(args, root, no_bound=args.no_bound)}")


def symlink_line(args, root: Path, g: Path) -> str | None:
    """A5: graphify writes through symlinks, so `<g>` and each entry directly in it are checked
    once, before a build. Deeper entries and symlinks made during the build are not defended."""
    entries = [g] if g.is_symlink() or not g.is_dir() else [g, *sorted(g.iterdir())]
    link = next((p for p in entries if p.is_symlink()), None)
    if link is None:
        return None
    return (f"graph build refused: {link} is a symlink; remove it, then rerun: "
            f"{rerun(args, root, no_bound=args.no_bound)}")


def build_reason(g: Path) -> str | None:
    """A2's four build conditions, or None: otherwise nothing builds, however far behind HEAD."""
    if not (g / "graph.json").exists():
        return "no graph"
    if as_graph(read_bytes(g / "graph.json")) is None:
        return "graph.json does not parse"
    marker = g / ".graphify_root"
    if marker.exists() or marker.is_symlink():
        try:
            if marker.read_text(encoding="utf-8") != ".":
                return "foreign .graphify_root"
        except (OSError, ValueError):
            return "foreign .graphify_root"
    if read_stamp(g) is None:
        return "stamp missing" if not (g / STAMP).exists() else "stamp does not parse"
    return None


def build(args, root: Path, groot: Path, bound_key: str) -> bool:
    """Delete the stamp, run the full forced build from the graph root, and stamp only an exit 0
    within the bound. Any other outcome prints the one failure line and leaves no stamp."""
    g = groot / OUT
    try:
        (g / STAMP).unlink()
    except FileNotFoundError:
        pass
    bound = None if args.no_bound else BOUNDS[bound_key]
    rc, _ = run(["graphify", "update", ".", "--force"], groot, graphify_env(), bound,
                stderr=subprocess.STDOUT)
    data = read_bytes(g / "graph.json") if rc == 0 else None
    if data is not None:
        write_stamp(g, head(root) or "", hashlib.sha256(data).hexdigest())
        return True
    reason = f"timed out after {bound} s" if rc is None else f"failed (exit {rc})"
    print(f"graph build {reason}; retry with: {rerun(args, root, no_bound=True)}")
    return False


def hooks_guarded(root: Path) -> bool:
    """Both hooks carry our guard immediately before graphify's block (AC-7)."""
    rc, hooks = git(root, "rev-parse", "--git-path", "hooks")
    for name, start in HOOK_STARTS.items():
        try:
            text = (root / hooks / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        before = text[:text.find(start)] if start in text else ""
        guard = before.rfind(GUARD_BEGIN)
        if guard < 0 or not before.endswith(GUARD_END + "\n") or before.count(GUARD_END, guard) != 1:
            return False
    return rc == 0


def install_hooks(root: Path) -> str:
    """`install_hooks.py --graph-only` on the main checkout, bounded; its result line."""
    _, dirs = git(root, "rev-parse", "--git-dir", "--git-common-dir")
    git_dir, common = ([(root / d).resolve() for d in dirs.splitlines()] + [None, None])[:2]
    main = root if common is None or git_dir == common else common.parent
    if not INSTALL_HOOKS.is_file():
        return f"graph refresh hooks not installed: {INSTALL_HOOKS} is missing"
    rc, out = run([sys.executable, str(INSTALL_HOOKS), str(main), "--graph-only"], main,
                  graphify_env(), BOUNDS["hooks"], stderr=subprocess.STDOUT)
    if rc is None:
        return f"graph refresh hooks not installed: install_hooks.py timed out after {BOUNDS['hooks']} s"
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return next((line for line in lines if "graph refresh" in line),
                lines[-1] if lines else f"install_hooks.py exited {rc}")


def setup(args, root: Path) -> None:
    if shutil.which("graphify") is None:
        print(NO_GRAPHIFY)
        return
    said = []
    say = lambda line: (print(line), said.append(line))  # noqa: E731
    groot = graph_root(root)
    refresh = shlex.join(["python3", str(SCRIPT), "view", "--root", str(root), "--refresh"])
    if git(root, "config", "--get", "core.hooksPath")[0] != 1:
        say("graph refresh hooks not installed while core.hooksPath is configured; "
            f"refresh on request with: {refresh}")
    elif groot != root:
        say(f"graph under {groot.relative_to(root).as_posix()}/ is not refreshed by git hooks; "
            f"refresh on request with: {refresh}")
    elif not hooks_guarded(root):
        say(install_hooks(root))
    if line := ignore_line(args, root, groot):
        return say(line)
    g = groot / OUT
    if reason := build_reason(g):
        if line := symlink_line(args, root, g):
            return say(line)
        said.append("build")
        if build(args, root, groot, "setup"):
            print(f"graph built: {reason}")
    if not said:
        print("graph ready")


def label(root: Path, g: Path, graph: dict, data: bytes) -> str:
    built = graph.get("built_at_commit")
    counts = None
    if isinstance(built, str) and COMMIT_ID.fullmatch(built):
        rc, out = git(root, "rev-list", "--left-right", "--count", f"{built}...HEAD")
        counts = out.split() if rc == 0 and len(out.split()) == 2 else None
    if counts is None:
        text = "graph build commit unknown"
    else:
        ahead, behind = counts
        text = (f"graph built at {built[:7]} ({behind} commits behind HEAD"
                f"{'' if ahead == '0' else f', {ahead} ahead'})")
    stamp, now = read_stamp(g), head(root)
    if stamp and now and stamp["head"] == now and stamp["sha256"] == hashlib.sha256(data).hexdigest():
        text += "; full build by setup at HEAD"
    return f"{text}; {ADVISORY}"


def safe_name(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", symbol).lstrip(".") or "symbol"


def view(args, root: Path) -> None:
    """`--out` itself must not be a symlink, and each output replaces whatever link is at its
    path (`write_new`); the directories above `--out` are the caller's."""
    if args.out_dir and args.out_dir.is_symlink():
        print(f"graph context off ({args.out_dir} is a symlink); read the route and grep")
        return
    if shutil.which("graphify") is None:
        print("graph context off (graphify not installed); read the route and grep")
        return
    groot = graph_root(root)
    g = groot / OUT
    if line := ignore_line(args, root, groot):
        print(line)
        print("graph context off (graph directory not ignored); read the route and grep")
        return
    if args.refresh:
        if line := symlink_line(args, root, g):
            print(line)
        elif build(args, root, groot, "view"):
            print("graph built: refresh requested")
    data = read_bytes(g / "graph.json")  # the one read: label, stamp check and results (A4)
    graph = as_graph(data)
    if graph is None:
        print("graph context off (no graph); read the route and grep")
        return
    text = label(root, g, graph, data)
    print(text)
    if not args.symbols:
        return
    snapshot = Path(tempfile.mkdtemp(prefix="graph-view-"))
    try:
        (snapshot / "graph.json").write_bytes(data)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        used: set[str] = set()
        for symbol in args.symbols:
            results, why = [], None
            for query in (["explain", symbol], ["affected", symbol, "--depth", "2"]):
                rc, out = run(["graphify", *query, "--graph", str(snapshot / "graph.json")],
                              groot, graphify_env(), BOUNDS["query"])
                if rc != 0:
                    why = (f"graphify {query[0]} timed out after {BOUNDS['query']} s"
                           if rc is None else f"graphify {query[0]} failed (exit {rc})")
                    break
                results.append(out.rstrip("\n"))
            if why:
                print(f"graph context off for {symbol} ({why}); read the route and grep")
                continue
            name, n = safe_name(symbol), 1
            while f"{name}.txt" in used:  # colliding safe names keep both results
                n += 1
                name = f"{safe_name(symbol)}-{n}"
            used.add(f"{name}.txt")
            path = args.out_dir / f"{name}.txt"
            write_new(path, "\n\n".join([text, *results]) + "\n")
            print(path)
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("setup", "view"):
        p = sub.add_parser(name)
        p.add_argument("--root", help="worktree (default: the git top level of the cwd)")
        p.add_argument("--no-bound", action="store_true", help="lift the build's time bound")
        if name == "view":
            p.add_argument("--refresh", action="store_true", help="run the full forced build first")
            p.add_argument("--out", nargs="+", metavar="DIR SYMBOL", help="<dir> <Symbol> ...")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 0  # usage errors are on stderr; exit 0 in every case
    out = getattr(args, "out", None) or []
    args.out_dir = Path(os.path.abspath(out[0])) if out else None
    args.symbols, args.refresh = out[1:], getattr(args, "refresh", False)
    start = Path(os.path.abspath(args.root or "."))
    try:
        rc, top = run(["git", "rev-parse", "--show-toplevel"], start, git_env(), BOUNDS["git"])
        if rc != 0 or not top.strip():
            print(f"not a git work tree: {start}; graph context off")
            return 0
        (setup if args.command == "setup" else view)(args, Path(top.strip()).resolve())
    except Exception as exc:  # noqa: BLE001 — the route is the fallback; never fail the caller
        print(f"graph context off ({args.command} stopped: {type(exc).__name__}: {exc}); "
              "read the route and grep")
    return 0


if __name__ == "__main__":
    sys.exit(main())
