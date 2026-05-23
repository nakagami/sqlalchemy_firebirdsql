# Copyright (C) 2005-2025 the SQLAlchemy authors and contributors <see AUTHORS
# file>
#
# This module is part of SQLAlchemy and is released under
# the MIT License: https://www.opensource.org/licenses/mit-license.php
# mypy: ignore-errors

r"""
.. dialect:: firebirdsql+asyn
    :name: firebirdsql
    :dbapi: firebirdsql
    :connectstring: firebirdsql+asyn://user:password@host:port/path/to/db[?key=value&key=value...]

This dialect should normally be used only with the
:func:`_asyncio.create_async_engine` engine creation function::

    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        "firebirdsql+asyn://user:password@host:port/path/to/db[?key=value&key=value...]
    )

"""  # noqa
from collections import deque

from .base import FBDialect
from sqlalchemy import pool
from sqlalchemy import util
from sqlalchemy.engine import AdaptedConnection
from sqlalchemy.util.concurrency import asyncio
from sqlalchemy.util.concurrency import await_fallback
from sqlalchemy.util.concurrency import await_only

import firebirdsql


class AsyncAdapt_firebirdsql_cursor:
    # TODO: base on connectors/asyncio.py
    # see #10415
    server_side = False
    __slots__ = (
        "_adapt_connection",
        "_connection",
        "await_",
        "_cursor",
        "_rows",
    )

    def __init__(self, adapt_connection):
        self._adapt_connection = adapt_connection
        self._connection = adapt_connection._connection
        self.await_ = adapt_connection.await_

        cursor = self._connection.cursor(adapt_connection.dbapi.Cursor)

        self._cursor = self.await_(cursor.__aenter__())
        self._rows = deque()

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def arraysize(self):
        return self._cursor.arraysize

    @arraysize.setter
    def arraysize(self, value):
        self._cursor.arraysize = value

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def close(self):
        # note we aren't actually closing the cursor here,
        # we are just letting GC do it.   to allow this to be async
        # we would need the Result to change how it does "Safe close cursor".
        # Firebird "cursors" don't actually have state to be "closed" besides
        # exhausting rows, which we already have done for sync cursor.
        self._rows.clear()

    def execute(self, operation, parameters=None):
        return self.await_(self._execute_async(operation, parameters))

    def executemany(self, operation, seq_of_parameters):
        return self.await_(
            self._executemany_async(operation, seq_of_parameters)
        )

    async def _execute_async(self, operation, parameters):
        async with self._adapt_connection._execute_mutex:
            result = await self._cursor.execute(operation, parameters)

            if not self.server_side:
                # firebirdsql.aio has a "fake" async result, so we have to pull it out
                # of that here since our default result is not async.
                # we could just as easily grab "_rows" here and be done with it
                # but this is safer.
                self._rows = deque(await self._cursor.fetchall())
            return result

    async def _executemany_async(self, operation, seq_of_parameters):
        async with self._adapt_connection._execute_mutex:
            return await self._cursor.executemany(operation, seq_of_parameters)

    def setinputsizes(self, *inputsizes):
        pass

    def __iter__(self):
        while self._rows:
            yield self._rows.popleft()

    def fetchone(self):
        if self._rows:
            return self._rows.popleft()
        else:
            return None

    def fetchmany(self, size=None):
        if size is None:
            size = self.arraysize

        rr = self._rows
        return [rr.popleft() for _ in range(min(size, len(rr)))]

    def fetchall(self):
        retval = list(self._rows)
        self._rows.clear()
        return retval


class AsyncAdapt_firebirdsql_connection(AdaptedConnection):
    # TODO: base on connectors/asyncio.py
    # see #10415
    await_ = staticmethod(await_only)
    __slots__ = ("dbapi", "_execute_mutex")

    def __init__(self, dbapi, connection):
        self.dbapi = dbapi
        self._connection = connection
        self._execute_mutex = asyncio.Lock()

    def ping(self, reconnect):
        return self.await_(self._connection.ping(reconnect))

    def character_set_name(self):
        return self._connection.character_set_name()

    def autocommit(self, value):
        self.await_(self._connection.autocommit(value))

    def cursor(self):
        return AsyncAdapt_firebirdsql_cursor(self)

    def rollback(self):
        self.await_(self._connection.rollback())

    def commit(self):
        self.await_(self._connection.commit())

    def terminate(self):
        # it's not awaitable.
        self._connection.close()

    def close(self) -> None:
        self.await_(self._connection.ensure_closed())


class AsyncAdaptFallback_firebirdsql_connection(AsyncAdapt_firebirdsql_connection):
    # TODO: base on connectors/asyncio.py
    # see #10415
    __slots__ = ()

    await_ = staticmethod(await_fallback)


class AsyncAdapt_firebirdsql_dbapi:
    def __init__(self, asyn, syn):
        self.asyn = asyn
        self.syn = syn
        self.paramstyle = "qmark"
        self._init_dbapi_attributes()
        self.Cursor = self.asyn.AsyncCursor

    def _init_dbapi_attributes(self):
        for name in (
            "Warning",
            "Error",
            "InterfaceError",
            "DataError",
            "DatabaseError",
            "OperationalError",
            "InterfaceError",
            "IntegrityError",
            "ProgrammingError",
            "InternalError",
            "NotSupportedError",
        ):
            setattr(self, name, getattr(firebirdsql, name))

        for name in (
            "NUMBER",
            "STRING",
            "DATETIME",
            "BINARY",
            "TIMESTAMP",
            "Binary",
        ):
            setattr(self, name, getattr(firebirdsql, name))

    def connect(self, *arg, **kw):
        async_fallback = kw.pop("async_fallback", False)
        creator_fn = kw.pop("async_creator_fn", self.asyn.connect)

        if util.asbool(async_fallback):
            return AsyncAdaptFallback_firebirdsql_connection(
                self,
                await_fallback(creator_fn(*arg, **kw)),
            )
        else:
            return AsyncAdapt_firebirdsql_connection(
                self,
                await_only(creator_fn(*arg, **kw)),
            )


class FBDialect_asyn(FBDialect):
    driver = "async"
    supports_statement_cache = True

    is_async = True
    has_terminate = True

    @classmethod
    def import_dbapi(cls):
        return AsyncAdapt_firebirdsql_dbapi(
            firebirdsql.aio, firebirdsql
        )

    @classmethod
    def get_pool_class(cls, url):
        async_fallback = url.query.get("async_fallback", False)

        if util.asbool(async_fallback):
            return pool.FallbackAsyncAdaptedQueuePool
        else:
            return pool.AsyncAdaptedQueuePool

    def do_terminate(self, dbapi_connection) -> None:
        dbapi_connection.terminate()

    def create_connect_args(self, url):
        opts = url.translate_connect_args(username="user")
        qry = url.query

        opts.update(qry)
        return ([], opts)

    def is_disconnect(self, e, connection, cursor):
        if super().is_disconnect(e, connection, cursor):
            return True
        else:
            str_e = str(e).lower()
            return "not connected" in str_e

    def get_driver_connection(self, connection):
        return connection._connection


dialect = FBDialect_asyn
