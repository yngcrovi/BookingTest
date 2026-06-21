from __future__ import annotations

from celery import Celery
from celery.signals import setup_logging

from app.core.config import settings
from app.core.logging_config import configure_logging

celery_app = Celery(
    "booking",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=1000,
)


@setup_logging.connect
def _setup_logging(**_: object) -> None:
    """Полностью заменяем дефолтное логирование Celery на наш structlog.

    Сам факт подключения обработчика к сигналу ``setup_logging`` отключает
    встроенную настройку Celery — иначе наши JSON-логи перебивались бы
    форматом по умолчанию
    """
    configure_logging()
