"""Reuse TLS and a small connection pool during the application lifespan."""

from contextlib import asynccontextmanager

import httpx

_client: httpx.AsyncClient | None = None


def start_http_client() -> None:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=8.0, limits=httpx.Limits(max_connections=4, max_keepalive_connections=2)
        )


async def stop_http_client() -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        await client.aclose()


@asynccontextmanager
async def market_client():
    if _client is not None:
        yield _client
    else:
        # Standalone adapters/tests work without starting the application.
        async with httpx.AsyncClient(timeout=8.0) as client:
            yield client
