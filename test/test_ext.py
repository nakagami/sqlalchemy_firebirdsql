from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import select
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy.testing import fixtures
from sqlalchemy.testing.assertions import eq_

from sqlalchemy_firebirdsql.ext import not_similar_to
from sqlalchemy_firebirdsql.ext import similar_to


class SimilarToTest(fixtures.TablesTest):
    __backend__ = True

    @classmethod
    def define_tables(cls, metadata):
        Table(
            "similar_test",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("code", String(10)),
        )

    @classmethod
    def insert_data(cls, connection):
        connection.execute(
            cls.tables.similar_test.insert(),
            [
                {"id": 1, "code": "ABC123"},
                {"id": 2, "code": "abc123"},
                {"id": 3, "code": "12345"},
            ],
        )

    def test_similar_to(self, connection):
        t = self.tables.similar_test
        rows = connection.execute(
            select(t.c.id).where(similar_to(t.c.code, "[A-Z]+[0-9]+"))
        ).fetchall()
        eq_([tuple(row) for row in rows], [(1,)])

    def test_not_similar_to(self, connection):
        t = self.tables.similar_test
        rows = connection.execute(
            select(t.c.id)
            .where(not_similar_to(t.c.code, "[0-9]+"))
            .order_by(t.c.id)
        ).fetchall()
        eq_([tuple(row) for row in rows], [(1,), (2,)])
