#!/usr/bin/env python3
"""Run a gate command and decide PASS or FAIL from what it actually executed.

  gate.py check    (--cmd CMD | --modules a,b|all) [--goal G] [--count none] [--junit GLOB] [--runs DIR]
  gate.py receipt  --goal G (--cmd CMD | --modules a,b|all) [--name full_gate|e2e|proof] [--count none]
                   [--junit GLOB] [--runs DIR]
  gate.py baseline --goal G --cmd CMD [--junit GLOB] [--runs DIR]
  gate.py coverage --goal G [--cmd CMD] [--runs DIR]

`check` gates a commit and writes nothing but a log, except that a failing check on a clean committed
tree rewrites a PASS receipt for (HEAD's tree, command) as FAIL, keeping the old record under
`superseded`. `receipt` needs a clean committed tree and binds its result to (tree, exact command);
it never deletes a receipt: replacing one carries its failures, or its reasons when it named no test,
in `rerun_of`, and counts the replacements in `reruns`. Exit codes: 0 PASS, 1 FAIL or refused,
2 usage/internal.

`--modules` runs each named module of docs/goals/modules.json in map order, each through the same rules
(`count` from the map). Its receipts are keyed by "module:<name>\n" + test; `receipt --modules` keeps a
module's PASS on the same tree, retries a failed one once (`retry_of`), and then refuses it.

`coverage` runs nothing and writes nothing: on HEAD's clean tree it compares the test count of the PASS
receipt for `--cmd` (default: the map's `replaces`) with the summed counts of the modules' PASS receipts,
skipping count-none modules. Advisory: exit 0 when they are equal, 1 otherwise.

Under a goal each run appends one line to `<runs>/<goal>/checks.jsonl`, and each command's last line is
its budget line. Every record line and receipt carries load readings (`started_at`, `load_before`,
`load_peak`, `cpus`) as diagnostics; no rule reads them. `--runs` names the `.runs` directory
(default `<root>/.runs`), so a run in a linked worktree can record into the main checkout's.
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
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modmap  # noqa: E402


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


def runs_dir(root, runs=None) -> Path:
    return Path(runs) if runs else Path(root) / ".runs"


def receipt_path(root, goal, tree, cmd, runs=None) -> Path:
    return runs_dir(root, runs) / goal / "receipts" / f"{tree}-{cmd_hash(cmd)[:12]}.json"


def active_goal(root, runs=None):
    try:
        return json.loads((runs_dir(root, runs) / "active").read_text())["goal"]
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
GRADLE_CACHED = re.compile(r"^\d+ actionable tasks?:.*\bfrom cache\b", re.M)
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


READINGS = ("started_at", "load_before", "load_peak", "cpus")


def run(root, cmd, goal, label, runs=None, load_before=None):
    """Run cmd under bash in root, echoing output and teeing it to a log.

    Return (exit, out, log, duration_s, readings); readings are diagnostics: the load before the run
    (load_before when given) and the highest load sampled every 5 s while it ran."""
    logdir = runs_dir(root, runs) / (goal or "_check") / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    log = logdir / f"{stamp}-{label}-{cmd_hash(cmd)[:12]}.log"
    chunks = []
    if load_before is None:
        load_before = os.getloadavg()[0]
    samples = [load_before]
    done = threading.Event()

    def sample():
        while not done.wait(5):
            samples.append(os.getloadavg()[0])

    readings = {"started_at": now()}
    started = time.monotonic()
    with open(log, "w") as fh:
        proc = subprocess.Popen(["bash", "-c", cmd], cwd=root, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        for line in proc.stdout:
            chunks.append(line)
            fh.write(line)
            sys.stdout.write(line)
        proc.wait()
        done.set()
        sampler.join()
    readings.update({"load_before": round(load_before, 2), "load_peak": round(max(samples), 2),
                     "cpus": os.cpu_count()})
    return proc.returncode, "".join(chunks), log, round(time.monotonic() - started, 2), readings


def budget_line(label, duration_s) -> str:
    budget = 600 if label == "check" else 1800
    if duration_s <= budget:
        return f"budget: ok ({duration_s:.0f} s of {budget} s)"
    return f"budget: {duration_s:.0f} s over {budget} s"


def record(root, goal, label, cmd, tree, duration_s, verdict, runs=None, readings=None):
    """Append one run, with its load readings, to the goal's checks record."""
    path = runs_dir(root, runs) / goal / "checks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps({"label": label, "command": cmd, "tree": tree, "duration_s": duration_s,
                             "verdict": verdict, "finished_at": now(), **(readings or {})}) + "\n")


def load_baseline(root, goal, cmd, runs=None) -> dict:
    """The baseline entry recorded for this exact command: {failures, exit, ...}, or {}."""
    if not goal:
        return {}
    try:
        data = json.loads((runs_dir(root, runs) / goal / "baseline.json").read_text())
    except (OSError, ValueError):
        return {}
    entry = data.get(cmd_hash(cmd), {})
    return entry if isinstance(entry, dict) else {}


def evaluate(root, cmd, goal, count_none, junit, label, runs=None, load_before=None):
    """Run cmd and apply the failure rules. Return the result record (without tree fields) and the duration.

    A check or a module receipt (label "module") accepts Gradle's --rerun; other receipts need --rerun-tasks."""
    before = snapshot(root)
    started = dt.datetime.now().timestamp()
    code, out, log, duration, readings = run(root, cmd, goal, label, runs, load_before)
    counts = parse_counts(out)
    rerun_ok = label in ("check", "module")
    # Under --rerun, JUnit XML that Gradle restored from the build cache looks fresh but did not run.
    cached = rerun_ok and GRADLE_CACHED.search(out)
    xml = parse_junit(root, junit, started) if junit and not cached else None
    src = xml or counts["gradle"]
    executed = counts["executed"] + src["executed"]
    failed = counts["failed"] + src["failed"]
    skipped = counts["skipped"] + src["skipped"]
    failures = sorted(set(counts["failures"] + (xml["failures"] if xml else [])))
    entry = load_baseline(root, goal, cmd, runs)
    baseline = set(entry.get("failures", []))
    new = [f for f in failures if f not in baseline]
    known = [f for f in failures if f in baseline]
    reasons = []
    gradle = re.search(r"\bgradlew?\b", cmd)
    if gradle and rerun_ok and not re.search(r"--rerun(?:-tasks)?(?![\w-])", cmd):
        reasons.append("gradle command without --rerun or --rerun-tasks may report cached results")
    elif gradle and not rerun_ok and "--rerun-tasks" not in cmd:
        reasons.append("gradle command without --rerun-tasks may report cached results")
    if cached:
        reasons.append("test results restored from the build cache did not run; add --no-build-cache")
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
            "baseline_failures": known, **readings, "finished_at": now(),
            "verdict": "FAIL" if reasons else "PASS", "reasons": reasons, "log": str(log)}, duration


def summary(res) -> str:
    line = (f"gate: {res['verdict']} · exit {res['exit']} · {res['executed']} run / "
            f"{res['failed']} failed / {res['skipped']} skipped")
    if res["baseline_failures"]:
        line += f" (baseline {len(res['baseline_failures'])})"
    return "\n".join([line] + [f"  - {r}" for r in res["reasons"]])


def read_receipt(path: Path) -> dict:
    try:
        old = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return old if isinstance(old, dict) else {}


def write_receipt(path: Path, res: dict):
    """Replace the receipt atomically: a run killed midway leaves the old one in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(res, indent=2) + "\n")
    os.replace(tmp, path)


def rerun_fields(old: dict) -> dict:
    """The history a new receipt carries forward: what the receipt it replaces had seen fail."""
    seen = list(old.get("rerun_of", []))
    if old.get("verdict") == "FAIL":
        ids = old.get("failures", []) + old.get("new_failures", [])
        seen += ids or [f"reason: {r}" for r in old.get("reasons", [])]
    return {"rerun_of": sorted(set(seen)), "reruns": old.get("reruns", 0) + (1 if old else 0)}


def supersede(path, res):
    """A FAIL on the very tree a PASS receipt certifies: that receipt no longer describes the latest run.
    It is kept as evidence, under the record that supersedes it, with its history and any spent retry."""
    old = read_receipt(path)
    if old.get("verdict") == "PASS":
        res.update({"tree": old.get("tree"), "name": old.get("name"), "superseded": old,
                    "rerun_of": old.get("rerun_of", []), "reruns": old.get("reruns", 0)})
        res.update({k: old[k] for k in ("module", "retry_of") if k in old})
        write_receipt(path, res)
        print(f"receipt superseded: {path}")


def contradict(root, goal, tree, cmd, res, runs=None):
    """A FAIL of cmd on a clean tree supersedes every PASS on that tree that ran cmd: the command's own
    receipt and the receipt of each module whose test is cmd."""
    try:
        mods = (modmap.load(root) or {}).get("modules") or {}
    except modmap.MapError:
        mods = {}
    for key in [cmd] + [module_key(n, s) for n, s in mods.items() if s.get("test") == cmd]:
        supersede(receipt_path(root, goal, tree, key, runs), dict(res))


def cmd_check(args, root):
    if args.modules is not None:
        return check_modules(args, root)
    goal = args.goal or active_goal(root, args.runs)
    before = git(root, "rev-parse", "-q", "--verify", "HEAD^{tree}", check=False)
    res, duration = evaluate(root, args.cmd, goal, args.count == "none", args.junit, "check", args.runs)
    print(summary(res))
    tree = git(root, "rev-parse", "-q", "--verify", "HEAD^{tree}", check=False)
    if goal:
        record(root, goal, "check", args.cmd, tree, duration, res["verdict"], args.runs,
               {k: res[k] for k in READINGS})
    if goal and res["verdict"] == "FAIL" and tree == before and not dirty_paths(root):
        contradict(root, goal, tree, args.cmd, res, args.runs)
    print(budget_line("check", duration))
    return 0 if res["verdict"] == "PASS" else 1


def refused_readings(load=None) -> dict:
    load = round(os.getloadavg()[0] if load is None else load, 2)  # nothing runs, so the peak is the load before
    return {"started_at": now(), "load_before": load, "load_peak": load, "cpus": os.cpu_count()}


def refuse_receipt(root, args, why, mods=()) -> int:
    """A refused receipt still leaves its line in the checks record, one per module, and ends with the budget line."""
    print(f"receipt refused: {why}")
    tree, readings = git(root, "rev-parse", "HEAD^{tree}"), refused_readings()
    for cmd, extra in [(spec["test"], {"module": name}) for name, spec in mods] or [(args.cmd, {})]:
        record(root, args.goal, "receipt", cmd, tree, 0.0, "REFUSED", args.runs, {**readings, **extra})
    print(budget_line("receipt", 0.0))
    return 1


def cmd_receipt(args, root):
    if args.modules is not None:
        return receipt_modules(args, root)
    dirty = dirty_paths(root)
    if dirty:
        return refuse_receipt(root, args, "the working tree is not clean; commit first:\n  " + "\n  ".join(dirty[:10]))
    tree = git(root, "rev-parse", "HEAD^{tree}")
    path = receipt_path(root, args.goal, tree, args.cmd, args.runs)
    old = read_receipt(path)
    res, duration = evaluate(root, args.cmd, args.goal, args.count == "none", args.junit, args.name, args.runs)
    res.update({"tree": tree, "name": args.name, **rerun_fields(old)})
    if git(root, "rev-parse", "HEAD^{tree}") != tree:
        res["reasons"].append("HEAD moved during the run")
        res["verdict"] = "FAIL"
    write_receipt(path, res)
    if res["verdict"] == "FAIL" and git(root, "rev-parse", "HEAD^{tree}") == tree:
        contradict(root, args.goal, tree, args.cmd, res, args.runs)
    record(root, args.goal, "receipt", args.cmd, tree, duration, res["verdict"], args.runs,
           {k: res[k] for k in READINGS})
    print(summary(res))
    if res["reruns"]:
        print(f"rerun: replaces {res['reruns']} earlier receipt(s); seen failing: "
              + (", ".join(res["rerun_of"]) or "none"))
    print(f"receipt: {path}")
    print(budget_line("receipt", duration))
    return 0 if res["verdict"] == "PASS" else 1


# ---- modules ------------------------------------------------------------------------------

def named_modules(root, wanted) -> list:
    """(name, spec) for each module wanted names ("a,b" or "all"), in map order."""
    try:
        m = modmap.load(root)
    except modmap.MapError as exc:
        raise RuntimeError(f"{modmap.MAP}: {exc}") from None
    mods = (m or {}).get("modules") or {}
    names = [n.strip() for n in wanted.split(",") if n.strip()]
    for n in names or [wanted]:
        if m is None or (n != "all" and n not in mods):
            raise RuntimeError(f"no module {n} in {modmap.MAP}")
    return [(n, spec) for n, spec in mods.items() if "all" in names or n in names]


def module_key(name, spec) -> str:
    """The receipt key of a module: it matches no --cmd receipt and no other module."""
    return f"module:{name}\n{spec['test']}"


def modules_line(failed, total) -> str:
    if failed:
        return f"modules: FAIL {len(failed)} of {total} ({', '.join(failed)})"
    return f"modules: PASS {total} of {total}"


def check_modules(args, root):
    """Run every named module; a failure on a clean tree that HEAD kept during the run supersedes that
    module's PASS receipt on that tree."""
    goal = args.goal or active_goal(root, args.runs)
    mods = named_modules(root, args.modules)
    load = os.getloadavg()[0]
    failed, total = [], 0.0
    for name, spec in mods:
        before = git(root, "rev-parse", "-q", "--verify", "HEAD^{tree}", check=False)
        res, duration = evaluate(root, spec["test"], goal, spec.get("count") == "none", args.junit, "check",
                                 args.runs, load)
        total += duration
        print(f"module {name}: {summary(res)}")
        tree = git(root, "rev-parse", "-q", "--verify", "HEAD^{tree}", check=False)
        if goal:
            record(root, goal, "check", spec["test"], tree, duration, res["verdict"], args.runs,
                   {**{k: res[k] for k in READINGS}, "module": name})
        if res["verdict"] == "FAIL":
            failed.append(name)
            if goal and tree == before and not dirty_paths(root):
                contradict(root, goal, tree, spec["test"], res, args.runs)
    print(modules_line(failed, len(mods)))
    print(budget_line("check", total))
    return 1 if failed else 0


def receipt_modules(args, root):
    """Per module on HEAD's tree: keep a PASS, run when there is no receipt, retry a FAIL once, then refuse it."""
    mods = named_modules(root, args.modules)
    load = os.getloadavg()[0]
    dirty = dirty_paths(root)
    if dirty:
        return refuse_receipt(root, args, "the working tree is not clean; commit first:\n  " + "\n  ".join(dirty[:10]),
                              mods)
    tree = git(root, "rev-parse", "HEAD^{tree}")
    failed, total = [], 0.0
    for name, spec in mods:
        path = receipt_path(root, args.goal, tree, module_key(name, spec), args.runs)
        old = read_receipt(path)
        retry = old.get("verdict") == "FAIL"
        if old.get("verdict") == "PASS":
            print(f"module {name}: PASS on this tree (kept)")
            continue
        if retry and "retry_of" in old:
            print(f"module {name} failed twice on this tree; diagnose and commit a fix")
            record(root, args.goal, "receipt", spec["test"], tree, 0.0, "REFUSED", args.runs,
                   {**refused_readings(load), "module": name})
            failed.append(name)
            continue
        if retry:
            print(f"module {name}: retry after a failure on this tree")
        res, duration = evaluate(root, spec["test"], args.goal, spec.get("count") == "none", args.junit, "module",
                                 args.runs, load)
        total += duration
        res.update({"tree": tree, "name": "module", "module": name, **rerun_fields(old)})
        if retry:
            res["retry_of"] = old  # the retry is spent whatever the new verdict
        if git(root, "rev-parse", "HEAD^{tree}") != tree:
            res["reasons"].append("HEAD moved during the run")
            res["verdict"] = "FAIL"
        write_receipt(path, res)
        if res["verdict"] == "FAIL" and git(root, "rev-parse", "HEAD^{tree}") == tree:
            contradict(root, args.goal, tree, spec["test"], res, args.runs)
        record(root, args.goal, "receipt", spec["test"], tree, duration, res["verdict"], args.runs,
               {**{k: res[k] for k in READINGS}, "module": name})
        print(f"module {name}: {summary(res)}")
        if res["verdict"] == "FAIL":
            failed.append(name)
    print(modules_line(failed, len(mods)))
    print(budget_line("receipt", total))
    return 1 if failed else 0


def cmd_coverage(args, root):
    """Compare the full gate's PASS receipt count with the modules' PASS receipt counts on HEAD's tree."""
    try:
        cmd = args.cmd or (modmap.load(root) or {}).get("replaces")
    except modmap.MapError as exc:
        raise RuntimeError(f"{modmap.MAP}: {exc}") from None
    if not cmd:
        raise RuntimeError(f"coverage needs --cmd or a replaces command in {modmap.MAP}")
    mods = named_modules(root, "all")
    dirty = dirty_paths(root)
    if dirty:
        print("coverage refused: the working tree is not clean; commit first:\n  " + "\n  ".join(dirty[:10]))
        return 1
    tree = git(root, "rev-parse", "HEAD^{tree}")
    full = read_receipt(receipt_path(root, args.goal, tree, cmd, args.runs))
    if full.get("verdict") != "PASS":
        print(f"coverage: no PASS receipt for {cmd} on tree {tree}")
        return 1
    total, missing = 0, []
    for name, spec in mods:
        if spec.get("count") == "none":
            continue
        res = read_receipt(receipt_path(root, args.goal, tree, module_key(name, spec), args.runs))
        if res.get("verdict") == "PASS":
            total += res.get("executed", 0)
        else:
            missing.append(name)
    n = full.get("executed", 0)
    if n == total and not missing:
        print(f"coverage: {n} = {total}")
        return 0
    print(f"coverage: full {n}, modules {total}" + (f"; {', '.join(missing)} missing" if missing else ""))
    return 1


def cmd_baseline(args, root):
    if re.search(r"\bgradlew?\b", args.cmd) and "--rerun-tasks" not in args.cmd:
        print("baseline refused: gradle command without --rerun-tasks may report cached results")
        return 1
    code, out, _log, duration, readings = run(root, args.cmd, args.goal, "baseline", args.runs)
    counts = parse_counts(out)
    xml = parse_junit(root, args.junit, 0) if args.junit else None
    failures = sorted(set(counts["failures"] + (xml["failures"] if xml else [])))
    tree = git(root, "rev-parse", "HEAD^{tree}")
    path = runs_dir(root, args.runs) / args.goal / "baseline.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    data[cmd_hash(args.cmd)] = {"command": args.cmd, "exit": code, "failures": failures,
                                "tree": tree, "recorded_at": now()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    record(root, args.goal, "baseline", args.cmd, tree, duration, "RECORDED", args.runs, readings)
    print(f"baseline: {len(failures)} failure id(s) recorded for this command in {path}")
    print(budget_line("baseline", duration))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("check", "receipt", "baseline"):
        p = sub.add_parser(name)
        if name == "baseline":
            p.add_argument("--cmd", required=True)
        else:
            which = p.add_mutually_exclusive_group(required=True)
            which.add_argument("--cmd")
            which.add_argument("--modules", help="a,b or all: the modules of docs/goals/modules.json to run")
        p.add_argument("--goal", required=name != "check")
        p.add_argument("--junit", help="glob of JUnit XML files, relative to the repository root")
        p.add_argument("--runs", help="the .runs directory to use (default: <root>/.runs)")
        if name != "baseline":
            p.add_argument("--count", choices=["none"])
        if name == "receipt":
            p.add_argument("--name", default="proof", choices=["full_gate", "e2e", "proof", "gate"])
    p = sub.add_parser("coverage")
    p.add_argument("--goal", required=True)
    p.add_argument("--cmd", help="the full gate command (default: the map's replaces)")
    p.add_argument("--runs", help="the .runs directory to use (default: <root>/.runs)")
    args = ap.parse_args(argv)
    if (getattr(args, "cmd", None) or "").startswith("module:"):
        print("gate.py: a --cmd may not start with 'module:', the prefix of module receipt keys", file=sys.stderr)
        return 2
    try:
        root = repo_root()
        return {"check": cmd_check, "receipt": cmd_receipt, "baseline": cmd_baseline,
                "coverage": cmd_coverage}[args.action](args, root)
    except (RuntimeError, OSError, ET.ParseError) as exc:
        print(f"gate.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
