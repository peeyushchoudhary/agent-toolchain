# S-3 spec: the guard's home-path rule matches only an absolute path

**Users and problem.** The founder committing in a project whose packages live under a `users/`
directory. `guard.py` reports any `/users/<name>` substring, case-insensitively, as an absolute
home path, so a diff line naming a file under `app/core/users/` is blocked by the installed
pre-commit hook, and every commit that touches or mentions such a file fails.

**What changes for the user.** A repository-relative path through `users/` or `home/` commits.
An absolute home path, in any letter case, still does not.

**Acceptance criteria.**

- AC1 WHEN a staged line holds a relative path through a `users/` directory, such as a file
  under `app/core/users/`, bare or inside backticks, THE SYSTEM SHALL exit 0 with no finding.
- AC2 WHEN a staged line holds `/Users/<name>` or `/home/<name>` at the start of the line or
  after a space, `(`, `=` or a backtick, in any letter case, THE SYSTEM SHALL exit 1 and name an
  absolute home path.
- AC3 WHEN `guard.py --self-test` runs THE SYSTEM SHALL pass with a package-path fixture that
  expects no finding.

**Non-goals.** The private-name list, `install.sh --retire-v5`, every other guard rule, the
placeholder set.

**Constraints.** Standard-library Python 3. Fixtures split the `/Users` literal so the test files
do not trip the guard. No downstream project name enters this public repository.
