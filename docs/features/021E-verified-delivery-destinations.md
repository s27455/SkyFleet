# Feature 021E — Verified Delivery Destinations

**Status:** Implemented and verified (automated checks and live PRG re-check); the owner confirmed
browser QA passed on 2026-11-15 (the individual steps were not recorded). Not committed.
**Scope:** the order generator's static catalog and destination selection, one map credit. No
migration, no database write, no change to existing orders, planner, dispatch or marker layout.

## 1. Why

The 021D-1 catalog had 16 hand-written points, and its coordinates did not match its addresses
(checked against the official register: `Aleja Grunwaldzka 82` was 701 m off, `Do Studzienki 25`
2.2 km off, `Narutowicza 11/12` 117 m off). Only 16 places were ever used, so open orders stacked on
the same points and the map fanned them out in symmetric rings.

## 2. Data source

| Item | Value |
|---|---|
| Register | Państwowy Rejestr Granic (PRG), address points, published by GUGiK |
| Service | OGC API Features, collection `PunktAdresowy`: `https://ogcapi.geoportal.gov.pl/res/ims/maps/prg_ad/apiFeatures` |
| Retrieved | 2026-11-15 (record versions `idWersja` 2026-11-10 to 2026-11-14) |
| Coordinates | WGS84 longitude/latitude (CRS84), rounded to 6 decimals (about 0.1 m) |
| Attribution | "Źródło: PRG, GUGiK (geoportal.gov.pl)" |
| Terms | The PRG page states the data is "dostępne bezpłatnie i do dowolnego wykorzystania" (free, any use) and names no specific licence. The Geoportal terms (§3.2) ask for the source to be named when material is published; §3.3 gives no accuracy guarantee. Not legal advice. |

Notes:

- The service has no key and no documented rate limit. It was queried once, with small bounding boxes
  and pauses between requests (about 115 search requests, then 84 for the final check, each at
  most 100 records per page). SkyFleet makes **no
  runtime calls**; the catalog is a static file.
- It supports bounding-box queries and paging (`limit` up to 100, `offset`) only; property and CQL
  filters return HTTP 400.
- The API's own links point to a host named `ogcapitest`; the production host answered. If it
  changes, the bulk packages (`opendata.geoportal.gov.pl/prg/adresy/...`) are the fallback.
- Official street names are the full form (`Aleja Grunwaldzka`, `os.…`). They are kept as is.

## 3. What the catalog holds

`backend/app/orders/generator_catalog.py`: 84 entries. Each entry is **one** PRG record: street,
house number, locality and coordinates come from the same record. Per entry:

- `destination_address` = `"<street> <number>, <locality>"` (official spelling),
- `longitude`, `latitude` (the record's point),
- `origin_hub_id` (the Hub the planner's `choose_origin_hub` picks), `min_weight_kg` 0.2,
  `max_weight_kg`,
- `city` (the record's official locality),
- `district` (**editorial**, not PRG: the search area the point was taken from; used only to spread
  orders, may differ from an official boundary),
- `prg_id` (`idLokalny`) and `prg_version` (`idWersja`): metadata only, never shown in labels.

### How it was built

1. For each of about 110 hand-chosen search areas (centres across Gdańsk, Sopot and Gdynia), request a
   bounding box of about 400 m × 400 m from the PRG service.
2. Take the nearest record with a street name and a locality in Gdańsk, Gdynia or Sopot. The record
   is stored unchanged; the search centre is never copied into the catalog.
3. Keep it only if it passes the existing rules, otherwise drop it without adjusting anything:
   inside the operating area (`operating_area.py`), flyable from the nearest Hub that can serve it
   (`feasibility.choose_origin_hub`, 0.2 kg), a street not already in the catalog, and a heaviest
   parcel of at least 0.5 kg. `max_weight_kg` is 3 kg, or 0.3 kg below the planner's full-battery
   limit when that is lower (two routes: `Morska 301, Gdynia` 1.8 kg, `Jemiołowa 83, Gdynia` 2.5 kg).
4. Re-query the live service for every final entry and confirm id, address, locality, coordinates
   and version are identical (84 of 84 matched on 2026-11-15).

### Coverage (84 points, 49 districts)

- Gdańsk 55, Gdynia 23, Sopot 6.
- By origin Hub: Galeria Bałtycka 32, Centrum Riviera 21, Forum Gdańsk 17, Centrum Handlowe Osowa 14.
- The old-town districts (Główne Miasto, Stare Przedmieście, Dolne Miasto, Śródmieście, Biskupia
  Górka) hold 5 points (6 %). No district has more than 4.

### Excluded

- Several search areas had no usable record (fields, forest, new developments): Matarnia and
  Kokoszki edges, parts of Osowa, Witomino, Orłowo, Karwiny, Leszczynki, Dąbrowa, Mały Kack,
  Górny Sopot and others.
- Points on the coast were outside the approximate operating polygon: Brzeźno shore, Nowy Port,
  Dolny Sopot shore (Sopot therefore has only 6 points), Obłuże, southern Chełm.
- `os.Bernadowo 4, Gdynia` (an official but unusual street name) was left out for readability.
- Nothing was excluded for range or battery: every point that was inside the operating area was
  flyable. The 14 km mission range around the four Hubs is generous, so the polygon is the limiting
  rule, not the planner.

## 4. Destination selection

`generator.pick_route`: the free routes (not used by an open order) are grouped by `(city,
district)`, one district is chosen uniformly, then one route in it. A busy district therefore
cannot dominate. When every route is in use a repeat is allowed, as before. Districts are visited in
sorted order, so a seeded random source is reproducible.

## 5. Not changed

- Existing orders, missions, history and the database. The seed orders (`ORD-001`…`ORD-011`) and the
  1559 legacy `Delivery Point TC-…` orders keep their old addresses and coordinates; the seed's old
  coordinates are still inaccurate and only affect the dev data.
- Planner, dispatch, routing, hub coordinates, operational limits, marker-offset algorithm.

## 6. UI credit

`mapConfig.DATA_ATTRIBUTION` is passed to Mapbox as `customAttribution`, so the credit appears once,
inside the map's existing attribution control.

## 7. Verification (2026-11-15)

- Backend: `ruff check` and `ruff format --check` clean; `pytest` 1075 passed (61 `postgres`
  tests deselected by default); `pytest -m postgres` 61 passed; `mypy .` reports 1 error in
  `tests/weather/test_rain_warning.py:208`, a file this feature does not touch (pre-existing, not
  investigated).
- New tests: `tests/orders/test_generator_catalog_verified.py` (record integrity, unique ids,
  operating area, planner feasibility at both weight bounds and origin Hub, distribution, selection,
  existing orders untouched); `test_order_generator.py` adjusted for the legacy seed orders no longer
  overlapping the catalog.
- Frontend: `tsc -b`, oxlint, prettier clean; vitest 847 passed; production build succeeded
  (chunk-size warning only).
- Live re-check of all 84 entries against the PRG service: 84 identical.

## 8. Limits and risks

- The offline tests cannot ask the PRG service; they check consistency, not truth. The one-off live
  check above did, and the PRG ids allow it to be repeated.
- A PRG point is an address record, not a landing zone: it can sit on a building, a courtyard or a
  road side. It is as credible as the official register, not a verified safe drop-off.
- `district` is editorial; a point may be labelled with a neighbouring district.
- With 84 points and at most 20 outstanding automatic orders, repeats are rare but possible; the map
  still fans out markers that share a point.
- The coast (Brzeźno, Nowy Port, Dolny Sopot shore) is under-represented because of the approximate
  operating polygon, which was deliberately not widened.
- Each Hub's share follows geography (Galeria Bałtycka serves the largest area), not an equal split.
