# GitHub

GitHub stores code and config. Nothing deploys from it, nothing runs on it, no gate lives there.
The founder laptop is the only release runner.

Keep the cost at zero. On a personal account with private repos, everything below is $0.

## Rules

| Rule | Why |
|---|---|
| Every project has a GitHub repo | One laptop is not a backup. Session start flags a project with none |
| **Private, always** | These repos hold health, financial, and personal data paths. Public is an incident, not a preference |
| Actions disabled, no workflows | Nothing should run on a push |
| No LFS, Packages, or Codespaces | The only GitHub features that bill on a personal account |
| Wiki, Projects, Issues off | Not cost — each is a place documentation or work tracking lives *outside* the repository route |
| PRs at milestone granularity | Unless a change is explicitly scoped smaller |
| **Merge commits, not squash** | With no CI the commit history is the audit trail, and the per-commit graph refresh already indexed each one |
| Update `README.md` before merging | Structural half gated by `make check-docs`; the honesty half by the PR template |

**Never create a repo, change visibility, or push on the founder's behalf without being asked.**
Flag the gap and let them decide.

`.github/pull_request_template.md` is a markdown file that GitHub renders. It is **not** a workflow
and must not be removed as one.

## Two paid features, enforced locally instead

Secret scanning on a private repo needs paid Secret Protection. Protected branches need a paid plan.
Both are replaced by a `pre-push` hook, which costs nothing and runs where the work happens.

It blocks:

- **a credential anywhere in the pushed commit range** — not the net diff. A secret added in one
  commit and removed in the next still ships to the server and stays recoverable. The net-diff
  version of this check was written first and verifiably missed exactly that case.
- **any file over 10 MB** — not configurable; git history keeps it forever and every future clone
  pays
- **a direct push to the default branch**

The v5.1 product-definition, milestone-seal and review-budget blocks were retired with that
methodology in v6 (F-3). The push guard is now `execution-methodology/scripts/guard.py
--pre-push`, installed per clone by `git-hooks.sh`.

For a deliberate direct push to the default branch, `PD_ALLOW_MAIN_PUSH=1 git push` is the
supported escape — scoped to the one command, it leaves no hole behind. A secret or
oversized-file finding has no such override: fix it. There is no env var left to raise the 10 MB
limit, so `git push --no-verify` is the only remaining route past a size or secret finding, not a
recommended one — using it ships the file or credential unscanned.

Secret patterns are deliberately narrow — AWS key id, GitHub token, Google API key, Slack token,
Stripe live key, private-key blocks. A generic high-entropy rule fires on lockfile hashes and base64
fixtures, and a guard that cries wolf gets bypassed.

## Checking state

Nothing in the toolkit creates a repository, changes visibility, or pushes.

## This repository is a deliberate exception

Everything above says *private, always*. This repository is public, because documentation nobody can
read is not documentation. That is a considered exception, not a loophole, and it comes with
different settings: **Issues stays enabled**, since it is the only channel a reader has to report a
problem, whereas a private repo routes work through its own backlog. Wiki and Projects stay off for
the same fragmentation reason as everywhere else.

The rule survives the exception only if the exception is written down. An undocumented "except when
I felt like it" is just an absent rule.

## Scripting notes

`git log --branches --not --remotes` ignores tags, so a commit reachable only from a tag reads as
unpushed when it is not. Check tags separately with `git ls-remote --tags origin`.
