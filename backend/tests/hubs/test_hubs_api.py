from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.hubs.seed import seed_hubs

EXPECTED = [
    ("hub-centrum-handlowe-osowa", "Centrum Handlowe Osowa", 18.49097, 54.42569),
    ("hub-centrum-riviera", "Centrum Riviera", 18.5317863, 54.5046621),
    ("hub-forum-gdansk", "Forum Gdańsk", 18.643527, 54.349346),
    ("hub-galeria-baltycka", "Galeria Bałtycka", 18.6006944, 54.3826244),
]


def test_list_hubs_returns_four_seeded_hubs_in_stable_order(
    client: TestClient, session: Session
) -> None:
    seed_hubs(session)

    response = client.get("/api/hubs")

    assert response.status_code == 200
    hubs = response.json()
    assert [(h["id"], h["name"], h["longitude"], h["latitude"]) for h in hubs] == EXPECTED
    assert all(h["drone_capacity"] == 50 for h in hubs)
    assert client.get("/api/hubs").json() == hubs


def test_list_hubs_is_empty_before_seeding(client: TestClient) -> None:
    assert client.get("/api/hubs").json() == []


def test_get_hub_returns_matching_hub(client: TestClient, session: Session) -> None:
    seed_hubs(session)

    response = client.get("/api/hubs/hub-forum-gdansk")

    assert response.status_code == 200
    assert response.json() == {
        "id": "hub-forum-gdansk",
        "name": "Forum Gdańsk",
        "address": "Targ Sienny 7, Gdańsk",
        "longitude": 18.643527,
        "latitude": 54.349346,
        "drone_capacity": 50,
    }


def test_get_unknown_hub_returns_404_with_message(client: TestClient, session: Session) -> None:
    seed_hubs(session)

    response = client.get("/api/hubs/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Hub 'does-not-exist' not found"}
