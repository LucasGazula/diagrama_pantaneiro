from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone
from pathlib import Path

import pytest
import respx
from httpx import Response

from app.market_data import tesouro
from app.market_data.base import AdapterNetworkError, AdapterNotFoundError
from app.market_data.tesouro import TesouroAdapter, _CSV_URL


@pytest.fixture(autouse=True)
def clear_cache():
    tesouro._reset_cache_for_tests()


def _fixture_csv_text() -> str:
    return (Path(__file__).parent / "fixtures" / "tesouro_sample.csv").read_text()


@respx.mock
async def test_matches_renda_plus_2065() -> None:
    respx.get(_CSV_URL).mock(return_value=Response(200, text=_fixture_csv_text()))
    quote = await TesouroAdapter().fetch_price("TESOURO RENDA + 2065")
    assert quote.price_brl == pytest.approx(2136.00)


@respx.mock
async def test_picks_most_recent_row_for_same_title() -> None:
    """Fixture has two rows for the 2065 title: 16/04 and 15/04. We should
    pick the newest (16/04 = R$2136, not 15/04 = R$2134)."""
    respx.get(_CSV_URL).mock(return_value=Response(200, text=_fixture_csv_text()))
    quote = await TesouroAdapter().fetch_price("TESOURO RENDA + 2065")
    assert quote.price_brl == pytest.approx(2136.00)


@respx.mock
async def test_matches_ipca_2035() -> None:
    respx.get(_CSV_URL).mock(return_value=Response(200, text=_fixture_csv_text()))
    quote = await TesouroAdapter().fetch_price("TESOURO IPCA+ 2035")
    assert quote.price_brl == pytest.approx(3200.00)


@respx.mock
async def test_no_match_for_private_rf() -> None:
    """Private RF (LCI, CDB, etc.) should never match against Tesouro CSV."""
    respx.get(_CSV_URL).mock(return_value=Response(200, text=_fixture_csv_text()))
    with pytest.raises(AdapterNotFoundError):
        await TesouroAdapter().fetch_price("LCI INTER 90,00")


@respx.mock
async def test_search_private_rf_returns_empty() -> None:
    respx.get(_CSV_URL).mock(return_value=Response(200, text=_fixture_csv_text()))
    adapter = TesouroAdapter()
    assert await adapter.search("lci") == []
    assert await adapter.search("lci inter") == []
    assert await adapter.search("cdb voiter") == []
    assert await adapter.search("CDB IPCA 2035") == []
    assert await adapter.search("LCI Selic 2035") == []
    assert await adapter.search("cra") == []


@respx.mock
async def test_no_match_when_year_missing_from_position_name() -> None:
    """We require a maturity year in the position name to disambiguate."""
    respx.get(_CSV_URL).mock(return_value=Response(200, text=_fixture_csv_text()))
    with pytest.raises(AdapterNotFoundError):
        await TesouroAdapter().fetch_price("TESOURO PREFIXADO SEM ANO")


@respx.mock
async def test_concurrent_quotes_share_one_download() -> None:
    route = respx.get(_CSV_URL).respond(200, text=_fixture_csv_text())
    quotes = await asyncio.gather(
        *(TesouroAdapter().fetch_price("TESOURO IPCA+ 2035") for _ in range(12))
    )
    assert route.call_count == 1
    assert all(q.price_brl == 3200.0 for q in quotes)
    assert len(tesouro._cache["csv"][0]) == 3


@respx.mock
async def test_ipca_with_and_without_semiannual_coupons_identity() -> None:
    csv_text = (
        "Tipo Titulo;Data Vencimento;Data Base;PU Compra Manha\n"
        "Tesouro IPCA+;15/05/2035;16/04/2026;3200,00\n"
        "Tesouro IPCA+ com Juros Semestrais;15/05/2035;16/04/2026;3450,00\n"
    )
    respx.get(_CSV_URL).respond(200, text=csv_text)
    adapter = TesouroAdapter()

    candidates = await adapter.search("ipca 2035")
    assert len(candidates) == 2

    c_standard = next(c for c in candidates if "JUROS SEMESTRAIS" not in c.name)
    c_semestrais = next(c for c in candidates if "JUROS SEMESTRAIS" in c.name)

    assert c_standard.name == "TESOURO IPCA+ 2035"
    assert c_standard.external_id == "Tesouro IPCA+|2035-05-15"
    assert c_standard.current_price_brl == 3200.00

    assert c_semestrais.name == "TESOURO IPCA+ COM JUROS SEMESTRAIS 2035"
    assert c_semestrais.external_id == "Tesouro IPCA+ com Juros Semestrais|2035-05-15"
    assert c_semestrais.current_price_brl == 3450.00

    # Fetch by candidate external_ids
    q_std = await adapter.fetch_price(c_standard.external_id)
    assert q_std.price_brl == 3200.00

    q_sem = await adapter.fetch_price(c_semestrais.external_id)
    assert q_sem.price_brl == 3450.00

    # Search with "semestrais" keyword only returns coupon bond
    candidates_sem = await adapter.search("ipca semestrais 2035")
    assert len(candidates_sem) == 1
    assert candidates_sem[0].external_id == "Tesouro IPCA+ com Juros Semestrais|2035-05-15"


@respx.mock
async def test_renda_and_educa_display_year_and_maturity_roundtrip() -> None:
    csv_text = (
        "Tipo Titulo;Data Vencimento;Data Base;PU Compra Manha\n"
        "Tesouro Renda+ Aposentadoria Extra;15/12/2084;16/04/2026;2136,00\n"
        "Tesouro Educa+;15/12/2034;16/04/2026;1500,00\n"
    )
    respx.get(_CSV_URL).respond(200, text=csv_text)
    adapter = TesouroAdapter()

    # Renda+ 2065 (maturity 2084 - 19 = 2065)
    candidates_renda = await adapter.search("renda 2065")
    assert len(candidates_renda) == 1
    renda_c = candidates_renda[0]
    assert "2065" in renda_c.name
    assert renda_c.external_id == "Tesouro Renda+ Aposentadoria Extra|2084-12-15"
    assert renda_c.current_price_brl == 2136.00

    quote_renda = await adapter.fetch_price(renda_c.external_id)
    assert quote_renda.price_brl == 2136.00

    quote_renda_legacy = await adapter.fetch_price("TESOURO RENDA + 2065")
    assert quote_renda_legacy.price_brl == 2136.00

    # Educa+ 2030 (maturity 2034 - 4 = 2030)
    candidates_educa = await adapter.search("educa 2030")
    assert len(candidates_educa) == 1
    educa_c = candidates_educa[0]
    assert "2030" in educa_c.name
    assert educa_c.external_id == "Tesouro Educa+|2034-12-15"
    assert educa_c.current_price_brl == 1500.00

    quote_educa = await adapter.fetch_price(educa_c.external_id)
    assert quote_educa.price_brl == 1500.00

    quote_educa_legacy = await adapter.fetch_price("TESOURO EDUCA+ 2030")
    assert quote_educa_legacy.price_brl == 1500.00


@respx.mock
async def test_search_by_family_and_year_does_not_return_all_years() -> None:
    csv_text = (
        "Tipo Titulo;Data Vencimento;Data Base;PU Compra Manha\n"
        "Tesouro IPCA+;15/05/2035;16/04/2026;3200,00\n"
        "Tesouro IPCA+;15/05/2045;16/04/2026;3800,00\n"
    )
    respx.get(_CSV_URL).respond(200, text=csv_text)
    adapter = TesouroAdapter()

    res_2035 = await adapter.search("ipca 2035")
    assert len(res_2035) == 1
    assert "2035" in res_2035[0].name
    assert res_2035[0].external_id == "Tesouro IPCA+|2035-05-15"

    res_2045 = await adapter.search("ipca 2045")
    assert len(res_2045) == 1
    assert "2045" in res_2045[0].name
    assert res_2045[0].external_id == "Tesouro IPCA+|2045-05-15"


@respx.mock
async def test_zero_and_negative_pu_rejected() -> None:
    csv_text = (
        "Tipo Titulo;Data Vencimento;Data Base;PU Compra Manha\n"
        "Tesouro IPCA+;15/05/2035;16/04/2026;0,00\n"
        "Tesouro Prefixado;01/01/2031;16/04/2026;-100,00\n"
    )
    respx.get(_CSV_URL).respond(200, text=csv_text)
    adapter = TesouroAdapter()

    assert await adapter.search("ipca") == []
    assert await adapter.search("prefixado") == []

    with pytest.raises(AdapterNotFoundError):
        await adapter.fetch_price("Tesouro IPCA+|2035-05-15")

    with pytest.raises(AdapterNotFoundError):
        await adapter.fetch_price("Tesouro Prefixado|2031-01-01")


@respx.mock
async def test_chronological_dates_and_missing_latest_price() -> None:
    csv_text = (
        "Tipo Titulo;Data Vencimento;Data Base;PU Compra Manha\n"
        "Tesouro IPCA+;15/05/2035;31/12/2025;3000,00\n"
        "Tesouro IPCA+;15/05/2035;01/01/2026;3200,00\n"
        "Tesouro IPCA+;15/05/2035;02/01/2026;\n"
    )
    respx.get(_CSV_URL).respond(200, text=csv_text)
    quote = await TesouroAdapter().fetch_price("TESOURO IPCA+ 2035")
    assert quote.price_brl == 3200
    assert quote.as_of == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert quote.stale is True

    candidates = await TesouroAdapter().search("ipca")
    assert len(candidates) == 0


def test_history_is_reduced_and_expired_titles_removed() -> None:
    csv_text = (
        "Tipo Titulo;Data Vencimento;Data Base;PU Compra Manha\n"
        "Tesouro Prefixado;01/01/2026;01/01/2025;100,00\n"
        "Tesouro IPCA+;15/05/2035;01/06/2026;3200,00\n"
        "Tesouro IPCA+;15/05/2035;01/05/2026;3000,00\n"
    )
    titles = tesouro._read_titles(io.BytesIO(csv_text.encode()))
    assert len(titles) == 1
    assert titles[0].quote_price == 3200


@respx.mock
async def test_stale_quotes_survive_download_failure() -> None:
    route = respx.get(_CSV_URL).respond(200, text=_fixture_csv_text())
    await TesouroAdapter().fetch_price("TESOURO IPCA+ 2035")
    tesouro._cache["csv"] = (tesouro._cache["csv"][0], 0)
    route.respond(503)
    assert (await TesouroAdapter().fetch_price("TESOURO IPCA+ 2035")).price_brl == 3200
    assert (await TesouroAdapter().fetch_price("TESOURO IPCA+ 2035")).price_brl == 3200
    assert route.call_count == 2


@respx.mock
async def test_malformed_csv_does_not_replace_cache() -> None:
    respx.get(_CSV_URL).respond(200, text="maintenance page")
    with pytest.raises(AdapterNetworkError):
        await TesouroAdapter().fetch_price("TESOURO IPCA+ 2035")
    assert not tesouro._cache
