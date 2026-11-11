# SkyFleet — Project Overview

## 1. Product Vision

**SkyFleet** is an autonomous urban drone delivery and AI-powered fleet operations platform designed to simulate the logistics network of a near-future delivery company operating across the Tricity area in Poland.

The platform represents a fictional logistics business that uses autonomous delivery drones to transport parcels between retail pickup locations and customer delivery points.

SkyFleet is both:
- A business operations platform for managing an urban drone delivery network.
- A live simulation environment that demonstrates how such a network operates over time.

The application should feel like a professional logistics control center rather than a conventional CRUD administration panel.

## 2. The Problem SkyFleet Addresses

Traditional urban delivery operations involve coordinating orders, pickup locations, available vehicles, delivery destinations, and operational resources.

As the number of deliveries and autonomous vehicles grows, operators need a unified way to understand:
- Which orders need to be fulfilled.
- Which drones are available.
- Where each drone is located.
- Which missions are currently in progress.
- Which hubs have available capacity.
- Which operational incidents require attention.
- How the overall delivery network is performing.

SkyFleet demonstrates how these responsibilities could be coordinated through a centralized, real-time operational platform.

## 3. Business Concept

SkyFleet operates a fictional drone delivery network across Gdańsk, Sopot, and Gdynia.

Its primary customers are physical retail stores located in shopping centers and commercial areas.

Example retail locations include:
- Galeria Bałtycka.
- Forum Gdańsk.
- Galeria Riviera.
- Galeria Metropolia.

These locations serve as examples for the simulated business network, not as claims of real commercial partnerships.

### Delivery Workflow

A typical delivery follows this process:

1. A customer purchases a product from a participating retail store.
2. The store prepares the parcel and submits a delivery order through the SkyFleet network.
3. The parcel is deposited at a designated Pickup Station.
4. The system receives the order and evaluates available delivery resources.
5. The Dispatch Engine selects a suitable drone.
6. The drone receives a mission and travels to the pickup location.
7. The parcel is collected and transported to the customer's delivery point.
8. The delivery is completed, or an operational exception is recorded.
9. After completing its mission, the drone returns to the nearest suitable Drone Hub.
10. At the hub, it may charge, wait for another mission, or undergo maintenance.

The system should represent this workflow through coherent operational states and visible changes over time.

## 4. Operational Infrastructure

SkyFleet's network consists of several types of locations.

### Drone Hubs

Drone Hubs are the main operational bases of the delivery network.

They provide:
- Drone parking and staging.
- Battery charging.
- Basic maintenance and servicing.
- Preparation for upcoming missions.
- Operational capacity management.

A drone does not necessarily have to return to the hub from which it originally departed. After completing a mission, the system may select another suitable hub based on the simulated operational situation.

### Pickup Stations

Pickup Stations are designated parcel collection points located near participating retail businesses.

Their purpose is to make parcels available to the drone delivery network.

A Pickup Station is not the same as a Drone Hub. A hub may serve multiple pickup locations.

### Delivery Points

Delivery Points represent destinations where parcels are delivered.

For the MVP, delivery destinations may be selected from a predefined set of realistic demonstration locations rather than requiring arbitrary address validation.

## 5. Main User

The primary user is a **SkyFleet Operations Operator**.

The operator uses the platform to monitor the delivery network, understand current operational conditions, investigate incidents, and make decisions when intervention is required.

The interface should help the operator answer questions such as:

- What is happening across the network right now?
- Where are the drones?
- Which orders are waiting for fulfillment?
- Which deliveries are in progress?
- Which hubs have available capacity?
- Are there any incidents requiring attention?
- Why did a particular drone or mission enter its current state?
- What should be done next?

The product should prioritize operational clarity, situational awareness, and fast access to relevant information.

## 6. Core Product Capabilities

The long-term product vision includes the following capabilities.

### 6.1 Live Fleet Monitoring

Display the drone fleet on an interactive map.

Operators should be able to understand:
- Drone locations.
- Current operational states.
- Assigned missions.
- Battery levels.
- Basic telemetry.
- Hub locations and availability.

### 6.2 Order Management

Manage incoming delivery orders and track their progress through the fulfillment lifecycle.

Orders should have clear statuses and relationships with pickup locations, delivery points, and missions.

### 6.3 Fleet & Mission Management

Monitor drones and their assigned missions.

The system should represent operational transitions such as:
- Available.
- Assigned.
- Traveling to pickup.
- Collecting a parcel.
- Delivering.
- Returning to a hub.
- Charging.
- Maintenance.
- Emergency or unavailable states.

The final set of states should be defined consistently in the domain model.

### 6.4 Automated Dispatch

The system should automatically assign eligible drones to incoming orders.

Dispatch decisions are based on deterministic business rules and operational constraints.

The platform should be able to explain why a drone was selected or why no suitable drone was available.

### 6.5 Operational Simulation

SkyFleet includes a continuously running simulation of the delivery network.

The simulation generates mock operational activity, including:
- Incoming orders.
- Drone movement.
- Mission progression.
- Battery consumption and charging.
- Drone availability changes.
- Operational events.
- Simulated incidents.

The simulation should create a believable impression of a functioning logistics operation.

It must not depend on an open frontend session.

### 6.6 Incident Monitoring & Investigation

The system should detect simulated operational problems and make them visible to the operator.

Example incidents include:
- Elevated motor temperature.
- Failed delivery attempt.
- Drone unable to continue its assigned mission.
- Emergency landing simulation.
- Unexpected operational conditions.

The system should preserve relevant event and telemetry history so that incidents can be investigated.

### 6.7 AI Operations Assistant

SkyFleet includes an AI-powered Fleet Operations Agent.

The agent helps operators understand the current operational situation by answering natural-language questions, investigating incidents, and generating recommendations.

Examples:
- "Which drones are currently unavailable and why?"
- "Why was this order not assigned?"
- "Summarize the active incidents."
- "Which hub has the most available capacity?"
- "What happened during this drone's last mission?"

The AI assistant should rely on controlled backend tools to retrieve operational information.

It may recommend actions, but any operation that changes system state must require explicit operator approval and backend validation.

## 7. Simulation Philosophy

SkyFleet is a software simulation, not a real drone control system.

All drone movement, telemetry, incidents, and operational events are simulated.

The goal is to demonstrate believable business processes and coherent system behavior rather than physical accuracy.

Important principles:

- Simulated states must remain internally consistent.
- Operational events should have understandable consequences.
- Drone movement should correspond to mission progression.
- Battery levels should change in a plausible way.
- Charging should affect drone availability.
- Incidents should influence the relevant drone, mission, or order.
- The frontend should visualize backend-owned simulation state.
- The simulation should continue independently of the frontend.

Do not introduce unnecessary physical modeling, real-world flight control, regulatory enforcement, or external hardware integrations.

## 8. Product Experience & Visual Direction

SkyFleet should look and feel like a modern autonomous logistics operations center.

The primary interface direction is:
- Dark visual theme.
- Map-first operational dashboard.
- Interactive Mapbox map centered on the Tricity area.
- Clearly distinguishable Drone Hubs and moving drones.
- Contextual information panels.
- Operational status indicators.
- Data-rich but readable interface.
- Real-time updates without unnecessary page refreshes.

The map is the primary spatial view of the network, while supporting panels provide operational details and controls.

The interface should favor clarity and information hierarchy over excessive decoration.

Detailed UI specifications belong in `ui-context.md`.

## 9. Project Scope & Constraints

SkyFleet is an MVP developed as a recruitment assignment.

The implementation must balance product quality, architectural clarity, and delivery time.

### In Scope

- A working frontend communicating with a backend API.
- Drone Hub and Pickup Station representation.
- Order, drone, and mission management.
- Deterministic dispatch logic.
- A backend-owned simulation runtime.
- Real-time operational updates.
- Simulated incidents and event history.
- A useful AI operations assistant.
- A polished demonstration experience.
- Public deployment and clear project documentation.

### Out of Scope

Unless explicitly approved as a future extension, do not implement:

- Real drone hardware integrations.
- Real flight control.
- Accurate aerodynamic or physical flight simulation.
- Real-world airspace management.
- Regulatory approval workflows.
- Real weather integrations.
- Actual parcel tracking hardware.
- Production-grade logistics infrastructure.
- Unnecessary microservices or distributed infrastructure.

### Scope Management

The project should be developed incrementally.

Prioritize a working end-to-end application over an extensive set of incomplete features.

The current implementation priorities and milestone status are maintained in `progress-tracker.md`.

## 10. Demonstration Goals

The final application should support a short, convincing demonstration for the job recruitment process.

The demonstration should show:

1. The operator opening the SkyFleet dashboard.
2. A dark interactive map of the Tricity area.
3. Drone Hubs displayed on the map.
4. Incoming orders appearing in the system.
5. Drones moving through simulated missions.
6. Drone status and battery changes.
7. Deliveries being completed.
8. Drones returning to hubs and charging.
9. An operational incident being detected and investigated.
10. The AI Operations Assistant answering a question using current system information.

The demonstration should communicate that SkyFleet is a coherent operational system rather than a collection of disconnected UI screens.

---

## 11. Project Success Criteria

SkyFleet will be considered successful when it demonstrates:

- A clear and understandable product concept.
- A coherent separation of frontend and backend responsibilities.
- A maintainable and appropriately structured codebase.
- Correct REST API communication and CORS configuration.
- A visually polished and usable interface.
- A functioning backend-owned simulation.
- Consistent operational state transitions.
- Meaningful use of AI rather than AI added purely for decoration.
- A reliable public demonstration.
- Clear documentation explaining the architecture, implementation, and use of AI during development.

**The central product principle:**

SkyFleet should make a simulated autonomous drone delivery network feel like a real, continuously operating logistics business — understandable, observable, and manageable from one operational control center.