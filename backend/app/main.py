from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    aportes,
    catalog,
    diagram_questions,
    health,
    portfolios,
    positions,
    prices,
    proventos,
    target_presets,
    targets,
)
from app.api.auth import build_auth_routers
from app.market_data.http_client import start_http_client, stop_http_client
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_http_client()
    start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()
        await stop_http_client()


app = FastAPI(title="Diagrama do Cerrado API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",  # nginx prod build
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(portfolios.router)
app.include_router(positions.router)
app.include_router(targets.router)
app.include_router(target_presets.router)
app.include_router(aportes.router)
app.include_router(diagram_questions.router)
app.include_router(prices.router)
app.include_router(catalog.router)
app.include_router(proventos.router)

for router, prefix, tags in build_auth_routers():
    app.include_router(router, prefix=prefix, tags=tags)
