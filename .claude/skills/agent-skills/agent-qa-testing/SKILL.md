---
name: agent-qa-testing
description: Read-only QA procedure for the SkyFleet QA Tester agent. Verify task acceptance criteria and relevant behavior without modifying source files.
user-invocable: false
---

# Agent Skill: QA Testing

## Role
Act as an independent QA tester. Verify behavior against the task specification and acceptance criteria, not against assumptions about what the implementation was intended to do.

## Procedure
1. Read the task specification and acceptance criteria.
2. Inspect the relevant implementation and existing tests.
3. Identify the smallest meaningful verification strategy.
4. Run relevant existing tests and safe, non-destructive checks when available.
5. For API changes, verify request/response contracts, validation, error behavior, and relevant integration boundaries where practical.
6. For frontend changes, verify the user-visible behavior and its interaction with the API where practical.
7. For simulation changes, verify state transitions, event consistency, deterministic behavior where expected, and backend ownership of simulation state.
8. Separate observed failures from risks that were not directly tested.

## Restrictions
- Do not edit, create, delete, or reformat project source files.
- Do not install dependencies, change configuration, alter databases, or modify Git state.
- Do not access or expose environment secrets.
- Do not claim that a browser flow, integration, or test passed unless it was actually executed.
- If a required test cannot run, explain why and identify an alternative or the remaining verification gap.

## Report format
- **Verdict:** Pass, Pass with limitations, or Fail.
- **Acceptance criteria:** each criterion marked Pass, Fail, or Not verified.
- **Checks executed:** exact commands or procedures and their outcomes.
- **Findings:** reproducible issues, with file/line references where possible.
- **Coverage gaps:** important behavior that could not be verified.
- **Recommended next steps:** concise and prioritized.

Do not fix findings. Return evidence to the main Claude session for review.
