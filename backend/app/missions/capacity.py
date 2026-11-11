"""Return-Hub selection against physical capacity.

The planned return Hub is the nearest Hub (to the delivery destination) that the drone can safely
reach with the parcel still on board and that has a free physical place. The choice is made at
planning time only: nothing is reserved, so the Hub may fill up before landing. The flight
simulation feature must recheck capacity before landing and re-pick a reachable Hub; actual
occupancy must never exceed the Hub's capacity.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.hubs.models import Hub

SkipReason = Literal["HUB_FULL", "OUT_OF_RANGE"]


@dataclass(frozen=True)
class ReturnHubChoice:
    hub: Hub | None
    # Hubs passed over, in order of distance, with the reason.
    skipped: list[tuple[Hub, SkipReason]] = field(default_factory=list)


def has_free_place(hub: Hub, occupancy: Counter[str], *, drone_docked_here: bool) -> bool:
    """A free physical place for this drone.

    A drone already docked at the Hub vacates its own place on takeoff, so it can plan to return
    there; any other drone needs occupancy below capacity.
    """
    occupied = occupancy[hub.id] - (1 if drone_docked_here else 0)
    return occupied < hub.drone_capacity


def choose_return_hub(
    candidates: Sequence[tuple[Hub, float]],
    occupancy: Counter[str],
    *,
    docked_at: Hub | None,
    is_reachable: Callable[[float], bool],
) -> ReturnHubChoice:
    """Pick the first candidate (nearest first) that is reachable and has a free place.

    `candidates` are (hub, distance from the destination) pairs, already sorted. `is_reachable`
    receives that distance and applies the distance budget and battery requirement.
    """
    skipped: list[tuple[Hub, SkipReason]] = []
    for hub, distance in candidates:
        if not is_reachable(distance):
            skipped.append((hub, "OUT_OF_RANGE"))
            continue
        here = docked_at is not None and docked_at.id == hub.id
        if not has_free_place(hub, occupancy, drone_docked_here=here):
            skipped.append((hub, "HUB_FULL"))
            continue
        return ReturnHubChoice(hub=hub, skipped=skipped)
    return ReturnHubChoice(hub=None, skipped=skipped)
