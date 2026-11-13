"""Curated catalog of prevalidated simulated delivery routes for the order generator.

Incoming orders are assumed to have passed customer checkout validation, so the generator does not
search or validate routes at runtime: it picks one entry from this catalog. Each route names an
origin Hub, a delivery point and a package-weight range that the SF-1 drone can fly with a full
battery under the mission planner's rules (route budget and payload-aware energy estimate). The
tests re-check every route and both weight bounds with the planner's own routing and energy helpers,
so a change to the Hubs, the drone model or the energy model that breaks a route fails the build.

All addresses, coordinates and weights are ILLUSTRATIVE SIMULATION DATA (inland urban points in
Gdańsk, Gdynia and Sopot; coordinates are approximate). They are not verified customer addresses
and not a legal flight corridor. Drone availability and battery state are the dispatcher's concern.
"""

from dataclasses import dataclass

from app.orders.models import MAX_PACKAGE_WEIGHT_KG

GALERIA = "hub-galeria-baltycka"
FORUM = "hub-forum-gdansk"
RIVIERA = "hub-centrum-riviera"
OSOWA = "hub-centrum-handlowe-osowa"


@dataclass(frozen=True)
class CatalogRoute:
    origin_hub_id: str
    destination_address: str
    longitude: float
    latitude: float
    min_weight_kg: float
    max_weight_kg: float


_FULL = MAX_PACKAGE_WEIGHT_KG

# Weight ranges keep a margin below the full-battery limit of each route; heavier parcels are only
# offered on short routes. Append-only: add new routes rather than reordering.
ROUTE_CATALOG: tuple[CatalogRoute, ...] = (
    # Galeria Bałtycka
    CatalogRoute(GALERIA, "ul. Grunwaldzka 82, Gdańsk", 18.5972, 54.3768, 0.2, _FULL),
    CatalogRoute(GALERIA, "ul. Do Studzienki 25, Gdańsk", 18.5887, 54.3881, 0.2, _FULL),
    CatalogRoute(GALERIA, "ul. Słowackiego 200, Gdańsk", 18.6120, 54.3935, 0.2, _FULL),
    CatalogRoute(GALERIA, "ul. Narutowicza 11/12, Gdańsk", 18.6178, 54.3722, 0.2, _FULL),
    CatalogRoute(GALERIA, "Park Oliwski, ul. Opata Rybickiego, Gdańsk", 18.5686, 54.4106, 0.2, 2.5),
    CatalogRoute(GALERIA, "ul. Monte Cassino 20, Sopot", 18.5693, 54.4467, 0.2, 1.0),
    # Cross-Hub: the nearest return Hub is Forum Gdańsk.
    CatalogRoute(GALERIA, "Podwale Grodzkie 2, Gdańsk", 18.6444, 54.3560, 0.2, 2.5),
    # Forum Gdańsk
    CatalogRoute(FORUM, "ul. Długa 45, Gdańsk", 18.6531, 54.3487, 0.2, _FULL),
    CatalogRoute(FORUM, "ul. Chmielna 10, Gdańsk", 18.6410, 54.3512, 0.2, _FULL),
    CatalogRoute(FORUM, "ul. Podwale Staromiejskie 60, Gdańsk", 18.6459, 54.3558, 0.2, _FULL),
    # Centrum Riviera
    CatalogRoute(RIVIERA, "ul. Świętojańska 30, Gdynia", 18.5440, 54.5189, 0.2, _FULL),
    CatalogRoute(RIVIERA, "ul. Morska 59, Gdynia", 18.5120, 54.5050, 0.2, _FULL),
    CatalogRoute(RIVIERA, "Skwer Kościuszki, Gdynia", 18.5530, 54.5188, 0.2, _FULL),
    CatalogRoute(RIVIERA, "Bulwar Nadmorski, Gdynia Orłowo", 18.5700, 54.4800, 0.2, 2.5),
    # Centrum Handlowe Osowa
    CatalogRoute(OSOWA, "ul. Spacerowa 12, Gdańsk", 18.4952, 54.4311, 0.2, _FULL),
    CatalogRoute(OSOWA, "ul. Kielnieńska 5, Gdańsk", 18.4720, 54.4180, 0.2, _FULL),
)
