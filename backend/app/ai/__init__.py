"""AI assistant foundation (Feature 024): a fail-closed, cost-guarded, read-only gateway.

Nothing in the application calls this package yet: there is no endpoint, no tool and no domain
access. It only sends one bounded text question to one allow-listed model and accounts for the
cost. The rules that keep it safe:

* disabled unless `SKYFLEET_AI_ENABLED=true` and the configuration passes `readiness`;
* the model identifier and its prices live together in `pricing.ALLOWED_MODELS`;
* every call first reserves a pessimistic cost, atomically and durably (`budget`), and is refused
  if a limit, the budget or the accounting itself cannot be trusted;
* the SDK never retries, never gets tools, and is the only thing `anthropic_transport` talks to;
* no key, prompt or answer is ever stored or logged.

This package imports no domain module (drones, orders, missions, ...); a test enforces it.
"""
