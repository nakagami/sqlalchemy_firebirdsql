from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import select
from sqlalchemy import String
import uuid

from sqlalchemy import Table
from sqlalchemy import column
from sqlalchemy import table
from sqlalchemy import testing
from sqlalchemy.testing import AssertsCompiledSQL
from sqlalchemy.testing import fixtures
from sqlalchemy.testing.assertions import eq_
from sqlalchemy.testing.assertions import eq_ignore_whitespace

from sqlalchemy_firebirdsql.merge import merge
from sqlalchemy_firebirdsql.syn import FBDialect_syn


class MergeCompileTest(fixtures.TestBase, AssertsCompiledSQL):
    __dialect__ = FBDialect_syn()

    def test_merge_basic(self):
        target = table("target", column("id", Integer), column("name", String))
        source = table("source", column("id", Integer), column("name", String))

        stmt = (
            merge(target)
            .using(source, target.c.id == source.c.id)
            .when_matched_then_update({target.c.name: source.c.name})
            .when_not_matched_then_insert(
                cols=[target.c.id, target.c.name],
                values=[source.c.id, source.c.name],
            )
        )
        eq_ignore_whitespace(
            str(stmt.compile(dialect=self.__dialect__)).replace("\n", " "),
            "MERGE INTO target USING source ON (target.id = source.id) "
            "WHEN MATCHED THEN UPDATE SET name = source.name "
            "WHEN NOT MATCHED THEN INSERT (id, name) VALUES (source.id, source.name)",
        )

    def test_merge_matched_only(self):
        target = table("target", column("id", Integer), column("val", Integer))
        source = table("source", column("id", Integer), column("val", Integer))

        stmt = (
            merge(target)
            .using(source, target.c.id == source.c.id)
            .when_matched_then_update({target.c.val: source.c.val})
        )
        eq_ignore_whitespace(
            str(stmt.compile(dialect=self.__dialect__)).replace("\n", " "),
            "MERGE INTO target USING source ON (target.id = source.id) "
            "WHEN MATCHED THEN UPDATE SET val = source.val",
        )

    def test_merge_not_matched_only(self):
        target = table("target", column("id", Integer), column("name", String))
        source = table("source", column("id", Integer), column("name", String))

        stmt = (
            merge(target)
            .using(source, target.c.id == source.c.id)
            .when_not_matched_then_insert(
                cols=[target.c.id, target.c.name],
                values=[source.c.id, source.c.name],
            )
        )
        eq_ignore_whitespace(
            str(stmt.compile(dialect=self.__dialect__)).replace("\n", " "),
            "MERGE INTO target USING source ON (target.id = source.id) "
            "WHEN NOT MATCHED THEN INSERT (id, name) VALUES (source.id, source.name)",
        )


class MergeBackendTest(fixtures.TestBase):
    __backend__ = True

    def test_merge_upsert(self):
        metadata = MetaData()
        suffix = uuid.uuid4().hex[:8]
        target_name = f"merge_target_{suffix}"
        source_name = f"merge_source_{suffix}"

        target = Table(
            target_name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)),
        )
        source = Table(
            source_name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)),
        )

        with testing.db.begin() as connection:
            metadata.create_all(connection)
            connection.execute(target.insert(), [{"id": 1, "name": "old_name"}])
            connection.execute(
                source.insert(),
                [
                    {"id": 1, "name": "updated_name"},
                    {"id": 2, "name": "new_name"},
                ],
            )

            stmt = (
                merge(target)
                .using(source, target.c.id == source.c.id)
                .when_matched_then_update({target.c.name: source.c.name})
                .when_not_matched_then_insert(
                    cols=[target.c.id, target.c.name],
                    values=[source.c.id, source.c.name],
                )
            )
            connection.execute(stmt)

            rows = connection.execute(
                select(target).order_by(target.c.id)
            ).fetchall()
            eq_(
                [tuple(row) for row in rows],
                [(1, "updated_name"), (2, "new_name")],
            )

        testing.db.dispose()
        with testing.db.begin() as cleanup_conn:
            for table_name in [source_name, target_name]:
                try:
                    cleanup_conn.exec_driver_sql(f"DROP TABLE {table_name}")
                except Exception:
                    pass
