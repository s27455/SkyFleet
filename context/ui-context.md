# SkyFleet — UI & UX Context

## 1. Design Vision

SkyFleet should look and feel like a modern autonomous logistics operations platform.

The interface should combine a technical, data-driven character with a clean, approachable, and intuitive user experience.

The primary design direction is:

**Dark Technical Theme — Modern, Minimal, Map-First, UX-Driven.**

The goal is not to create an overloaded futuristic control panel filled with indicators, glowing elements, and decorative visualizations.

Instead, SkyFleet should feel like a polished modern SaaS product designed for operators who need to understand and manage a complex operational environment.

User experience, clarity, and information hierarchy always take priority over visual complexity.

## 2. Core Design Principles

### 2.1 UX First

Every interface element should have a clear purpose.

- Prioritize usability over decorative effects.
- Make important information easy to find.
- Keep interactions predictable and consistent.
- Avoid unnecessary clicks and confusing navigation.
- Provide clear feedback after user actions.
- Make operational states understandable at a glance.

Do not introduce visual elements or interactions that make the application harder to use merely to make it look more technical.

### 2.2 Minimalism Without Losing Information

The application is an operational platform, so it must present meaningful data without overwhelming the operator.

Use a balanced information density.

- Display the most important information by default.
- Group related information logically.
- Use contextual panels for additional details.
- Avoid excessive cards, borders, dividers, and decorative containers.
- Avoid displaying the same information in multiple places without a clear reason.
- Prefer meaningful visual hierarchy over simply making everything smaller.

### 2.3 Progressive Disclosure

Detailed operational information should be available when needed, rather than permanently occupying screen space.

Examples:
- Selecting a drone opens its operational details.
- Selecting a Mall Pickup Hub reveals its location and status.
- Selecting an incident provides access to its details and history.
- Advanced telemetry can be displayed in contextual detail views.

The interface should support moving naturally from a high-level operational overview to more detailed information.

### 2.4 Consistency

Use consistent patterns throughout the application.

- Similar entities should use similar interaction patterns.
- Status indicators should have consistent meanings and colors.
- Spacing, typography, and component styling should follow shared design rules.
- Navigation and contextual panels should behave predictably.
- Reuse existing components where appropriate.

Avoid implementing visually inconsistent components independently.

## 3. Responsive Design

SkyFleet must support Responsive Web Design (RWD).

The interface should adapt to desktop, tablet, and mobile screens.

### Desktop

Desktop is the primary target for the operations dashboard.

- Use available screen space efficiently.
- Give the map a prominent position.
- Keep navigation and operational panels accessible.
- Avoid excessive horizontal scrolling.
- Support information-rich layouts without visual clutter.

### Tablet

- Adapt panel widths and navigation.
- Preserve access to the main map and essential operational information.
- Avoid squeezing the desktop layout into a smaller viewport.

### Mobile

Mobile is a secondary but supported experience.

- Prioritize essential operational information.
- Use collapsible navigation and contextual panels.
- Allow map interaction without obstructing the entire screen.
- Stack content vertically where appropriate.
- Ensure controls remain touch-friendly.
- Avoid requiring hover interactions.

Do not treat responsiveness as simply scaling desktop components down. Adapt layouts and interaction patterns to the available space.

## 4. Visual Direction

### 4.1 Theme

Use a dark technical visual theme.

The interface should primarily use:
- Deep charcoal and graphite backgrounds.
- Slightly lighter surfaces for panels and interactive areas.
- Subtle borders and separators.
- High-contrast primary text.
- Muted secondary text.
- Restrained accent colors.

Avoid pure black as the default background unless there is a specific visual reason.

The overall result should be comfortable to look at during longer operational sessions.

### 4.2 Accent Colors

Use a restrained accent palette.

Preferred direction:
- Electric cyan / blue for primary interactions and selected elements.
- Green for healthy or operational states.
- Amber for warnings and attention-required states.
- Red for critical incidents and failures.
- Neutral gray for inactive or secondary information.

Color must communicate meaning, not serve purely as decoration.

Do not use accent colors excessively. Reserve strong colors for important interactions and operational states.

### 4.3 Typography

Typography should be modern, readable, and consistent.

- Use a clear typographic hierarchy.
- Keep headings distinct from supporting information.
- Use readable font sizes.
- Avoid unnecessarily small labels.
- Use tabular or monospaced numerals where useful for telemetry and technical values.
- Do not rely on typography alone to communicate status.

### 4.4 Surfaces & Components

Use clean, restrained surfaces.

- Prefer subtle separation between interface sections.
- Use consistent corner radii.
- Avoid excessive shadows and glowing effects.
- Keep borders subtle.
- Use cards only when they improve grouping and readability.
- Maintain consistent spacing throughout the application.

Avoid excessive nesting of cards inside cards.

## 5. Styling Technology & Tailwind CSS

Use **Tailwind CSS** as the primary styling solution for the frontend.

Tailwind should support a consistent design system and responsive layouts without encouraging unnecessarily complex component styling.

### Guidelines

- Prefer Tailwind utility classes for layout, spacing, typography, colors, responsiveness, and common visual patterns.
- Use responsive utility variants to implement adaptive layouts.
- Maintain consistent design tokens for colors, spacing, typography, borders, and radii.
- Prefer existing design tokens and shared patterns over arbitrary one-off values.
- Extract reusable React components when styling patterns or UI structures are repeated.
- Avoid unnecessarily long and difficult-to-maintain class lists.
- Use custom CSS only when Tailwind utilities are insufficient or when implementing specialized styling, animations, or third-party integrations.
- Keep component styling consistent with the global SkyFleet design direction.
- Do not introduce additional styling frameworks without a clear technical reason.

Tailwind CSS should support the design system, not replace thoughtful UI architecture or reusable components.

Do not build a large design system prematurely. Establish shared tokens and patterns as the application grows.

## 6. Main Dashboard & Map-First Experience

The map is the primary spatial view of SkyFleet.

It should occupy a prominent part of the main operational dashboard and provide a clear overview of the simulated drone delivery network across the Tricity area.

The main dashboard should prioritize:
- Geographic awareness.
- Drone locations and operational states.
- Mall Pickup Hub locations.
- Active deliveries and missions.
- Important operational alerts.
- Quick access to relevant details.

The map should integrate naturally with the surrounding interface rather than feel like an isolated embedded component.

### Map Interaction Principles

- Map markers must be visually distinguishable.
- Important states should be recognizable without opening additional panels.
- Selecting a marker should provide relevant contextual information.
- Interactions should not unnecessarily obstruct map visibility.
- Map controls should remain accessible and intuitive.
- Avoid excessive marker labels and overlapping information.

The map should remain useful at different viewport sizes.

## 7. Contextual Detail Views & Interactive Visualizations

SkyFleet should support contextual detail views that allow operators to move from a high-level network overview to a focused inspection of individual operational entities.

Examples include:
- Selecting a drone on the map to open its detailed operational view.
- Inspecting drone telemetry through interactive visual representations.
- Visualizing equipment health and simulated component-level incidents.
- Exploring operational history and related events.

Where appropriate, use interactive visualizations and 3D representations to make complex technical information easier to understand.

These views should follow the global design principles:
- Clear information hierarchy.
- Minimal visual clutter.
- Contextual disclosure of detailed information.
- Consistent interaction patterns.
- Responsive layouts.
- Smooth, purposeful transitions between overview and detail views.

3D visualizations should serve an operational purpose rather than exist purely as decoration. Their displayed values must correspond to the current backend simulation state.

Detailed layouts, component interactions, telemetry specifications, and visualization requirements should be documented in separate feature specifications when implementation is planned.

Do not introduce complex visualization libraries before a specific feature requires them.

## 8. Data Visualization & Operational Status

SkyFleet presents operational and technical information, so data visualization should prioritize clarity and immediate understanding.

Examples include:
- Battery level indicators.
- Drone operational status.
- Hub status and orders awaiting pickup.
- Mission progress.
- Telemetry values.
- Incident severity.
- Historical trends.

Guidelines:
- Use charts only when they communicate something better than a simple value or status indicator.
- Avoid unnecessary gauges and decorative graphs.
- Keep units and labels explicit.
- Use consistent status colors.
- Make critical information visually prominent without making the entire interface visually aggressive.
- Provide context for values when needed.

Operational information should be easy to scan quickly.

## 9. Interaction & Motion

Interactions should feel responsive, natural, and predictable.

Use purposeful animations for:
- Opening and closing contextual panels.
- Selecting map markers.
- Navigating between overview and detail views.
- Displaying notifications and operational events.
- Updating visual operational states.

Animation guidelines:
- Keep transitions short and subtle.
- Avoid unnecessary movement.
- Do not delay interactions with decorative animations.
- Avoid excessive bouncing, pulsing, or glowing.
- Respect reduced-motion preferences where possible.

Real-time updates should be visually understandable without causing distracting layout shifts.

## 10. States & Feedback

Every important interactive component should account for its relevant UI states.

Examples:
- Loading.
- Empty.
- Error.
- Success.
- Selected.
- Disabled.
- Warning.
- Critical.

Provide clear feedback when:
- Data is being loaded.
- An operation has completed.
- An operation has failed.
- New incidents appear.
- A drone changes operational state.
- The connection to the backend or real-time service is unavailable.

Avoid relying exclusively on color to communicate important information. Combine color with text, icons, or other visual indicators.

## 11. Accessibility & Usability

Accessibility should be considered throughout implementation.

- Maintain sufficient contrast.
- Use semantic HTML elements.
- Provide accessible labels for interactive controls.
- Support keyboard navigation where appropriate.
- Avoid hover-only functionality.
- Ensure touch targets are comfortable on mobile.
- Provide meaningful alternative text for informative images.
- Respect reduced-motion preferences.
- Make operational statuses understandable without relying only on color.

## 12. Component & Implementation Guidelines

The UI should be built from reusable, maintainable components.

- Prefer reusable components over duplicated implementations.
- Keep presentation separate from business logic.
- Avoid unnecessarily large components.
- Use consistent component APIs and naming.
- Keep map-specific behavior separate from general dashboard components.
- Reuse shared visual tokens for colors, spacing, typography, and borders.
- Ensure components handle their loading, empty, and error states.

Before introducing a new UI library or visualization dependency, evaluate whether the existing stack already provides an appropriate solution.

Do not add dependencies simply because they are popular or visually appealing.

## 13. Iterative UI Development

The UI should evolve through implementation, visual review, and refinement.

The initial design direction described in this document is a foundation, not an immutable specification.

When implementing a new screen or feature:

1. Review this document and relevant feature specifications.
2. Inspect existing UI patterns and reusable components.
3. Propose a clear layout and interaction approach.
4. Implement a focused, working version.
5. Verify the result at relevant viewport sizes.
6. Review usability, consistency, and visual hierarchy.
7. Refine based on feedback.
8. Update this document when a change establishes a new global design principle.

Small local adjustments do not require documentation changes.

Feature-specific layouts and detailed interactions should be documented separately under `docs/features/`.

Do not assume that every future screen must follow the exact same layout. Preserve the global design language while adapting the interface to the needs of each feature.

---

## 14. Final Design Principle

**SkyFleet should feel like a modern, intelligent, and approachable operations platform — technically sophisticated underneath, but simple and intuitive to operate.**

Prioritize clarity over density, usability over decoration, and meaningful information over visual noise.

The interface should help operators understand what is happening, identify what requires attention, and decide what to do next.