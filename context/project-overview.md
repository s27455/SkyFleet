# SkyFleet — Project Overview

## 1. Product Vision

**SkyFleet** is an autonomous urban drone delivery and AI-powered fleet operations platform designed to simulate the logistics network of a near-future delivery company operating across the Tricity area in Poland.

The platform represents a fictional B2B logistics business that uses autonomous delivery drones to transport parcels from Mall Pickup Hubs to delivery addresses provided by the end customers of SkyFleet's business partners.

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
- Which hubs have orders awaiting pickup.
- Which operational incidents require attention.
- How the overall delivery network is performing.

SkyFleet demonstrates how these responsibilities could be coordinated through a centralized, real-time operational platform.

## 3. Business Concept

SkyFleet operates a fictional drone delivery network across Gdańsk, Sopot, and Gdynia.

SkyFleet is a **B2B platform**. Its customers are **Partners**: businesses such as restaurants, fast-food outlets, and retail stores located in shopping malls.

End customers order directly from a Partner and, at checkout, may choose drone delivery and enter a delivery address. The end customer is **not** a direct SkyFleet customer or platform user; the Partner submits the delivery request to SkyFleet.

Example malls (for the simulated network) include:

- Galeria Bałtycka.
- Forum Gdańsk.
- Centrum Riviera.
- Centrum Handlowe Osowa.

These locations serve as examples for the simulated business network, not as claims of real commercial partnerships.

### Delivery Workflow

A typical delivery follows this process:

1. A customer places an order with a SkyFleet Partner and chooses drone delivery, providing a delivery address.
2. The Partner submits a delivery request (with order information) to SkyFleet.
3. The customer deposits the parcel in a partner parcel locker, and it is transported to the selected Mall Pickup Hub; an order can exist before the parcel reaches the Hub, and only a parcel confirmed at the Hub can be assigned to a drone.
4. The system evaluates available delivery resources and the Dispatch Engine selects a suitable drone.
5. The drone receives a mission, arrives at the hub, and collects the parcel.
6. The drone delivers the parcel to the delivery address from the order.
7. The delivery is completed, or an operational exception is recorded.
8. After every delivery attempt, the drone returns to the nearest suitable Hub; after an unsuccessful attempt it retains the parcel.

The system should represent this workflow through coherent operational states and visible changes over time. The primary BPMN process is maintained in `docs/diagrams/skyfleet-main-process.bpmn` (rendered as `skyfleet-main-process.svg`). Supporting MVP rules and unresolved details are maintained in `business-rules.md`.

## 4. Operational Infrastructure

### Mall Pickup Hubs

A Hub is a location inside a shopping mall (potentially on an upper floor or designated logistics area) that combines two responsibilities:

- Parcel handover and pickup: parcels deposited by customers in partner parcel lockers are transported to the Hub, where they are held in the Hub's designated parcel compartment/locker until a drone collects them. For the MVP, parcel validation is assumed to have been completed successfully before SkyFleet begins the delivery workflow, and parcel-locker integration is out of scope.
- Drone operations: Hubs are also the locations where drones are stored, charged, inspected, maintained, prepared, and made ready for missions.

A Hub therefore serves both as a parcel pickup point and as the operational home/base for the drone fleet. Do not model a separate DroneBase for the MVP.

The initial planning capacity is 50 drones per Hub. This is drone accommodation capacity, not parcel or order capacity. Occupancy counts only drones physically docked at the Hub: a drone in flight occupies no Hub, mission assignment reserves nothing, and actual occupancy must never exceed 50. Return-Hub capacity is checked when a mission is planned; the flight simulation rechecks it before landing. The operational target is about 40 occupied places (80%), above which a future rebalancing feature should relocate suitable idle drones (see `business-rules.md`).

Partners may use any available Hub in the SkyFleet network. A specific Order identifies the Hub where its parcel will be handed over; a Partner is not permanently restricted to one Hub.

### Delivery Addresses

A Delivery Address is supplied by the end customer to the Partner and passed to SkyFleet as part of the Partner's delivery request. For the MVP, address data is stored directly on the Order rather than in a separate DeliveryAddress entity.

### Drone Operations and Return

After a delivery attempt, the drone returns to the nearest suitable Hub, which may differ from the pickup Hub. After a successful handover the drone returns without the parcel. If the recipient does not collect the parcel or the delivery otherwise fails, the drone retains the parcel and returns with it.

At the Hub, the drone is unloaded if it is carrying a returned parcel, receives a quick post-flight inspection, and proceeds to charging or maintenance as appropriate before waiting for another task.

The detailed definition of a suitable return Hub, handling of returned parcels, and exceptional cases such as a full Hub remain documented open decisions in `business-rules.md`.

### Environmental and Airspace Checks

For the MVP, weather conditions and airspace availability are simulated inputs. The system checks operational conditions during dispatch and performs a second pre-flight check immediately before takeoff. A simulated restriction may prevent or delay takeoff. Do not integrate real weather services, real air traffic systems, or real emergency-service feeds.

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
- Hub locations and status.

### 6.2 Order Management

Manage incoming B2B delivery requests submitted by Partners and track their progress through the fulfillment lifecycle.

Orders should have clear statuses and relationships with the originating Partner, the pickup Hub, the delivery address, and missions.

### 6.3 Fleet & Mission Management

Monitor drones, their operational states, telemetry, and assigned missions.

The MVP should represent states such as:

- Available / waiting for assignment.
- Waiting for acceptable weather or operational conditions.
- Assigned to an order or mission.
- Preparing/loading at a Hub.
- Performing pre-flight checks.
- In flight to the delivery address.
- Waiting at the delivery location for parcel collection.
- Returning to a Hub, with or without a parcel.
- Charging.
- Under inspection or maintenance.
- Unavailable due to a fault or incident.

The final state names and permitted transitions must be defined consistently in the domain model and `business-rules.md`. These are operational examples, not a finalized exhaustive enum.

Operators should be able to inspect a drone's telemetry and issue supported interventions such as requesting a return or landing. The exact command semantics, safety constraints, and emergency behavior remain subject to MVP rules and must be validated by the backend.

A selected drone should have a detailed view, potentially including a 3D model, alongside its current telemetry and operational condition.

Telemetry may include position, altitude, speed, heading, battery level, estimated time to destination, motor temperature, battery temperature, and other useful simulated health indicators. The backend owns telemetry and simulation state.

### 6.4 Automated Dispatch

The system should automatically assign eligible drones to incoming orders.

Dispatch decisions are based on deterministic business rules and operational constraints.

The platform should be able to explain why a drone was selected or why no suitable drone was available.

### 6.5 Operational Simulation

SkyFleet includes a continuously running backend-owned simulation of the delivery network.

The simulation should generate and evolve:

- Incoming Partner orders.
- Parcel handover readiness at Hubs (the MVP assumes parcel validation has already succeeded).
- Drone assignment, preparation, loading, and pre-flight checks.
- Simulated weather and airspace availability checks, including a second check immediately before takeoff.
- Drone movement and mission progression.
- Delivery arrival and a waiting period for the recipient to collect the parcel.
- Successful delivery and unsuccessful collection/delivery outcomes.
- Return flights to the nearest suitable Hub, with or without the parcel.
- Post-flight unloading, quick inspection, charging, and maintenance.
- Drone availability changes and telemetry updates.
- Fleet balancing (future feature): when operationally appropriate and a drone is idle and sufficiently charged, the dispatcher may reposition it to a Hub with greater need, while respecting Hub capacity. The target is about 40 of 50 places occupied per Hub.
- Operational events and simulated incidents.

The simulation must remain coherent and independent of an open frontend session. All movement, weather, airspace, and telemetry are simulated; physical accuracy is not the objective.

Exact dispatch thresholds, Hub suitability rules, repositioning policy, and exceptional capacity behavior are tracked as open or to-be-defined MVP rules in `business-rules.md`.

### 6.6 Incident Monitoring & Investigation

The system should record operational events and detect simulated conditions that may require operator attention.

Example scenarios include:

- Elevated motor or battery temperature.
- Failed delivery / recipient not collecting the parcel.
- Drone unable to continue its assigned mission.
- Emergency landing simulation.
- Weather or simulated airspace restriction preventing takeoff or continuation.
- Low battery or other abnormal telemetry.
- Hub capacity or availability constraints.

The backend should preserve relevant event and telemetry history so incidents can be investigated. Exact incident severity levels, emergency procedures, and recovery transitions are MVP details to be defined incrementally; do not invent real-world aviation procedures.

### 6.7 AI Operations Assistant

SkyFleet includes an AI-powered Fleet Operations Agent.

The agent helps operators understand the current operational situation by answering natural-language questions, investigating incidents, and generating recommendations.

Examples:

- "Which drones are currently unavailable and why?"
- "Why was this order not assigned?"
- "Summarize the active incidents."
- "Which hub has the most orders awaiting pickup?"
- "What happened during this drone's last mission?"

The AI assistant should rely on controlled backend tools to retrieve operational information.

It may recommend actions, but any operation that changes system state must require explicit operator approval and backend validation.

## 7. Simulation Philosophy

SkyFleet is a software simulation, not a real drone control system. All drone movement, telemetry, weather, airspace availability, incidents, and operational events are simulated.

The goal is to demonstrate believable business processes and coherent system behavior rather than physical accuracy.

Important principles:

- Simulated states must remain internally consistent.
- Operational events should have understandable consequences.
- Drone movement should correspond to mission progression.
- Battery levels and temperature indicators should change plausibly.
- Weather and airspace conditions are simulated checks, not live integrations.
- The pre-flight check must be repeated immediately before takeoff.
- A drone waits at the delivery location for the recipient; if the parcel is not collected, it returns to a Hub with the parcel.
- After every delivery attempt, the drone returns to the nearest suitable Hub, not necessarily its pickup Hub.
- At the Hub, returned parcels are unloaded, and drones undergo a quick inspection before charging, maintenance, or waiting for another task.
- Idle, sufficiently charged drones may be repositioned between Hubs to balance fleet distribution, subject to capacity and dispatch rules.
- The frontend visualizes backend-owned operational and simulation state.
- The simulation continues independently of the frontend.

Do not introduce unnecessary physical modeling, real-world flight control, regulatory enforcement, or external hardware/weather/airspace integrations.

## 8. Product Experience & Visual Direction

SkyFleet should look and feel like a modern autonomous logistics operations center.

The primary interface direction is:

- Dark visual theme.
- Map-first operational dashboard.
- Interactive Mapbox map centered on the Tricity area.
- Clearly distinguishable Mall Pickup Hubs and moving drones.
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
- Mall Pickup Hub and Partner representation.
- Order (B2B delivery request), drone, and mission management.
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
3. Mall Pickup Hubs displayed on the map.
4. Incoming Partner delivery requests appearing in the system.
5. Drones moving through simulated missions.
6. Drone status and battery changes.
7. Deliveries being completed.
8. Drones returning after delivery (behavior pending the drone base decision).
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
