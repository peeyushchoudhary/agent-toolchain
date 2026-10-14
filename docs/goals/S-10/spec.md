# S-10 spec: the README's seven questions, the repository rules in the skill, and a shipped link check

**Users and problem.** Chiefs and founders in product repositories on v7.3. Five audits found:
- Every README's status was stale, and the standard says only "front page for a human". The
  standard is not installed, so product-repository agents never read it.
- The link check is never installed, so broken links pass product gates.
- Six nested `AGENTS.md` files lack a `CLAUDE.md` twin; Codex never loads nested ones.
- Tool output is about a fifth of tracked files, and gates and code read some of it.

**What changes for the user.** A shipped reference states the README's seven sections and the
layout and lifecycle rules; `docs.py links` ships; a README can declare what it covers; both
harnesses read nested `AGENTS.md` files; a runbook migrates a repository safely.

**Acceptance criteria.**
- AC1 WHEN a relative link in `README.md`, `AGENTS.md` or a tracked `docs/**/*.md` names a missing
  file, or an anchor no heading in its target has, THE SYSTEM SHALL list it in `docs.py links` and
  exit 1.
- AC2 WHEN a tracked `AGENTS.md` has no sibling `CLAUDE.md` holding the line `@AGENTS.md`, THE
  SYSTEM SHALL list it in `docs.py links`. WHEN `docs.py pointers` creates an `AGENTS.md`, it SHALL
  write that twin, and `docs.py lint` SHALL not treat a `CLAUDE.md` holding only `@AGENTS.md` as a
  page.
- AC3 WHEN `README.md` holds a `covers` comment and a covered path was committed after the README's
  last commit, THE SYSTEM SHALL list `README.md` in `docs.py stale`.
- AC4 `verify.sh` SHALL run `docs.py links`; `install/tests/link_check.py` is removed.
- AC5 The skill SHALL ship `references/repository.md`: the README's seven sections and what it
  never states, the layout rules and the lifecycle rules. `planning.md` and `close.md` SHALL point
  to it; a milestone that changes what ships SHALL update the README in its last task. `global.md`
  SHALL carry the `AGENTS.md` reading rule within the 1,350-word ceiling. D36 SHALL record the
  choice; the runbook SHALL grep for a path's readers before moving or untracking it.
- AC6 This repository's `README.md` SHALL answer the seven questions, with a `covers` comment.

**Non-goals.**
- A check that sections are present, or a word cap.
- Migrating any product repository.
- Generating status from tags.
- Prescribing source layout, or renaming existing paths.

**Constraints.** Standard library and `git`; no project names; 1,350 always-loaded words.
