"""
.. dialect:: firebirdsql+syn
    :name: firebirdsql
    :dbapi: firebirdsql
    :connectstring: firebirdsql+syn://user:password@host:port/path/to/db[?key=value&key=value...]
"""  # noqa

from sqlalchemy import util
from .base import FBDialect

import firebirdsql


class FBDialect_syn(FBDialect):
    driver = "syn"
    supports_statement_cache = True

    @classmethod
    def import_dbapi(cls):
        return firebirdsql

    @util.memoized_property
    def _isolation_lookup(self):
        return {
            "AUTOCOMMIT": "autocommit",
            "READ COMMITTED": "read_committed",
            "REPEATABLE READ": "repeatable_read",
            "SERIALIZABLE": "serializable",
        }

    def get_isolation_level_values(self, dbapi_connection):
        return list(self._isolation_lookup)

    def set_isolation_level(self, dbapi_connection, level):
        dbapi_connection.set_isolation_level(self._isolation_lookup[level])

    def set_readonly(self, connection, value):
        connection.readonly = value

    def get_readonly(self, connection):
        return connection.readonly

    def set_deferrable(self, connection, value):
        connection.deferrable = value

    def get_deferrable(self, connection):
        return connection.deferrable

    def create_connect_args(self, url):
        opts = url.translate_connect_args(username="user")
        qry = url.query

        opts.update(qry)
        return ([], opts)

    def do_rollback(self, dbapi_connection):
        dbapi_connection.rollback()

    def do_commit(self, dbapi_connection):
        dbapi_connection.commit()


dialect = FBDialect_syn
