import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_async_session
from app.models.user import User
from app.models.auth_session import AuthSession
from app.schemas.user import UserCreate, UserRead, UserUpdate


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = get_settings().jwt_secret
    verification_token_secret = get_settings().jwt_secret


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    settings = get_settings()
    return JWTStrategy(secret=settings.jwt_secret, lifetime_seconds=settings.jwt_lifetime_seconds)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)


def build_auth_routers():
    return [
        (session_router, "/api/auth/jwt", ["auth"]),
        (fastapi_users.get_register_router(UserRead, UserCreate), "/api/auth", ["auth"]),
        (fastapi_users.get_users_router(UserRead, UserUpdate), "/api/users", ["users"]),
    ]


session_router = APIRouter()
_COOKIE = "diagrama_refresh"
_COOKIE_PATH = "/api/auth/jwt"


def _same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        origin and urlparse(origin).hostname != request.url.hostname
    ):
        raise HTTPException(403, "Cross-site authentication request rejected")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@session_router.post("/login")
async def persistent_login(
    request: Request,
    response: Response,
    credentials: OAuth2PasswordRequestForm = Depends(),
    manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    _same_origin(request)
    user = await manager.authenticate(credentials)
    if user is None or not user.is_active:
        raise HTTPException(400, "LOGIN_BAD_CREDENTIALS")
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(48)
    settings = get_settings()
    await session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    old_token = request.cookies.get(_COOKIE)
    if old_token:
        await session.execute(delete(AuthSession).where(AuthSession.token_hash == _hash(old_token)))
    session.add(
        AuthSession(
            token_hash=_hash(token),
            user_id=user.id,
            expires_at=now + timedelta(seconds=settings.refresh_lifetime_seconds),
        )
    )
    await session.commit()
    response.set_cookie(
        _COOKIE,
        token,
        max_age=settings.refresh_lifetime_seconds,
        httponly=True,
        secure=settings.refresh_cookie_secure or request.url.scheme == "https",
        samesite="strict",
        path=_COOKIE_PATH,
    )
    return {"access_token": await get_jwt_strategy().write_token(user), "token_type": "bearer"}


@session_router.post("/refresh")
async def refresh_login(request: Request, session: AsyncSession = Depends(get_async_session)):
    _same_origin(request)
    token = request.cookies.get(_COOKIE)
    stored = await session.get(AuthSession, _hash(token)) if token else None
    if stored is None or stored.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(
        timezone.utc
    ):
        raise HTTPException(401, "Session expired")
    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "Session inactive")
    return {"access_token": await get_jwt_strategy().write_token(user), "token_type": "bearer"}


@session_router.post("/logout", status_code=204)
async def end_login(
    request: Request, response: Response, session: AsyncSession = Depends(get_async_session)
):
    _same_origin(request)
    token = request.cookies.get(_COOKIE)
    if token:
        await session.execute(delete(AuthSession).where(AuthSession.token_hash == _hash(token)))
        await session.commit()
    response.delete_cookie(_COOKIE, path=_COOKIE_PATH)
