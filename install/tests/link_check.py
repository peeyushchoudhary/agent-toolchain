"""The docs link check run by verify.sh: `link_check.py [ROOT]` prints the bad links, exits 1 if any.

Over AGENTS.md, README.md and every tracked docs/**/*.md: each relative Markdown link outside a code
fence names an existing file. A link to decisions.md#<anchor> must resolve the way GitHub does: the
anchor equals the slug of a heading in that file (lowercased, punctuation dropped, each space a `-`,
so "D17 — x" is `d17--x`), or is a bare `dNN` with a heading that starts with `DNN`. The slug and
the code-fence rule are the skill's (scripts/docs.py), so links and `reads:` anchors resolve alike.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "execution-methodology" / "scripts"))
from docs import fenced, headings, slug  # noqa: E402


def read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def decision_anchors(path: str) -> tuple[set[str], set[str]]:
    slugs, numbers = set(), set()
    for _n, _level, text in headings(read_lines(path)):
        slugs.add(slug(text))
        n = re.match(r"D(\d+)\b", text, re.I)
        if n:
            numbers.add(n[1])
    return slugs, numbers


def check_links(root: str = ".") -> list[str]:
    tracked = subprocess.run(["git", "-C", root, "ls-files", "docs/*.md", "docs/**/*.md"],
                             capture_output=True, text=True, check=True).stdout.split()
    bad, anchors = [], {}
    for f in dict.fromkeys(["AGENTS.md", "README.md"] + tracked):
        for n, line, fence in fenced(read_lines(os.path.join(root, f))):
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
