# TASK 01 — Initial Mapbox Setup

## Objective

Integrate an interactive Mapbox map of the Tricity area into SkyFleet, establishing the map as the main application workspace.

## Functional Requirements

- Integrate Mapbox GL JS into the existing frontend.
- Use a dark map style.
- Set the initial map view to cover the Tricity area: Gdańsk, Sopot, and Gdynia.
- Support standard map interactions, including zooming, panning, and dragging.
- Make the map occupy the available space within the main application workspace.
- Ensure the map responds correctly to browser window resizing and container size changes.

## Technical Requirements

- Follow the existing frontend stack, architecture, and coding conventions.
- Store the Mapbox access token in a frontend environment variable rather than hardcoding it in source code.
- Handle missing or invalid Mapbox access tokens gracefully.
- Provide an appropriate loading state and error handling for map initialization failures.
- Properly clean up the Mapbox map instance when the React component unmounts.
- Avoid unnecessary dependencies and additional abstractions.

## Out of Scope

The following functionality is explicitly excluded from this task:

- Drone markers and animations.
- Drone Hubs and Pickup Stations.
- Backend integration.
- WebSocket communication.
- Telemetry and simulation functionality.
- Drone-related interactions or operational controls.

## Definition of Done

- The Mapbox map renders successfully without runtime errors.
- Users can zoom, pan, and drag the map.
- The initial viewport covers Gdańsk, Sopot, and Gdynia.
- The map occupies the available main workspace area.
- The map behaves correctly when the browser window is resized.
- Missing configuration and map initialization errors are handled appropriately.
- No TypeScript errors are introduced.
- No lint errors are introduced.