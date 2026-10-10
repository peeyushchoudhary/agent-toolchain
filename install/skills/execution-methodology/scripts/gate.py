#!/usr/bin/env python3
"""Run a gate command and decide PASS or FAIL from what it actually executed.

  gate.py check    --cmd CMD [--goal G] [--count none] [--junit GLOB]
  gate.py receipt  --goal G --cmd CMD [--name full_gate|e2e|proof] [--count none] [--junit GLOB]
  gate.py baseline --goal G --cmd CMD [--junit GLOB]

`check` gates a commit and writes nothing but a log; on a clean committed tree it first deletes any
receipt for (HEAD's tree, command), since it reruns that command. `receipt` needs a clean committed
tree and binds its result to (tree, exact command). Exit codes: 0 PASS, 1 FAIL or refused, 2 usage/internal.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def git(root, *args, check=True):
    """Run git in root and return stdout (stripped of the trailing newline)."""
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout.rstrip("\n")


def repo_root(cwd=None) -> Path:
    return Path(git(cwd or os.getcwd(), "rev-parse", "--show-toplevel"))


def cmd_hash(cmd: str) -> str:
    return hashlib.sha256(cmd.encode()).hexdigest()


def receipt_path(root, goal, tree, cmd) -> Path:
    return Path(root) / ".runs" / goal / "receipts" / f"{tree}-{cmd_hash(cmd)[:12]}.json"


def active_goal(root):
    try:
        return json.loads((Path(root) / ".runs" / "active").read_text())["goal"]
    except (OSError, ValueError, KeyError):
        return None


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---- counting -----------------------------------------------------------------------------

UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
UNITTEST_END = re.compile(r"^(OK|FAILED)(?: \(([^)]*)\))?\s*$", re.M)
UNITTEST_ID = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)\s]+)\)", re.M)
PYTEST_LINE = re.compile(r"^[= ]*(\d+ (?:passed|failed|errors?|skipped)\b.*|no tests ran) in [\d.]+s",
                         re.M)
PYTEST_PAIR = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)\b")
PYTEST_ID = re.compile(r"^(?:FAILED|ERROR) (\S+::\S+)", re.M)
GRADLE_LINE = re.compile(r"(\d+) tests completed, (\d+) failed(?:, (\d+) skipped)?")
GRADLE_ID = re.compile(r"^(\S+) > (\S+).* FAILED\s*$", re.M)
# Playwright's end-of-run summary: one two-space-indented line per outcome; `passed` carries the
# duration. Failed and interrupted tests are listed beneath their line, indented four spaces.
PLAYWRIGHT_LINE = re.compile(r"^  (\d+) (passed|flaky|failed|interrupted|skipped|did not run)"
                             r"(?: \([\d.]+(?:ms|s|m|h)\))?[ \t]*$", re.M)
PLAYWRIGHT_ID = re.compile(r"^    (\[[^\]\n]+\] › .+?)[ \t─]*$")
VERDICT_FAIL = re.compile(r"FAILED \(|\b[1-9]\d* failed\b|GATE DID NOT PASS|BUILD FAILED"
                          # a line-anchored FAIL verdict: `FAIL: test_x`, `verify: FAIL (1 checks)`
                          r"|^[ \t]*(?:[\w./-]+: )?FAIL(?:ED)?\b(?!:?[ \t]*0\b)", re.M)


def parse_counts(out: str) -> dict:
    """Sum executed/failed/skipped across every unittest, pytest, Playwright and Gradle summary in out."""
    executed = failed = skipped = 0
    ids = []
    rans = list(UNITTEST_RAN.finditer(out))
    for k, ran in enumerate(rans):
        end = UNITTEST_END.search(out, ran.end(), rans[k + 1].start() if k + 1 < len(rans) else len(out))
        detail = end.group(2) or "" if end else ""
        kv = dict(p.strip().split("=", 1) for p in detail.split(",") if "=" in p)
        skip = int(kv.get("skipped", 0))
        executed += int(ran.group(1)) - skip
        skipped += skip
        failed += int(kv.get("failures", 0)) + int(kv.get("errors", 0))
    for name, where in UNITTEST_ID.findall(out):
        ids.append(where if where.endswith("." + name) else f"{where}.{name}")
    for line in PYTEST_LINE.findall(out):
        for n, word in PYTEST_PAIR.findall(line):
            n = int(n)
            if word in ("passed", "xpassed", "xfailed"):
                executed += n
            elif word == "skipped":
                skipped += n
            else:
                executed += n
                failed += n
    ids += PYTEST_ID.findall(out)
    lines = out.splitlines()
    for k, line in enumerate(lines):
        m = PLAYWRIGHT_LINE.match(line)
        if not m:
            continue
        n, word = int(m.group(1)), m.group(2)
        if word in ("passed", "flaky"):
            executed += n
        elif word in ("skipped", "did not run"):
            skipped += n
        else:
            executed += n
            failed += n
            for listed in lines[k + 1:]:
                hit = PLAYWRIGHT_ID.match(listed)
                if not hit:
                    break
                ids.append(hit.group(1))
    gradle = {"executed": 0, "failed": 0, "skipped": 0}
    for done_, bad, skip in GRADLE_LINE.findall(out):
        skip = int(skip or 0)
        gradle["executed"] += int(done_) - skip
        gradle["failed"] += int(bad)
        gradle["skipped"] += skip
    ids += [f"{c}.{m}" for c, m in GRADLE_ID.findall(out)]
    return {"executed": executed, "failed": failed, "skipped": skipped,
            "failures": ids, "gradle": gradle}


def parse_junit(root, pattern, since: float) -> dict | None:
    """Count test cases in JUnit XML files under root matching pattern and modified after since."""
    files = [f for f in glob.glob(str(Path(root) / pattern), recursive=True)
             if os.path.getmtime(f) >= since]
    if not files:
        return None
    res = {"executed": 0, "failed": 0, "skipped": 0, "failures": []}
    for f in files:
        for case in ET.parse(f).getroot().iter("testcase"):
            tags = {child.tag for child in case}
            if "skipped" in tags:
                res["skipped"] += 1
                continue
            res["executed"] += 1
            if tags & {"failure", "error"}:
                res["failed"] += 1
                res["failures"].append(f"{case.get('classname', '')}.{case.get('name', '')}")
    return res


# ---- running ------------------------------------------------------------------------------

def dirty_paths(root) -> list:
    """`git status --porcelain` lines for changes outside .runs/; empty means a clean committed tree."""
    out = git(root, "status", "--porcelain", "--untracked-files=all")
    return [l for l in out.splitlines() if not l[3:].startswith(".runs/")]


def snapshot(root) -> dict:
    """HEAD plus each dirty or untracked (non-ignored) path's content hash, ignoring .runs/."""
    out = git(root, "status", "--porcelain", "--untracked-files=all", "-z")
    snap = {"\0HEAD": git(root, "rev-parse", "-q", "--verify", "HEAD", check=False)}
    for entry in filter(None, out.split("\0")):
        path = entry[3:]
        if path.startswith(".runs/"):
            continue
        try:
            snap[path] = hashlib.sha256((Path(root) / path).read_bytes()).hexdigest()
        except OSError:
            snap[path] = "missing"
    return snap


def run(root, cmd, goal, label):
    """Run cmd under bash in root, echoing output and teeing it to a log. Return (exit, out, log)."""
    logdir = Path(root) / ".runs" / (goal or "_check") / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    log = logdir / f"{stamp}-{label}-{cmd_hash(cmd)[:12]}.log"
    chunks = []
    with open(log, "w") as fh:
        proc = subprocess.Popen(["bash", "-c", cmd], cwd=root, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        for line in proc.stdout:
            chunks.append(line)
            fh.write(line)
            sys.stdout.write(line)
        proc.wait()
    return proc.returncode, "".join(chunks), log


def load_baseline(root, goal, cmd) -> dict:
    """The baseline entry recorded for this exact command: {failures, exit, ...}, or {}."""
    if not goal:
        return {}
    try:
        data = json.loads((Path(root) / ".runs" / goal / "baseline.json").read_text())
    except (OSError, ValueError):
        return {}
    entry = data.get(cmd_hash(cmd), {})
    return entry if isinstance(entry, dict) else {}


def evaluate(root, cmd, goal, count_none, junit, label):
    """Run cmd and apply the failure rules. Return the result record (without tree fields)."""
    before = snapshot(root)
    started = dt.datetime.now().timestamp()
    started_at = now()
    code, out, log = run(root, cmd, goal, label)
    counts = parse_counts(out)
    xml = parse_junit(root, junit, started) if junit else None
    src = xml or counts["gradle"]
    executed = counts["executed"] + src["executed"]
    failed = counts["failed"] + src["failed"]
    skipped = counts["skipped"] + src["skipped"]
    failures = sorted(set(counts["failures"] + (xml["failures"] if xml else [])))
    entry = load_baseline(root, goal, cmd)
    baseline = set(entry.get("failures", []))
    new = [f for f in failures if f not in baseline]
    known = [f for f in failures if f in baseline]
    reasons = []
    if re.search(r"\bgradlew?\b", cmd) and "--rerun-tasks" not in cmd:
        reasons.append("gradle command without --rerun-tasks may report cached results")
    if code != 0:
        if not failures:
            reasons.append(f"nonzero exit {code}")
        elif failed > len(failures):
            reasons.append(f"nonzero exit {code} with {failed - len(failures)} unidentified failure(s)")
        elif not new and entry.get("exit") != code:
            # Baselined failures explain a nonzero exit only when the baseline run exited the same way.
            recorded = "no recorded exit" if entry.get("exit") is None else f"exit {entry['exit']}"
            reasons.append(f"nonzero exit {code} is not explained by the baseline ({recorded})")
    elif failed or failures:
        reasons.append(f"exit 0 with {max(failed, len(failures))} counted failure(s) (exit/verdict mismatch)")
    elif VERDICT_FAIL.search(out):
        reasons.append("exit 0 but the output reports a failure (exit/verdict mismatch)")
    if executed == 0 and not count_none:
        reasons.append("zero tests executed")
    if new:
        reasons.append("failures not in baseline: " + ", ".join(new))
    after = snapshot(root)
    if after.pop("\0HEAD") != before.pop("\0HEAD"):
        reasons.append("the run changed the tree: HEAD moved (a commit, reset or checkout during the run)")
    if after != before:
        reasons.append("the run changed the working tree")
    return {"command": cmd, "exit": code, "executed": executed, "failed": failed,
            "skipped": skipped, "failures": failures, "new_failures": new,
            "baseline_failures": known, "started_at": started_at, "finished_at": now(),
            "verdict": "FAIL" if reasons else "PASS", "reasons": reasons, "log": str(log)}


def summary(res) -> str:
    line = (f"gate: {res['verdict']} · exit {res['exit']} · {res['executed']} run / "
            f"{res['failed']} failed / {res['skipped']} skipped")
    if res["baseline_failures"]:
        line += f" (baseline {len(res['baseline_failures'])})"
    return "\n".join([line] + [f"  - {r}" for r in res["reasons"]])


def cmd_check(args, root):
    goal = args.goal or active_goal(root)
    if goal and not dirty_paths(root):
        # On a clean committed tree this is a rerun of that exact command on HEAD's tree, so an
        # earlier receipt for (tree, command) no longer describes the latest run.
        receipt_path(root, goal, git(root, "rev-parse", "HEAD^{tree}"), args.cmd).unlink(missing_ok=True)
    res = evaluate(root, args.cmd, goal, args.count == "none", args.junit, "check")
    print(summary(res))
    return 0 if res["verdict"] == "PASS" else 1


def cmd_receipt(args, root):
    dirty = dirty_paths(root)
    if dirty:
        print("receipt refused: the working tree is not clean; commit first:\n  "
              + "\n  ".join(dirty[:10]))
        return 1
    tree = git(root, "rev-parse", "HEAD^{tree}")
    path = receipt_path(root, args.goal, tree, args.cmd)
    if path.exists():
        path.unlink()
    res = evaluate(root, args.cmd, args.goal, args.count == "none", args.junit, args.name)
    res.update({"tree": tree, "name": args.name})
    if git(root, "rev-parse", "HEAD^{tree}") != tree:
        res["reasons"].append("HEAD moved during the run")
        res["verdict"] = "FAIL"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, indent=2) + "\n")
    print(summary(res))
    print(f"receipt: {path}")
    return 0 if res["verdict"] == "PASS" else 1


def cmd_baseline(args, root):
    code, out, _log = run(root, args.cmd, args.goal, "baseline")
    counts = parse_counts(out)
    xml = parse_junit(root, args.junit, 0) if args.junit else None
    failures = sorted(set(counts["failures"] + (xml["failures"] if xml else [])))
    path = Path(root) / ".runs" / args.goal / "baseline.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    data[cmd_hash(args.cmd)] = {"command": args.cmd, "exit": code, "failures": failures,
                                "tree": git(root, "rev-parse", "HEAD^{tree}"), "recorded_at": now()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"baseline: {len(failures)} failure id(s) recorded for this command in {path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("check", "receipt", "baseline"):
        p = sub.add_parser(name)
        p.add_argument("--cmd", required=True)
        p.add_argument("--goal", required=name != "check")
        p.add_argument("--junit", help="glob of JUnit XML files, relative to the repository root")
        if name != "baseline":
            p.add_argument("--count", choices=["none"])
        if name == "receipt":
            p.add_argument("--name", default="proof", choices=["full_gate", "e2e", "proof", "gate"])
    args = ap.parse_args(argv)
    try:
        root = repo_root()
        return {"check": cmd_check, "receipt": cmd_receipt, "baseline": cmd_baseline}[args.action](args, root)
    except (RuntimeError, OSError, ET.ParseError) as exc:
        print(f"gate.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
