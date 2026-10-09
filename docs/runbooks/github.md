---
summary: GitHub as storage only: private repositories, everything but code and history switched off, one pull request per milestone merged with a merge commit and then tagged. The guard hooks `git-hooks.sh` installs in each clone, what they block at commit and at push, the one override for a deliberate direct push, and why this repository is public by exception.
read-when: Creating a repository, merging a milestone, or installing the guard in a clone
covers: []
last-verified: 2026-10-09
---

# GitHub

GitHub stores code and history at zero cost. Nothing deploys from or runs on it; the local gate
is the only gate.

## Rules

- Every project has a private repository. Never create one (always `--private`), change visibility
  or push unless asked.
- Actions, workflows, LFS, Packages, Codespaces, Wiki, Projects and Issues are off.
- One pull request per milestone, merged with a merge commit, never squash
  ([D4](../decisions/decisions.md#d4--merge-commits-never-squash)), then a milestone tag. Update
  `README.md` before merging.

## The guard

Git never clones hooks, so run this once in every clone:

```bash
~/.claude/skills/execution-methodology/scripts/git-hooks.sh [REPO]
```

It writes pre-commit, pre-merge-commit, commit-msg and pre-push hooks into the path
`git rev-parse --git-path hooks` names (honouring `core.hooksPath`), each calling the installed
`guard.py`, and refuses when that file is absent. `--uninstall` removes only its own hooks.

At commit the guard blocks home paths, the local git identity, names on the private list
(`$PD_PRIVATE_IDENTIFIERS`, else `~/.claude/private-identifiers.txt`) and secrets. At push it
blocks a secret in any commit of the range, not just the net diff
([D3](../decisions/decisions.md#d3--the-secret-scan-reads-every-commit-in-the-pushed-range-not-the-net-diff)),
files over 10 MB, and moving an existing `main` or `master`; `PD_ALLOW_MAIN_PUSH=1 git push` allows
one deliberate direct push. Secrets and size have no override. Secret patterns stay narrow, because
a guard that cries wolf gets bypassed.

This repository is public by deliberate exception, and Issues stays on as a reader's only channel.
