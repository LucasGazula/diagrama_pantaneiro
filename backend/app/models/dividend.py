from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Dividend(Base):
    __tablename__ = "dividends"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount_per_share: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="BRL")
    dividend_type: Mapped[str] = mapped_column(String(32), default="Dividendo")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "ticker", "payment_date", "amount_per_share", name="uq_dividends_ticker_paydate_amount"
        ),
    )
