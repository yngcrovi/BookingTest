from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.bookings import router as bookings_router
from app.core.logging_config import configure_logging
from app.core.rate_limit import limiter

configure_logging()


def create_app() -> FastAPI:
    """Фабрика FastAPI-приложения.

    Вынесено в функцию, чтобы было удобно собирать отдельный экземпляр
    в тестах или с переопределёнными зависимостями.
    """
    app = FastAPI(
        title="Booking Service",
        version="0.1.0",
        description="Сервис записи на встречи: FastAPI + Celery.",
    )

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": f"rate limit exceeded: {exc.detail}"},
        )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Проба жизнеспособности — используется в docker-compose healthcheck."""
        return {"status": "ok"}

    app.include_router(bookings_router)
    return app


app = create_app()
