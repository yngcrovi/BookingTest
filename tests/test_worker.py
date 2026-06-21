from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.core import db as db_module
from app.core.config import settings
from app.models import Booking, BookingStatus
from app.services.notifier import ExternalNotificationError
from app.worker.tasks import process_booking


@pytest.fixture()
def patched_db(engine, session_factory, monkeypatch):
    """Перенаправляем воркер на тестовый SQLite-engine."""
    monkeypatch.setattr(db_module, "engine", engine, raising=True)
    monkeypatch.setattr(db_module, "SessionLocal", session_factory, raising=True)
    return session_factory


def _make_pending(session_factory) -> uuid.UUID:
    """Создаёт бронь в pending и возвращает её id."""
    with session_factory() as s:
        b = Booking(
            name="Bob",
            datetime=datetime.now(timezone.utc) + timedelta(days=1),
            service_type="haircut",
            status=BookingStatus.PENDING,
        )
        s.add(b)
        s.commit()
        return b.id


def test_worker_confirms_booking_on_success(patched_db):
    booking_id = _make_pending(patched_db)

    with patch("app.worker.tasks.send_confirmation") as send:
        result = process_booking.apply(args=[str(booking_id)]).get()

    assert result == "confirmed"
    send.assert_called_once()
    with patched_db() as s:
        assert s.get(Booking, booking_id).status == BookingStatus.CONFIRMED


def test_worker_marks_failed_after_exhausting_retries(patched_db):
    booking_id = _make_pending(patched_db)

    with patch(
        "app.worker.tasks.send_confirmation",
        side_effect=ExternalNotificationError("boom"),
    ):
        result = process_booking.apply(
            args=[str(booking_id)],
            retries=settings.worker_max_retries,
        ).get()

    assert result == "failed"
    with patched_db() as s:
        assert s.get(Booking, booking_id).status == BookingStatus.FAILED


def test_worker_is_idempotent_on_already_confirmed(patched_db):
    booking_id = _make_pending(patched_db)
    # Подделываем "уже подтверждённое" состояние.
    with patched_db() as s:
        s.get(Booking, booking_id).status = BookingStatus.CONFIRMED
        s.commit()

    with patch("app.worker.tasks.send_confirmation") as send:
        result = process_booking.apply(args=[str(booking_id)]).get()

    assert result == "noop:confirmed"
    send.assert_not_called()
    with patched_db() as s:
        assert s.get(Booking, booking_id).status == BookingStatus.CONFIRMED


def test_worker_handles_missing_booking(patched_db):
    # Брони с таким id никогда не было — задача должна просто завершиться.
    result = process_booking.apply(args=[str(uuid.uuid4())]).get()
    assert result == "missing"


def test_worker_does_not_touch_cancelled_booking(patched_db):
    booking_id = _make_pending(patched_db)
    with patched_db() as s:
        s.get(Booking, booking_id).status = BookingStatus.CANCELLED
        s.commit()

    with patch("app.worker.tasks.send_confirmation") as send:
        result = process_booking.apply(args=[str(booking_id)]).get()

    assert result == "noop:cancelled"
    send.assert_not_called()
