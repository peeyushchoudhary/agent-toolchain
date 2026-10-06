#!/usr/bin/env python3
"""Drive an approved goal through fresh headless chief sessions until it is done or cannot go on.

  run_goal.py --goal G --harness claude|codex [--plan PATH] [--max-sessions N] [--quota-wait HOURS]
              [--backoff SECONDS] [--poll SECONDS] [--harness-arg ARG ...]

Each iteration selects the active milestone (the first without a goal/<G>/M<n> tag), launches one
chief session with the resume prompt, and ends it when the envelope (run.session_hours) expires.
When the session's milestone gets tagged, the envelope is closed so the Stop hook lets the session
end and the next milestone starts fresh. Progress is newly completed tasks (ticked, committed and
guard-clean) or a new milestone tag. Exit codes: 0 goal done, 3 every remaining task parked or
queued, 4 stalled (two sessions without progress) or session limit, 5 quota exhausted after
backoff, 2 usage or internal error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
GOAL_PY = SCRIPTS / "goal.py"
SESSION_HOOK = SKILL.parent.parent / "hooks" / "goal-session.sh"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SKILL.parent / "agent-personas" / "scripts"))
import goal  # noqa: E402
import sync_personas  # noqa: E402
from gate import git  # noqa: E402
from review import QUOTA_RE, parse_output  # noqa: E402


def stamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(ctx, line):
    ctx.runs.mkdir(parents=True, exist_ok=True)
    with open(ctx.runs / "progress.md", "a") as fh:
        fh.write(f"{stamp()} {line}\n")
    print(f"run_goal: {line}", flush=True)


def hook_commands(ctx):
    """The Stop and SessionStart hook commands; each decision is also appended to hooks.log."""
    q, hooks_log = shlex.quote, ctx.runs / "hooks.log"
    return {"Stop": f"python3 {q(str(GOAL_PY))} stop-hook | tee -a {q(str(hooks_log))}",
            "SessionStart": f"bash {q(str(SESSION_HOOK))} | tee -a {q(str(hooks_log))}"}


def hooks_config(ctx):
    """The `hooks` block in the shape both Claude settings and Codex .codex/hooks.json read."""
    return {event: [{"hooks": [{"type": "command", "command": cmd, "timeout": 120}]}]
            for event, cmd in hook_commands(ctx).items()}


def claude_settings(ctx):
    """Write .runs/<goal>/claude-settings.json: the chief's allow rules and its two hooks."""
    meta = ctx.plan["meta"]
    allow = ["Bash(git add:*)", "Bash(git commit:*)", f"Bash(git tag goal/{ctx.goal}/:*)"]
    paths = [str(SCRIPTS / name) for name in ("goal.py", "gate.py", "review.py")]
    allow += [f"Bash(python3 {form}:*)" for p in paths for form in dict.fromkeys((p, shlex.quote(p), f'"{p}"'))]
    allow += [f"Bash({meta[k]})" for k in ("gate", "full_gate", "e2e") if meta.get(k)]
    path = ctx.runs / "claude-settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"allow": allow}, "hooks": hooks_config(ctx)}, indent=2) + "\n")
    return path


def session_command(harness, route, prompt, settings=None, network=False, extra=()):
    if harness == "claude":
        return ["claude", "-p", "--model", route["model"], "--effort", route["effort"],
                "--permission-mode", "auto", "--settings", str(settings), "--output-format", "json",
                *extra, prompt]
    net = ["-c", "sandbox_workspace_write.network_access=true"] if network else []
    return ["codex", "exec", "--approve-for-me", "-m", route["model"],
            "-c", f"model_reasoning_effort={route['effort']}", *net, "--json", *extra, prompt]


def resume_prompt(ctx, mid, harness):
    m = goal.milestone(ctx.plan, mid)
    status = subprocess.run([sys.executable, str(GOAL_PY), "--plan", ctx.plan_rel, "status"],
                            cwd=ctx.root, capture_output=True, text=True).stdout.strip()
    tail = "\n".join((goal.file_at(ctx.runs, None, "progress.md") or "").splitlines()[-15:]) or "(empty)"
    return (f"You are the chief, the root session, for goal {ctx.goal}: {ctx.plan['meta'].get('title', '')}.\n"
            f"Plan: {ctx.plan_rel}. Rules: {SKILL / 'methodology.md'}; procedure: "
            f"{SKILL / 'references' / 'run.md'}. Tools: {GOAL_PY}, {SCRIPTS / 'gate.py'}, "
            f"{SCRIPTS / 'review.py'}.\n"
            f"Active milestone: {mid} — {m['title']}. Work only on {mid}: complete its ready tasks, "
            f"then close it (receipts, evidence, cross-vendor acceptance through review.py, goal.py done) "
            f"and tag goal/{ctx.goal}/{mid}. After the tag, end your turn; the driver starts a fresh "
            f"session for the next milestone. This harness is {harness}.\n\n"
            f"goal.py status:\n{status}\n\nProgress tail:\n{tail}\n")


def score(ctx):
    """Milestone tags plus ticked tasks whose [T<n>] commits since approval are all guard-clean."""
    n = sum(ctx.tagged(m["id"]) for m in ctx.plan["milestones"])
    approved = ctx.tag("approved")
    if not goal.rev_exists(ctx.root, approved):
        return n
    try:
        plan = ctx.plan_at("HEAD")
    except goal.PlanError:
        return n
    log_lines = git(ctx.root, "log", "--format=%H %s", f"{approved}..HEAD").splitlines()
    for t in plan["tasks"].values():
        commits = [l.split()[0] for l in log_lines if re.search(rf"\[{t['id']}\]", l)]
        if t["state"] == "x" and commits and not any(
                goal.guard(ctx, t, f"{c}^", c) for c in commits):
            n += 1
    return n


def waiting(ctx, mid):
    """True when tasks remain and every one is parked, queued, or needs one that is."""
    tasks = goal.milestone(ctx.plan, mid)["tasks"]
    stuck = {t["id"] for t in tasks if t["state"] == "!"}
    stuck |= {tid for q in ctx.plan["queue"] for blocked in re.findall(r"\[blocks ([^\]]+)\]", q)
              for tid in re.findall(r"T\d+", blocked)}
    grew = True
    while grew:
        more = {t["id"] for t in ctx.plan["tasks"].values() if t["state"] != "x"
                and any(n in stuck for n in t["needs"])}
        grew, stuck = not more <= stuck, stuck | more
    remaining = [t["id"] for t in tasks if t["state"] != "x"]
    return bool(remaining) and all(t in stuck for t in remaining)


def run_session(ctx, args, mid, route, settings, hours, number):
    """Launch one chief session and supervise its envelope. Return (exit, stdout, stderr, note)."""
    network = bool((ctx.plan["meta"].get("run") or {}).get("network"))
    cmd = session_command(args.harness, route, resume_prompt(ctx, mid, args.harness), settings,
                          network, args.harness_arg)
    session_file = ctx.runs / "session.json"
    ctx.runs.mkdir(parents=True, exist_ok=True)
    started = time.time()
    session_file.write_text(json.dumps({"started_at": started, "hours": hours, "milestone": mid,
                                        "harness": args.harness, "session": number}) + "\n")
    out_dir = ctx.runs / "sessions"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path, err_path = out_dir / f"{number:03d}-{args.harness}.out", out_dir / f"{number:03d}-{args.harness}.err"
    env = {**os.environ, "GOAL_ROLE": "chief", "GOAL_HARNESS": args.harness}
    note = ""
    with open(out_path, "w") as out, open(err_path, "w") as err:
        try:
            proc = subprocess.Popen(cmd, cwd=ctx.root, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        except FileNotFoundError:
            return 127, "", f"{args.harness} CLI not found", "launch failed"
        closed = False
        while proc.poll() is None:
            time.sleep(args.poll)
            if not closed and ctx.tagged(mid):
                # The milestone is tagged: an expired envelope lets the Stop hook allow the stop.
                session_file.write_text(json.dumps({"started_at": started, "hours": 0, "milestone": mid,
                                                    "closed": "milestone tagged"}) + "\n")
                closed = True
            if time.time() > started + hours * 3600:
                note = "envelope expired; session ended"
                proc.terminate()
                try:
                    proc.wait(30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    session_file.unlink(missing_ok=True)
    return proc.returncode, out_path.read_text(errors="replace"), err_path.read_text(errors="replace"), note


def drive(args):
    root = Path(os.path.realpath(git(os.getcwd(), "rev-parse", "--show-toplevel")))
    if (root / goal.RUNTIME_PIN).exists():
        print(f"run_goal.py: {goal.MIGRATE_NOTICE}", file=sys.stderr)
        return 2
    plan = args.plan or f"docs/product/goals/{args.goal}/plan.md"
    active = goal.read_json(root / ".runs" / "active")
    if active and active.get("goal") != args.goal:
        raise goal.PlanError(f"goal {active.get('goal')} is active; stop it with 'goal.py stop' first")
    if not active:
        res = subprocess.run([sys.executable, str(GOAL_PY), "start", "--goal", args.goal, "--plan", plan],
                             cwd=root, capture_output=True, text=True)
        if res.returncode:
            raise goal.PlanError(res.stderr.strip() or res.stdout.strip())
    elif args.plan and active.get("plan") != goal.Ctx(root, root / plan).plan_rel:
        raise goal.PlanError(f"the active plan is {active.get('plan')}, not {args.plan}")
    route = sync_personas.routing(sync_personas.load("chief")[0])[args.harness]
    stalls, number = 0, 0
    while True:
        ctx = goal.find_ctx(argparse.Namespace(plan=None, goal=None), cwd=str(root))
        mid = ctx.active()
        if mid is None:
            log(ctx, f"driver: goal {ctx.goal} done, every milestone tagged")
            return 0
        if waiting(ctx, mid):
            log(ctx, f"driver: {mid} has only parked or queued tasks left; waiting for the founder")
            return 3
        if number >= args.max_sessions:
            log(ctx, f"driver: session limit {args.max_sessions} reached")
            return 4
        hours = float((ctx.plan["meta"].get("run") or {}).get("session_hours", 3))
        settings = claude_settings(ctx) if args.harness == "claude" else None
        before, delay, deadline = score(ctx), args.backoff, time.time() + args.quota_wait * 3600
        while True:
            number += 1
            code, out, err, note = run_session(ctx, args, mid, route, settings, hours, number)
            text, usage, error = parse_output(args.harness, out)
            failed = code != 0 or bool(error)
            if failed and QUOTA_RE.search(f"{error}\n{err[-2000:]}\n{text[-2000:]}") and not note:
                log(ctx, f"session {number} {args.harness} {mid}: quota exhausted · usage: {usage}")
                if time.time() + delay > deadline:
                    log(ctx, "driver: quota still exhausted after the retry window; stopping")
                    return 5
                time.sleep(delay)
                delay = min(delay * 2, 3600)
                continue
            break
        ctx = goal.find_ctx(argparse.Namespace(plan=None, goal=None), cwd=str(root))
        after = score(ctx)
        denials = ""
        if args.harness == "claude":
            try:
                denials = f" · denials {len(json.loads(out.strip().splitlines()[-1]).get('permission_denials') or [])}"
            except (ValueError, IndexError, AttributeError):
                pass
        why = note or (f"error: {(error or err.strip())[:160]}" if failed else "")
        log(ctx, f"session {number} {args.harness} {mid}: exit {code} · progress {before}→{after}"
                 f"{denials}{' · ' + why if why else ''} · usage: {usage}")
        stalls = 0 if after > before else stalls + 1
        if stalls >= 2:
            log(ctx, f"driver: STALLED — two consecutive sessions without progress on {mid}")
            return 4


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--goal", required=True)
    ap.add_argument("--harness", required=True, choices=("claude", "codex"))
    ap.add_argument("--plan")
    ap.add_argument("--max-sessions", type=int, default=40)
    ap.add_argument("--quota-wait", type=float, default=10.0, help="hours of quota retries (default 10)")
    ap.add_argument("--backoff", type=float, default=300.0, help="first quota retry delay in seconds")
    ap.add_argument("--poll", type=float, default=2.0, help="seconds between envelope checks")
    ap.add_argument("--harness-arg", action="append", default=[],
                    help="extra argument for the harness CLI (repeatable), e.g. for an isolated smoke run")
    args = ap.parse_args(argv)
    if any(a.startswith("--dangerously") for a in args.harness_arg):
        ap.error("--harness-arg may not pass a --dangerously-* flag; the launch profile is fixed")
    try:
        return drive(args)
    except (goal.PlanError, sync_personas.PersonaError, RuntimeError, OSError, ValueError) as exc:
        print(f"run_goal.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
