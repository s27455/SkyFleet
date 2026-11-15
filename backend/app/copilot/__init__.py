"""The operator-facing AI Copilot (Feature 026): access control, the service and its API contract.

A read-only assistant: one question in, one grounded answer out, through `ask_fleet_question`
(Feature 025) and the Feature 024 gateway. It gives the model no tool and no write action.

`access.py` decides WHO may ask (operator token, Origin allow-list, a bounded in-memory throttle of
failed attempts). `service.py` builds the gateway and the fleet context from ONE `Settings` instance
and maps every refusal to a fixed error code. `schemas.py` is the typed HTTP contract. The route
(`app/api/routes/copilot.py`) stays thin and runs the access checks before anything else.
"""
