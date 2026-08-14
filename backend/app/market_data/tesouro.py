"""Tesouro Direto (public Brazilian gov bonds) adapter.

Pulls the official daily CSV from tesourotransparente.gov.br, parses it
with pandas, and matches position names by substring + maturity year.
Private RF (LCI, CDB, Voiter) never matches here — stays manual entry.

Schema cache TTL is 6h: the CSV is regenerated daily and shouldn't be
re-downloaded on every refresh click.
"""

from __future__ import annotations

import io
import time

import httpx
import pandas as pd

from app.market_data.base import (
    AdapterNetworkError,
    AdapterNotFoundError,
    Candidate,
    PriceQuote,
)

_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)
_CSV_CACHE_TTL = 6 * 3600  # 6 hours

_cache: dict[str, tuple[pd.DataFrame, float]] = {}


async def _load_csv() -> pd.DataFrame:
    now = time.time()
    cached = _cache.get("csv")
    if cached is not None and now - cached[1] < _CSV_CACHE_TTL:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(_CSV_URL)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text), sep=";", decimal=",")
            
            # Filter out expired bonds (vencimento < latest data base in file)
            venc_date = pd.to_datetime(df["Data Vencimento"], format="%d/%m/%Y", errors="coerce")
            base_date = pd.to_datetime(df["Data Base"], format="%d/%m/%Y", errors="coerce")
            if not base_date.dropna().empty:
                df = df[venc_date >= base_date.max()]
    except Exception as e:
        if cached is not None:
            return cached[0]
        raise AdapterNetworkError(f"Tesouro CSV fetch failed: {e}") from e

    _cache["csv"] = (df, now)
    return df


def _reset_cache_for_tests() -> None:
    _cache.clear()


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


# Distinguishing product keywords across all Tesouro titles. Two titles
# sharing the same keyword (e.g. "Tesouro IPCA+" and "Tesouro IPCA+ com
# Juros Semestrais") are considered the same product family — we pick the
# most-recent row regardless.
_PRODUCT_KEYWORDS = ("educa", "igpm", "ipca", "prefixado", "renda", "selic")


def _product_of(title_or_name: str) -> str | None:
    """Identify the Tesouro product family from a title or position name.
    Strips '+' so "Renda+" and "RENDA +" both resolve to "renda"."""
    s = _normalize(title_or_name).replace("+", "")
    for keyword in _PRODUCT_KEYWORDS:
        if keyword in s:
            return keyword
    return None


class TesouroAdapter:
    async def search(self, query: str) -> list[Candidate]:
        """Search titles in the cached CSV. Matches query against the product
        family (renda/ipca/...). Returns one Candidate per unique maturity of
        the matching product, named like 'TESOURO RENDA + 2064' so the user
        can pick a real year straight from the dropdown."""
        q = query.strip()
        if not q:
            return []
        try:
            df = await _load_csv()
        except Exception:
            return []

        q_product = _product_of(query)
        # If the query doesn't identify a product yet (user typed "tes"),
        # return one representative row per product so they can drill in.
        df_sorted = df.sort_values(by="Data Base", ascending=False)
        seen: set[tuple[str, str]] = set()
        results: list[Candidate] = []

        for _, row in df_sorted.iterrows():
            title_raw = str(row.get("Tipo Titulo", ""))
            title_product = _product_of(title_raw)
            if title_product is None:
                continue
            if q_product is not None and title_product != q_product:
                continue

            maturity = str(row.get("Data Vencimento", ""))
            year = maturity.split("/")[-1] if maturity else ""
            key = (title_product, year)
            if key in seen:
                continue
            seen.add(key)

            price = row.get("PU Compra Manha")
            price_float: float | None = (
                float(price) if price is not None and not pd.isna(price) else None
            )

            display_year = year if year else "sem ano"
            results.append(
                Candidate(
                    name=f"TESOURO {title_product.upper()}+ {display_year}",
                    label=title_raw,
                    current_price_brl=price_float,
                )
            )
            if len(results) >= 20:
                break

        return results

    async def fetch_price(self, external_id: str) -> PriceQuote:
        """external_id is the position.name (e.g. "TESOURO RENDA + 2065").
        Matches CSV rows by product family (ipca/renda/selic/etc.) plus
        maturity year.

        If the product matches but the year doesn't, the error lists years
        available for THAT specific product — so the user can correct the
        position name (e.g. "2065" → "2064")."""
        df = await _load_csv()
        needle = _normalize(external_id)
        needle_product = _product_of(external_id)

        if needle_product is None:
            raise AdapterNotFoundError(
                f"Tesouro: could not identify product family in '{external_id}'"
            )

        df_sorted = df.sort_values(by="Data Base", ascending=False)

        candidate_years: set[str] = set()

        for _, row in df_sorted.iterrows():
            title_raw = str(row.get("Tipo Titulo", ""))
            title_product = _product_of(title_raw)
            if title_product != needle_product:
                continue

            maturity = str(row.get("Data Vencimento", ""))
            year = maturity.split("/")[-1] if maturity else ""
            if year:
                candidate_years.add(year)

            if (not year) or (year in needle):
                price = row.get("PU Compra Manha")
                if price is not None and not pd.isna(price):
                    return PriceQuote.now(
                        external_id=external_id, price_brl=float(price)
                    )

        if candidate_years:
            years_str = ", ".join(sorted(candidate_years))
            raise AdapterNotFoundError(
                f"Tesouro {needle_product}+: no row for the year in "
                f"'{external_id}'. Available years: {years_str}"
            )
        raise AdapterNotFoundError(f"Tesouro: no match for '{external_id}'")
