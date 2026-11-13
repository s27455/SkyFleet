"""The approximate operating area for generated delivery points (Feature 017C).

The polygon below is a hand-drawn, simplified outline of the inland Tricity around the four Hubs.
It is NOT an accurate land or sea mask and not an airspace or no-fly-zone definition: the east edge
follows the Gdańsk Bay coast only roughly, kept a little inland, and nothing here knows about
water inside the area, parks, rail yards or buildings. It exists so the order generator does not
place points in the bay or far outside the map. Edit the vertices here to change the area; every
Hub must stay inside (a test checks it).

Vertices are (longitude, latitude), in order around the area (clockwise from the south-west).
"""

from app.missions.routing import Point

OPERATING_AREA: tuple[Point, ...] = (
    (18.420, 54.340),  # south-west, beyond Osowa
    (18.420, 54.400),
    (18.420, 54.480),
    (18.460, 54.540),  # north-west, Gdynia hinterland
    (18.520, 54.545),
    (18.552, 54.530),  # Gdynia, a little inland of the port
    (18.560, 54.480),  # Orłowo
    (18.556, 54.455),  # Sopot
    (18.580, 54.430),  # Jelitkowo
    (18.610, 54.410),  # Brzeźno
    (18.650, 54.395),  # Gdańsk port
    (18.700, 54.370),  # east, Gdańsk lowlands
    (18.720, 54.340),
    (18.680, 54.325),  # south-east
    (18.550, 54.325),
)


def contains(point: Point, area: tuple[Point, ...] = OPERATING_AREA) -> bool:
    """Whether the point lies inside the polygon (ray casting; a point on an edge is arbitrary)."""
    x, y = point
    inside = False
    j = len(area) - 1
    for i, (xi, yi) in enumerate(area):
        xj, yj = area[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside
