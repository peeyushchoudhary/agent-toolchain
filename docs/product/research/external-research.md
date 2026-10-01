# External announcements and projects — checked 2026-09-30

**Status: dated research. Announcements are candidate evidence, not installed capability.**
Primary official pages and project repositories support the comparisons below. GitHub popularity
and vendor benchmark claims do not establish results for this workflow. Moving default branches
must be pinned to commits before an implementation imports code or configuration.

Earlier pilot recommendations below are retained as research rationale. The
[current replan](velocity-and-quality-replan.md) supersedes them: reviewed direct rollout, then a
first-week review and weekly observation; no prerequisite model or workflow pilot.

## Recent changes that matter

| Date | Verified announcement | Implication for this proposal |
| --- | --- | --- |
| 2026-09-29 | GPT-6.1 Sol released for Codex/Work; CLI 0.159.0 published | Compare cheaper complex-work routing; test client compatibility. |
| 2026-09-28 | CLI 0.158.0 fixes unnecessary reviews for runtime-only grants and macOS patch path aliases | Test an update against observed permission friction. |
| 2026-09-22 | GPT-6 Sol/Luna rollout; CLI 0.156.0 usage analytics and worktree improvements | Use observed usage and safe task isolation for pilots. |
| 2026-09-28 | Claude Sonnet 5.5 announced | Candidate for bounded implementation and ordinary tasks in the Claude harness. |
| 2026-09-22 | Claude Opus 5.5 announced | Candidate for judgment-heavy work; architect already has a dated pilot. |

The installed CLI reports 0.157.1, so the later fixes are not established locally. Release data comes
from the [official changelog](https://learn.chatgpt.com/docs/changelog). Updates and model activation
remain separate from this proposal.

Anthropic's [Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5) and
[Opus 5.5](https://www.anthropic.com/claude-opus-5-5) announcements support those candidate roles.
Reported speed/cost gains are vendor results; they are not measured savings for this repository.
The announced future Haiku 5.5 is not treated as available.

Current [native long-running work](https://learn.chatgpt.com/docs/long-running-work) supports
same-session goals in desktop, CLI and IDE, retaining sandbox and approval boundaries. Pilot this
before building a new local daemon. It does not establish offline or crash recovery in this project.

[Codex automatic approval review](https://learn.chatgpt.com/docs/sandboxing/auto-review) handles
eligible requests with a separate reviewer; it does not expand filesystem/network permissions.
The machine already enables it. Improvements should reduce needless boundary crossings and agent
questions, while preserving denied-action handling.

## Best practices with evidence and limits

Anthropic's [long-running harness study](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
(2025-11-26) uses incremental features, restart recipes, Git/progress artifacts and end-to-end
checks to bridge contexts. Adapt those practices into the existing resume owner. Its web-app demo
is not a universal benchmark.

The later [harness study](https://www.anthropic.com/engineering/harness-design-long-running-apps)
(2026-03-24) reports better application quality with planner/generator/evaluator separation, but an
example full harness took six hours/$200 against twenty minutes/$9 for a solo run. Its later
iterations remove scaffolding as models improve. This supports component-by-component experiments;
it does not justify assuming a larger council is cheaper.

[Claude Code auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode) (2026-03-25)
uses automatic action review and denial recovery to reduce permission friction. Automatic review
remains fallible and complements a sandbox. The local Claude configuration already selects auto
mode; repeated prompts need cause-level observation before further configuration changes.

## GitHub comparison

| Project and primary source | Useful pattern | Recommendation for SWE Agent |
| --- | --- | --- |
| [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) | Small loop, transparent trajectories and run limits | Adapt trajectory metadata and use a simple baseline for bounded tasks. Its benchmark claims do not replace independent review. |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | Trajectory/configuration evidence | Reference only; current project guidance favors mini-SWE-agent for new use. |
| [Aider](https://github.com/Aider-AI/aider), [benchmark recipe](https://github.com/Aider-AI/aider/blob/main/benchmark/README.md) | Repository maps and repeatable benchmark trials | Adapt selective context and paired experiment mechanics. Auto-commit behavior must remain subject to local authority. |
| [Spec Kit](https://github.com/github/spec-kit), [current documentation](https://github.github.com/spec-kit/) | Intent-to-task trace and structured processes | Reference/adapt templates only where a concrete field is missing. The current methodology already owns the equivalent chain. |
| [Superpowers](https://github.com/obra/superpowers) | Small plans, worktree isolation, systematic debugging and evidence | Adapt useful task techniques. Its two-stage semantic review would duplicate the current one-reviewer policy if imported wholesale. |
| [GSD Core](https://github.com/open-gsd/gsd-core) | Lean controller, fresh worker context, phased verification | Adapt bounded handoffs. Do not add its phase controller beside the chief. |
| [LangGraph](https://github.com/langchain-ai/langgraph), [persistence docs](https://docs.langchain.com/oss/python/langgraph/persistence) | Checkpoint/restart and separation of state lifetimes | Reference recovery concepts; defer runtime adoption because Git and the existing pointer already own progress. |
| [OpenHands / Agent Canvas](https://github.com/OpenHands/OpenHands) | Control center with local, container and VM agent backends | Reference backend isolation patterns; replacing the current tooling requires measured benefit and a reviewed design. |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | Reproducible fail-to-pass and regression evaluation | Adapt evaluation mechanics; use project tasks to judge routing. |
| [Anthropic autonomous-coding demo](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding) | Persistent progress and incremental work | Adapt restart acceptance scenarios; demo authorization is not this project's authority. |
| [Anthropic sandbox-runtime](https://github.com/anthropics/sandbox-runtime) | OS-level filesystem/network restrictions and explicit socket risk | Reference a capability test design; do not replace the existing sandbox without a concrete failure and compatibility proof. |

The older [GSD repository](https://github.com/gsd-build/get-shit-done) now explicitly redirects to
GSD Core. Copies and forks remain searchable, so establish the active source before treating an
old README as current advice.

OpenAI's [SWE-bench Verified audit](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)
raises contamination and evaluation defects. The relevant lesson is to use hidden, local,
task-specific cases and actual integration outcomes rather than promote a model by a public score.

## Selection rule

Adopt concepts that close a named gap, adapt only the necessary artifact or check, and defer a
replacement framework until matched evidence shows that native clients and existing owners cannot
deliver the outcome. Check licenses and pin imported source before implementation. This research
does not install any compared project or activate its hooks.
