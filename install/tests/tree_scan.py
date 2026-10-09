"""Stage everything a commit of REPO could carry into a scratch repository at DEST.

    tree_scan.py REPO DEST

Tracked files and untracked non-ignored files are copied; a symlink is recreated as a symlink, so
git stores its link text, which is what a commit publishes. `git add -A -f` stages them all, so an
ignore rule copied with the tree cannot drop a file that was already tracked. The origin URL is
carried over for the guard's account rule. The caller then runs `guard.py --staged` inside DEST.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def stage_tree(repo: str, dest: str) -> None:
    out = subprocess.run(["git", "-C", repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         capture_output=True, check=True).stdout
    os.makedirs(dest, exist_ok=True)
    for raw in filter(None, out.split(b"\0")):
        rel = os.fsdecode(raw)
        src, dst = os.path.join(repo, rel), os.path.join(dest, rel)
        if os.path.islink(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(os.readlink(src), dst)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    subprocess.run(["git", "-C", dest, "init", "-q"], check=True)
    subprocess.run(["git", "-C", dest, "add", "-A", "-f"], check=True)
    origin = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"], capture_output=True, text=True)
    if origin.returncode == 0:
        subprocess.run(["git", "-C", dest, "remote", "add", "origin", origin.stdout.strip()], check=True)


if __name__ == "__main__":
    stage_tree(sys.argv[1], sys.argv[2])
