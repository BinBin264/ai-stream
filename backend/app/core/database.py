from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.core.config import settings


def asyncpg_dsn() -> str:
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def db_connection() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(asyncpg_dsn())
    try:
        yield conn
    finally:
        await conn.close()
