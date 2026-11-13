# ADR 0003 — Three.js / React Three Fiber for the drone 3D viewer

**Status:** Accepted (2026-11-13, approved with Feature 016A)

## Context

`context/ui-context.md` asks for 3D representations where they serve an operational purpose, but
not to add visualization libraries before a feature requires them. Feature 016 (Drone Technical
Inspector) requires an interactive 3D drone model. The frontend is React 19 with no 3D library.

## Decision

- Use `three`, `@react-three/fiber` and `@react-three/drei` (for orbit controls, rounded boxes,
  environment lighting and contact shadows), plus `@types/three`, pinned to exact versions.
- Build the model procedurally in code: no downloaded or licensed assets.
- Load the viewer lazily so the 3D code is a separate chunk, fetched only when a viewer is shown.

## Consequences

- The viewer chunk is about 1,008 kB minified (273 kB gzip) once the app imports it; the main chunk
  is unaffected until then. Replacing drei helpers with plain Three.js could reduce it later.
- `@react-three/fiber@9.8.2` peers on `react >=19 <19.4`; the project uses React 19.3.1. Check this
  range before upgrading React.
- WebGL is required; the viewer shows a text fallback otherwise.
