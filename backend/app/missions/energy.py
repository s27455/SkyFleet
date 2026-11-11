"""Simple, explicit energy model for mission planning (simulation assumptions only).

This is not certified flight performance and not battery physics. A full battery covers the
model's nominal range empty; carrying the parcel raises consumption linearly with its weight:

    empty_rate  = 100 / max_range_km                                   (% of battery per km)
    loaded_rate = empty_rate * (1 + payload_energy_factor * weight / max_payload_kg)

    expected    = outbound_km * loaded_rate + return_km * empty_rate   (parcel out, none back)
    worst_case  = total_km * loaded_rate                               (parcel never leaves)
    required    = worst_case + minimum battery reserve

The worst case is never below the expected case, so it is the conservative gate: even if delivery
fails and the parcel stays on board, the drone can still reach the return Hub with the reserve left.
"""

from dataclasses import dataclass

from app.drones.models import DroneModel


@dataclass(frozen=True)
class EnergyEstimate:
    empty_rate_pct_per_km: float
    loaded_rate_pct_per_km: float
    expected_pct: float
    worst_case_pct: float
    reserve_pct: float
    required_battery_pct: float


def estimate_energy(
    *,
    outbound_km: float,
    return_km: float,
    weight_kg: float,
    model: DroneModel,
    payload_energy_factor: float,
) -> EnergyEstimate:
    empty_rate = 100.0 / model.max_range_km
    loaded_rate = empty_rate * (1 + payload_energy_factor * weight_kg / model.max_payload_kg)
    expected = outbound_km * loaded_rate + return_km * empty_rate
    worst_case = (outbound_km + return_km) * loaded_rate
    reserve = float(model.min_battery_reserve_pct)
    return EnergyEstimate(
        empty_rate_pct_per_km=empty_rate,
        loaded_rate_pct_per_km=loaded_rate,
        expected_pct=expected,
        worst_case_pct=worst_case,
        reserve_pct=reserve,
        required_battery_pct=worst_case + reserve,
    )


def has_enough_battery(battery_pct: float, estimate: EnergyEstimate) -> bool:
    """Exactly the required level passes; anything below fails."""
    return battery_pct >= estimate.required_battery_pct
