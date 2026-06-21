FROM python:3.11-slim AS base

# Запрещаем буферизацию stdout и генерацию .pyc — в контейнере это лишнее.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# build-essential + libpq-dev нужны для сборки psycopg2 из исходников
# на случай отсутствия колеса под нашу архитектуру.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Сначала ставим зависимости — слой попадает в кэш, переустанавливается
# только при изменении pyproject.toml.
COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
