from __future__ import annotations

import uuid
from typing import Literal

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class PositionOut(BaseModel):
    id: uuid.UUID
    name: str
    asset_type: str
    amount: float
    current_price: float | None = None
    current_value_brl: float  # derived: price x amount OR amount (RF)
    strength: int
    diagram_responses: list[str] | None = None
    source: str
    updated_at: datetime | None = None
    tracking_mode: Literal["balance", "units"]
    external_id: str | None = None
    quote_as_of: datetime | None = None
    quote_stale: bool = False

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
    )


class PositionCreate(BaseModel):
    name: str
    asset_type: str
    amount: float = Field(ge=0, allow_inf_nan=False)
    current_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    tracking_mode: Literal["balance", "units"] | None = None
    external_id: str | None = Field(default=None, max_length=180)
    strength: int
    diagram_responses: list[str] | None = None

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class PositionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    external_id: str | None = Field(default=None, max_length=180)
    amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    current_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    tracking_mode: Literal["balance", "units"] | None = None
    strength: int | None = None
    diagram_responses: list[str] | None = None

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
