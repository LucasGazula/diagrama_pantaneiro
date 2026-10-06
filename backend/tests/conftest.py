import asyncio
import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db import Base
# Import models so their tables are registered on Base.metadata before create_all.
from app.models import user as _user  # noqa: F401
from app.models import auth_session as _auth_session  # noqa: F401
from app.models import aporte_allocation as _aporte_allocation  # noqa: F401
from app.models import aporte_event as _aporte_event  # noqa: F401
from app.models import diagram_question as _diagram_question  # noqa: F401
from app.models import investment_target as _investment_target  # noqa: F401
from app.models import portfolio as _portfolio  # noqa: F401
from app.models import position as _position  # noqa: F401
from app.models import target_preset as _target_preset  # noqa: F401


@pytest_asyncio.fixture
async def engine():
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(session_maker):
    from app.core import db as db_module
    from app.main import app

    # Override the DB session dependency to use the test engine
    async def _get_test_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[db_module.get_async_session] = _get_test_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
