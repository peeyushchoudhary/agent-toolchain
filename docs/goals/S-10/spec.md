# S-10 spec: the README's seven questions, a shipped link check, and the layout rules

**Users and problem.** A founder or chief opening a product repository on v7.3. Five audits found:
- Every README's status was stale, and the standard says only "front page for a human".
- The link check lives in `install/tests/`, which the installer never ships, so broken links pass
  product gates.
- Six nested `AGENTS.md` files have no `CLAUDE.md` twin, so Claude never loads them.
- Codex never loads a nested `AGENTS.md`, because sessions start at the root.
- Tool output and old run records are about a fifth of product repositories' tracked files.

**What changes for the user.** The standard names the README's seven sections; `docs.py links`
ships; a README can declare what it covers; both harnesses read nested `AGENTS.md` files; a
runbook migrates a repository's layout.

**Acceptance criteria.**
- AC1 WHEN a relative link in `README.md`, `AGENTS.md` or a tracked `docs/**/*.md` names a missing
  file, or an anchor no heading in its target has, THE SYSTEM SHALL list it in `docs.py links` and
  exit 1.
- AC2 WHEN a tracked `AGENTS.md` has no sibling `CLAUDE.md` holding the line `@AGENTS.md`, THE
  SYSTEM SHALL list it in `docs.py links`. WHEN `docs.py pointers` creates an `AGENTS.md`, it SHALL
  write that twin, and `docs.py lint` SHALL not treat a `CLAUDE.md` under `docs/` as a page.
- AC3 WHEN `README.md` holds a `covers` comment and a covered path was committed after the README's
  last commit, THE SYSTEM SHALL list `README.md` in `docs.py stale`.
- AC4 `verify.sh` SHALL run `docs.py links` in place of `install/tests/link_check.py`, which is
  removed.
- AC5 `repository-standard.md` SHALL name the README's seven sections and what it never states,
  together with the layout rules. `planning.md` SHALL give a milestone that changes what ships a
  README update in its last task. `global.md` SHALL carry the `AGENTS.md` reading rule, within the
  1,350-word ceiling. D36 SHALL record the choice, and a runbook SHALL migrate a repository's
  layout.
- AC6 This repository's `README.md` SHALL answer the seven questions with a `covers` comment, and
  `docs.py links` SHALL pass here.

**Non-goals.**
- A check that sections are present, or a word cap.
- Migrating any product repository.
- Generating status from tags.

**Constraints.**
- Standard library and `git`.
- No project names in this public repository.
- The always-loaded files stay within 1,350 words.
