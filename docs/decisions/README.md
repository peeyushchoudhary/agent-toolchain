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

Splitting it into a file per decision would break the `decisions.md#dNN` anchors that other
documents cite, which the gate's link check verifies. If the record outgrows one sitting, move
decisions that no longer apply out; do not shard it.
