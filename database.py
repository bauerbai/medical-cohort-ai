from typing import Optional

import asyncpg

from config import settings


_pool: Optional[asyncpg.Pool] = None


async def init_db_pool() -> None:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=1,
            max_size=10,
            server_settings={"search_path": "ukb_semantic"},
        )


async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_db_connection() -> asyncpg.Connection:
    if _pool is None:
        await init_db_pool()

    if _pool is None:
        raise RuntimeError("Database connection pool is not initialized")

    return await _pool.acquire()


async def release_db_connection(connection: asyncpg.Connection) -> None:
    if _pool is not None:
        await _pool.release(connection)
