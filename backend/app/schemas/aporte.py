from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class AporteCreate(BaseModel):
    value: float = Field(gt=0, allow_inf_nan=False)


class AporteAllocationOut(BaseModel):
    id: uuid.UUID
    position_id: uuid.UUID | None = None
    position_name_snapshot: str
    asset_type_snapshot: str
    price_at_aporte_brl: float | None = None
    tracking_mode_snapshot: str | None = None
    suggested_value_brl: float
    suggested_quantity: float
    applied: bool
    applied_at: datetime | None = None
    applied_value_brl: float | None = None
    applied_quantity: float | None = None
    excluded: bool = False

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, from_attributes=True)


class AporteEventOut(BaseModel):
    id: uuid.UUID
    aporte_value_brl: float
    created_at: datetime
    allocations: list[AporteAllocationOut]

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, from_attributes=True)


class ApplyRequest(BaseModel):
    applied_value_brl: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    applied_quantity: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class ExcludeRequest(BaseModel):
    allocation_id: uuid.UUID
