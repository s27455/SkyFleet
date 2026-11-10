# AI Workflow Rules — SkyFleet

## 1. Purpose

This document defines how AI coding assistants, especially Claude Code, should work on the SkyFleet project.

The goal is to maintain a structured, predictable development process, produce maintainable code, and avoid unnecessary complexity.

The assistant should act as a thoughtful engineering partner, not simply a code generator.

These rules apply throughout the entire project unless the user explicitly overrides them.

---

## 2. Core Principles

### 2.1 Understand Before Implementing

Never start implementing a non-trivial feature without first understanding:

- The project structure.
- The existing architecture.
- Relevant documentation.
- Existing implementations related to the task.
- Dependencies and potential side effects.

Do not assume that a feature should be implemented in a particular way just because it is a common industry practice.

Inspect the actual project before making decisions.

### 2.2 Plan Before Coding

For every non-trivial task:

1. Understand the requested outcome.
2. Read relevant project documentation.
3. Inspect the existing implementation.
4. Identify affected modules and dependencies.
5. Propose a clear implementation plan.
6. Identify assumptions, risks, and unresolved questions.
7. Wait for user approval before proceeding when the task involves significant architectural or behavioral decisions.

Small, straightforward changes do not require a lengthy planning phase.

### 2.3 Work in Small, Verifiable Steps

- Implement one feature or logical unit at a time.
- Avoid implementing multiple unrelated features in one task.
- Prefer incremental changes over large rewrites.
- Verify each meaningful step before moving forward.
- Keep changes focused on the requested task.

Do not introduce additional functionality simply because it might be useful in the future.

### 2.4 Do Not Invent Requirements

If expected behavior is unclear:

- Ask the user for clarification when the decision materially affects implementation.
- If the detail is minor, propose a reasonable assumption and clearly communicate it.
- Record important unresolved decisions in the relevant documentation or progress tracker.

Never silently turn an assumption into an established project requirement.

---

## 3. Context and Documentation

Before working on a task, consult the documentation relevant to that task.

The project's documentation is organized into:

- `project-overview.md` — product purpose, domain, and functional scope.
- `architecture-context.md` — system architecture and component responsibilities.
- `code-standards.md` — coding conventions and implementation standards.
- `ui-context.md` — visual design and user interface guidelines.
- `progress-tracker.md` — current progress, completed work, and open tasks.
- `ai-workflow-rules.md` — development workflow and assistant behavior.

Also read `CLAUDE.md` and any relevant instructions located in the repository.

### Documentation Rules

- Treat project documentation as the primary source of project-specific requirements.
- Keep documentation consistent with the actual implementation.
- Update documentation when an approved architectural or behavioral decision changes.
- Do not duplicate large sections of information across multiple files.
- Do not mark planned or partially implemented work as completed.
- Do not modify unrelated documentation without a clear reason.

If documentation conflicts with the actual code, identify the discrepancy and discuss it before making significant changes.

---

## 4. Task Execution Workflow

Follow this workflow for non-trivial development tasks.

### Phase A — Understand

- Read the task carefully.
- Inspect the relevant files and modules.
- Understand existing behavior before changing it.
- Identify dependencies and integration points.
- Check the current Git status to avoid interfering with existing user changes.

### Phase B — Plan

Present a concise plan containing:

- What will be implemented.
- Which parts of the application will be affected.
- How data will flow through the system.
- Which tests or verification steps will be needed.
- Any important assumptions or risks.

If the task introduces a new architectural concept or changes existing system behavior, discuss the approach with the user first.

### Phase C — Implement

- Follow the approved plan.
- Make focused changes.
- Respect existing architectural boundaries.
- Reuse existing components and utilities when appropriate.
- Avoid unnecessary abstractions and premature optimization.
- Do not refactor unrelated code.
- Do not overwrite existing user work.

If implementation reveals a problem that requires changing the approved approach, stop and explain the issue before making a significant deviation.

### Phase D — Verify

After implementation:

- Run relevant automated tests.
- Run linting and formatting checks when available.
- Run type checking when available.
- Verify important application behavior.
- Check for regressions in affected functionality.

Never claim that a test, command, or verification step succeeded unless it was actually executed and its result was checked.

If a check cannot be performed, clearly state why.

### Phase E — Review and Report

Before considering a task complete:

- Review the changed files.
- Check for accidental or unrelated modifications.
- Confirm that implementation matches the acceptance criteria.
- Update relevant documentation.
- Update `progress-tracker.md` when project progress or task status changes.

Provide a concise summary of:

1. What was implemented.
2. Which files were changed.
3. What verification was performed.
4. Any remaining limitations or known issues.
5. Any decisions that still require user input.

Do not automatically commit changes unless the user explicitly asks.

---

## 5. Scope Control

SkyFleet is a time-limited project with a defined delivery deadline.

Prioritize a working, coherent MVP over an unnecessarily sophisticated system.

Always distinguish between:

- Required functionality.
- Valuable improvements.
- Future possibilities.

Do not introduce technologies or infrastructure solely to make the project appear more advanced.

Avoid unnecessary:

- Microservices.
- Message brokers.
- Distributed infrastructure.
- Additional databases.
- Complex abstractions.
- External integrations.
- Dependencies that do not provide meaningful value.

Before introducing a new dependency or major technical component, explain:

- Why it is needed.
- What problem it solves.
- Whether an existing solution is sufficient.
- What additional maintenance or complexity it introduces.

The simplest solution that satisfies the requirements is generally preferred.

---

## 6. SkyFleet-Specific Development Rules

### 6.1 Simulation Ownership

The backend is the authoritative owner of the SkyFleet simulation.

- Simulation logic must run independently of the frontend.
- The simulation must not depend on an open browser window.
- The frontend displays and interacts with simulation state but does not own the simulation.
- Simulation state changes must be persisted or otherwise managed by the backend according to the approved architecture.
- Real-time updates should be communicated through the backend's designated real-time mechanism.

The simulation represents a fictional drone delivery operation.

Unless explicitly approved otherwise, all flight activity, telemetry, incidents, and operational events are simulated.

Do not implement real drone control, real-world flight physics, live weather integrations, or actual aviation regulatory logic.

The objective is a convincing operational simulation, not a real autonomous aircraft control system.

### 6.2 Business Logic and State Transitions

Operational behavior must remain coherent across the application.

Examples include:

- An order being created and dispatched.
- A drone being assigned to a mission.
- A drone travelling to a delivery location.
- A successful delivery.
- A failed delivery and return with the package.
- A drone returning to an appropriate hub.
- A drone charging or waiting for another mission.
- An incident changing the operational status of a drone.

Implement business rules in the appropriate backend layer.

Do not duplicate authoritative business logic in the frontend.

Important state transitions should be explicit, controlled, and testable.

### 6.3 Deterministic Operational Rules

Core operational decisions should be deterministic whenever possible.

In particular, dispatch and drone assignment should use explicit business rules rather than relying on an LLM to make operational decisions.

Given the same inputs and system state, deterministic rules should produce predictable results.

This improves reliability, testability, and explainability.

### 6.4 AI Integration

AI should provide meaningful operational intelligence rather than being added to every part of the application.

Potential responsibilities include:

- Answering questions about fleet status and active missions.
- Investigating incidents using available operational data.
- Explaining system events.
- Providing operational recommendations.
- Assisting operators through natural-language interaction.

AI must use controlled backend tools and explicitly available data.

Do not give an AI model unrestricted database access or allow it to execute arbitrary SQL.

AI recommendations must not silently bypass deterministic business rules.

Any AI-assisted operation that changes important system state must require explicit operator approval and backend validation before execution.

AI must not be responsible for safety-critical control decisions.

---

## 7. Backend and Frontend Boundaries

Maintain clear separation of responsibilities.

### Backend

The backend is responsible for:

- Business logic.
- Data validation.
- Persistence.
- Order and mission management.
- Drone and hub state.
- Dispatch decisions.
- Simulation execution.
- Incident generation and processing.
- AI integration and controlled operational tools.
- REST API and real-time communication.

API route handlers should remain focused on HTTP concerns rather than containing large amounts of business logic.

### Frontend

The frontend is responsible for:

- Presenting operational information.
- Displaying drones and their movement on the map.
- Showing orders, missions, hubs, and incidents.
- Providing operator controls.
- Displaying real-time updates.
- Providing AI interaction and recommendations.

The frontend must not independently simulate drone movement or make authoritative operational decisions.

### Map Visualization

The map is a visualization layer.

Map rendering and interaction must remain separate from authoritative simulation logic.

Mapbox-related configuration and credentials must follow the project's environment-variable and security conventions.

---

## 8. Testing and Quality

Testing should focus on meaningful application behavior.

Prioritize tests for:

- Business rules.
- Order and mission lifecycle.
- Drone state transitions.
- Dispatch decisions.
- Simulation behavior.
- Incident generation and handling.
- API contracts and validation.
- Important frontend interactions.

Prefer testing observable behavior rather than implementation details.

Tests should be deterministic and independent of real-world external services whenever possible.

Do not add tests that merely increase test count without providing meaningful confidence.

When a bug is fixed, add a regression test when practical.

---

## 9. Code Changes and Git Safety

Before making changes:

- Inspect the Git working tree.
- Identify existing uncommitted changes.
- Avoid modifying files unrelated to the task.

Never perform destructive Git operations without explicit user approval.

This includes:

- Resetting changes.
- Reverting user work.
- Removing untracked files.
- Force pushing.
- Amending existing commits.

Do not silently replace working implementations with completely different approaches.

Do not modify generated files, vendor libraries, or build artifacts unless explicitly required.

Keep changes reviewable and logically grouped.

---

## 10. Skills and Subagents

Use Claude Code skills and subagents when they provide a clear benefit.

- Prefer relevant project-specific skills when available.
- Review external skills before adopting them.
- Avoid installing or duplicating tools without a clear purpose.
- Use subagents for independent research, analysis, or code review.
- Do not delegate conflicting implementation work on the same files.
- Review and verify all subagent output before incorporating it.

The main assistant remains responsible for consistency and integration.

Never assume that generated code or external recommendations are correct without reviewing them.

---

## 11. Security and Configuration

- Never commit API keys, passwords, tokens, or private credentials.
- Use environment variables for secrets and environment-specific configuration.
- Keep `.env` files out of version control.
- Maintain an appropriate `.env.example` without real credentials.
- Validate external input at application boundaries.
- Avoid logging secrets or sensitive configuration.
- Use the minimum required permissions for external services.

Do not expose private backend credentials in frontend code.

---

## 12. Definition of Done

A task is considered complete only when:

- The requested behavior has been implemented.
- The implementation follows the approved approach.
- Relevant tests and checks have been executed where possible.
- No known unrelated changes have been introduced.
- Relevant documentation has been updated.
- Remaining limitations are clearly communicated.
- The user has received a summary of the work.

A task is not complete merely because code has been written.

---

## 13. Final Working Principle

Always optimize for a project that is understandable, maintainable, demonstrable, and finished.

The goal is not to build the most complicated system possible.

The goal is to build a convincing, well-engineered SkyFleet MVP that demonstrates strong fullstack development skills, sound architectural decisions, and thoughtful use of AI.