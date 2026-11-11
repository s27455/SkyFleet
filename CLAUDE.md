# SkyFleet — Claude Code Project Instructions

## 1. Project Overview

SkyFleet is an Autonomous Urban Drone Delivery & AI Operations Platform.

It simulates a fictional logistics company operating a fleet of autonomous delivery drones across the Tricity area in Poland.

The platform allows operators to monitor drones, manage partner delivery orders and missions, inspect Mall Pickup Hubs, track simulated telemetry, investigate incidents, and interact with an AI-powered Fleet Operations Agent.

The application is a recruitment project focused on demonstrating:

- Clean architecture and separation of responsibilities.
- A functional frontend connected to a backend API.
- Well-designed REST API endpoints.
- A continuously running backend simulation.
- Real-time operational updates.
- Clear, maintainable, and testable code.
- Thoughtful UX/UI.
- Meaningful AI integration.

The goal is to build a convincing and usable MVP, not a production-grade autonomous aviation system.

## 2. Documentation — Source of Truth

Before making architectural decisions, implementing new features, or modifying existing structures, consult the relevant project documentation.

The following files define the project context:

| Document | Purpose |
|---|---|
| `business-rules.md` | Confirmed business rules and MVP behavior, plus open business questions (authoritative for business behavior) |
| `project-overview.md` | Product vision, business concept, workflows, and MVP scope |
| `architecture-context.md` | System architecture, technologies, domain boundaries, and integrations |
| `code-standards.md` | Coding conventions, implementation standards, and testing expectations |
| `ui-context.md` | Global UI/UX direction, design principles, and Tailwind CSS guidelines |
| `ai-workflow-rules.md` | Collaboration rules, planning workflow, and development constraints |
| `progress-tracker.md` | Project roadmap, priorities, implementation status, and open decisions |

These documents are the primary source of truth.

### Documentation Rules

- Read `business-rules.md` before implementing or changing any business behavior.
- Read `project-overview.md` and `architecture-context.md` before proposing major architectural changes.
- Read `code-standards.md` before implementing application code.
- Read `ui-context.md` before designing or modifying frontend interfaces.
- Follow `ai-workflow-rules.md` throughout the development process.
- Check `progress-tracker.md` before choosing the next implementation task.
- Update relevant documentation when an approved decision materially changes the project.

Do not silently introduce architectural or product decisions that contradict these documents.

If documentation is ambiguous or conflicting, identify the conflict. Classify unresolved questions as: (1) Blocker — a decision is genuinely required before the current task can proceed safely; (2) MVP simplification — use a clearly stated, reversible assumption when it does not contradict an approved business rule; or (3) Future — record it for later without blocking the current task. Ask the user only about Blockers. Never present an assumption or recommendation as an approved business decision. Consult `context/business-rules.md` for confirmed rules and open questions. Avoid repeatedly raising questions already answered there.

## 3. Technology Direction

The intended technology stack is:

### Frontend

- React.
- TypeScript.
- Tailwind CSS.
- Mapbox GL JS.

### Backend

- Python.
- FastAPI.
- Pydantic.
- SQLAlchemy.

### Runtime & Testing

- Separate Simulation Worker process.
- Pytest.
- REST API.
- WebSocket for real-time updates.

### AI

- LLM integration through controlled backend tools.
- Fleet Operations Agent.
- Human approval for state-changing AI-assisted actions.

Some implementation decisions, including the database and hosting provider, remain open.

Do not assume that an undecided technology has already been selected.

Before introducing a new dependency or infrastructure component, explain why it is needed and whether the existing stack is sufficient.

## 4. Core Architectural Rules

### Backend Owns Operational State

The backend is the source of truth for:

- Orders.
- Drones.
- Partners.
- Mall Pickup Hubs (parcel handover locations and drone operational bases).
- Missions.
- Dispatch decisions.
- Charging.
- Maintenance.
- Incidents.
- Telemetry.
- Simulation state.

The frontend must not become the owner of operational or simulation logic.

### Modular Monolith

Use a modular monolith with clear domain boundaries.

The main backend and Simulation Worker may run as separate processes while sharing domain modules and persistence.

Do not introduce microservices, message brokers, Kubernetes, or distributed infrastructure without a concrete requirement.

### Simulation Independence

The Simulation Worker must operate independently of the frontend.

An open browser or active WebSocket connection must never be required for simulation execution.

### Deterministic Business Logic

Dispatch, eligibility checks, operational rules, and state transitions must be deterministic and testable.

Do not use an LLM for decisions that should be handled by predictable business rules.

### AI Boundaries

AI should support operators by retrieving information, investigating incidents, explaining decisions, and proposing recommendations.

AI must use controlled backend tools rather than unrestricted database access.

State-changing AI-assisted operations require explicit operator approval and backend validation.

## 5. Development Workflow

Follow a structured, incremental development process.

For every meaningful feature:

1. Review the relevant documentation.
2. Inspect the existing implementation.
3. Understand dependencies and affected modules.
4. Identify the intended outcome.
5. Propose an implementation plan.
6. Identify important edge cases and potential risks.
7. Wait for approval when the task involves significant architectural decisions or expands the agreed scope.
8. Implement in small, logical steps.
9. Run relevant tests and verification commands.
10. Review the resulting changes.
11. Update documentation and `progress-tracker.md` when appropriate.
12. Summarize what changed and what remains.

Do not jump directly into coding when a task requires planning.

For small, clearly defined tasks, avoid unnecessary planning overhead.

## 6. Scope Control

The project is an MVP with a defined delivery deadline.

Prioritize:

- Working end-to-end workflows.
- Clear architecture.
- Reliable simulation behavior.
- A polished and usable interface.
- Meaningful demonstration value.

Avoid:

- Premature optimization.
- Unnecessary abstractions.
- Over-engineering.
- Features unrelated to the MVP.
- Infrastructure added solely for architectural appearance.
- Large refactors unrelated to the current task.

When a feature is significantly more complex than its MVP value justifies, propose a simpler alternative.

Do not expand the project scope without discussing it first.

## 7. Frontend Rules

- Use React and TypeScript.
- Use Tailwind CSS as the primary styling solution.
- Follow `ui-context.md` for global visual and interaction principles.
- Keep components focused and reusable.
- Separate API communication from presentation components.
- Use typed API contracts.
- Handle loading, empty, error, and disconnected states.
- Keep business logic out of presentation components.
- Avoid hardcoding operational entities in UI components.
- Use backend-provided data for operational visualizations.

The main interface should remain map-first and focused on operational awareness.

## 8. Backend Rules

- Use FastAPI for HTTP and WebSocket interfaces.
- Keep API route handlers thin.
- Place business logic in appropriate domain or application services.
- Validate incoming data.
- Use clear and consistent API contracts.
- Keep persistence concerns organized.
- Implement explicit state transitions.
- Avoid circular dependencies.
- Add meaningful tests for important business behavior.

Do not allow API handlers to become containers for simulation or domain logic.

## 9. Simulation Rules

The simulation represents believable business operations using mock data and simulated events.

It should support:

- Automatically generated orders.
- Drone movement.
- Mission progression.
- Pickup and delivery.
- Post-delivery return to the nearest suitable Hub, with or without the parcel (see `business-rules.md`).
- Battery consumption and charging.
- Operational waiting states.
- Simulated telemetry.
- Incident generation and handling.

Simulation logic must remain independent of frontend rendering.

Do not implement real flight physics, real hardware integration, or unnecessary aviation-specific validation.

The goal is a coherent operational simulation, not a physically accurate drone simulator. Weather and airspace availability are simulated inputs; do not integrate real services. Re-check simulated operating conditions immediately before takeoff. After each delivery attempt, a drone returns to the nearest suitable Hub; it returns with the parcel if delivery/collection fails. At the Hub, returned parcels are unloaded and drones receive a quick inspection before charging, maintenance, or waiting for another task. Idle, sufficiently charged drones may be repositioned to balance Hub fleet distribution, subject to Hub capacity and deterministic rules. See `business-rules.md` for confirmed details and unresolved policy choices.

## 10. AI Integration Rules

Implement AI only where it provides meaningful operational value.

Prioritize:

1. Fleet Operations Agent.
2. Incident investigation.
3. Operational explanations and recommendations.
4. Carefully controlled operator-approved actions.

Use narrow, typed backend tools.

Never expose unrestricted SQL, database access, or arbitrary backend execution to the LLM.

Keep deterministic operational decisions outside the LLM.

## 11. Code Quality & Testing

Follow `code-standards.md`.

General requirements:

- Prefer readable and maintainable code.
- Use meaningful names.
- Avoid unnecessary complexity.
- Keep functions and components focused.
- Handle errors explicitly.
- Avoid duplicated business logic.
- Use types appropriately.
- Add tests for important behavior.
- Do not claim that tests pass unless they have actually been executed.

Before finishing a task, inspect the changes and identify any known limitations.

Do not silently ignore failed tests, linting errors, or build failures.

## 12. Git & Project Safety

- Never overwrite or discard existing user changes without permission.
- Inspect Git status before potentially destructive operations.
- Do not commit secrets, credentials, or real API keys.
- Keep environment-specific configuration out of version control.
- Maintain a useful `.gitignore`.
- Do not create commits unless explicitly requested.
- Prefer small, understandable changes.

## 13. Communication Expectations

Act as a technical development partner, not just a code generator.

When working with the project:

- Explain important technical decisions in understandable language.
- Distinguish between confirmed requirements and suggestions.
- State assumptions explicitly.
- Highlight risks and trade-offs.
- Ask for clarification when an important decision is genuinely ambiguous.
- Do not repeatedly ask about decisions already documented.
- Recommend simpler approaches when they satisfy the requirement.
- Do not pretend that an implementation is complete if it has not been verified.

The user is learning Claude Code and developing the project iteratively. Explain unfamiliar concepts when they are relevant, without overwhelming the user with unnecessary theory.

## 14. Definition of Done

A task is considered complete only when:

- The requested functionality has been implemented.
- The implementation follows the relevant architecture and coding standards.
- Relevant tests or verification steps have been executed.
- Known errors and limitations have been reported.
- Relevant documentation has been updated when necessary.
- The result has been summarized clearly.

Do not mark planned work as completed merely because files or scaffolding have been created.

---

## Final Principle

**Build SkyFleet incrementally, keep the architecture understandable, preserve backend ownership of operational behavior, and prioritize a working, polished MVP over unnecessary complexity.**
