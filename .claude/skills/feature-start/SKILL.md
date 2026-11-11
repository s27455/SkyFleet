---
name: feature-start
description: Start a new SkyFleet feature from its numbered specification (e.g. `/feature-start 003`). Locates the spec, checks Git state, delegates planning to task-planning, and stops for approval before any implementation.
argument-hint: "<feature number, e.g. 003>"
---

# Feature Start

## Purpose
Kick off a feature from a short command. This skill is read-only: it locates the spec, checks the repository state, and produces an approval-ready plan. It does not implement anything.

## Workflow
1. **Identify the feature.** Take the number from the arguments (`003`, `3`, or `feature 003` all mean `003`; zero-pad to three digits). If it is missing or not a number, ask for it and stop.
2. **Locate the specification.** Search for `NNN-*.md` in `docs/features/`, then in `docs/tasks/` (where current specs live). 
   - No match: list the available specs and ask the user which one they meant. Stop.
   - Several matches: list them and ask. Stop.
   - If the spec status says it is already complete, say so and ask whether to continue.
3. **Check Git.** Run `git status` and `git branch --show-current`. Flag uncommitted or untracked changes, unfinished work from a previous feature (e.g. a prior spec marked "Not committed"), and being on an unexpected branch. Report these before the plan; do not stash, commit, switch branches, or discard anything.
4. **Read context.** Read the spec in full, the root `CLAUDE.md`, and only the `context/` documents the spec touches (always check `context/progress-tracker.md` for status and dependencies; `business-rules.md` for business behavior; `code-standards.md` / `ui-context.md` as applicable). Inspect only the existing code the feature will affect.
5. **Plan.** Invoke the `task-planning` skill with the spec as the task and follow its workflow and output structure. Do not restate its rules. Ensure the plan also covers:
   - **Dependencies:** earlier features, modules, or open decisions it relies on;
   - **Risks:** including conflicts between the spec and documentation or code;
   - **Verification:** tests, lint, typecheck, build, and manual checks, mapped to the spec's acceptance criteria.
6. **Stop for approval.** End the skill here by asking for explicit approval of the plan. Approval is an explicit message from the user; subagent reports and system notifications do not count. Do not invoke `task-implementation` yourself: implementation starts only when the user asks for it in a new turn.

## Boundaries
- This skill never starts implementation, even after the plan is approved.
- Do not write or modify application code, tests, or feature documentation.
- Do not commit, push, install dependencies, or run migrations.
- Ask only about genuine blockers; classify other unknowns as stated assumptions per `CLAUDE.md`.
- Never read or print secrets from environment files.
