# S-9 design: S-8's follow-ups, and the pilot's end

## Structure

- **`goal.py`.**
  - Done row 4 compares a protected section without its trailing blank lines.
  - Cleanup's fetch refusal quotes git's `fatal:` line.
- **`gate.py`.** The module docstring, which is its usage text, names the two `--modules`
  refusals.
- **Words.**
  - `SKILL.md` loop step 4 removes the builder's branch with its worktree.
  - `close.md` step 3 pushes the approval tag, and step 1 stops repeating the chain's "`done`
    prints DONE".
- **Records and pages.**
  - D35 ends the pilot.
  - `methodology.md` turns the stop rule into ended rationale.
  - `repository-standard.md` sorts `modules.json` with the current-state pages.
  - `measurements.md`'s `read-when` stops naming the stop rule.

## Interfaces

1. **Done row 4** (durable). For an anchored protected entry, row 4 compares
   `settled(protected_text(<parent's file>, anchor))` with `settled(protected_text(<commit's
   file>, anchor))`. Here `settled(t)` drops the trailing lines of `t` that are empty or
   whitespace-only, as `re.sub(r"(\n[ \t]*)+\Z", "", t)`.
   - `protected_text` itself is unchanged, and so is the comparison for whole-file entries.
   - A section's trailing blank lines carry no content, so appending a section after the last
     protected one passes.
   - Every non-blank line stays protected byte for byte, trailing spaces of the last content line
     included. That holds whether the range ends the file or an unprotected section follows it
     (design review R1).
2. **Cleanup's refusal** (durable). On a failed fetch the message is:
   - `goal.py: cleanup needs origin/main: <line>`, exit 2;
   - `<line>` is the first stderr line that starts `fatal:`, stripped;
   - else git's last non-blank stderr line;
   - on timeout, `timed out`, as today.
3. **`gate.py` usage.** The `--modules` paragraph of the module docstring adds one sentence: an
   empty selection, or a selected module whose test command is blank, is refused with exit 2
   before anything runs. Behaviour is unchanged (S-8 T1).
4. **The skill's words** (durable).
   - **Loop step 4:** "remove its worktree and branch after the commit".
   - **Close step 3:** `git push origin goal/<id>/approved goal/<id>/<milestone>`.
   - **Close step 1:** "The PR's head is the commit `done` passed; it is the milestone's."
5. **D35** (durable). Its title: "The pilot and its stop rule have ended (S-9)".
   - **Chose:** no stop rule. A change to `install/` is a goal the founder approves like any
     other. `measurements.md` keeps recording numbers, and nothing reverts automatically.
   - **Over:** keeping the four triggers as watch items; a new stop rule.
   - **Why:** after S-2, S-3 and S-6 to S-8 added mechanism to `install/` under the founder's
     approval. The clause no longer described practice (founder, 2026-10-13).
   - **Reverses:** D29's stop rule and D30's amendment of it. Both sections stay
     byte-identical as rationale, and D29's table status names D35.

## Data touched

None. No store, record format or receipt changes. Row 4 judges more commits acceptable; it
judges no commit it passes today as failing.

## Smallest change

- **Row 4.** One helper applied on both sides of one comparison.
- **Cleanup.** One expression for the quoted line.
- **The rest.** Words and one docstring sentence.

## Rejected options

- **`.rstrip()` on both sides.** It would also ignore trailing spaces on the last protected
  content line (design review R1).
- **Requiring no stale page on the final tree.** `repository-standard.md` covers `docs/**`, so the
  plan-only Decisions commit after T4 and any merge-review fix make a page stale again. AC6 is
  judged at T4's commit, as S-8's AC8 was, and the next goal re-verifies (design review R2).
- **Stripping trailing blank lines inside `protected_text`.** It also feeds the approval packet's
  HTML. Its tested return value would change for no reader's gain.
- **Ignoring all blank lines in protected text.** A paragraph break inside a decision is content.
- **A packet warning instead of the fix.** S-7 wrote the warning, and S-8 still hit the trap.
- **Teaching cleanup to judge builder worktrees by task commits.** It needs a worktree-to-task
  map; removing the branch at the commit is enough (founder, 2026-10-13).
