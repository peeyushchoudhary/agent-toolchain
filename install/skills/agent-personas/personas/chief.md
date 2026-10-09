---
name: chief
description: Routing profile for the root session that runs a goal. The driver reads its model and effort; it is never rendered as a spawnable agent.
writes: yes
spawnable: no
claude.model: claude-opus-5-5
claude.effort: medium
codex.model: gpt-6.1-sol
codex.effort: medium
---

The chief is the root session in Claude Code or Codex. It plans, dispatches, runs gates and guards,
commits and keeps run state. Its rules are the execution methodology; this file carries only its
model and effort, so every run starts the chief the same way.

It is never spawned as a subagent. A chief layered under another long-lived session took most of
the measured spend without adding judgement, so the renderer skips this profile and the driver
starts it as the root.

Effort stays constant within a session so the prompt cache holds.
