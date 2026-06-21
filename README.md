# Booking Service

Backend для записи на встречи. Пользователь создаёт бронь через REST API,
сервис кладёт её в очередь, Celery-воркер в фоне подтверждает запись и пишет
mock-уведомление.

Стек: FastAPI, Celery, PostgreSQL, Redis, Alembic, structlog.

## Запуск

```bash
# 1. создать .env из шаблона
cp .env.example .env

# 2. заполнить значения — пример готового блока ниже,
#    раздел [Переменные окружения](#переменные-окружения).
#    Без .env стек не поднимется (это намеренно).

# 3. поднять стек
docker compose up --build
```

После старта:

- API — http://localhost:8000
- Swagger — http://localhost:8000/docs
- Health — http://localhost:8000/health

## API

| Метод  | Путь             | Описание |
|--------|------------------|----------|
| POST   | `/bookings`      | Создать бронь: `name`, `datetime`, `service_type` |
| GET    | `/bookings/{id}` | Получить бронь и её статус |
| GET    | `/bookings`      | Список с фильтром `status=` и пагинацией `limit/offset` |
| DELETE | `/bookings/{id}` | Отменить бронь — только если она ещё `pending` |
| GET    | `/health`        | Liveness-проба |

Статусы: `pending` → `confirmed` / `failed`; из `pending` можно уйти в `cancelled`.

Пример:

```bash
curl -X POST http://localhost:8000/bookings \
  -H 'content-type: application/json' \
  -d '{"name":"Alice","datetime":"2026-07-01T10:00:00Z","service_type":"consultation"}'
```

Ответ приходит сразу со статусом `pending` — через ~30 мс воркер обычно успевает
перевести бронь в `confirmed`. В `failed` бронь уходит, только если mock-сервис
сфейлит **все 4 попытки подряд** (1 первая + 3 ретрая). При `WORKER_FAILURE_RATE=0.15`
это ~0.05% случаев; чтобы воспроизвести сценарий целенаправленно — поставь
`WORKER_FAILURE_RATE=1.0` в `.env` и перезапусти воркер.

## Тесты

Docker для тестов не нужен — гоняем на SQLite и Celery в eager-режиме:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

С отчётом о покрытии: `make test-cov`.

## Локальная разработка без Docker

```bash
pip install -e ".[dev]"
cp .env.example .env       # затем POSTGRES_HOST=localhost и т.д.
make migrate               # alembic upgrade head
make dev                   # uvicorn с reload
make worker                # в другом терминале — Celery
```

Цели Makefile: `dev`, `worker`, `test`, `test-cov`, `lint`, `format`, `migrate`,
`up`, `down`, `logs`, `clean`.

## Структура проекта

```
app/
  main.py            точка входа FastAPI
  models.py          ORM-модель Booking
  schemas.py         Pydantic-схемы
  api/               HTTP-роутеры (тонкий слой над сервисами)
  services/          бизнес-логика: BookingService + notifier
  worker/            Celery-приложение и задачи
  core/              инфраструктура: config, db, logging, rate-limit
alembic/             миграции
tests/               pytest (SQLite + eager Celery)
docker/              entrypoint.sh для контейнера
```

## Технические решения

**FastAPI + Celery.** FastAPI закрывает требования к API (валидация через
Pydantic, `/docs` из коробки) минимальным кодом. Celery с Redis-брокером —
самый прямой способ закрыть требования к фоновой обработке: отдельный
долгоживущий процесс, retry-политики, backoff. TaskIQ в ТЗ был указан как
альтернатива; выбрал Celery как более прямое попадание в требования.

**Идемпотентность задачи.** `bookings.process` получает только `booking_id`.
Перед любым действием воркер читает текущий статус: если запись не в `pending`
(уже обработана, отменена или вовсе отсутствует) — выходит no-op'ом. Это
безопасно при дублирующей доставке, которую разрешает
`task_acks_late=True` + `task_reject_on_worker_lost=True` (если воркер падает
посреди работы, сообщение возвращается в очередь и достаётся другому воркеру).

**Retry с экспоненциальным backoff.** Стандартный механизм Celery:

```python
@celery_app.task(
    autoretry_for=(ExternalNotificationError,),
    retry_backoff=2, retry_backoff_max=60, retry_jitter=True,
    max_retries=settings.worker_max_retries,
)
```

Пока ретраи не исчерпаны — бронь остаётся `pending`. В `failed` уходит только
на финальной попытке, чтобы не сбивать с толку клиента промежуточным
состоянием.

**Логи.** structlog в JSON на stdout, единым потоком для FastAPI, SQLAlchemy и
Celery. Пример:

```json
{"event": "task.confirmed", "booking_id": "8b7c…", "attempt": 1, "level": "info", "timestamp": "..."}
```

Чтобы Celery не перебивал формат своим текстовым логером, подписался на сигнал
`setup_logging` — это полностью отключает дефолтную конфигурацию Celery.

**Rate limiting.** `slowapi` на `POST /bookings`, 10 запросов/мин на IP по
умолчанию (`RATE_LIMIT_CREATE`). В тестах лимит задирается до 1000/мин, чтобы
фикстуры не ловили 429.

**Хранилище.** PostgreSQL + SQLAlchemy 2.0 (Declarative с `Mapped[...]`),
миграции через Alembic. Сырых SQL нет — только ORM. В Alembic-миграции есть
`sa.text("CURRENT_TIMESTAMP")` для server-side default'ов, но это часть DDL,
а не запросов.

**Тесты без Docker.** Используют файловый SQLite (`./_test.db`) и
`task_always_eager=True` — задача выполняется синхронно прямо в запросе.
Это позволяет проверить полный путь POST → задача → апдейт статуса одним
`pytest` без Redis и Postgres.

Что покрыто:

- API: 201 / 422 (валидация) / 404 (нет такой брони) / 409 (нельзя отменить
  не-`pending`), пагинация, фильтр по статусу.
- Воркер: успех, переход в `failed` после исчерпания ретраев, идемпотентность
  на повторный запуск, пропуск отсутствующей брони, отказ трогать
  `cancelled`.

## Переменные окружения

`.env.example` пустой — это шаблон, чтобы случайно ничего не утекло. Заполни
`.env` своими значениями или скопируй блок ниже (рабочий пресет для Docker).

| Переменная              | Пример для Docker                              | Назначение |
|-------------------------|------------------------------------------------|------------|
| `API_HOST`              | `0.0.0.0`                                      | Хост uvicorn |
| `API_PORT`              | `8000`                                         | Порт API |
| `LOG_LEVEL`             | `INFO`                                         | Уровень логирования |
| `RATE_LIMIT_CREATE`     | `10/minute`                                    | Лимит на `POST /bookings` (формат slowapi) |
| `POSTGRES_USER`         | `booking`                                      | Пользователь БД |
| `POSTGRES_PASSWORD`     | `booking`                                      | Пароль БД |
| `POSTGRES_DB`           | `booking`                                      | Имя БД |
| `POSTGRES_HOST`         | `postgres` в Docker, `localhost` локально      | Хост БД |
| `POSTGRES_PORT`         | `5432`                                         | Порт БД |
| `REDIS_URL`             | `redis://redis:6379/0`                         | Redis (общий) |
| `CELERY_BROKER_URL`     | `redis://redis:6379/1`                         | Брокер Celery |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2`                         | Result backend |
| `WORKER_FAILURE_RATE`   | `0.15`                                         | Вероятность фейла mock-сервиса |
| `WORKER_MAX_RETRIES`    | `3`                                            | Максимум ретраев на задачу |

Готовый блок в `.env`:

```dotenv
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
RATE_LIMIT_CREATE=10/minute
POSTGRES_USER=booking
POSTGRES_PASSWORD=booking
POSTGRES_DB=booking
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
WORKER_FAILURE_RATE=0.15
WORKER_MAX_RETRIES=3
```

## Чего не использовал

- Аутентификация и multi-tenancy — за рамками ТЗ.
- Полноценный outbox — для текущего масштаба хватает `acks_late` +
  идемпотентности задачи.
- TaskIQ как альтернатива Celery — выбор стека закреплён в пользу основного
  варианта из ТЗ.
