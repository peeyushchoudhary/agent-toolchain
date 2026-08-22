# Decisions

**Authority: current.** Accepted decision records: each settled choice against the alternative it
was chosen over.

| Document | What it holds |
| --- | --- |
| [decisions.md](decisions.md) | Every accepted decision, D1 onward, newest last |

## Why this directory holds ONE file and not one file per decision

The standard requires a DIRECTORY here, and this repository had a FILE. Splitting `decisions.md`
into a file per record was rejected, and renaming it to `README.md` was rejected; both were
measured rather than argued.

`validate_disclosure.py` exempts a RECORD from the word budget by FILENAME —
`^(measurements|benchmarks|decisions|adr|rulings|improvements|changelog|history)(?:[-_][a-z0-9]+)?\.md$`,
tested against the basename alone. `decisions.md` matches; `README.md` does not. The rename would
therefore have stripped the exemption from a file sitting at 1,185 words of a 1,200-word budget —
two decisions from the wall `measurements.md` hit first, which is the incident the exemption was
written for. The class name travels with the basename, so the basename stays.

A file per decision would have escaped the budget too, by sharding. That is the exit the same
source comment records as GAMING the metric rather than answering it: "answered by sharding
lessons.md into two compliant files with more total text, not shorter text". A decision record
accretes by definition — a decision that stops being listed stops being findable — and splitting it
also breaks every `decisions.md#dNN` anchor cited from the operating model, the measurements and
`AGENTS.md`.

So: the directory is real, this README states its purpose and authority, and the record keeps its
name. When the record does outgrow one sitting, the honest move is `../archive/`, not a shard.
