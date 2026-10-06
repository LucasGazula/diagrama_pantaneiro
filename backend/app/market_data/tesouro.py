"""Tesouro Direto (public Brazilian gov bonds) adapter.

Streams the official CSV to a temporary file, retaining only the latest
quotes per product and maturity year instead of the full historical dataset.
Private RF (LCI, CDB, Voiter) never matches here — stays manual entry.

Schema cache TTL is 6h: the CSV is regenerated daily and shouldn't be
re-downloaded on every refresh click.
"""

from __future__ import annotations

import asyncio
import csv
import io
import math
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import BinaryIO

from app.market_data.base import (
    AdapterNetworkError,
    AdapterNotFoundError,
    Candidate,
    PriceQuote,
)
from app.market_data.http_client import market_client

_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)
_CSV_CACHE_TTL = 6 * 3600  # 6 hours


@dataclass(slots=True)
class _Title:
    product: str
    year: str
    title: str
    maturity: date
    updated: date
    price: float | None
    quote_date: date
    quote_price: float | None


_cache: dict[str, tuple[list[_Title], float]] = {}
_load_lock = asyncio.Lock()
_retry_after = 0.0


def _read_titles(source: BinaryIO) -> list[_Title]:
    """Reduce history in one pass. Keep older valid prices when newest is missing."""

    @lru_cache(maxsize=8192)
    def parse_date(value: str) -> date:
        day, month, year = value.split("/")
        return date(int(year), int(month), int(day))

    titles: dict[tuple[str, date], _Title] = {}
    latest = date.min
    source.seek(0)
    text = io.TextIOWrapper(source, encoding="utf-8-sig", newline="")
    try:
        reader = csv.DictReader(text, delimiter=";")
        required = {"Tipo Titulo", "Data Vencimento", "Data Base", "PU Compra Manha"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Tesouro CSV missing required columns")
        for row in reader:
            updated = parse_date(row["Data Base"])
            latest = max(latest, updated)
            maturity = parse_date(row["Data Vencimento"])
            if maturity < latest:
                continue
            title = row["Tipo Titulo"]
            product = _product_of(title)
            if product is None:
                continue
            year = str(maturity.year)
            raw_price = row["PU Compra Manha"].strip()
            price = float(raw_price.replace(",", ".")) if raw_price else None
            if price is not None and (not math.isfinite(price) or price <= 0):
                price = None
            key = (title, maturity)
            previous = titles.get(key)
            if previous is None:
                titles[key] = _Title(
                    product,
                    year,
                    title,
                    maturity,
                    updated,
                    price,
                    updated if price is not None else date.min,
                    price,
                )
                continue
            if updated > previous.updated:
                previous.title = title
                previous.maturity = maturity
                previous.updated = updated
                previous.price = price
            if price is not None and updated > previous.quote_date:
                previous.quote_date = updated
                previous.quote_price = price
    finally:
        text.detach()
    return sorted(
        (t for t in titles.values() if t.maturity >= latest), key=lambda t: t.updated, reverse=True
    )


async def _load_csv() -> list[_Title]:
    global _retry_after
    async with _load_lock:
        now = time.monotonic()
        cached = _cache.get("csv")
        if cached is not None and (now - cached[1] < _CSV_CACHE_TTL or now < _retry_after):
            return cached[0]
        try:
            with tempfile.TemporaryFile() as source:
                async with market_client() as client:
                    async with client.stream("GET", _CSV_URL, timeout=30.0) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes(64 * 1024):
                            source.write(chunk)
                titles = await asyncio.to_thread(_read_titles, source)
        except Exception as e:
            if cached is not None:
                _retry_after = time.monotonic() + 60
                return cached[0]
            raise AdapterNetworkError(f"Tesouro CSV fetch failed: {e}") from e
        _cache["csv"] = (titles, time.monotonic())
        _retry_after = 0.0
        return titles


def _reset_cache_for_tests() -> None:
    global _load_lock, _retry_after
    _cache.clear()
    _load_lock = asyncio.Lock()
    _retry_after = 0.0


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


# Product families are search filters only; title + full maturity identify a security.
_PRODUCT_KEYWORDS = ("educa", "igpm", "ipca", "prefixado", "renda", "selic")


def _product_of(title_or_name: str) -> str | None:
    """Identify the Tesouro product family from a title or position name.
    Strips '+' so "Renda+" and "RENDA +" both resolve to "renda"."""
    s = _normalize(title_or_name).replace("+", "")
    for keyword in _PRODUCT_KEYWORDS:
        if keyword in s:
            return keyword
    return None


def _display_year(title: _Title) -> str:
    # Renda+/Educa+ names use the start of income, not the final amortization.
    offset = {"renda": 19, "educa": 4}.get(title.product, 0)
    return str(title.maturity.year - offset)


def _external_id(title: _Title) -> str:
    return f"{title.title}|{title.maturity.isoformat()}"


def _instrument(name: str) -> tuple[str | None, bool]:
    return _product_of(name), "semestrais" in _normalize(name)


class TesouroAdapter:
    async def search(self, query: str) -> list[Candidate]:
        q = _normalize(query)
        if not q:
            return []
        if re.search(r"\b(cdb|lci|lca|cri|cra|deb[eê]ntures?|voiter)\b", q):
            return []
        product = _product_of(q)
        if product is None and not (q.startswith("tes") or q.isdigit()):
            return []
        try:
            titles = await _load_csv()
        except AdapterNetworkError:
            return []
        years = re.findall(r"\b\d{4}\b", q)
        latest = max((t.updated for t in titles), default=date.min)
        results = []
        for title in titles:
            if product is not None and title.product != product:
                continue
            if "semestrais" in q and "semestrais" not in _normalize(title.title):
                continue
            if years and _display_year(title) not in years:
                continue
            # Historical quotes may value holdings but cannot imply availability to buy.
            if title.updated != latest or title.price is None or title.maturity <= date.today():
                continue
            results.append(
                Candidate(
                    name=f"{title.title.upper()} {_display_year(title)}",
                    label=f"{title.title} · vencimento {title.maturity:%d/%m/%Y}",
                    current_price_brl=title.price,
                    external_id=_external_id(title),
                    quote_as_of=datetime.combine(title.updated, datetime.min.time(), timezone.utc),
                )
            )
        return sorted(results, key=lambda c: c.name)[:20]

    async def fetch_price(self, external_id: str) -> PriceQuote:
        titles = await _load_csv()
        if "|" in external_id:
            matches = [t for t in titles if _external_id(t) == external_id]
        else:
            product, coupons = _instrument(external_id)
            years = re.findall(r"\b\d{4}\b", external_id)
            matches = [
                t
                for t in titles
                if _instrument(t.title) == (product, coupons) and _display_year(t) in years
            ]
        if len(matches) != 1:
            raise AdapterNotFoundError(
                f"Tesouro: título não encontrado ou ambíguo: '{external_id}'. "
                "Selecione título completo no catálogo (incluindo juros semestrais)."
            )
        title = matches[0]
        if title.quote_price is None:
            raise AdapterNotFoundError(f"Tesouro: sem cotação válida para '{external_id}'")
        now = datetime.now(timezone.utc)
        as_of = datetime.combine(title.quote_date, datetime.min.time(), timezone.utc)
        # Daily source: weekends/holidays tolerated; older fallbacks remain visible as stale.
        stale = (now.date() - title.quote_date).days > 4 or title.price is None or _retry_after > 0
        return PriceQuote(external_id, title.quote_price, now, as_of=as_of, stale=stale)
