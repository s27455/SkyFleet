---
name: documentation-update
description: Update SkyFleet project documentation after implementation or an approved architectural decision, using verified repository facts only.
---

# Documentation Update

## Purpose
Keep project documentation aligned with the actual, verified state of the repository without duplicating code or recording assumptions as facts.

## Workflow
1. Identify what changed and verify it in source code, tests, configuration, or an explicitly approved decision.
2. Read the relevant existing documentation before editing it.
3. Update only documents affected by the verified change.
4. Update `docs/progress-tracker.md` only when a task's status has genuinely changed and the result has been verified.
5. Record architectural decisions in the project's established decision-record location only when a meaningful decision has actually been made.
6. Preserve existing structure, terminology, and useful content. Avoid broad rewrites.

## Documentation rules
- Distinguish implemented, tested, partially implemented, planned, and proposed work.
- Never mark a task complete if required verification has not passed.
- Do not invent endpoints, fields, workflows, test results, deployment details, or architectural decisions.
- Do not copy large portions of `CLAUDE.md` or other context files into multiple documents.
- Keep instructions concise and actionable.
- Do not document secrets, private tokens, credentials, or local environment values.

## Output
Summarize:
- files updated;
- facts or decisions documented;
- items intentionally left unchanged;
- any missing evidence that prevents an accurate update.

Do not commit or push documentation changes. Leave them for user review.
