---
name: task-planning
description: Analyze and plan a SkyFleet development task before implementation. Use when a feature, bug fix, refactor, or technical change needs scoping and an approval-ready plan.
---

# Task Planning

## Purpose
Produce a small, evidence-based implementation plan. This skill is read-only: do not modify project files.

## Workflow
1. Read the root `CLAUDE.md`.
2. Read only the relevant project context and rules, especially the applicable files under `docs/` and `.claude/rules/`.
3. Inspect the current repository state before making assumptions:
   - Check `git status` and the current branch.
   - Inspect relevant source files, tests, API contracts, and existing patterns.
   - Do not assume documentation describes the current implementation perfectly.
4. Clarify the requested outcome and identify what is explicitly out of scope.
5. Identify:
   - affected modules and files;
   - dependencies and prerequisites;
   - API, data-model, UI, and simulation implications;
   - risks and unresolved decisions;
   - tests and verification needed.
6. Prefer the smallest solution that satisfies the requirement. Do not introduce new infrastructure, abstractions, dependencies, or features without a clear need.
7. Present an ordered plan with concrete acceptance criteria.

## Output
Use this structure:
- **Understanding:** concise restatement of the requested outcome.
- **Current state:** relevant findings from the repository.
- **Scope:** included and explicitly excluded work.
- **Files/modules:** expected files to create or modify, with reasons.
- **Implementation steps:** small, ordered steps.
- **Verification:** tests and checks that will demonstrate completion.
- **Risks / decisions:** only genuine uncertainties that require input.

## Approval gate
Stop after presenting the plan. Do not edit files, install dependencies, run migrations, commit, push, or deploy until the user explicitly approves implementation.

If a critical decision is unresolved, ask one focused question instead of silently choosing an assumption.
