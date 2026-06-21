from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone


def _payload(**overrides: object) -> dict[str, object]:
    """Базовая валидная нагрузка для POST /bookings; поля можно переопределить."""
    base: dict[str, object] = {
        "name": "Alice",
        "datetime": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "service_type": "consultation",
    }
    base.update(overrides)
    return base


def test_create_booking_returns_201_and_confirms_eagerly(client):
    response = client.post("/bookings", json=_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alice"
    assert body["service_type"] == "consultation"
    follow_up = client.get(f"/bookings/{body['id']}")
    assert follow_up.status_code == 200
    assert follow_up.json()["status"] == "confirmed"


def test_create_booking_validates_required_fields(client):
    response = client.post("/bookings", json={"name": "", "service_type": "x"})
    assert response.status_code == 422


def test_get_booking_not_found(client):
    response = client.get(f"/bookings/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "booking not found"


def test_get_booking_invalid_uuid_returns_422(client):
    response = client.get("/bookings/not-a-uuid")
    assert response.status_code == 422


def test_list_bookings_pagination_and_filter(client):
    for name in ("a", "b", "c"):
        client.post("/bookings", json=_payload(name=name))

    page = client.get("/bookings?limit=2&offset=0").json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["limit"] == 2
    assert page["offset"] == 0

    confirmed = client.get("/bookings?status=confirmed").json()
    assert confirmed["total"] == 3
    pending = client.get("/bookings?status=pending").json()
    assert pending["total"] == 0


def test_list_bookings_rejects_invalid_status(client):
    response = client.get("/bookings?status=garbage")
    assert response.status_code == 422


def test_cancel_pending_booking(client, session_factory):
    from app.models import Booking, BookingStatus

    with session_factory() as s:
        b = Booking(
            name="X",
            datetime=datetime.now(timezone.utc) + timedelta(days=1),
            service_type="cut",
            status=BookingStatus.PENDING,
        )
        s.add(b)
        s.commit()
        booking_id = b.id

    response = client.delete(f"/bookings/{booking_id}")
    assert response.status_code == 204

    follow_up = client.get(f"/bookings/{booking_id}")
    assert follow_up.json()["status"] == "cancelled"


def test_cancel_non_pending_returns_409(client):
    created = client.post("/bookings", json=_payload()).json()
    response = client.delete(f"/bookings/{created['id']}")
    assert response.status_code == 409
    assert "confirmed" in response.json()["detail"]


def test_cancel_missing_returns_404(client):
    response = client.delete(f"/bookings/{uuid.uuid4()}")
    assert response.status_code == 404


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
