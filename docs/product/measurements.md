---
summary: The dated numbers the decisions and the methodology cite: cross-vendor review cost and findings, token prices, v5.1 and v6 load and waste, real defects by review round, the v6 guards' catches, founder decisions per milestone. Also the size of `install/` per ref and the always-loaded word count, the pilot's measures with their definitions and its stop rule, and the records of the end-to-end runs.
read-when: Citing a number, recording a measurement, or applying the pilot's stop rule
covers: []
last-verified: 2026-10-09
---

# Measurements

The numbers the decisions and the [methodology](../architecture/methodology.md) cite, each dated.

## Dated

| Date | Measure | Value |
|---|---|---|
| 2026-07-26 | Cross-vendor review, a 34-line class with two planted bugs (n=1) | Codex with repository and scoped prompt: 5 grounded findings, 186K input tokens, $0.367; Claude subagent: 5 grounded, 30K, $0.212; both found both bugs, Codex also a nonexistent method. Naive and no-repository Codex calls: 2 findings each, ungrounded or shallow |
| 2026-07-26 | Floor of any `codex exec` call | about 23K input tokens; a naive call cost 84% more |
| 2026-08 | Criterion ids on tests, four product repositories | 0 of 5,866 `@Test` methods |
| 2026-09-23 | Price per million tokens, uncached in / cached in / out | [Claude Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/overview) $4 / $0.20 / $20; [GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol) $2 / $0.20 / $10; one cross-vendor review re-priced at about 0.77× an in-harness one |
| 2026-10-06 | v5.1 load | 47,500 words of prose, 25,500 script lines, 46,000 test lines; 15,800 words before a task |
| 2026-10-06 | v5.1, one six-task milestone | 70–90 agent steps, 30+ contexts, 4–7 founder transactions |
| 2026-10-06 | v5.1 review | 11 of 13 task reviews blocked in round one, 6 of 6 acceptances passed; 0.74 blockers per design artifact, 0.09 per implementation artifact |
| 2026-10-06 | v5.1 machinery | task cards 2,256 lines for 18 keys; a 1,630-line review-budget checker; 99% of builders on the expensive tier; every sampled failure a test judge reported environmental or pre-existing |
| 2026-10-06 | v5.1 waste | 116 of 558 files out of scope; 68% of one project's spend in the controller; 31% of tool calls polling |
| 2026-10-09 | Real defects by review round | this repository's diff reviews 20, then 2; 150 sampled product findings 64, 9, 8 (rounds one, two, three-plus) |
| 2026-10-09 | Two v6 guards, seven repositories | 3,785 lines, 0 real catches, 3 legitimate pushes blocked |
| 2026-10-09 | v6 `install/` | 5.7 lines of process policing per line of done-check |
| 2026-10-09 | Founder decisions per v6 milestone | 10–13, against a contract of 2 |

## `install/` size

Newlines of every file in `git ls-tree -r <ref> install`; test files are under `tests/` or named
`test_*`.

| Ref | Files | Lines | Non-test | Test |
|---|---|---|---|---|
| `methodology/v6-base`, also `goal/S-1/approved` | 73 | 22,428 | 11,300 | 11,128 |
| S-1 T7 (`f3cf892`) | 26 | 4,165 | 1,937 | 2,228 |

Always-loaded prose after S-1 T6: 1,263 words of 1,350.

## Pilot

One product repository, migrated after S-1 M2, reviewed after a week and judged over four; its
baseline is first recomputed from its own history under these definitions.

| Measure | Definition |
|---|---|
| Accepted merges per week | `git log --first-parent --merges` per ISO week |
| Rework | fix commits ÷ task commits per milestone |
| Escapes | confirmed post-merge defects from the other vendor's sampled follow-up review (all data or auth goals, half the rest); blocking 3, non-blocking 1 |
| Founder decisions per milestone | approval, merge, and founder lines in Decisions and Parked |

Tasks ticked and founder days absent are recorded too.

Any one reverts: a blocking escape in two milestones; merges per week below baseline without a
logged external cause; founder decisions above four per milestone twice; more than one default in
five reversed at merge.

## End-to-end run

S-1 T9 records here: each harness's wall time and sessions, and one unattended session's recurring
cost.

## 2026-10-09 — S-1 T9 (v7, M2)

- Unattended two-task goal (`e2e_run.sh`): the loop is proven with a fake harness (three sessions,
  `[T1]` and `[T2]` commits, `DONE`, `packet.md`); live `claude -p` and `codex exec` sessions were
  skipped by founder decision (no credentials in disposable homes), so wall time, session count,
  reported cost, the push-denial probe and the `--settings` merge question are owed to the first
  authenticated run.
- `install/` lines: 2,025 non-test, 2,469 test
  (`git ls-files install | grep -v '/tests/' | xargs cat | wc -l`, and the same with `grep '/tests/'`).
- Always-loaded words: 1,263 (`global.md` + `AGENTS.md` + `SKILL.md`, `wc -w`); ceiling 1,350.
- One unattended session runs one fresh `claude -p` or `codex exec`, a `goal.py done` per stop
  (blocked at most three times), and two `goal.py`/`gate.py` calls in `run.sh`. Claude reports
  `total_cost_usd`, Codex tokens only; both go to `.runs/<id>/progress.md`. Dollar cost unmeasured.
- Review catches, S-1: M1 15 blocking in one round, all closed by fix commits with closing tests;
  M2: see `.runs/S-1/review.md` (filled at the M2 close).

## 2026-10-09 — S-2 (v7.1)

Taken on the T11 tree before its commit; every number with the command that printed it.

- `install/` lines: 2,738 non-test, 3,214 test (`git ls-files install | grep -v /tests/ | xargs wc -l`,
  and the same with `grep /tests/`).
- `goal.py` 751 lines, `docs.py` 244
  (`wc -l install/skills/execution-methodology/scripts/goal.py install/skills/execution-methodology/scripts/docs.py`).
- Always-loaded words: 1,319 of the AC11 ceiling 1,350; `global.md` 133, `AGENTS.md` 256, `SKILL.md`
  930 (`wc -w install/global.md AGENTS.md install/skills/execution-methodology/SKILL.md`).
- On-demand reference words: `design.md` 212, `planning.md` 396, `roles.md` 136,
  `security-checklist.md` 101; 845 in all (`wc -w install/skills/execution-methodology/references/*.md`).
- Agent body words, after the frontmatter as `test_rules.py` counts them: builder 348, reviewer 331,
  scout 137, against ceilings of 350, 350 and 200 (`awk 'c==2{print} /^---$/{c++}' agents/<name>.md | wc -w`).
- This goal's tokens from the approval tag to the T11 build, recorded, never enforced (AC11), as
  `python3 install/skills/execution-methodology/scripts/goal.py --goal S-2 cost` printed them in the
  main checkout (Claude's input includes cache reads and writes):

  ```
  claude: input 66517152 output 220853 (11 transcripts)
  codex: input 664283 output 7678 (1 transcripts)
  ```

- End to end: `e2e_run.sh` drives the v7.1 fixture goal (spec, `reads:`, one page with `covers`, its
  generated pointers, `docs.py lint` in the gate) to `DONE M1` in both harnesses with no launcher,
  writes the approval page, and prints `unknown` cost for each harness (a scratch HOME has no
  transcripts); `e2e_install.sh` installs both homes, writes no settings or hooks file and uninstalls.
