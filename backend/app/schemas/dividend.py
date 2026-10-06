from __future__ import annotations

import uuid
from datetime import date
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class DividendItemOut(BaseModel):
    id: uuid.UUID
    ticker: str
    asset_type: str
    payment_date: date
    ex_date: date | None = None
    amount_shares: float
    rate_native: float
    currency: str
    rate_brl: float
    rate_net_brl: float
    total_native: float
    total_brl: float
    total_net_brl: float
    tax_rate: float = 0.0
    tax_brl: float = 0.0
    is_jcp: bool = False
    dividend_type: str
    status: str  # "pago" | "previsto"

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class DividendCalendarOut(BaseModel):
    year: int
    month: int
    date_mode: str  # "payment" | "ex"
    usd_rate: float
    total_received_brl: float
    total_received_net_brl: float
    total_projected_brl: float
    total_projected_net_brl: float
    total_month_brl: float
    total_month_net_brl: float
    total_tax_brl: float
    items: list[DividendItemOut]

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class DividendSyncOut(BaseModel):
    synced_tickers: int
    failed_tickers: list[str]
    total_dividends_stored: int

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
