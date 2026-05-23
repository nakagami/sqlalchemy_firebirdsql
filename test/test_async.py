"""Tests for the Firebird async dialect (firebirdsql+asyn)."""

import asyncio

import pytest
from sqlalchemy import testing
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.testing import fixtures


def get_async_url(sync_url):
    url_str = str(sync_url)
    if "+syn" in url_str:
        return url_str.replace("+syn", "+asyn")
    if "firebirdsql://" in url_str:
        return url_str.replace("firebirdsql://", "firebirdsql+asyn://")
    return url_str


class AsyncDialectTest(fixtures.TestBase):
    __backend__ = True

    def test_async_dialect_importable(self):
        from sqlalchemy_firebirdsql.asyn import FBDialect_asyn

        assert FBDialect_asyn is not None
        assert FBDialect_asyn.driver == "async"
        assert FBDialect_asyn.is_async is True

    def test_create_async_engine_url(self):
        async_url = get_async_url(testing.db.url)
        assert "+asyn" in async_url

    def test_async_connection(self):
        async_url = get_async_url(testing.db.url)
        engine = create_async_engine(async_url, echo=False)

        async def run_query():
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1 FROM rdb$database"))
                return result.fetchone()

        try:
            row = asyncio.run(run_query())
            assert row[0] == 1
        except Exception as err:
            if "Unauthorized" in str(err) or "not defined" in str(err):
                pytest.skip(
                    "firebirdsql async driver cannot authenticate in test environment"
                )
            raise
        finally:
            asyncio.run(engine.dispose())

    def test_async_execute_select(self):
        async_url = get_async_url(testing.db.url)
        engine = create_async_engine(async_url, echo=False)

        async def run_query():
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT rdb$relation_name FROM rdb$relations "
                        "WHERE COALESCE(rdb$system_flag, 0) = 0 ROWS 1 TO 1"
                    )
                )
                return result.fetchone()

        try:
            row = asyncio.run(run_query())
            assert row is not None
        except Exception as err:
            if "Unauthorized" in str(err) or "not defined" in str(err):
                pytest.skip(
                    "firebirdsql async driver cannot authenticate in test environment"
                )
            raise
        finally:
            asyncio.run(engine.dispose())
