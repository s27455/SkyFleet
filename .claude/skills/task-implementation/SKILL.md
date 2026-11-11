---
name: task-implementation
description: Implement an explicitly approved SkyFleet task plan in small, controlled steps, then run relevant verification.
---

# Task Implementation

## Preconditions
- A task plan exists in the current conversation or an approved task specification.
- The user has explicitly approved implementation.
- If approval or the intended plan is unclear, stop and ask.

## Workflow
1. Re-read the approved plan and its acceptance criteria.
2. Check the current Git status. Preserve unrelated user changes; never overwrite or revert them.
3. Read the relevant source files and project rules before editing.
4. Implement only the approved scope, following existing project patterns.
5. Work in small, coherent steps. Keep backend, frontend, and simulation responsibilities separated.
6. Add or update tests for changed behavior where appropriate.
7. Run the narrowest relevant checks first, then broader checks when practical:
   - backend tests and lint/type checks applicable to the changed code;
   - frontend tests, lint, typecheck, and production build as applicable.
8. Inspect the final diff and compare it with the approved plan.
9. Report completed work, verification results, remaining issues, and any deviation from the plan.

## SkyFleet constraints
- The backend is the source of truth for operational and simulation state.
- Keep dispatch decisions deterministic and testable; do not delegate core safety or dispatch decisions to an LLM.
- Keep the architecture a modular monolith with a separate simulation worker where appropriate. Do not introduce microservices or infrastructure without explicit justification.
- Use AI through controlled backend tools and preserve human approval for state-changing AI-assisted operations.
- Keep mocked simulation behavior internally consistent without expanding into real-world flight physics or external integrations unless requested.

## Boundaries
- Do not expand scope or perform unrelated refactoring.
- Do not install, remove, or upgrade dependencies without user approval.
- Do not perform destructive database operations or migrations without user approval.
- Do not commit, push, merge, rebase, or deploy. These are separate user-approved actions.
- Never read, print, copy, or expose secrets from environment files.
- If implementation requires a material change to the approved plan, stop and explain the reason before proceeding.

## Completion
Do not claim success based only on code edits. State exactly which checks passed, failed, or were not run. Leave the working tree ready for the user's review.
