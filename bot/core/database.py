import logging
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Connection-level failures (stale/closed sockets, server restarts) are worth
# retrying once against a fresh pool. Anything else (syntax/constraint errors)
# must surface normally.
_RETRYABLE = (asyncpg.PostgresConnectionError, asyncpg.InterfaceError)


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

        self.DB_URL = os.getenv("DB_URL")

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            dsn=self.DB_URL,
            min_size=1,
            max_size=10,
            # Reap idle connections before the server / proxy drops them,
            # so a pooled connection is unlikely to be dead when handed out.
            max_inactive_connection_lifetime=60,
        )

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def _reconnect(self):
        logger.warning("Database connection lost — rebuilding pool and retrying.")
        await self.close()
        await self.connect()

    async def _call(self, method: str, query: str, args: tuple):
        if not self.pool:
            raise RuntimeError("Database pool is not initialized. Call connect() first.")
        try:
            result = await getattr(self.pool, method)(query, *args)
        except _RETRYABLE as exc:
            logger.warning("Database connection failed: %s", exc)
            await self._reconnect()
            if not self.pool:
                raise RuntimeError("Database pool is not initialized.")
            result = await getattr(self.pool, method)(query, *args)
        return result

    def acquire(self):
        if not self.pool:
            raise RuntimeError("Database pool is not initialized. Call connect() first.")
        return self.pool.acquire()

    async def execute(self, query: str, *args):
        return await self._call("execute", query, args)

    async def fetch(self, query: str, *args):
        return await self._call("fetch", query, args)

    async def fetchrow(self, query: str, *args):
        return await self._call("fetchrow", query, args)

    async def fetchval(self, query: str, *args):
        return await self._call("fetchval", query, args)