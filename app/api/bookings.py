import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.logging_config import get_logger
from app.core.rate_limit import CREATE_LIMIT, limiter
from app.models import BookingStatus
from app.schemas import BookingCreate, BookingOut, BookingPage
from app.services.bookings import (
    BookingNotCancellableError,
    BookingNotFoundError,
    BookingService,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])
log = get_logger(__name__)


def get_booking_service(session: Annotated[Session, Depends(get_session)]) -> BookingService:
    """FastAPI-зависимость: собирает сервис, привязанный к сессии запроса."""
    return BookingService(session)


# Готовый тип для аннотаций — чтобы в каждом роуте не повторять Annotated[...].
ServiceDep = Annotated[BookingService, Depends(get_booking_service)]


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(CREATE_LIMIT)
def create_booking(
    request: Request,  # обязательный позиционный аргумент для slowapi
    payload: Annotated[BookingCreate, Body()],
    service: ServiceDep,
) -> BookingOut:
    booking = service.create(payload)
    # Импорт внутри функции — чтобы модуль API можно было импортировать
    from app.worker.tasks import process_booking

    process_booking.delay(str(booking.id))
    log.info("booking.created", booking_id=str(booking.id))
    return BookingOut.model_validate(booking)


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: uuid.UUID,
    service: ServiceDep,
) -> BookingOut:
    try:
        booking = service.get(booking_id)
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="booking not found") from exc
    return BookingOut.model_validate(booking)


@router.get("", response_model=BookingPage)
def list_bookings(
    service: ServiceDep,
    status_filter: Annotated[BookingStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BookingPage:
    items, total = service.list(status=status_filter, limit=limit, offset=offset)
    return BookingPage(
        items=[BookingOut.model_validate(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_booking(
    booking_id: uuid.UUID,
    service: ServiceDep,
) -> Response:
    try:
        service.cancel(booking_id)
    except BookingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="booking not found") from exc
    except BookingNotCancellableError as exc:
        # Отмена разрешена только из pending — иначе 409.
        raise HTTPException(
            status_code=409,
            detail=f"cannot cancel booking in status '{exc.args[0]}'",
        ) from exc
    log.info("booking.cancelled", booking_id=str(booking_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
