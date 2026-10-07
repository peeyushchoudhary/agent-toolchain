# Decisions

**Authority: current.** The accepted decisions that are in force, each against the alternative it was
chosen over. A decision that no longer applies is removed and git holds it, so the identifiers of the
rest do not change.

| Document | What it holds |
| --- | --- |
| [decisions.md](decisions.md) | The decisions in force, with their reasons; a gap in the numbering is a removed decision |

How goals run is a design matter and lives in
[lean-execution.md](../architecture/lean-execution.md), with the numbers in
[measurements.md](../product/measurements.md).

## Why this directory holds one file

The standard requires a directory here. The record stays one file named `decisions.md`.

`validate_disclosure.py` exempts an accreting record from the word budget by file name, tested
against the basename alone, and `decisions.md` matches where `README.md` does not. Renaming the file
to `README.md` would strip the exemption. Splitting it into a file per decision would escape the
budget by sharding, which the validator's source treats as gaming the metric, and it would break the
`decisions.md#dNN` anchors that other documents cite. If the record outgrows one sitting, move
decisions that no longer apply out; do not shard it.
