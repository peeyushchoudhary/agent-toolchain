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

It warns on a newly added `.env`-style file and on source changing while `README.md` did not.

**In a repository that holds `docs/product/`, and only there, it blocks two more.** The first is a
product definition that is not in current-state form: `spec_check.py` and `plan_waves.py` run at the
push. The second is a milestone document moving to `status: shipped` without evidence that its
declared `Gate:` command ran and passed against the tree being pushed. Elsewhere this half does
nothing and prints nothing — adoption is staggered, and a gate that blocks a push in a repository
that never opted in is a gate that gets uninstalled, after which it protects nothing anywhere.

Measured 2026-08-21, private repository, 204 documents under `docs/product/`, median of seven runs:
`spec_check.py` 107 ms, `plan_waves.py` 41 ms, **154 ms added to a push** end to end. That number is
why both run over the whole tree rather than the pushed range — range-scoping saves nothing a human
can feel and would let a spec broken by an edit outside `docs/product/` push clean. Re-measure
before changing it. (Not in [measurements.md](measurements.md): that document is at 1194 words
against the 1200-word route budget, so it cannot take a new measurement without evicting an old one.)

For a deliberate direct push to the default branch, `PD_ALLOW_MAIN_PUSH=1 git push` is the
supported escape — scoped to the one command, it leaves no hole behind. `PD_SKIP_SPEC_CHECK=1` and
`PD_ALLOW_UNSEALED_MILESTONE=1` are the same shape for the two product-definition blocks, and each
prints a `pre-push SKIPPED` line saying the check did not run: an escape nobody can see is worse
than none, because the push then looks identical to a checked one. Two variables rather than one
blanket skip, so pushing past a lint finding does not silently disarm the seal gate. A secret or
oversized-file finding has no such override: fix it. There is no env var left to raise the 10 MB
limit, so `git push --no-verify` is the only remaining route past a size or secret finding, not a
recommended one — using it ships the file or credential unscanned.

Secret patterns are deliberately narrow — AWS key id, GitHub token, Google API key, Slack token,
Stripe live key, private-key blocks. A generic high-entropy rule fires on lockfile hashes and base64
fixtures, and a guard that cries wolf gets bypassed.

## Checking state

```bash
check_github.py .                    # is this project stored, private, pushed, and quiet?
check_github.py --sweep <projects-dir>   # the fleet view
check_github.py . --apply-settings   # disable Wiki/Projects/Issues (never touches visibility)
```

Local checks are git-only and always run. Remote checks are one `gh` call cached for 24h, so session
start stays fast (measured 0.22s warm). Session start reports: no repo, no remote, **public**,
unpushed work older than 3 days, and anything enabled that runs or bills.

Nothing in the toolkit creates a repository, changes visibility, or pushes.

## This repository is a deliberate exception

Everything above says *private, always*. This repository is public, because documentation nobody can
read is not documentation. That is a considered exception, not a loophole, and it comes with
different settings: **Issues stays enabled**, since it is the only channel a reader has to report a
problem, whereas a private repo routes work through its own backlog. Wiki and Projects stay off for
the same fragmentation reason as everywhere else.

The rule survives the exception only if the exception is written down. An undocumented "except when
I felt like it" is just an absent rule.

## Fleet status

`check_github.py --sweep <projects-dir>` gives the current picture across every project directory in
one table: which are repositories, which have remotes, which are private, and which carry unpushed
work. Run it rather than maintaining the answer by hand — it goes stale within a week.

The first sweep is usually sobering. Expect to find directories that were never `git init`-ed,
repositories that never got a remote, and remotes carrying commits from weeks ago that exist on
exactly one machine.

## Scripting notes

`git log --branches --not --remotes` ignores tags, so a commit reachable only from a tag reads as
unpushed when it is not. Check tags separately with `git ls-remote --tags origin`.
