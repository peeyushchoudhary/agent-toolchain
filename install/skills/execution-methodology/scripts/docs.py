#!/usr/bin/env python3
"""The pages under docs/: `lint [ROOT]`, `index [ROOT]`, `reads <Tn> [--goal <id>]`.

lint: every tracked docs/**/*.md but docs/README.md and docs/goals/** starts with summary (<=120
words), read-when, covers and last-verified, and the table in docs/README.md is `index`'s output.
reads: each entry of the task's reads: line as path:start-end, path, or term: <word>; the plan is
found the way goal.py finds it. Exit codes: 0 clean, 1 findings, 2 could not run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from goal import PlanError, find_ctx, git, parse_plan  # noqa: E402

KEYS = ("summary", "read-when", "covers", "last-verified")
HEADER = ["| Page | Read when |", "|---|---|"]

def slug(heading: str) -> str:
    """A GitHub heading anchor: lowercased, markup and punctuation dropped, each space a '-'."""
    text = re.sub(r"[`*_~]", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")

def fenced(lines):
    """(n, line, inside) per line, n from 1; inside is true within a ``` or ~~~ fence and on its opening line."""
    fence = None
    for n, line in enumerate(lines, 1):
        s = line.lstrip()
        fence = (None if s.startswith(fence) else fence) if fence else (s[:3] if s.startswith(("```", "~~~")) else None)
        yield n, line, bool(fence)

def headings(lines):
    """[(n, level, text)] for every Markdown heading outside a code fence."""
    return [(n, len(h.group(1)), h.group(2)) for n, line, inside in fenced(lines)
            if not inside and (h := re.match(r"(#{1,6})\s+(.*?)\s*#*$", line))]

def pages(root):
    files = git(root, "ls-files", "-z", "--", "docs/*.md").split("\0")
    return sorted(f for f in files if f.endswith(".md") and f != "docs/README.md" and not f.startswith("docs/goals/"))

def frontmatter(root, page):
    return parse_plan((Path(root) / page).read_text(encoding="utf-8"))

def index(root):
    whens = {p: frontmatter(root, p)["meta"].get("read-when") for p in pages(root)}
    return HEADER + [f"| [{p[5:]}]({p[5:]}) | {w if isinstance(w, str) else ''} |" for p, w in whens.items()]

def lint(root):
    errs = []
    for page in pages(root):
        parsed = frontmatter(root, page)  # parse_plan's errors that start "line " are the frontmatter's
        meta = parsed["meta"]
        errs += [f"{page}: frontmatter {e}" for e in parsed["errors"] if e.startswith("line ")]
        for key in KEYS:
            if meta.get(key) in (None, {}, ""):
                errs.append(f"{page}: no {key}")
            elif not isinstance(meta[key], list if key == "covers" else str):
                errs.append(f"{page}: {key} is not {'a list' if key == 'covers' else 'one line'}")
        summary, date = meta.get("summary"), meta.get("last-verified")
        if isinstance(summary, str) and len(summary.split()) > 120:
            errs.append(f"{page}: summary is {len(summary.split())} words, over 120")
        if isinstance(date, str) and date:
            try:
                dt.date.fromisoformat(date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else "not a date")
            except ValueError:
                errs.append(f"{page}: last-verified {date!r} is not a YYYY-MM-DD date")
        covers = meta["covers"] if isinstance(meta.get("covers"), list) else []
        errs += [f"{page}: covers entry {c!r} is not repository-relative" for c in covers
                 if not isinstance(c, str) or not c or c.startswith("/") or ".." in c.split("/")]
    readme = Path(root) / "docs" / "README.md"
    lines = [l.strip() for l in readme.read_text(encoding="utf-8").splitlines()] if readme.is_file() else []
    if HEADER[0] not in lines:
        return errs + [f"docs/README.md: no index table (header {HEADER[0]})"]
    start, want = lines.index(HEADER[0]), index(root)
    have = lines[start:next((k for k in range(start, len(lines)) if not lines[k].startswith("|")), len(lines))]
    if have != want:  # the table runs from its header row to the last row; prose around it is free
        errs += ([f"docs/README.md: index lacks {r}" for r in want if r not in have]
                 + [f"docs/README.md: index has extra {r}" for r in have if r not in want]
                 or ["docs/README.md: index rows out of order; print them with docs.py index"])
    return errs

def resolve(root, entry):
    """(ok, line) for one reads: entry: a term, a whole file, or a file's section by anchor."""
    path, hashed, anchor = entry.partition("#")
    target = Path(root) / path
    if not hashed and "/" not in entry and "." not in entry and not target.exists():
        return True, f"term: {entry}"
    if not (target.is_file() if hashed else target.exists()):
        return False, f"{entry}: no such file"
    if not hashed:
        return True, path
    lines = target.read_text(encoding="utf-8").splitlines()
    heads, number = headings(lines), re.fullmatch(r"d(\d+)", anchor, re.I)
    slugs, seen = [], {}
    for _n, _l, text in heads:  # GitHub suffixes a repeated slug: examples, examples-1, examples-2
        s = slug(text); slugs.append(f"{s}-{seen[s]}" if s in seen else s); seen[s] = seen.get(s, 0) + 1
    for k, (n, level, text) in enumerate(heads):  # the section ends before a heading of its level or higher
        if slugs[k] == anchor.lower() or (number and re.match(rf"D{number[1]}\b", text, re.I)):
            return True, f"{path}:{n}-{next((m - 1 for m, lv, _t in heads[k + 1:] if lv <= level), len(lines))}"
    return False, f"{entry}: no heading matches #{anchor}"

def cmd_reads(a):
    ctx = find_ctx(goal=a.goal)
    if (task := ctx.plan["tasks"].get(a.task)) is None:
        raise PlanError(f"{ctx.plan_rel} has no task {a.task}")
    results = [resolve(ctx.root, e) for e in task["reads"]]
    print("\n".join(line if ok else f"error: {line}" for ok, line in results))
    return 0 if all(ok for ok, _l in results) else 1

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="action", required=True)
    [sub.add_parser(name).add_argument("root", nargs="?", default=".") for name in ("lint", "index")]
    reads = sub.add_parser("reads")
    reads.add_argument("task")
    reads.add_argument("--goal")
    a = ap.parse_args(argv)
    try:
        if a.action != "lint":
            return cmd_reads(a) if a.action == "reads" else print("\n".join(index(a.root))) or 0
        errs = lint(a.root)
        print("".join(f"{e}\n" for e in errs) + f"docs.py lint: {f'FAIL ({len(errs)})' if errs else 'PASS'}")
        return 1 if errs else 0
    except (PlanError, RuntimeError, OSError, ValueError) as exc:
        print(f"docs.py: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
