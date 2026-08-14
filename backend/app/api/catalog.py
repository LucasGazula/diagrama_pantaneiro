"""Catalog search endpoint — autocomplete for the add-position form."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.auth import current_active_user
from app.market_data.brapi import BrapiAdapter
from app.market_data.coingecko import CoinGeckoAdapter
from app.market_data.tesouro import TesouroAdapter
from app.market_data.yfinance_adapter import YFinanceAdapter
from app.models.user import User
from app.schemas.catalog import CandidateOut

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

_brapi = BrapiAdapter()
_coingecko = CoinGeckoAdapter()
_tesouro = TesouroAdapter()
_yfinance = YFinanceAdapter()


@router.get("/search", response_model=list[CandidateOut])
async def search(
    type: str = Query(..., description="asset_type to search within"),
    q: str = Query(default="", max_length=64),
    user: User = Depends(current_active_user),
) -> list[CandidateOut]:
    """Return up-to-20 Candidate rows matching `q` for the given asset_type.

    - acoes_nacionais, fundos_imobiliarios -> Brapi /api/available
    - acoes_internacionais, reits -> Yahoo Finance /v1/finance/search
    - criptomoedas -> CoinGecko /search
    - rendafixa -> Tesouro CSV (Tesouro titles only; private RF stays manual)
    - anything else -> empty list (no adapter search support)
    """
    q = q.strip()
    if not q:
        return []

    if type in ("acoes_nacionais", "fundos_imobiliarios"):
        candidates = await _brapi.search(q)
    elif type in ("acoes_internacionais", "reits"):
        candidates = await _yfinance.search(q)
    elif type == "criptomoedas":
        candidates = await _coingecko.search(q)
    elif type == "rendafixa":
        candidates = await _tesouro.search(q)
    else:
        candidates = []

    return [
        CandidateOut(
            name=c.name, label=c.label, current_price_brl=c.current_price_brl
        )
        for c in candidates
    ]
