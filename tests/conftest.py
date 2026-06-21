from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator

import pytest


os.environ.setdefault("DATABASE_URL", "sqlite:///./_test.db")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("WORKER_FAILURE_RATE", "0")
os.environ.setdefault("RATE_LIMIT_CREATE", "1000/minute")

from fastapi.testclient import TestClient  
from sqlalchemy import create_engine 
from sqlalchemy.orm import sessionmaker  

from app.core import db as db_module 
from app.main import app 
from app.models import Base  
from app.worker.celery_app import celery_app 


@pytest.fixture(scope="session", autouse=True)
def _configure_celery_eager() -> Iterator[None]:
    """Запускаем Celery-задачи синхронно прямо в процессе теста."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield


@pytest.fixture()
def engine():
    """Свежий engine + схема на каждый тест — изоляция гарантирована."""
    eng = create_engine("sqlite:///./_test.db", future=True)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()
    # Подчищаем файл БД, чтобы он не утекал между запусками.
    with contextlib.suppress(FileNotFoundError):
        os.remove("./_test.db")


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(engine, session_factory, monkeypatch) -> Iterator[TestClient]:
    """TestClient, привязанный к engine конкретного теста."""
    # Подменяем engine/SessionLocal в модуле app.core.db — все зависимости,
    # которые читают их через атрибут модуля, увидят свежие значения.
    monkeypatch.setattr(db_module, "engine", engine, raising=True)
    monkeypatch.setattr(db_module, "SessionLocal", session_factory, raising=True)
    with TestClient(app) as c:
        yield c
