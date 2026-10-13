#!/usr/bin/env python3
"""Run a gate command and decide PASS or FAIL from what it actually executed.

  gate.py check    --cmd CMD [--goal G] [--count none] [--junit GLOB] [--runs DIR]
  gate.py receipt  --goal G --cmd CMD [--name full_gate|e2e|proof] [--count none] [--junit GLOB] [--runs DIR]
                   [--rerun-failed SUBSET --cause TEXT]
  gate.py baseline --goal G --cmd CMD [--junit GLOB] [--runs DIR]

`check` gates a commit and writes nothing but a log, except that a failing check on a clean committed
tree rewrites a PASS receipt for (HEAD's tree, command) as FAIL, keeping the old record under
`superseded`. `receipt` needs a clean committed tree and binds its result to (tree, exact command);
it never deletes a receipt: replacing one carries its failures, or its reasons when it named no test,
in `rerun_of`, and counts the replacements in `reruns`. Exit codes: 0 PASS, 1 FAIL or refused,
2 usage/internal.

Under a goal each run appends one line to `<runs>/<goal>/checks.jsonl`, and each command's last line is
its budget line. `--runs` names the `.runs` directory (default `<root>/.runs`), so a run in a linked
worktree can record into the main checkout's. `receipt --rerun-failed` completes, once, a FAIL receipt
whose only reason is failures not in the baseline, each a timeout or resource error during recorded
load, by running SUBSET, which names every one of them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
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
PYTEST_HEADER = re.compile(r"^_{3,} (\S+) _{3,}$", re.M)
# Evidence is an exception line, the line a runner prints for what was raised: a dotted class name,
# then `: message`, ` at <place>` or the end of the line, after pytest's `E` prefix or a summary's `- `.
# Frames, source excerpts (pytest's `>` lines) and test names never count.
EXCEPTION_LINE = re.compile(r"^(?:E\s+|\s*-\s+|\s*)((?:[A-Za-z_$][\w$]*\.)*[A-Z][\w$]*)(?::\s*(.*?)|\s+at\s+\S+)?\s*$")
TIMEOUT_CLASSES = {"TimeoutExpired", "TimeoutError", "TimeoutException", "OutOfMemoryError", "MemoryError",
                   "DeadlineExceeded", "DeadlineExceededError"}
RESOURCE_MESSAGE = re.compile(r"Too many open files|Cannot allocate memory")
ASSERTION = re.compile(r"\b(?:AssertionError|AssertionFailedError|ComparisonFailure)\b|^E\s+assert\b", re.M)


def timeout_evidence(block: str) -> bool:
    """Whether a failure block raised a timeout or resource error and shows no assertion failure."""
    if ASSERTION.search(block):
        return False
    for line in block.splitlines():
        m = EXCEPTION_LINE.match(line)
        if not m:
            continue
        name, message = m.group(1).rsplit(".", 1)[-1], m.group(2) or ""
        if (name in TIMEOUT_CLASSES or (name == "Failed" and message.startswith("Timeout"))
                or (name in ("OSError", "IOError", "IOException") and RESOURCE_MESSAGE.search(message))):
            return True
    return False
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
            else:
                res.setdefault("passed", []).append(f"{case.get('classname', '')}.{case.get('name', '')}")
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


def run(root, cmd, goal, label, runs=None):
    """Run cmd under bash in root, echoing output and teeing it to a log. Return (exit, out, log, duration_s)."""
    logdir = runs_dir(root, runs) / (goal or "_check") / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
    log = logdir / f"{stamp}-{label}-{cmd_hash(cmd)[:12]}.log"
    chunks = []
    started = time.monotonic()
    with open(log, "w") as fh:
        proc = subprocess.Popen(["bash", "-c", cmd], cwd=root, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        for line in proc.stdout:
            chunks.append(line)
            fh.write(line)
            sys.stdout.write(line)
        proc.wait()
    return proc.returncode, "".join(chunks), log, round(time.monotonic() - started, 2)


def budget_line(label, duration_s) -> str:
    budget = 600 if label == "check" else 1800
    if duration_s <= budget:
        return f"budget: ok ({duration_s:.0f} s of {budget} s)"
    return f"budget: {duration_s:.0f} s over {budget} s"


def record(root, goal, label, cmd, tree, duration_s, verdict, runs=None):
    """Append one run to the goal's checks record."""
    path = runs_dir(root, runs) / goal / "checks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps({"label": label, "command": cmd, "tree": tree, "duration_s": duration_s,
                             "verdict": verdict, "finished_at": now()}) + "\n")


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


def evaluate(root, cmd, goal, count_none, junit, label, runs=None):
    """Run cmd and apply the failure rules. Return the result record (without tree fields) and the duration."""
    before = snapshot(root)
    started = dt.datetime.now().timestamp()
    started_at = now()
    code, out, log, duration = run(root, cmd, goal, label, runs)
    counts = parse_counts(out)
    # In a check, JUnit XML that Gradle restored from the build cache looks fresh but did not run.
    cached = label == "check" and GRADLE_CACHED.search(out)
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
    if gradle and label == "check" and not re.search(r"--rerun(?:-tasks)?(?![\w-])", cmd):
        reasons.append("gradle command without --rerun or --rerun-tasks may report cached results")
    elif gradle and label != "check" and "--rerun-tasks" not in cmd:
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
            "baseline_failures": known, "started_at": started_at, "finished_at": now(),
            "verdict": "FAIL" if reasons else "PASS", "reasons": reasons, "log": str(log),
            "load": [round(x, 2) for x in os.getloadavg()], "cpus": os.cpu_count()}, duration


def summary(res) -> str:
    line = (f"gate: {res['verdict']} · exit {res['exit']} · {res['executed']} run / "
            f"{res['failed']} failed / {res['skipped']} skipped")
    if res["baseline_failures"]:
        line += f" (baseline {len(res['baseline_failures'])})"
    lines = [line] + [f"  - {r}" for r in res["reasons"]]
    if res.get("partial"):
        lines.append(f"  - partial: reran {len(res['partial'].get('new_failures', []))} failed test(s) "
                     f"after a load failure; cause: {res['cause']}")
    return "\n".join(lines)


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


def cmd_check(args, root):
    goal = args.goal or active_goal(root, args.runs)
    res, duration = evaluate(root, args.cmd, goal, args.count == "none", args.junit, "check", args.runs)
    print(summary(res))
    tree = git(root, "rev-parse", "-q", "--verify", "HEAD^{tree}", check=False)
    if goal:
        record(root, goal, "check", args.cmd, tree, duration, res["verdict"], args.runs)
    if goal and res["verdict"] == "FAIL" and not dirty_paths(root):
        # The same command just failed on the very tree a PASS receipt certifies: that receipt no
        # longer describes the latest run. It is kept as evidence, under the record that supersedes it.
        path = receipt_path(root, goal, tree, args.cmd, args.runs)
        old = read_receipt(path)
        if old.get("verdict") == "PASS":
            res.update({"tree": old.get("tree"), "name": old.get("name"), "superseded": old,
                        "rerun_of": old.get("rerun_of", []), "reruns": old.get("reruns", 0)})
            write_receipt(path, res)
            print(f"receipt superseded: {path}")
    print(budget_line("check", duration))
    return 0 if res["verdict"] == "PASS" else 1


def failure_blocks(out: str) -> dict:
    """Each failed test's blocks in a log: from just after the id on the line naming it to the next such line."""
    heads = [(m.start(), m.end(), m.group(2) if m.group(2).endswith("." + m.group(1)) else f"{m.group(2)}.{m.group(1)}")
             for m in UNITTEST_ID.finditer(out)]
    heads += [(m.start(), m.end(1), m.group(1)) for m in (*PYTEST_ID.finditer(out), *PYTEST_HEADER.finditer(out))]
    heads += [(m.start(), m.end(2), f"{m.group(1)}.{m.group(2)}") for m in GRADLE_ID.finditer(out)]
    heads.sort()
    blocks = {}
    for k, (_start, body, key) in enumerate(heads):
        blocks.setdefault(key, []).append(out[body:heads[k + 1][0] if k + 1 < len(heads) else len(out)])
    return blocks


def overlapping_run(checks: Path, old: dict) -> bool:
    """Whether another run in the checks record overlaps the failed run old."""
    try:
        start, end = (dt.datetime.fromisoformat(old[k]) for k in ("started_at", "finished_at"))
        lines = checks.read_text().splitlines()
    except (OSError, KeyError, TypeError, ValueError):
        return False
    for line in lines:
        try:
            rec = json.loads(line)
            if (rec["command"], rec["tree"]) == (old.get("command"), old.get("tree")):
                continue  # the failed run's own record
            rec_end = dt.datetime.fromisoformat(rec["finished_at"])
            if rec_end - dt.timedelta(seconds=rec["duration_s"]) < end and rec_end > start:
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


def plain_command(cmd: str) -> bool:
    """Whether cmd is one plain command: no unquoted comment, chain, pipe or redirection, and no command
    substitution. Quoted text, such as a pytest id `'t.py::test_x[a#b]'`, is an argument, not syntax."""
    if "`" in cmd or "$(" in cmd or "\n" in cmd:
        return False
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split, lex.commenters = True, ""
        tokens = list(lex)
        bare = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        bare.whitespace_split = True
        uncommented = list(bare)
    except ValueError:  # an unclosed quote
        return False
    operators = [tok for tok in tokens if tok and set(tok) <= set("();<>|&")]
    return bool(tokens) and not operators and tokens == uncommented and tokens[0] not in ("echo", "printf", "true", ":")


UNITTEST_OK = re.compile(r"^(\w+) \(([^)\s]+)\)(?: .*)? \.\.\. ok$", re.M)
PYTEST_PASSED = re.compile(r"^(?:(\S+::\S+) PASSED\b|PASSED (\S+::\S+))", re.M)
GRADLE_PASSED = re.compile(r"^(\S+) > (\S+).* PASSED\s*$", re.M)


def canonical(test_id: str) -> str:
    """One spelling per test: a pytest node `tests/a.py::C::t` reads as JUnit XML names it, `tests.a.C.t`."""
    if "::" not in test_id:
        return test_id
    path, rest = test_id.split("::", 1)
    path = path[:-3] if path.endswith(".py") else path
    return path.replace("/", ".") + "." + rest.replace("::", ".")


def passed_ids(out: str, xml: dict | None) -> set:
    """The tests a run reports by name as passed: unittest -v, pytest -v or -rA, Gradle's PASSED events,
    and JUnit XML."""
    ids = [where if where.endswith("." + name) else f"{where}.{name}" for name, where in UNITTEST_OK.findall(out)]
    ids += [a or b for a, b in PYTEST_PASSED.findall(out)]
    ids += [f"{c}.{m}" for c, m in GRADLE_PASSED.findall(out)]
    ids += (xml or {}).get("passed", [])
    return {canonical(i) for i in ids}


def last_complete_run(runs: Path, cmd: str) -> dict:
    """The newest PASS receipt of cmd in any goal under runs, not itself completed by a rerun: how many
    tests a run of cmd executes when nothing stops it early."""
    found = []
    for path in runs.glob("*/receipts/*.json"):
        r = read_receipt(path)
        if r.get("command") == cmd and r.get("verdict") == "PASS" and "partial" not in r:
            found.append((str(r.get("finished_at", "")), r))
    return max(found, key=lambda x: x[0])[1] if found else {}


def rerun_refusal(old: dict, tree, cmd, subset, checks: Path) -> str:
    """Why `--rerun-failed subset` cannot complete the receipt old for (tree, cmd); empty when it can."""
    if "partial" in old or "rerun_started" in old:
        return "this receipt was already completed once with --rerun-failed; run the full receipt again"
    if not (old.get("verdict") == "FAIL" and old.get("tree") == tree and old.get("command") == cmd):
        return "--rerun-failed needs a FAIL receipt for this tree and command"
    reasons = old.get("reasons", [])
    if len(reasons) != 1 or not reasons[0].startswith("failures not in baseline: "):
        return "--rerun-failed needs a FAIL receipt whose only reason is failures not in baseline"
    if re.search(r"\bgradlew?\b", cmd) and "--continue" not in cmd:
        return "gradle command without --continue: the modules after the first failure did not run"
    complete = last_complete_run(checks.parent.parent, cmd)
    if not complete:
        return "no earlier PASS receipt of this command shows how many tests a complete run executes"
    if old.get("executed", 0) < complete.get("executed", 0):
        return (f"the failed run executed {old.get('executed', 0)} test(s), fewer than the {complete['executed']} "
                "of the last complete run: tests that did not run need the full gate")
    if not plain_command(subset):
        return ("the --rerun-failed command must be one plain test command: no comment, echo, chaining, "
                "pipe, redirection or substitution")
    try:
        blocks = failure_blocks(Path(old.get("log", "")).read_text(errors="replace"))
    except OSError:
        blocks = {}
    shorts = [f.split("::", 1)[1].replace("::", ".") for f in old.get("failures", []) if "::" in f]
    for f in old.get("new_failures", []):
        short = f.split("::", 1)[1].replace("::", ".") if "::" in f else None
        # A pytest traceback header names the test without its file: it counts only when no other failure
        # shares that name, so same-named tests in two files never lend each other evidence.
        keys = [f] + ([short] if short and shorts.count(short) == 1 else [])
        if not any(timeout_evidence(b) for k in keys for b in blocks.get(k, [])):
            return (f"{f}: not a timeout or resource error; a test that fails in the suite and passes alone "
                    "may depend on another test, so run the full gate")
    load, cpus = old.get("load") or [], old.get("cpus")
    if not (len(load) > 1 and cpus and load[1] >= cpus) and not overlapping_run(checks, old):
        return "no recorded load during the failed run"
    return ""


def refuse_receipt(root, args, why) -> int:
    """A refused receipt still leaves its line in the checks record and ends with the budget line."""
    print(f"receipt refused: {why}")
    record(root, args.goal, "receipt", args.cmd, git(root, "rev-parse", "HEAD^{tree}"), 0.0, "REFUSED", args.runs)
    print(budget_line("receipt", 0.0))
    return 1


def cmd_receipt(args, root):
    if bool(args.rerun_failed) != bool(args.cause):
        return refuse_receipt(root, args, "--rerun-failed and --cause go together")
    dirty = dirty_paths(root)
    if dirty:
        return refuse_receipt(root, args, "the working tree is not clean; commit first:\n  " + "\n  ".join(dirty[:10]))
    tree = git(root, "rev-parse", "HEAD^{tree}")
    path = receipt_path(root, args.goal, tree, args.cmd, args.runs)
    old = read_receipt(path)
    cmd = args.cmd
    if args.rerun_failed:
        why = rerun_refusal(old, tree, args.cmd, args.rerun_failed,
                            runs_dir(root, args.runs) / args.goal / "checks.jsonl")
        if why:
            return refuse_receipt(root, args, why)
        cmd = args.rerun_failed
        # The one try is spent before the subset runs, so an interrupted attempt cannot be repeated.
        write_receipt(path, {**old, "rerun_started": now()})
    res, duration = evaluate(root, cmd, args.goal, args.count == "none", args.junit, args.name, args.runs)
    if args.rerun_failed:
        # The subset proves each failure passed by naming it in its own output; naming it in the command
        # proves nothing, since a different test can share the name as a prefix.
        out = Path(res["log"]).read_text(errors="replace")
        since = dt.datetime.fromisoformat(res["started_at"]).timestamp()
        passed = passed_ids(out, parse_junit(root, args.junit, since) if args.junit else None)
        missing = [f for f in old.get("new_failures", []) if canonical(f) not in passed]
        if missing:
            res["reasons"].append("the rerun did not report " + ", ".join(missing) + " as passed; run those "
                                  "tests verbosely (unittest -v, pytest -v, Gradle testLogging events "
                                  "\"passed\") or name their JUnit XML with --junit")
            res["verdict"] = "FAIL"
    # `command` stays the full command, so the receipt path and `goal.py done` are unchanged.
    res.update({"command": args.cmd, "tree": tree, "name": args.name, **rerun_fields(old)})
    if args.rerun_failed:
        res.update({"partial": old, "rerun_command": cmd, "cause": args.cause})
    if git(root, "rev-parse", "HEAD^{tree}") != tree:
        res["reasons"].append("HEAD moved during the run")
        res["verdict"] = "FAIL"
    write_receipt(path, res)
    record(root, args.goal, "receipt", cmd, tree, duration, res["verdict"], args.runs)
    print(summary(res))
    if res["reruns"]:
        print(f"rerun: replaces {res['reruns']} earlier receipt(s); seen failing: "
              + (", ".join(res["rerun_of"]) or "none"))
    print(f"receipt: {path}")
    print(budget_line("receipt", duration))
    return 0 if res["verdict"] == "PASS" else 1


def cmd_baseline(args, root):
    if re.search(r"\bgradlew?\b", args.cmd) and "--rerun-tasks" not in args.cmd:
        print("baseline refused: gradle command without --rerun-tasks may report cached results")
        return 1
    code, out, _log, duration = run(root, args.cmd, args.goal, "baseline", args.runs)
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
    record(root, args.goal, "baseline", args.cmd, tree, duration, "RECORDED", args.runs)
    print(f"baseline: {len(failures)} failure id(s) recorded for this command in {path}")
    print(budget_line("baseline", duration))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("check", "receipt", "baseline"):
        p = sub.add_parser(name)
        p.add_argument("--cmd", required=True)
        p.add_argument("--goal", required=name != "check")
        p.add_argument("--junit", help="glob of JUnit XML files, relative to the repository root")
        p.add_argument("--runs", help="the .runs directory to use (default: <root>/.runs)")
        if name != "baseline":
            p.add_argument("--count", choices=["none"])
        if name == "receipt":
            p.add_argument("--name", default="proof", choices=["full_gate", "e2e", "proof", "gate"])
            p.add_argument("--rerun-failed", help="a command that reruns, by name, every new failure of the FAIL receipt")
            p.add_argument("--cause", help="the evidence that machine load caused the failure")
    args = ap.parse_args(argv)
    try:
        root = repo_root()
        return {"check": cmd_check, "receipt": cmd_receipt, "baseline": cmd_baseline}[args.action](args, root)
    except (RuntimeError, OSError, ET.ParseError) as exc:
        print(f"gate.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
