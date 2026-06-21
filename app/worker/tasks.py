from __future__ import annotations

import uuid

from celery import Task

from app.core import db
from app.core.config import settings
from app.core.logging_config import get_logger
from app.models import Booking, BookingStatus
from app.services.notifier import ExternalNotificationError, send_confirmation
from app.worker.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="bookings.process",
    # При ExternalNotificationError Celery автоматически перезапустит задачу.
    autoretry_for=(ExternalNotificationError,),
    retry_backoff=2,  # экспоненциальный backoff: 2, 4, 8, ... сек
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=settings.worker_max_retries,
)
def process_booking(self: Task, booking_id: str) -> str:
    """Подтверждает бронь и пишет mock-уведомление"""
    bid = uuid.UUID(booking_id)
    bound_log = log.bind(booking_id=str(bid), attempt=self.request.retries + 1)

    # SessionLocal достаём через атрибут модуля db — это позволяет тестам
    # подменить фабрику сессий через monkeypatch.
    with db.SessionLocal() as session:
        booking: Booking | None = session.get(Booking, bid)
        if booking is None:
            bound_log.warning("task.skip.booking_missing")
            return "missing"

        if booking.status != BookingStatus.PENDING:
            # Бронь уже обработана или отменена — ничего не делаем.
            bound_log.info("task.skip.already_processed", status=booking.status.value)
            return f"noop:{booking.status.value}"

        try:
            send_confirmation(booking.id, booking.name, booking.service_type)
        except ExternalNotificationError as exc:
            # Финальная попытка: фиксируем failure в БД и прекращаем ретраи.
            if self.request.retries >= self.max_retries:
                booking.status = BookingStatus.FAILED
                session.commit()
                bound_log.error("task.failed", reason=str(exc))
                return "failed"
            # Иначе пробрасываем исключение — autoretry_for поставит задачу
            # в очередь снова с задержкой backoff.
            bound_log.warning("task.retry", reason=str(exc))
            raise

        booking.status = BookingStatus.CONFIRMED
        session.commit()
        bound_log.info("task.confirmed")
        return "confirmed"
