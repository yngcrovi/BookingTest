.PHONY: dev test test-cov lint format migrate revision worker up down logs clean

# Локальный API-сервер с автоперезагрузкой.
dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Локальный Celery-воркер.
worker:
	celery -A app.worker.celery_app.celery_app worker --loglevel=INFO

# Тесты.
test:
	pytest -v

# Тесты с отчётом о покрытии.
test-cov:
	pytest --cov=app --cov-report=term-missing

# Линт через ruff (без автофикса).
lint:
	ruff check app tests
	ruff format --check app tests

# Автоформатирование и автофикс.
format:
	ruff check --fix app tests
	ruff format app tests

# Применить миграции к текущему DATABASE_URL.
migrate:
	alembic upgrade head

# Сгенерировать новую миграцию. Использование: make revision msg="add field"
revision:
	alembic revision --autogenerate -m "$(msg)"

# Поднять весь стек через docker compose.
up:
	docker compose up --build

# Остановить и удалить контейнеры + тома.
down:
	docker compose down -v

logs:
	docker compose logs -f

# Удалить кэши и временные файлы.
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
