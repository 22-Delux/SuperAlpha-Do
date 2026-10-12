import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest

from bot.core.database import Database


class _Down:
    n = 0

    def _raise(self):
        self.n += 1
        raise asyncpg.InterfaceError("connection is closed")


class _DownExecute(_Down):
    def execute(self, query, *args):
        self._raise()


class _DownFetchrow(_Down):
    def fetchrow(self, query, *args):
        self._raise()


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_execute_retries_once_against_a_fresh_pool():
    db = Database()
    broken = _DownExecute()
    good = SimpleNamespace(execute=AsyncMock(return_value="OK"))
    db.pool = broken
    db._reconnect = AsyncMock(side_effect=lambda: setattr(db, "pool", good))

    result = _run(db.execute("SELECT 1"))

    assert result == "OK"
    assert broken.n == 1
    db._reconnect.assert_awaited_once()


def test_retry_reraises_when_pool_is_still_absent():
    db = Database()
    broken = _DownFetchrow()
    db.pool = broken
    db._reconnect = AsyncMock(side_effect=lambda: setattr(db, "pool", None))

    with pytest.raises(RuntimeError):
        _run(db.fetchrow("SELECT 1"))
    assert broken.n == 1
    db._reconnect.assert_awaited_once()


def test_retry_reraises_when_new_pool_fails_too():
    db = Database()
    broken = _DownFetchrow()
    another = _DownFetchrow()
    db.pool = broken
    db._reconnect = AsyncMock(side_effect=lambda: setattr(db, "pool", another))

    with pytest.raises(asyncpg.InterfaceError):
        _run(db.fetchrow("SELECT 1"))
    assert broken.n == 1
    assert another.n == 1
    db._reconnect.assert_awaited_once()


def test_non_connection_errors_are_not_retried(monkeypatch):
    db = Database()

    class _Bad:
        n = 0

        def fetch(self, query, *args):
            self.n += 1
            raise asyncpg.SyntaxOrAccessError("no such table: x")

    pool = _Bad()
    db.pool = pool

    with pytest.raises(asyncpg.SyntaxOrAccessError):
        _run(db.fetch("SELECT bad syntax"))
    assert pool.n == 1


def test_uninitialized_pool_raises_before_any_query():
    db = Database()

    with pytest.raises(RuntimeError):
        _run(db.execute("SELECT 1"))