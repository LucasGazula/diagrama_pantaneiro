from __future__ import annotations

import asyncio
import calendar
import uuid
from collections import OrderedDict
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup, SoupStrainer
import httpx
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from app.market_data.usd_brl import get_usd_brl_rate
from app.market_data.base import AdapterNetworkError, FETCH_CONCURRENCY, fetch_slots
from app.models.dividend import Dividend
from app.models.position import Position
from app.schemas.dividend import DividendCalendarOut, DividendItemOut, DividendSyncOut

DIVIDEND_ASSET_TYPES = {
    "acoes_nacionais",
    "fundos_imobiliarios",
    "acoes_internacionais",
    "reits",
}

_FUNDAMENTUS_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_last_sync: OrderedDict[str, date] = OrderedDict()


def _to_py_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if hasattr(val, "date") and callable(val.date):
        try:
            return val.date()
        except Exception:
            pass
    if isinstance(val, str):
        v = val.strip().split("T")[0].split(" ")[0]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(v, fmt).date()
            except Exception:
                pass
    return None


def _parse_pt_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").date()
    except Exception:
        return None


def _parse_pt_float(s: str) -> float | None:
    try:
        return float(s.strip().replace(".", "").replace(",", "."))
    except Exception:
        return None


def _is_jcp(dividend_type: str | None) -> bool:
    if not dividend_type:
        return False
    dt = dividend_type.upper()
    return any(k in dt for k in ("JRS", "JCP", "JUROS", "JSCP"))


def _fetch_fundamentus_sync(
    ticker: str, asset_type: str
) -> dict[tuple[date, float], dict[str, Any]]:
    clean = ticker.upper().strip()
    records: dict[tuple[date, float], dict[str, Any]] = {}
    if asset_type == "fundos_imobiliarios":
        url = f"https://www.fundamentus.com.br/fii_proventos.php?papel={clean}&tipo=2"
    elif asset_type == "acoes_nacionais":
        url = f"https://www.fundamentus.com.br/proventos.php?papel={clean}"
    else:
        return records

    try:
        r = httpx.get(url, headers=_FUNDAMENTUS_HEADERS, follow_redirects=True, timeout=10.0)
        r.raise_for_status()
        soup = BeautifulSoup(
            r.text, "html.parser", parse_only=SoupStrainer("table", id="resultado")
        )
        table = soup.find("table", {"id": "resultado"})
        if table:
            for tr in table.find_all("tr")[1:]:
                tds = [td.text.strip() for td in tr.find_all("td")]
                if asset_type == "fundos_imobiliarios" and len(tds) >= 4:
                    ex_d = _parse_pt_date(tds[0])
                    div_type = tds[1] or "Rendimento"
                    pay_d = _parse_pt_date(tds[2]) or ex_d
                    val = _parse_pt_float(tds[3])
                    if pay_d and val and val > 0:
                        records[(pay_d, round(val, 6))] = {
                            "ticker": clean,
                            "payment_date": pay_d,
                            "ex_date": ex_d,
                            "amount_per_share": val,
                            "currency": "BRL",
                            "dividend_type": div_type,
                        }
                elif asset_type == "acoes_nacionais" and len(tds) >= 4:
                    ex_d = _parse_pt_date(tds[0])
                    val = _parse_pt_float(tds[1])
                    div_type = tds[2] or "Dividendo"
                    pay_d = _parse_pt_date(tds[3]) or ex_d
                    if pay_d and val and val > 0:
                        records[(pay_d, round(val, 6))] = {
                            "ticker": clean,
                            "payment_date": pay_d,
                            "ex_date": ex_d,
                            "amount_per_share": val,
                            "currency": "BRL",
                            "dividend_type": div_type,
                        }
    except Exception:
        pass

    return records


def _fetch_ticker_dividends_sync(ticker: str, asset_type: str) -> list[dict[str, Any]]:
    import yfinance as yf

    # An upstream failure must be reported, not mistaken for an empty history
    # that would replace previously cached dividends.
    yf.config.debug.hide_exceptions = False

    clean_ticker = ticker.strip().upper()
    records: dict[tuple[date, float], dict[str, Any]] = {}

    # 1. For Brazilian assets, query Fundamentus first (has exact ex_date and payment_date)
    if asset_type in ("acoes_nacionais", "fundos_imobiliarios"):
        records = _fetch_fundamentus_sync(clean_ticker, asset_type)

    # 2. Query yfinance (primary for US assets, supplementary for B3 recent declarations)
    if asset_type in ("acoes_nacionais", "fundos_imobiliarios") and not clean_ticker.endswith(
        ".SA"
    ):
        yf_symbol = f"{clean_ticker}.SA"
    else:
        yf_symbol = clean_ticker

    t = yf.Ticker(yf_symbol)
    currency = "BRL" if asset_type in ("acoes_nacionais", "fundos_imobiliarios") else "USD"
    default_div_type = (
        "Rendimento" if asset_type in ("fundos_imobiliarios", "reits") else "Dividendo"
    )

    # Historical / declared in yfinance
    history_error: Exception | None = None
    try:
        df = t.dividends
        if df is not None and not df.empty:
            series_items = df.items() if hasattr(df, "items") else df.iterrows()
            for idx, val in series_items:
                val = float(val.iloc[0]) if hasattr(val, "iloc") else float(val)
                if val <= 0:
                    continue
                d = _to_py_date(idx)
                if not d:
                    continue
                round_val = round(val, 6)

                # Check if Fundamentus already has this dividend (by month and amount)
                already_has = any(
                    rec["amount_per_share"] == val
                    and (
                        (
                            rec["ex_date"]
                            and rec["ex_date"].year == d.year
                            and rec["ex_date"].month == d.month
                        )
                        or (
                            rec["payment_date"]
                            and rec["payment_date"].year == d.year
                            and rec["payment_date"].month == d.month
                        )
                    )
                    for rec in records.values()
                )
                if already_has:
                    continue

                # If not in Fundamentus (e.g. recent month or US stock):
                if asset_type == "fundos_imobiliarios":
                    # In Brazil, FII payment date is typically the 14th of the month
                    est_pay_date = date(
                        d.year, d.month, min(14, calendar.monthrange(d.year, d.month)[1])
                    )
                    records[(est_pay_date, round_val)] = {
                        "ticker": clean_ticker,
                        "payment_date": est_pay_date,
                        "ex_date": d,
                        "amount_per_share": val,
                        "currency": currency,
                        "dividend_type": default_div_type,
                    }
                else:
                    records[(d, round_val)] = {
                        "ticker": clean_ticker,
                        "payment_date": d,
                        "ex_date": d,
                        "amount_per_share": val,
                        "currency": currency,
                        "dividend_type": default_div_type,
                    }
    except Exception as exc:
        history_error = exc

    # Calendar upcoming in yfinance
    try:
        cal = t.calendar
        if isinstance(cal, dict):
            p_date = _to_py_date(cal.get("Dividend Date"))
            e_date = _to_py_date(cal.get("Ex-Dividend Date"))
            if p_date or e_date:
                matched = False
                for rec in list(records.values()):
                    if e_date and rec.get("ex_date") == e_date:
                        if p_date:
                            rec["payment_date"] = p_date
                        matched = True
                        break
                if not matched and (p_date or e_date):
                    val = None
                    try:
                        val = t.info.get("lastDividendValue")
                    except Exception:
                        pass
                    if not val and records:
                        val = list(records.values())[-1]["amount_per_share"]
                    if val and float(val) > 0:
                        use_p = p_date or (
                            date(e_date.year, e_date.month, 14)
                            if (e_date and asset_type == "fundos_imobiliarios")
                            else e_date
                        )
                        if use_p:
                            records[(use_p, round(float(val), 6))] = {
                                "ticker": clean_ticker,
                                "payment_date": use_p,
                                "ex_date": e_date,
                                "amount_per_share": float(val),
                                "currency": currency,
                                "dividend_type": default_div_type,
                            }
    except Exception:
        pass

    if history_error is not None and not records:
        raise AdapterNetworkError(f"Dividend history unavailable for {ticker}") from history_error
    return list(records.values())


async def sync_portfolio_dividends(
    session: AsyncSession,
    portfolio_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> DividendSyncOut:
    if user_id is not None:
        where_clause = or_(Position.user_id == user_id, Position.user_id == str(user_id))
    elif portfolio_id is not None:
        where_clause = Position.portfolio_id == portfolio_id
    else:
        where_clause = True

    positions = (
        await session.execute(
            select(Position.name, Position.asset_type)
            .distinct()
            .where(
                where_clause,
                Position.asset_type.in_(list(DIVIDEND_ASSET_TYPES)),
            )
        )
    ).all()

    ticker_map: dict[str, str] = {}
    for p in positions:
        name = p.name.strip().upper()
        if name:
            ticker_map[name] = p.asset_type

    synced = 0
    failed: list[str] = []
    total_stored = 0
    successful_tickers: list[str] = []

    async def fetch_one(
        ticker: str, asset_type: str
    ) -> tuple[str, list[dict[str, Any]], str | None]:
        try:
            async with fetch_slots:
                items = await asyncio.to_thread(_fetch_ticker_dividends_sync, ticker, asset_type)
            return ticker, items, None
        except Exception as e:
            return ticker, [], str(e)

    tickers_to_fetch = list(ticker_map.items())
    for offset in range(0, len(tickers_to_fetch), FETCH_CONCURRENCY):
        results = await asyncio.gather(
            *(fetch_one(t, at) for t, at in tickers_to_fetch[offset : offset + FETCH_CONCURRENCY])
        )

        for ticker, items, err in results:
            if err:
                failed.append(ticker)
                continue
            synced += 1
            successful_tickers.append(ticker)

            # Replace only successfully fetched histories. Failed requests retain cached data.
            await session.execute(delete(Dividend).where(Dividend.ticker == ticker))

            for offset_items in range(0, len(items), 100):
                values = []
                for item in items[offset_items : offset_items + 100]:
                    pay_d = _to_py_date(item.get("payment_date"))
                    if not pay_d:
                        continue
                    values.append(
                        dict(
                            id=uuid.uuid4(),
                            ticker=item["ticker"],
                            payment_date=pay_d,
                            ex_date=_to_py_date(item.get("ex_date")),
                            amount_per_share=item["amount_per_share"],
                            currency=item["currency"],
                            dividend_type=item["dividend_type"],
                        )
                    )
                if not values:
                    continue
                stmt = sqlite_upsert(Dividend).values(values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker", "payment_date", "amount_per_share"],
                    set_={
                        "ex_date": stmt.excluded.ex_date,
                        "currency": stmt.excluded.currency,
                        "dividend_type": stmt.excluded.dividend_type,
                    },
                )
                await session.execute(stmt)
                total_stored += len(values)

    await session.commit()
    for ticker in successful_tickers:
        _last_sync[ticker] = date.today()
        _last_sync.move_to_end(ticker)
        if len(_last_sync) > 512:
            _last_sync.popitem(last=False)
    return DividendSyncOut(
        synced_tickers=synced,
        failed_tickers=failed,
        total_dividends_stored=total_stored,
    )


async def get_portfolio_proventos(
    session: AsyncSession,
    portfolio_id: uuid.UUID,
    year: int,
    month: int,
    date_mode: str = "payment",
) -> DividendCalendarOut:
    usd_rate = await get_usd_brl_rate()
    last_day = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)

    positions = (
        (
            await session.execute(
                select(Position).where(
                    Position.portfolio_id == portfolio_id,
                    Position.asset_type.in_(DIVIDEND_ASSET_TYPES),
                )
            )
        )
        .scalars()
        .all()
    )

    pos_by_ticker: dict[str, Position] = {
        p.name.strip().upper(): p for p in positions if p.name.strip()
    }

    if not pos_by_ticker:
        return DividendCalendarOut(
            year=year,
            month=month,
            date_mode=date_mode,
            usd_rate=usd_rate,
            total_received_brl=0.0,
            total_received_net_brl=0.0,
            total_projected_brl=0.0,
            total_projected_net_brl=0.0,
            total_month_brl=0.0,
            total_month_net_brl=0.0,
            total_tax_brl=0.0,
            items=[],
        )

    tickers = list(pos_by_ticker.keys())

    # Auto-sync on view if no dividends cached or if not synced today
    latest_updates = dict(
        (
            await session.execute(
                select(Dividend.ticker, func.max(Dividend.updated_at))
                .where(Dividend.ticker.in_(tickers))
                .group_by(Dividend.ticker)
            )
        ).all()
    )

    today = date.today()
    if any(
        _last_sync.get(ticker) != today
        and (latest_updates.get(ticker) is None or latest_updates[ticker].date() < today)
        for ticker in tickers
    ):
        await sync_portfolio_dividends(session, portfolio_id)

    if date_mode == "ex":
        query = (
            select(Dividend)
            .where(
                Dividend.ticker.in_(tickers),
                Dividend.ex_date >= start_date,
                Dividend.ex_date <= end_date,
            )
            .order_by(Dividend.ex_date.asc(), Dividend.ticker.asc())
        )
    else:
        query = (
            select(Dividend)
            .where(
                Dividend.ticker.in_(tickers),
                Dividend.payment_date >= start_date,
                Dividend.payment_date <= end_date,
            )
            .order_by(Dividend.payment_date.asc(), Dividend.ticker.asc())
        )

    rows = (await session.execute(query)).scalars().all()

    today = date.today()
    items: list[DividendItemOut] = []

    for d in rows:
        p = pos_by_ticker.get(d.ticker)
        if not p:
            continue
        shares = p.amount
        rate_native = d.amount_per_share
        rate_brl = round(rate_native * usd_rate if d.currency == "USD" else rate_native, 4)
        total_native = round(shares * rate_native, 2)
        total_brl = round(shares * rate_brl, 2)

        is_jcp = _is_jcp(d.dividend_type)
        tax_rate = 0.15 if is_jcp else 0.0
        rate_net_brl = round(rate_brl * (1.0 - tax_rate), 4)
        total_net_brl = round(shares * rate_net_brl, 2)
        tax_brl = round(total_brl - total_net_brl, 2)

        is_paid = d.payment_date <= today
        status = "pago" if is_paid else "previsto"

        items.append(
            DividendItemOut(
                id=d.id,
                ticker=d.ticker,
                asset_type=p.asset_type,
                payment_date=d.payment_date,
                ex_date=d.ex_date,
                amount_shares=shares,
                rate_native=rate_native,
                currency=d.currency,
                rate_brl=rate_brl,
                rate_net_brl=rate_net_brl,
                total_native=total_native,
                total_brl=total_brl,
                total_net_brl=total_net_brl,
                tax_rate=tax_rate,
                tax_brl=tax_brl,
                is_jcp=is_jcp,
                dividend_type=d.dividend_type,
                status=status,
            )
        )

    total_received_brl = sum(i.total_brl for i in items if i.status == "pago")
    total_received_net_brl = sum(i.total_net_brl for i in items if i.status == "pago")
    total_projected_brl = sum(i.total_brl for i in items if i.status == "previsto")
    total_projected_net_brl = sum(i.total_net_brl for i in items if i.status == "previsto")
    total_month_brl = total_received_brl + total_projected_brl
    total_month_net_brl = total_received_net_brl + total_projected_net_brl
    total_tax_brl = round(total_month_brl - total_month_net_brl, 2)

    return DividendCalendarOut(
        year=year,
        month=month,
        date_mode=date_mode,
        usd_rate=usd_rate,
        total_received_brl=round(total_received_brl, 2),
        total_received_net_brl=round(total_received_net_brl, 2),
        total_projected_brl=round(total_projected_brl, 2),
        total_projected_net_brl=round(total_projected_net_brl, 2),
        total_month_brl=round(total_month_brl, 2),
        total_month_net_brl=round(total_month_net_brl, 2),
        total_tax_brl=total_tax_brl,
        items=items,
    )
