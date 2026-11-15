"""Deterministic compact JSON and the byte budget (Feature 025).

`serialize` always yields the same text for the same context: fixed field order, compact
separators, no whitespace, UTF-8 left as UTF-8 (the budget counts bytes, so nothing is inflated by
escapes). `render_context` makes it fit a byte budget, or refuses.

REDUCTION. When the text is too large it is reduced one entry at a time, always from the least
important end, and re-measured, until it fits:

  1. unflagged drone rows, from the end of the roster: the roster is ordered flagged drones,
     then drones in flight or on an active mission, then the rest, so idle and charging rows go
     first and active ones only after them
  2. recovered alerts (history)
  3. Hub rows
  4. flagged drone rows, least urgent first
  5. active incidents, oldest first

The summary, simulation block, limitations, `omitted` and the operational warnings are never
dropped. Every removal is recorded in `omitted` and, through `apply_omissions`, as a
`*_OMITTED:n` limitation with `truncated` true and `data_status` degraded, so nothing is ever
omitted silently. If it still does not fit with every list empty, the request is refused.
"""

import json
from dataclasses import dataclass

from app.fleet_context.errors import FleetContextTooLargeError
from app.fleet_context.schemas import FleetContext, Omitted, apply_omissions

TOO_LARGE = "The fleet context does not fit the request size limit, even without its lists."


@dataclass(frozen=True)
class RenderedContext:
    text: str
    size_bytes: int
    context: FleetContext  # the context exactly as rendered (reductions applied)
    reduced: bool  # True when entries had to be dropped to fit the budget


def serialize(context: FleetContext) -> str:
    return json.dumps(context.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


def _drop_last(context: FleetContext, field: str, omitted_field: str) -> FleetContext:
    entries = getattr(context, field)
    smaller = context.model_copy(update={field: entries[:-1]})
    count = getattr(context.omitted, omitted_field) + 1
    return apply_omissions(smaller, context.omitted.model_copy(update={omitted_field: count}))


def _reduce(context: FleetContext) -> FleetContext | None:
    """One step of the reduction ladder, or None when nothing is left to drop."""
    if context.drones and not context.drones[-1].flags:
        return _drop_last(context, "drones", "drones")
    if context.recovered_alerts:
        return _drop_last(context, "recovered_alerts", "recovered_alerts")
    if context.hubs:
        return _drop_last(context, "hubs", "hubs")
    if context.drones:
        return _drop_last(context, "drones", "drones")
    if context.active_incidents:
        return _drop_last(context, "active_incidents", "active_incidents")
    return None


def render_context(context: FleetContext, max_bytes: int) -> RenderedContext:
    """The context as text of at most `max_bytes` UTF-8 bytes, reduced and flagged if needed."""
    current = context
    text = serialize(current)
    reduced = False
    while len(text.encode("utf-8")) > max_bytes:
        smaller = _reduce(current)
        if smaller is None:
            raise FleetContextTooLargeError(TOO_LARGE)
        current, reduced = smaller, True
        text = serialize(current)
    return RenderedContext(text, len(text.encode("utf-8")), current, reduced)


__all__ = ["Omitted", "RenderedContext", "TOO_LARGE", "render_context", "serialize"]
