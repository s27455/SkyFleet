# Code Standards — SkyFleet

## 1. Purpose

This document defines coding standards and quality expectations for the SkyFleet project.

The goal is to maintain code that is:

- Readable and understandable.
- Consistent across the codebase.
- Easy to maintain and extend.
- Properly separated by responsibility.
- Testable.
- Appropriate for the project's actual complexity.

Code should be written for the next developer who needs to understand and maintain it, not only for the person or AI that initially creates it.

These standards apply to both backend and frontend development.

---

## 2. General Coding Principles

### 2.1 Readability First

- Prefer clear and descriptive names.
- Use consistent naming conventions.
- Keep functions and classes focused on one responsibility.
- Avoid deeply nested conditions.
- Avoid unnecessarily complicated expressions.
- Prefer straightforward implementations over clever shortcuts.
- Make important business logic easy to follow.

A developer should be able to understand the purpose of a function without having to inspect the entire application.

### 2.2 Keep Responsibilities Separate

- Separate business logic from presentation logic.
- Separate API handling from application services.
- Separate persistence concerns from domain rules.
- Avoid mixing unrelated responsibilities in one module.
- Follow the architectural boundaries defined in `architecture-context.md`.

Do not place large amounts of business logic inside API route handlers or frontend components.

### 2.3 Avoid Unnecessary Abstraction

Do not introduce abstractions, interfaces, factories, or generic frameworks without a concrete reason.

Prefer a simple implementation that solves the current problem.

Introduce additional abstraction when it:

- Removes meaningful duplication.
- Clarifies responsibilities.
- Makes testing easier.
- Supports a real extension requirement.
- Improves maintainability.

Do not optimize for hypothetical future requirements at the expense of present clarity.

### 2.4 Avoid Code Duplication

Reuse existing functions, components, and utilities when appropriate.

When similar logic appears in multiple places, evaluate whether it should be extracted into a shared implementation.

However, do not force unrelated functionality into a generic abstraction merely because the code looks similar.

### 2.5 Explicit Over Implicit

Prefer code that makes important behavior visible.

- Avoid hidden side effects.
- Avoid unnecessary global state.
- Make dependencies clear.
- Validate important inputs explicitly.
- Handle errors intentionally.
- Make important state transitions easy to identify.

---

## 3. Naming Conventions

Use descriptive names that reflect the domain and purpose of the code.

### Python

Follow standard Python naming conventions:

- `snake_case` for variables, functions, and modules.
- `PascalCase` for classes.
- `UPPER_SNAKE_CASE` for constants.

Examples:

- `get_available_drones()`
- `calculate_dispatch_score()`
- `DroneMission`
- `MAX_BATTERY_THRESHOLD`

### TypeScript and React

Follow common TypeScript and React conventions:

- `camelCase` for variables, functions, and properties.
- `PascalCase` for React components, classes, and types.
- `UPPER_SNAKE_CASE` for shared constants where appropriate.

Examples:

- `getFleetStatus()`
- `activeMissions`
- `DroneCard`
- `MissionStatus`

### Domain Naming

Use consistent domain terminology throughout the application.

Prefer established terms such as:

- `Partner`
- `Drone`
- `Hub` (Mall Pickup Hub: parcel handover point and drone base)
- `Order`
- `Mission`
- `Incident`
- `TelemetryRecord`
- `SystemEvent`

Do not introduce multiple names for the same domain concept without a clear reason.

---

## 4. Backend Standards

### 4.1 Project Organization

Organize backend code around clear responsibilities and domain boundaries.

The intended separation includes:

- API routes and request handling.
- Request and response schemas.
- Domain models and business rules.
- Application services.
- Persistence and repositories.
- Simulation runtime.
- AI integration.
- Shared utilities and configuration.

The exact directory structure should follow the approved architecture.

Avoid creating unnecessary layers that only forward calls without adding meaningful responsibility.

### 4.2 API Routes

API route handlers should remain thin.

They should primarily:

- Receive requests.
- Validate request data.
- Invoke the appropriate application service.
- Translate results into API responses.
- Handle appropriate HTTP status codes and errors.

Do not implement complex dispatch logic, simulation behavior, or mission lifecycle rules directly inside route handlers.

### 4.3 Business Logic

Business logic should live in appropriate domain or application service modules.

Examples include:

- Determining whether a drone is eligible for a mission.
- Selecting a drone for an order.
- Advancing mission state.
- Handling failed deliveries.
- Determining whether a drone can accept another mission.
- Updating charging state.

Business rules should not depend directly on HTTP requests or frontend implementation details.

### 4.4 Validation

Validate external input at application boundaries.

Use typed request and response schemas.

Validation should cover relevant constraints, such as:

- Required fields.
- Valid data types.
- Allowed status values.
- Valid identifiers.
- Relevant numeric ranges.
- Valid operational transitions.

Do not rely on the frontend to enforce backend business rules.

### 4.5 Error Handling

- Use appropriate error types and HTTP status codes.
- Return understandable error messages.
- Do not silently ignore unexpected errors.
- Avoid exposing internal stack traces or sensitive information to clients.
- Log useful diagnostic information when appropriate.

Expected business outcomes should be handled explicitly rather than treated as unexpected application failures.

### 4.6 Persistence

Keep database access separate from business logic where practical.

- Use consistent persistence patterns.
- Avoid duplicating database queries throughout the application.
- Avoid returning raw database implementation details directly to unrelated layers.
- Handle database transactions when an operation changes multiple related records.
- Maintain consistency across related entities.

Database-specific decisions should remain aligned with the approved architecture.

### 4.7 Type Safety

Use Python type hints for function parameters, return values, and important data structures.

Use TypeScript types for application data, component properties, API responses, and important function contracts.

Avoid unnecessary use of untyped values or broad escape hatches such as `Any` and `any`.

When an untyped boundary is unavoidable, validate the data before using it.

---

## 5. Frontend Standards

### 5.1 Component Design

React components should have clear and focused responsibilities.

- Keep components reasonably small.
- Extract reusable UI elements when appropriate.
- Separate complex business-independent logic from presentation.
- Avoid large components that manage unrelated parts of the interface.
- Use clear component and property names.

Do not split every small JSX fragment into a separate component without a practical reason.

### 5.2 State Management

Use the simplest state management approach that satisfies the requirements.

Distinguish between:

- Server state received from the backend.
- Local UI state.
- Temporary interaction state.

The frontend must not become the authoritative source of operational simulation state.

Do not independently simulate drone positions, dispatch decisions, mission progress, or other backend-owned behavior.

### 5.3 API Communication

Keep API communication organized and consistent.

- Reuse shared API utilities or client modules.
- Avoid scattering raw HTTP requests throughout unrelated components.
- Handle loading, success, empty, and error states.
- Keep request and response types consistent with backend contracts.
- Avoid unnecessary repeated requests.

### 5.4 Real-Time Updates

The MVP uses REST polling, not WebSocket (`docs/decisions/0015-frontend-polling-instead-of-websocket.md`). Handle polling in an organized way.

- Use the shared polling hook and `POLL_INTERVALS_MS` (`frontend/src/features/data/`) instead of ad-hoc timers.
- Show loading, error and stale-data states; a failed or timed-out read must not leave the data silently frozen.
- Avoid duplicate pollers for the same resource.
- Stop timers and cancel pending requests when components unmount.
- If WebSocket is ever added, follow the earlier guidance: a shared connection, reconnection handling, no duplicate connections, and cleanup of subscriptions.
- Apply incoming updates consistently to the frontend state.

Real-time messages should update the displayed backend state, not create an independent simulation.

### 5.5 UI and Map Components

Keep visual presentation separate from operational business rules.

Map components should focus on displaying geographic information and user interactions.

Do not put authoritative drone movement logic or dispatch rules inside map components.

Use reusable UI components where they improve consistency across the application.

### 5.6 User Experience

Important interactions should provide clear feedback.

Handle:

- Loading states.
- Empty states.
- Error states.
- Successful operations.
- Disabled controls.
- Confirmation for important actions.

Avoid interfaces that appear interactive but do not perform a real operation.

---

## 6. Simulation and Domain Logic Standards

Simulation code must remain predictable, understandable, and testable.

### 6.1 Deterministic Behavior

Prefer deterministic logic for core operational decisions.

For identical inputs and initial state, deterministic functions should produce identical results.

Avoid unnecessary randomness in business rules.

Randomness may be used intentionally for simulated events, incidents, telemetry variation, and automatic order generation.

When randomness is used, make it possible to control or reproduce it in tests.

### 6.2 State Transitions

Important domain entities should have explicit and valid state transitions.

For example:

- A drone should not accept a new mission while unavailable.
- A completed mission should not continue progressing.
- A charging drone should not be treated as ready for dispatch.
- A failed delivery should produce a coherent order and mission outcome.

Do not change operational status through arbitrary assignments scattered throughout the codebase.

Use appropriate domain operations or services to enforce valid transitions.

### 6.3 Simulation Independence

Simulation execution must not depend on frontend components or browser activity.

Keep simulation progression separate from API request handling.

Avoid duplicating the same simulation logic in multiple places.

### 6.4 Time Handling

Use consistent time handling across the backend.

- Prefer timezone-aware timestamps.
- Store timestamps consistently.
- Avoid mixing local and UTC timestamps without explicit conversion.
- Keep simulation time behavior understandable and testable.

---

## 7. AI Integration Standards

AI integration must remain controlled and isolated from core domain logic.

- Use explicit tool definitions and input schemas.
- Validate tool arguments.
- Limit tools to the information and operations they actually need.
- Handle AI provider errors and timeouts.
- Do not trust AI-generated values without validation.
- Do not allow arbitrary database queries.
- Do not allow AI to bypass backend business rules.

AI-generated recommendations must be distinguishable from confirmed system facts.

State-changing AI operations must follow the approval and validation flow defined in `architecture-context.md`.

Keep provider-specific AI integration separate from unrelated business logic where practical.

---

## 8. Comments and Documentation

Write comments to explain why something is done, not simply repeat what the code already says.

Good comments explain:

- Non-obvious business rules.
- Important architectural decisions.
- Unexpected technical constraints.
- Complex behavior that would otherwise be difficult to understand.

Avoid:

- Obvious comments.
- Large blocks of commented-out code.
- Misleading or outdated explanations.
- Comments that merely restate function names.

Use docstrings for public functions, classes, and complex modules when they provide meaningful context.

Keep documentation consistent with actual behavior.

---

## 9. Testing Standards

Tests should provide confidence that the application behaves correctly.

### Backend Tests

Prioritize tests for:

- Business rules.
- Dispatch eligibility and ranking.
- Valid and invalid state transitions.
- Order and mission lifecycle.
- Drone charging behavior.
- Failed deliveries.
- Incident generation and handling.
- API request validation.
- Important persistence operations.

### Frontend Tests

Prioritize tests for:

- Important user interactions.
- Component behavior.
- Displaying different operational states.
- Loading and error states.
- API integration behavior.
- Real-time update handling where practical.

### Test Quality

- Keep tests deterministic.
- Avoid unnecessary dependence on external services.
- Use meaningful test names.
- Test observable behavior rather than private implementation details.
- Include regression tests for important bug fixes.

Do not introduce unnecessary mocking that makes tests disconnected from actual application behavior.

---

## 10. Dependencies and Technical Debt

Before adding a dependency:

1. Determine whether the functionality already exists in the project.
2. Evaluate whether the dependency is genuinely necessary.
3. Consider its maintenance and complexity costs.
4. Explain the reason for introducing it.

Avoid adding packages for trivial functionality that can be implemented clearly with existing tools.

Do not upgrade or replace dependencies without a clear reason.

Do not leave temporary workarounds, unused dependencies, or unnecessary abstractions without documenting why they remain.

---

## 11. Code Review Checklist

Before considering a code change complete, review the following:

### Structure

- Does each module have a clear responsibility?
- Are architectural boundaries respected?
- Is business logic located in the appropriate layer?
- Is there unnecessary duplication?

### Readability

- Are names descriptive?
- Are functions focused?
- Is the implementation straightforward?
- Are comments useful and accurate?

### Correctness

- Are inputs validated?
- Are errors handled?
- Are state transitions valid?
- Are related records kept consistent?

### Quality

- Are relevant tests included?
- Have appropriate checks been executed?
- Are there unused imports, variables, or dependencies?
- Are there unintended side effects?

### Security

- Are secrets kept out of source code?
- Is external input validated?
- Are sensitive details protected?

---

## 12. Final Quality Principle

Prefer code that a developer can confidently understand, test, and modify.

The goal is not to maximize the number of abstractions, files, classes, or design patterns.

The goal is to maintain a clean and reliable codebase that supports the SkyFleet architecture and can be completed within the project's time constraints.