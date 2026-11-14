"""Automatic fleet rebalancing (Feature 019B): part of the Auto Dispatch pass.

While Auto Dispatch is ON, each pass first dispatches orders (014C) and then, if a Hub has orders
waiting that none of its own drones can serve, moves one spare drone there with the 019A
`start_relocation`. There is no toggle, state or scheduler of its own: Auto Dispatch OFF means no
new relocation, flights already started continue, and manual relocation is unaffected.

The policy is deterministic and reuses the dispatch definitions (`recommend`,
`available_drones_by_hub`), so "queued order" and "available drone" mean what they mean for
dispatch:

- Demand: orders the dispatch recommendation leaves without a drone because their Hub has none
  free (`NO_ELIGIBLE_DRONE_AT_HUB`). Orders the planner rejects are blocked, not demand. Relocations
  already flying to the Hub (manual or automatic) count as incoming supply, one per order.
- Surplus: a Hub donates only a drone it does not need: at least two available drones, and more
  than its own queued orders will use. It never gives up its last available drone.
- Choice: the Hub with the most unmet demand (then Hub id); the shortest feasible transfer to it
  (then drone id). One relocation per pass.
- Cooldown: a Hub pair that had a relocation in either direction within the cooldown is skipped,
  read from the stored flights, so it survives restarts. Only automatic choices are limited.

Nothing is reserved by the plan: `start_relocation` revalidates under row locks, so a stale plan
can never bypass the 019A rules. It assumes one worker process (two could each start one transfer;
the per-drone unique index still prevents double assignment).
"""

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch.schemas import PendingReason, RecommendationsResponse
from app.dispatch.service import active_claims, available_drones_by_hub, recommend_for_session
from app.drones import repository as drone_repository
from app.drones.models import Drone
from app.events.models import EventOrigin
from app.hubs.models import Hub
from app.missions import repository as mission_repository
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission, MissionPurpose
from app.missions.routing import distance_km, hub_point
from app.missions.service import MissionError
from app.simulation.models import MissionFlight
from app.simulation.relocation import evaluate_relocation, start_relocation
from app.simulation.service import WorkerUnavailableError

logger = logging.getLogger("skyfleet.dispatch")


@dataclass(frozen=True)
class Transfer:
    drone_id: str
    source_hub_id: str
    destination_hub_id: str
    distance_km: float
    reason: str


def plan_transfer(
    *,
    result: RecommendationsResponse,
    drones: Sequence[Drone],
    hubs: Sequence[Hub],
    active_drone_ids: set[str],
    incoming: Counter[str],
    cooling_pairs: set[frozenset[str]],
    dock_proximity_m: float,
) -> Transfer | None:
    """The one transfer to start now, or None. Pure over already-loaded data."""
    by_id = {hub.id: hub for hub in hubs}
    available = available_drones_by_hub(drones, hubs, active_drone_ids, dock_proximity_m)

    unmet: Counter[str] = Counter(
        pending.origin_hub_id
        for pending in result.pending
        if pending.reason == PendingReason.NO_ELIGIBLE_DRONE_AT_HUB
    )
    # Drones a Hub needs for its own queue: those recommended now plus the orders still waiting.
    needed: Counter[str] = Counter(rec.origin_hub_id for rec in result.recommendations)
    needed.update(unmet)

    demands = [(hub_id, count - incoming[hub_id]) for hub_id, count in unmet.items()]
    for destination_id, open_demand in sorted(demands, key=lambda d: (-d[1], d[0])):
        if open_demand <= 0 or destination_id not in by_id:
            continue
        destination = by_id[destination_id]
        best: tuple[float, str, Hub, int] | None = None
        for source_id, free in available.items():
            spare = len(free) - needed[source_id]
            if source_id == destination_id or len(free) < 2 or spare < 1:
                continue
            if frozenset((source_id, destination_id)) in cooling_pairs:
                continue
            source = by_id[source_id]
            km = distance_km(hub_point(source), hub_point(destination))
            drone = free[0]  # the drones of a Hub are alike for a transfer: the lowest id goes
            plan = evaluate_relocation(
                drone=drone,
                destination=destination,
                hubs=hubs,
                drones=drones,
                drone_has_active_mission=False,  # already excluded by `available`
                waiting_orders_at_origin=0,
                dock_proximity_m=dock_proximity_m,
            )
            if plan.eligible and (best is None or (km, drone.id) < (best[0], best[1])):
                best = (km, drone.id, source, spare)
        if best is not None:
            km, drone_id, source, spare = best
            return Transfer(
                drone_id=drone_id,
                source_hub_id=source.id,
                destination_hub_id=destination.id,
                distance_km=km,
                reason=(
                    f"automatic rebalancing: {destination.name} has {open_demand} queued "
                    f"order(s) and no available drone; {source.name} has {spare} spare"
                ),
            )
    return None


def _incoming(session: Session) -> Counter[str]:
    """Active relocations by the Hub they fly to (manual ones too: they are supply as well)."""
    active = [status.value for status in ACTIVE_MISSION_STATUSES]
    rows = session.scalars(
        select(Mission.return_hub_id).where(
            Mission.purpose == MissionPurpose.RELOCATION.value, Mission.status.in_(active)
        )
    )
    return Counter(rows)


def _cooling_pairs(session: Session, now: datetime, settings: Settings) -> set[frozenset[str]]:
    """Hub pairs with a relocation started within the cooldown (either direction)."""
    since = now - timedelta(seconds=settings.rebalance_pair_cooldown_seconds)
    rows = session.execute(
        select(Mission.origin_hub_id, Mission.return_hub_id)
        .join(MissionFlight, MissionFlight.mission_id == Mission.id)
        .where(
            Mission.purpose == MissionPurpose.RELOCATION.value, MissionFlight.started_at >= since
        )
    ).all()
    return {frozenset((origin, destination)) for origin, destination in rows}


def select_transfer(session: Session, settings: Settings, now: datetime) -> Transfer | None:
    """Load the current state (reads only) and decide."""
    result = recommend_for_session(session, settings)
    _, active_drone_ids = active_claims(session)
    return plan_transfer(
        result=result,
        drones=drone_repository.list_drones(session),
        hubs=mission_repository.list_hubs(session),
        active_drone_ids=active_drone_ids,
        incoming=_incoming(session),
        cooling_pairs=_cooling_pairs(session, now, settings),
        dock_proximity_m=settings.hub_dock_proximity_m,
    )


def run_rebalancing(
    factory: sessionmaker[Session],
    settings: Settings,
    now: datetime,
    is_enabled: Callable[[], bool],
) -> str | None:
    """One rebalancing step of an Auto Dispatch pass; a summary only when a drone was sent.

    Finding nothing to do is normal and silent. The caller has checked the mode; `is_enabled` reads
    it again right before the start, so turning Auto Dispatch OFF stops a transfer not yet begun.
    """
    with factory() as session:
        transfer = select_transfer(session, settings, now)
    if transfer is None or not is_enabled():
        return None
    with factory() as session:
        try:
            start_relocation(
                session,
                transfer.drone_id,
                transfer.destination_hub_id,
                now,
                settings,
                origin=EventOrigin.AUTOMATIC,
                reason=transfer.reason,
            )
        except (WorkerUnavailableError, MissionError):
            return None  # state changed since the plan, or no worker: the next pass decides again
        except Exception:
            logger.exception("Rebalancing of %s failed", transfer.drone_id)
            return "unexpected error rebalancing the fleet"
    return (
        f"Relocating {transfer.drone_id} from {transfer.source_hub_id} "
        f"to {transfer.destination_hub_id}"
    )
