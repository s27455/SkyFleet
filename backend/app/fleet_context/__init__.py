"""Read-only fleet context for the AI gateway (Feature 025).

A bounded, deterministic snapshot of the CURRENT operational state, taken in one read-only
PostgreSQL transaction, rendered as compact JSON and handed to `app.ai.gateway.AiGateway.ask` as
the "Fleet context". It is data for the model, never instructions.

What this package never does: write to the database, call a service with side effects, expose an
HTTP endpoint, give the model a tool or database access, or contact the provider when a trustworthy
snapshot could not be built. Nothing outside this package imports it yet (no route, no worker).

Layout: `schemas.py` (the typed contract), `snapshot.py` (the read-only builder), `render.py`
(deterministic JSON and the byte budget), `service.py` (`ask_fleet_question`), `errors.py`.
"""
