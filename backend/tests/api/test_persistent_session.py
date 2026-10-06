from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.auth_session import AuthSession


async def _login(client):
    await client.post(
        "/api/auth/register", json={"email": "session@example.com", "password": "StrongPass!123"}
    )
    response = await client.post(
        "/api/auth/jwt/login",
        data={"username": "session@example.com", "password": "StrongPass!123"},
    )
    assert response.status_code == 200
    return response


async def test_persistent_session_refresh_and_logout(client):
    response = await _login(client)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    refreshed = await client.post("/api/auth/jwt/refresh")
    assert refreshed.status_code == 200
    me = await client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    )
    assert me.status_code == 200
    old_cookie = client.cookies.get("diagrama_refresh")
    assert (await client.post("/api/auth/jwt/logout")).status_code == 204
    assert (
        await client.post(
            "/api/auth/jwt/refresh", headers={"Cookie": f"diagrama_refresh={old_cookie}"}
        )
    ).status_code == 401


async def test_refresh_rejects_expired_session(client, session_maker):
    await _login(client)
    async with session_maker() as session:
        stored = (await session.execute(select(AuthSession))).scalar_one()
        stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    assert (await client.post("/api/auth/jwt/refresh")).status_code == 401


async def test_refresh_rejects_cross_site_request(client):
    await _login(client)
    assert (
        await client.post("/api/auth/jwt/refresh", headers={"Origin": "https://evil.example"})
    ).status_code == 403


async def test_expired_access_token_renews_without_password(client, monkeypatch):
    from fastapi_users.authentication import JWTStrategy
    from app.api import auth
    from app.core.config import get_settings

    secret = get_settings().jwt_secret
    with monkeypatch.context() as patch:
        patch.setattr(
            auth, "get_jwt_strategy", lambda: JWTStrategy(secret=secret, lifetime_seconds=-1)
        )
        login = await _login(client)
    old_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get("/api/users/me", headers=old_headers)).status_code == 401
    refreshed = await client.post("/api/auth/jwt/refresh")
    assert refreshed.status_code == 200
    new_headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    assert (await client.get("/api/users/me", headers=new_headers)).status_code == 200
