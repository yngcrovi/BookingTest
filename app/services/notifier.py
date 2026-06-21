from __future__ import annotations

import random
import uuid

from app.core.config import settings
from app.core.logging_config import get_logger

log = get_logger(__name__)


class ExternalNotificationError(RuntimeError):
    pass


def send_confirmation(booking_id: uuid.UUID, name: str, service_type: str) -> None:
    """Делает вид, что зовёт внешний сервис уведомлений.

    С вероятностью ``settings.worker_failure_rate`` бросает
    ``ExternalNotificationError`` — это эмулирует сбой стороннего API.
    При успехе пишет в лог mock-сообщение об отправке.
    """
    if random.random() < settings.worker_failure_rate:
        raise ExternalNotificationError("notification provider unavailable")

    log.info(
        "notification.sent",
        booking_id=str(booking_id),
        name=name,
        service_type=service_type,
        channel="mock",
    )
