"""начальная схема: таблица bookings

Revision ID: 0001
Revises:
Create Date: 2026-06-19 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "confirmed", "failed", "cancelled", name="booking_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_bookings_status", "bookings", ["status"])
    op.create_index("ix_bookings_created_at", "bookings", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_bookings_created_at", table_name="bookings")
    op.drop_index("ix_bookings_status", table_name="bookings")
    op.drop_table("bookings")
    sa.Enum(name="booking_status").drop(op.get_bind(), checkfirst=True)
