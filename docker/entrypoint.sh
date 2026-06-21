#!/usr/bin/env bash
# Универсальный entrypoint для контейнера: одна и та же команда годится
# и для API ("api"), и для Celery-воркера ("worker"). Выбор режима — через
# первый аргумент. Перед стартом обязательно ждём, пока поднимется Postgres.
set -euo pipefail

cmd="${1:-api}"

# Простейшее ожидание TCP-порта без зависимости от netcat/wait-for-it.
wait_for() {
  local host="$1"
  local port="$2"
  local name="$3"
  echo "waiting for ${name} at ${host}:${port}..."
  for _ in $(seq 1 60); do
    if (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
      echo "${name} is up."
      return 0
    fi
    sleep 1
  done
  echo "${name} did not become available in time" >&2
  exit 1
}

wait_for "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "postgres"

case "${cmd}" in
  api)
    # Перед стартом API накатываем миграции — это безопасно,
    # т.к. alembic upgrade head идемпотентен.
    echo "applying migrations..."
    alembic upgrade head
    exec uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
    ;;
  worker)
    exec celery -A app.worker.celery_app.celery_app worker --loglevel="${LOG_LEVEL:-INFO}"
    ;;
  *)
    # Произвольная команда — например, для отладки: docker compose run api bash
    exec "$@"
    ;;
esac
