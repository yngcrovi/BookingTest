from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus
from app.schemas import BookingCreate


class BookingNotFoundError(LookupError):
    """Брони с таким id нет в БД."""


class BookingNotCancellableError(ValueError):
    """Попытка отменить бронь, которая уже не в статусе pending."""


class BookingService:

    def __init__(self, session: Session) -> None:
        self._session = session


    def create(self, data: BookingCreate) -> Booking:
        """Создаёт бронь в статусе pending."""
        booking = Booking(
            name=data.name,
            datetime=self._ensure_aware(data.datetime),
            service_type=data.service_type,
            status=BookingStatus.PENDING,
        )
        self._session.add(booking)
        self._session.commit()
        self._session.refresh(booking)
        return booking

    def cancel(self, booking_id: uuid.UUID) -> Booking:
        """Переводит бронь в cancelled. Разрешено только из pending."""
        booking = self.get(booking_id)
        if booking.status != BookingStatus.PENDING:
            raise BookingNotCancellableError(booking.status.value)
        booking.status = BookingStatus.CANCELLED
        self._session.commit()
        self._session.refresh(booking)
        return booking

    def get(self, booking_id: uuid.UUID) -> Booking:
        """Возвращает бронь по id или бросает BookingNotFoundError."""
        booking = self._session.get(Booking, booking_id)
        if booking is None:
            raise BookingNotFoundError(str(booking_id))
        return booking

    def list(
        self,
        *,
        status: BookingStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Booking], int]:
        """Постранично возвращает брони + общее количество с учётом фильтра."""
        base = select(Booking)
        count_q = select(func.count()).select_from(Booking)
        if status is not None:
            base = base.where(Booking.status == status)
            count_q = count_q.where(Booking.status == status)

        items = (
            self._session.execute(
                base.order_by(Booking.created_at.desc()).limit(limit).offset(offset)
            )
            .scalars()
            .all()
        )
        total = self._session.execute(count_q).scalar_one()
        return list(items), total


    @staticmethod
    def _ensure_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
