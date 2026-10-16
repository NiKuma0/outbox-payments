"""SQLAlchemy table mappings.

Statuses and currencies are ``VARCHAR`` with CHECK constraints rather than native
Postgres enums: adding a value to a native enum is a migration that cannot run inside
a transaction, a CHECK constraint is an ordinary one.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    MetaData,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from outbox_payments.domain import Currency, JsonObject, PaymentStatus

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TIMESTAMPTZ = DateTime(timezone=True)


def _sql_in(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class PaymentRow(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            f"currency IN ({_sql_in(list(Currency))})", name="currency_known"
        ),
        CheckConstraint(
            f"status IN ({_sql_in(list(PaymentStatus))})", name="status_known"
        ),
    )

    # uuid7 primary keys are time-ordered: inserts append to the right edge of the
    # B-tree instead of splitting random pages, which keeps the index compact.
    id: Mapped[UUID] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[JsonObject] = mapped_column("metadata", JSONB)
    status: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    webhook_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    webhook_delivered_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)


class OutboxRow(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        # The relay only ever scans unpublished rows; a partial index stays tiny no
        # matter how many published rows accumulate before the purge.
        Index(
            "ix_outbox_unpublished",
            "created_at",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
        Index("ix_outbox_published_at", "published_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)  # = event_id
    event_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[UUID]
    payload: Mapped[JsonObject] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    attempts: Mapped[int] = mapped_column(server_default=text("0"), default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
