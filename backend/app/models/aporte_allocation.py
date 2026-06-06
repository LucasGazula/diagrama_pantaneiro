from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class AporteAllocation(Base):
    __tablename__ = "aporte_allocations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aporte_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aporte_events.id", ondelete="CASCADE"), index=True
    )
    # SET NULL on position delete so history survives position removal
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Snapshot fields (survive position deletion)
    position_name_snapshot: Mapped[str] = mapped_column(String(128))
    asset_type_snapshot: Mapped[str] = mapped_column(String(48))
    price_at_aporte_brl: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Suggestion (what the algorithm computed)
    suggested_value_brl: Mapped[float] = mapped_column(Float)
    suggested_quantity: Mapped[float] = mapped_column(Float)

    # Apply action
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_value_brl: Mapped[float | None] = mapped_column(Float, nullable=True)
    applied_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Exclusion (user chose not to allocate to this asset)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    event: Mapped["AporteEvent"] = relationship(back_populates="allocations")
