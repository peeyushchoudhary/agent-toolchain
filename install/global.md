# Operating rules

Solo founder, one machine, no hosted CI. Local gates are the only gates: report each with the
command that ran and its real output. A green unit suite is not end-to-end validation.

Never push, merge, deploy, publish, change a repository's visibility or spend money unless the
founder asks for it. Private facts (names, personal paths, accounts, emails, secrets) stay out of
public repositories; the guard checks this, and the rule holds where it cannot.

When a repository has `docs/goals/*/plan.md` with an open milestone, load the
`execution-methodology` skill and follow it. A decision the plan does not settle is defaulted and
logged as a Decisions line, or parked for the founder; never stop to ask about work the plan
already decides.

Report outcomes, not intentions: what changed, what ran, what failed.
