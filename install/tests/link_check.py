"""The docs link check run by verify.sh: `link_check.py [ROOT]` prints the bad links, exits 1 if any.

Over AGENTS.md, README.md and every tracked docs/**/*.md: each relative Markdown link outside a code
fence names an existing file. A link to decisions.md#<anchor> must resolve the way GitHub does: the
anchor equals the slug of a heading in that file (lowercased, punctuation dropped, each space a `-`,
so "D17 — x" is `d17--x`), or is a bare `dNN` with a heading that starts with `DNN`.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys


def read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def slug(heading: str) -> str:
    text = re.sub(r"[`*_~]", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def decision_anchors(path: str) -> tuple[set[str], set[str]]:
    slugs, numbers, fence = set(), set(), False
    for line in read_lines(path):
        if line.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"#{1,6}\s+(.*?)\s*#*$", line)
        if m:
            slugs.add(slug(m[1]))
            n = re.match(r"D(\d+)\b", m[1], re.I)
            if n:
                numbers.add(n[1])
    return slugs, numbers


def check_links(root: str = ".") -> list[str]:
    tracked = subprocess.run(["git", "-C", root, "ls-files", "docs/*.md", "docs/**/*.md"],
                             capture_output=True, text=True, check=True).stdout.split()
    bad, anchors = [], {}
    for f in dict.fromkeys(["AGENTS.md", "README.md"] + tracked):
        fence = False
        for n, line in enumerate(read_lines(os.path.join(root, f)), 1):
            if line.lstrip().startswith("```"):
                fence = not fence
            for target in ([] if fence else re.findall(r"\]\(<?([^)\s>]+)", line)):
                if re.match(r"(https?:|mailto:|#)", target):
                    continue
                path, _, anchor = target.partition("#")
                dest = os.path.normpath(os.path.join(os.path.dirname(f), path))
                if not os.path.exists(os.path.join(root, dest)):
                    bad.append(f"{f}:{n}: {target}")
                elif anchor and dest.endswith(os.path.join("docs", "decisions", "decisions.md")):
                    if dest not in anchors:
                        anchors[dest] = decision_anchors(os.path.join(root, dest))
                    slugs, numbers = anchors[dest]
                    bare = re.fullmatch(r"d(\d+)", anchor, re.I)
                    if not (anchor.lower() in slugs or (bare and bare[1] in numbers)):
                        bad.append(f"{f}:{n}: {target}")
    return bad


if __name__ == "__main__":
    problems = check_links(sys.argv[1] if len(sys.argv) > 1 else ".")
    print("\n".join(problems) or "verify: links ok")
    sys.exit(1 if problems else 0)
