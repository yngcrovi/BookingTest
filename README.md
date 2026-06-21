# Booking Service

Маленький backend для записи на встречи. Пользователь создаёт бронь через REST API,
сервис ставит её в очередь, Celery-воркер асинхронно подтверждает запись и логирует
mock-уведомление.

Стек: **FastAPI** · **Celery** · **PostgreSQL** · **Redis** · **Alembic** · **structlog**

---

## TL;DR

```bash
docker compose up --build
```

Без дополнительных шагов: `docker-compose.yml` содержит рабочие дефолты,
файл `.env` опционален. Если нужно что-то переопределить — скопируй шаблон:
`cp .env.example .env` и правь.

После старта:

* API:           http://localhost:8000
* Swagger UI:    http://localhost:8000/docs
* Healthcheck:   http://localhost:8000/health

---

## API

| Метод  | Путь                  | Описание                                          |
|--------|-----------------------|---------------------------------------------------|
| POST   | `/bookings`           | Создать бронь (`name`, `datetime`, `service_type`) |
| GET    | `/bookings/{id}`      | Получить бронь и её статус                        |
| GET    | `/bookings`           | Список с фильтром `status=` и пагинацией `limit/offset` |
| DELETE | `/bookings/{id}`      | Отменить бронь (только в статусе `pending`)       |
| GET    | `/health`             | Liveness-проба                                    |

Возможные статусы: `pending`, `confirmed`, `failed`, `cancelled`.

Пример:

```bash
curl -X POST http://localhost:8000/bookings \
  -H 'content-type: application/json' \
  -d '{"name":"Alice","datetime":"2026-07-01T10:00:00Z","service_type":"consultation"}'
```

Ответ:

```json
{
  "id": "8b7c…",
  "name": "Alice",
  "datetime": "2026-07-01T10:00:00+00:00",
  "service_type": "consultation",
  "status": "pending",
  "created_at": "…",
  "updated_at": "…"
}
```

Через секунду статус становится `confirmed` (или `failed` с вероятностью ≈15%).

---

## Запуск тестов

Тесты не требуют Docker — используют SQLite-файл и Celery в eager-режиме.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

Покрытие:

```bash
make test-cov
```

---

## Локальная разработка без Docker

```bash
pip install -e ".[dev]"
cp .env.example .env       # затем правим POSTGRES_HOST=localhost, REDIS_URL=…
make migrate               # alembic upgrade head
make dev                   # uvicorn с reload
make worker                # в отдельном терминале — Celery-воркер
```

Makefile-цели: `dev`, `worker`, `test`, `test-cov`, `lint`, `format`, `migrate`, `up`, `down`, `logs`, `clean`.

---

## Технические решения

### Почему FastAPI + Celery
FastAPI даёт автогенерируемые контракты (`/docs`) и валидацию через Pydantic
"из коробки" — на этом масштабе это самое короткое расстояние от ТЗ до работающего
API. Celery с Redis-broker'ом — индустриальный стандарт под именно ту задачу,
которая описана в требованиях (отдельный долгоживущий воркер, retry-политики,
backoff). TaskIQ был указан как «плюс», но Celery был выбран намеренно — он
прямее закрывает основное требование, а его экосистема (signals, retry,
acks_late) экономит много кода.

### Структура проекта
```
app/
  api/         — HTTP-роутеры (тонкий слой над сервисами)
  services/    — бизнес-логика (создание / получение / отмена брони, notifier)
  worker/      — Celery app + tasks
  models.py    — SQLAlchemy ORM
  schemas.py   — Pydantic DTO
  config.py    — настройки через pydantic-settings
  db.py        — engine + сессия
  rate_limit.py
  logging_config.py
alembic/       — миграции
tests/         — pytest (SQLite + eager Celery)
docker/        — entrypoint.sh
```

Роутеры намеренно "тонкие": вся работа с БД и доменом — в `app/services`.
Это даёт удобство тестирования (сервисы дёргаются напрямую) и одинаковую
логику для API и воркера.

### Идемпотентность задачи
`bookings.process` принимает `booking_id`. Перед любым действием воркер
читает текущий статус и:

* если запись отсутствует → `missing`;
* если статус **не** `pending` → no-op (повторный запуск той же задачи или
  гонка с отменой не создают дубль и не "переподтверждают" бронь);
* иначе вызывает mock-внешний сервис, и только потом — атомарно — обновляет
  статус на `confirmed` / `failed`.

Дополнительно: `task_acks_late=True` + `task_reject_on_worker_lost=True` —
если воркер падает посреди обработки, сообщение остаётся в очереди и
переобрабатывается. Поскольку задача идемпотентна, дублирующая доставка
безопасна.

### Retry с экспоненциальным backoff
Реализован стандартным Celery-механизмом:

```python
@celery_app.task(
    autoretry_for=(ExternalNotificationError,),
    retry_backoff=2, retry_backoff_max=60, retry_jitter=True,
    max_retries=settings.worker_max_retries,
)
```

В `failed` запись переводится только после исчерпания всех ретраев — на
промежуточных попытках бронь остаётся `pending`, что согласуется с логикой
идемпотентности.

### Логи
`structlog` → JSON на stdout, единый формат для FastAPI, SQLAlchemy и Celery.
Пример строки:

```json
{"event": "booking.created", "booking_id": "8b7c…", "level": "info", "timestamp": "2026-06-19T12:00:00Z"}
```

### Rate limiting
`slowapi` на `POST /bookings`: 10 запросов/мин на IP по умолчанию,
настраивается через `RATE_LIMIT_CREATE`. В тестах лимит подменяется на
заведомо большой — чтобы фикстуры не натыкались на 429.

### Хранилище
PostgreSQL + SQLAlchemy 2.0 (Declarative с `Mapped[...]`), миграции —
Alembic. Никаких сырых SQL-запросов: всё через ORM.

### Тесты без Docker
Тесты используют файловый SQLite (`./_test.db`) и `task_always_eager=True` —
Celery-задача выполняется внутри запроса. Это позволяет проверить полный
путь (POST → задача → обновление статуса) одним `pytest`'ом без
необходимости поднимать брокер.

Покрытие:
* API: happy path, 404, 422 (валидация), 409 (нельзя отменить
  `confirmed`/`cancelled`), пагинация, фильтр по статусу;
* воркер: успех, окончательный фейл после исчерпания ретраев,
  идемпотентность при повторном запуске, отсутствующая бронь,
  отменённая бронь не трогается.

---

## Структура `.env`

См. `.env.example`. Ключевые переменные:

| Переменная             | По умолчанию          | Назначение |
|------------------------|-----------------------|-----------|
| `DATABASE_URL`         | собирается из частей  | Полный URL Postgres'а. Если не задан — собирается из `POSTGRES_*`. |
| `CELERY_BROKER_URL`    | `redis://redis:6379/1`| Брокер Celery. |
| `CELERY_RESULT_BACKEND`| `redis://redis:6379/2`| Result backend. |
| `WORKER_FAILURE_RATE`  | `0.15`                | Вероятность фейла mock-внешнего вызова. |
| `WORKER_MAX_RETRIES`   | `3`                   | Сколько раз ретраить транзиентный фейл. |
| `RATE_LIMIT_CREATE`    | `10/minute`           | Лимит для `POST /bookings`. |

---

## Чего здесь сознательно нет

* Аутентификации / multi-tenancy — выходит за рамки ТЗ.
* Полноценного outbox-паттерна — для текущего объёма достаточно
  `acks_late` + идемпотентности задачи.
* Async-FastAPI + TaskIQ как альтернативы Celery — выбор стека был
  закреплён в пользу основного варианта из ТЗ; переход на async-стек —
  механическая правка слоя `services` и замена воркера.
