from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import BookingStatus


class BookingCreate(BaseModel):
    "Новая бронь"
    name: str = Field(..., min_length=1, max_length=120)
    datetime: datetime
    service_type: str = Field(..., min_length=1, max_length=64)


class BookingOut(BaseModel):
    # from_attributes=True позволяет валидатору читать значения из ORM-объекта.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    datetime: datetime
    service_type: str
    status: BookingStatus
    created_at: datetime
    updated_at: datetime


class BookingPage(BaseModel):
    """Страница списка броней + метаданные пагинации."""

    items: list[BookingOut]
    total: int
    limit: int
    offset: int
