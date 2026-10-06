import respx

from app.market_data.http_client import market_client, start_http_client, stop_http_client


@respx.mock
async def test_lifespan_reuses_client_and_closes_connections():
    route = respx.get("https://example.test/quote").respond(200, json={"price": 1})
    start_http_client()
    try:
        async with market_client() as first:
            await first.get("https://example.test/quote")
        async with market_client() as second:
            await second.get("https://example.test/quote")
        assert first is second
        assert not first.is_closed
        assert route.call_count == 2
    finally:
        await stop_http_client()
    assert first.is_closed
    async with market_client() as standalone:
        assert standalone is not first
    assert standalone.is_closed
