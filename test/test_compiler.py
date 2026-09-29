from sqlalchemy import Boolean, Date, DateTime, Identity, Time, and_
from sqlalchemy import cast
from sqlalchemy import column
from sqlalchemy import Column
from sqlalchemy import Computed
from sqlalchemy import delete
from sqlalchemy import exc
from sqlalchemy import func
from sqlalchemy import insert
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import schema
from sqlalchemy import select
from sqlalchemy import String
from sqlalchemy import table
from sqlalchemy import Table
from sqlalchemy import testing
from sqlalchemy import text
from sqlalchemy import update
from sqlalchemy.sql import sqltypes
from sqlalchemy.testing import assert_raises_message
from sqlalchemy.testing import AssertsCompiledSQL
from sqlalchemy.testing import fixtures
from sqlalchemy.testing.assertions import eq_ignore_whitespace
from sqlalchemy.types import TypeEngine

import sqlalchemy_firebirdsql.types as FbTypes

from sqlalchemy_firebirdsql.syn import FBDialect_syn


class CompileTest(fixtures.TablesTest, AssertsCompiledSQL):
    __dialect__ = FBDialect_syn()

    def test_alias(self):
        t = table("sometable", column("col1"), column("col2"))
        s = select(t.alias())
        self.assert_compile(
            s,
            "SELECT sometable_1.col1, sometable_1.col2 "
            "FROM sometable AS sometable_1",
        )

    @testing.provide_metadata
    def test_function(self):
        self.assert_compile(
            func.foo(1, 2),
            "foo(CAST(:foo_1 AS INTEGER), CAST(:foo_2 AS INTEGER))",
        )
        self.assert_compile(func.current_time(), "CURRENT_TIME")
        self.assert_compile(func.foo(), "foo")
        t = Table(
            "sometable",
            self.metadata,
            Column("col1", Integer),
            Column("col2", Integer),
        )
        self.assert_compile(
            select(func.max(t.c.col1)),
            "SELECT max(sometable.col1) AS max_1 FROM sometable",
        )

    def test_limit_only(self):
        t = table("sometable", column("col1"), column("col2"))
        self.assert_compile(
            select(t).limit(5),
            "SELECT sometable.col1, sometable.col2 FROM sometable  ROWS 1 TO 5",
            literal_binds=True,
        )

    def test_offset_only(self):
        t = table("sometable", column("col1"), column("col2"))
        self.assert_compile(
            select(t).offset(10),
            "SELECT sometable.col1, sometable.col2 FROM sometable"
            "  ROWS 10 + 1 TO 9223372036854775807",
            literal_binds=True,
        )

    def test_limit_and_offset(self):
        t = table("sometable", column("col1"), column("col2"))
        self.assert_compile(
            select(t).limit(5).offset(10),
            "SELECT sometable.col1, sometable.col2 FROM sometable"
            "  ROWS 10 + 1 TO 10 + 5",
            literal_binds=True,
        )

    def test_fetch_only(self):
        t = table("sometable", column("col1"), column("col2"))
        self.assert_compile(
            select(t).fetch(5),
            "SELECT sometable.col1, sometable.col2 FROM sometable  ROWS 1 TO 5",
            literal_binds=True,
        )

    def test_fetch_with_offset(self):
        t = table("sometable", column("col1"), column("col2"))
        self.assert_compile(
            select(t).fetch(5).offset(10),
            "SELECT sometable.col1, sometable.col2 FROM sometable"
            "  ROWS 10 + 1 TO 10 + 5",
            literal_binds=True,
        )

    def test_delete_returning(self):
        table1 = table(
            "mytable",
            column("myid", Integer),
            column("name", String(128)),
            column("description", String(128)),
        )
        d = (
            delete(table1)
            .where(table1.c.myid == 7)
            .returning(table1.c.myid, table1.c.name)
        )
        self.assert_compile(
            d,
            "DELETE FROM mytable WHERE mytable.myid = CAST(:myid_1 AS INTEGER) "
            "RETURNING mytable.myid, mytable.name",
        )
        d = delete(table1).returning(table1)
        self.assert_compile(
            d,
            "DELETE FROM mytable RETURNING mytable.myid, mytable.name, "
            "mytable.description",
        )

    def test_true_division(self):
        c1 = column("c1", Integer)
        c2 = column("c2", Integer)
        self.assert_compile(
            select(c1 / c2),
            "SELECT c1 / (c2 + 0.0) AS anon_1 FROM rdb$database",
        )

    def test_mod(self):
        c1 = column("c1", Integer)
        c2 = column("c2", Integer)
        self.assert_compile(
            select(c1 % c2),
            "SELECT MOD(c1, c2) AS anon_1 FROM rdb$database",
        )

    def test_now_func(self):
        self.assert_compile(func.now(), "CURRENT_TIMESTAMP")

    def test_boolean_ddl(self):
        m = MetaData()
        tbl = Table("testtbl", m, Column("flag", Boolean))
        self.assert_compile(
            schema.CreateTable(tbl),
            "CREATE TABLE testtbl (flag BOOLEAN)",
        )

    def test_timestamp_timezone_ddl(self):
        m = MetaData()
        tbl = Table(
            "testtbl",
            m,
            Column("ts_with", DateTime(timezone=True)),
            Column("ts_without", DateTime(timezone=False)),
        )
        self.assert_compile(
            schema.CreateTable(tbl),
            "CREATE TABLE testtbl (ts_with TIMESTAMP WITH TIME ZONE, "
            "ts_without TIMESTAMP WITHOUT TIME ZONE)",
        )

    def test_time_timezone_ddl(self):
        m = MetaData()
        tbl = Table(
            "testtbl",
            m,
            Column("t_with", Time(timezone=True)),
            Column("t_without", Time(timezone=False)),
        )
        self.assert_compile(
            schema.CreateTable(tbl),
            "CREATE TABLE testtbl (t_with TIME WITH TIME ZONE, "
            "t_without TIME WITHOUT TIME ZONE)",
        )

    def test_nulls_ordering(self):
        t = table("sometable", column("col1"), column("col2"))
        self.assert_compile(
            select(t).order_by(t.c.col1.nulls_first()),
            "SELECT sometable.col1, sometable.col2 FROM sometable "
            "ORDER BY sometable.col1 NULLS FIRST",
        )
        self.assert_compile(
            select(t).order_by(t.c.col1.nulls_last()),
            "SELECT sometable.col1, sometable.col2 FROM sometable "
            "ORDER BY sometable.col1 NULLS LAST",
        )

    def test_window_function(self):
        t = table("sometable", column("col1", Integer), column("col2"))
        self.assert_compile(
            select(func.row_number().over(order_by=t.c.col1)).select_from(t),
            "SELECT row_number OVER (ORDER BY sometable.col1) AS anon_1 "
            "FROM sometable",
        )

    def test_create_table_on_commit_delete(self):
        m = MetaData()
        tbl = Table(
            "atable",
            m,
            Column("id", Integer),
            prefixes=["GLOBAL TEMPORARY"],
            firebirdsql_on_commit="DELETE ROWS",
        )
        self.assert_compile(
            schema.CreateTable(tbl),
            "CREATE GLOBAL TEMPORARY TABLE atable (id INTEGER) "
            "ON COMMIT DELETE ROWS",
        )

    def test_charset(self):
        """Exercise CHARACTER SET options on string types."""
        columns = [
            (FbTypes.FBCHAR, [1], {}, "CHAR(1)"),
            (
                FbTypes.FBCHAR,
                [1],
                {"charset": "OCTETS"},
                "CHAR(1) CHARACTER SET OCTETS",
            ),
            (FbTypes.FBVARCHAR, [1], {}, "VARCHAR(1)"),
            (
                FbTypes.FBVARCHAR,
                [1],
                {"charset": "OCTETS"},
                "VARCHAR(1) CHARACTER SET OCTETS",
            ),
        ]
        for type_, args, kw, res in columns:
            print(type_, args, kw, res)
            self.assert_compile(type_(*args, **kw), res)

    def test_quoting_initial_chars(self):
        self.assert_compile(column("_somecol"), '"_somecol"')
        self.assert_compile(column("$somecol"), '"$somecol"')

    #
    # Tests from postgresql/test_compiler.py
    #

    def test_plain_stringify_returning(self):
        t = Table(
            "t",
            MetaData(),
            Column("myid", Integer, primary_key=True),
            Column("name", String, server_default="some str"),
            Column("description", String, default=func.lower("hi")),
        )
        stmt = t.insert().values().return_defaults()
        eq_ignore_whitespace(
            str(stmt.compile()),
            "INSERT INTO t (description) VALUES (lower(:lower_1)) "
            "RETURNING t.myid, t.name, t.description",
        )

    def test_update_returning(self):
        table1 = table(
            "mytable",
            column("myid", Integer),
            column("name", String(128)),
            column("description", String(128)),
        )
        u = (
            update(table1)
            .values(dict(name="foo"))
            .returning(table1.c.myid, table1.c.name)
        )
        self.assert_compile(
            u,
            "UPDATE mytable SET name=CAST(:name AS VARCHAR(128)) "
            "RETURNING mytable.myid, mytable.name",
        )
        u = update(table1).values(dict(name="foo")).returning(table1)
        self.assert_compile(
            u,
            "UPDATE mytable SET name=CAST(:name AS VARCHAR(128)) "
            "RETURNING mytable.myid, mytable.name, "
            "mytable.description",
        )
        u = (
            update(table1)
            .values(dict(name="foo"))
            .returning(func.length(table1.c.name))
        )
        self.assert_compile(
            u,
            "UPDATE mytable SET name=CAST(:name AS VARCHAR(128)) "
            "RETURNING CHAR_LENGTH(mytable.name) AS length_1",
        )

    def test_insert_returning(self):
        table1 = table(
            "mytable",
            column("myid", Integer),
            column("name", String(128)),
            column("description", String(128)),
        )
        i = (
            insert(table1)
            .values(dict(name="foo"))
            .returning(table1.c.myid, table1.c.name)
        )
        self.assert_compile(
            i,
            "INSERT INTO mytable (name) VALUES "
            "(CAST(:name AS VARCHAR(128))) RETURNING mytable.myid, "
            "mytable.name",
        )
        i = insert(table1).values(dict(name="foo")).returning(table1)
        self.assert_compile(
            i,
            "INSERT INTO mytable (name) VALUES "
            "(CAST(:name AS VARCHAR(128))) RETURNING mytable.myid, "
            "mytable.name, mytable.description",
        )
        i = (
            insert(table1)
            .values(dict(name="foo"))
            .returning(func.length(table1.c.name))
        )
        self.assert_compile(
            i,
            "INSERT INTO mytable (name) VALUES "
            "(CAST(:name AS VARCHAR(128))) RETURNING CHAR_LENGTH(mytable.name) "
            "AS length_1",
        )

    @testing.fixture
    def column_expression_fixture(self):
        class MyString(TypeEngine):
            def column_expression(self, column):
                return func.lower(column)

        return table(
            "some_table", column("name", String), column("value", MyString)
        )

    @testing.combinations("columns", "table", argnames="use_columns")
    def test_plain_returning_column_expression(
        self, column_expression_fixture, use_columns
    ):
        """test #8770"""
        table1 = column_expression_fixture

        if use_columns == "columns":
            stmt = insert(table1).returning(table1)
        else:
            stmt = insert(table1).returning(table1.c.name, table1.c.value)

        # Type MyString have render_bind_cast = False
        self.assert_compile(
            stmt,
            'INSERT INTO some_table (name, "value") '
            "VALUES (CAST(:name AS BLOB SUB_TYPE TEXT), :value) RETURNING some_table.name, "
            'lower(some_table."value") AS "value"',
        )

    def test_cast_double_pg_double(self):
        """test sqlalchemy Double to Firebird DOUBLE PRECISION"""
        d1 = sqltypes.Double

        stmt = select(cast(column("foo"), d1))
        self.assert_compile(
            stmt,
            "SELECT CAST(foo AS DOUBLE PRECISION) AS foo FROM rdb$database",
        )

    def test_create_table_with_multiple_options(self):
        m = MetaData()
        tbl = Table(
            "atable",
            m,
            Column("id", Integer),
            prefixes=["GLOBAL TEMPORARY"],
            firebirdsql_on_commit="PRESERVE ROWS",
        )
        self.assert_compile(
            schema.CreateTable(tbl),
            "CREATE GLOBAL TEMPORARY TABLE atable (id INTEGER) "
            "ON COMMIT PRESERVE ROWS",
        )

    def test_create_index_descending(self):
        m = MetaData()
        tbl = Table("testtbl", m, Column("data", Integer))

        idx1 = Index("test_idx1", tbl.c.data, firebirdsql_descending=True)
        self.assert_compile(
            schema.CreateIndex(idx1),
            "CREATE DESCENDING INDEX test_idx1 ON testtbl (data)",
        )

    def test_create_partial_index(self):
        m = MetaData()
        tbl = Table("testtbl", m, Column("data", Integer))
        idx = Index(
            "test_idx1",
            tbl.c.data,
            firebirdsql_where=and_(tbl.c.data > 5, tbl.c.data < 10),
        )
        idx = Index(
            "test_idx1",
            tbl.c.data,
            firebirdsql_where=and_(tbl.c.data > 5, tbl.c.data < 10),
        )

        # test quoting and all that

        idx2 = Index(
            "test_idx2",
            tbl.c.data,
            firebirdsql_where=and_(tbl.c.data > "a", tbl.c.data < "b's"),
        )
        self.assert_compile(
            schema.CreateIndex(idx),
            "CREATE INDEX test_idx1 ON testtbl (data) "
            "WHERE data > 5 AND data < 10",
        )
        self.assert_compile(
            schema.CreateIndex(idx2),
            "CREATE INDEX test_idx2 ON testtbl (data) "
            "WHERE data > 'a' AND data < 'b''s'",
        )

        idx3 = Index(
            "test_idx2",
            tbl.c.data,
            firebirdsql_where=text("data > 'a' AND data < 'b''s'"),
        )
        self.assert_compile(
            schema.CreateIndex(idx3),
            "CREATE INDEX test_idx2 ON testtbl (data) "
            "WHERE data > 'a' AND data < 'b''s'",
        )

    def test_create_index_with_text_or_composite(self):
        m = MetaData()
        tbl = Table("testtbl", m, Column("d1", String), Column("d2", Integer))

        idx = Index("test_idx1", text("x"))
        tbl.append_constraint(idx)

        idx2 = Index("test_idx2", text("y"), tbl.c.d2)

        self.assert_compile(
            schema.CreateIndex(idx),
            "CREATE INDEX test_idx1 ON testtbl COMPUTED BY (x)",
        )
        self.assert_compile(
            schema.CreateIndex(idx2),
            "CREATE INDEX test_idx2 ON testtbl COMPUTED BY (y||d2)",
        )

    def test_create_index_with_multiple_options(self):
        m = MetaData()
        tbl = Table("testtbl", m, Column("data", String))

        idx1 = Index(
            "test_idx1",
            tbl.c.data,
            firebirdsql_descending=True,
            firebirdsql_where=and_(tbl.c.data > 5, tbl.c.data < 10),
        )

        self.assert_compile(
            schema.CreateIndex(idx1),
            "CREATE DESCENDING INDEX test_idx1 ON testtbl "
            "(data) "
            "WHERE data > 5 AND data < 10",
        )

    def test_create_index_expr_gets_parens(self):
        m = MetaData()
        tbl = Table("testtbl", m, Column("x", Integer), Column("y", Integer))

        idx1 = Index("test_idx1", 5 // (tbl.c.x + tbl.c.y))
        self.assert_compile(
            schema.CreateIndex(idx1),
            "CREATE INDEX test_idx1 ON testtbl COMPUTED BY (5 / (x + y))",
        )

    def test_create_index_literals(self):
        m = MetaData()
        tbl = Table("testtbl", m, Column("data", Integer))

        idx1 = Index("test_idx1", tbl.c.data + 5)
        self.assert_compile(
            schema.CreateIndex(idx1),
            "CREATE INDEX test_idx1 ON testtbl COMPUTED BY (data + 5)",
        )

    def test_substring(self):
        self.assert_compile(
            func.substring("abc", 1, 2),
            "SUBSTRING(CAST(:substring_1 AS BLOB SUB_TYPE TEXT) FROM CAST(:substring_2 AS INTEGER) FOR CAST(:substring_3 AS INTEGER))",
        )
        self.assert_compile(
            func.substring("abc", 1),
            "SUBSTRING(CAST(:substring_1 AS BLOB SUB_TYPE TEXT) FROM CAST(:substring_2 AS INTEGER))",
        )

    def test_for_update(self):
        table1 = table(
            "mytable", column("myid"), column("name"), column("description")
        )

        self.assert_compile(
            table1.select().where(table1.c.myid == 7).with_for_update(),
            "SELECT mytable.myid, mytable.name, mytable.description "
            "FROM mytable WHERE mytable.myid = CAST(:myid_1 AS INTEGER) "
            "FOR UPDATE WITH LOCK",
        )

        self.assert_compile(
            table1.select()
            .where(table1.c.myid == 7)
            .with_for_update(nowait=True),
            "SELECT mytable.myid, mytable.name, mytable.description "
            "FROM mytable WHERE mytable.myid = CAST(:myid_1 AS INTEGER) WITH LOCK",
        )

        try:
            table1.select().where(table1.c.myid == 7).with_for_update(
                skip_locked=True
            ).compile(dialect=FBDialect_syn())
            assert False, "Should have raised CompileError"
        except exc.CompileError as err:
            assert "SKIP LOCKED" in str(err)

    def test_for_update_basic(self):
        t = table("sometable", column("col1"), column("col2"))
        eq_ignore_whitespace(
            str(select(t).with_for_update().compile(dialect=self.__dialect__)),
            "SELECT sometable.col1, sometable.col2 FROM sometable FOR UPDATE WITH LOCK",
        )

    def test_for_update_nowait(self):
        t = table("sometable", column("col1"), column("col2"))
        eq_ignore_whitespace(
            str(
                select(t)
                .with_for_update(nowait=True)
                .compile(dialect=self.__dialect__)
            ),
            "SELECT sometable.col1, sometable.col2 FROM sometable WITH LOCK",
        )

    def test_for_update_skip_locked_raises(self):
        t = table("sometable", column("col1"), column("col2"))
        try:
            select(t).with_for_update(skip_locked=True).compile(
                dialect=FBDialect_syn()
            )
            assert False, "Should have raised CompileError"
        except exc.CompileError as err:
            assert "SKIP LOCKED" in str(err)

    def test_for_update_read_raises(self):
        """Firebird has no shared/read-only row locking — should raise."""
        t = table("sometable", column("col1"), column("col2"))
        try:
            select(t).with_for_update(read=True).compile(dialect=FBDialect_syn())
            assert False, "Should have raised CompileError"
        except exc.CompileError as err:
            assert "read" in str(err).lower() or "shared" in str(err).lower()

    def test_for_update_of_ignored(self):
        """Firebird ignores the 'of' (specific-column) locking hint."""
        t = table("sometable", column("col1"), column("col2"))
        # Should not raise — 'of' is silently ignored
        eq_ignore_whitespace(
            str(
                select(t)
                .with_for_update(of=t.c.col1)
                .compile(dialect=self.__dialect__)
            ),
            "SELECT sometable.col1, sometable.col2 FROM sometable FOR UPDATE WITH LOCK",
        )

    def test_similar_to_operator(self):
        from sqlalchemy_firebirdsql.ext import not_similar_to
        from sqlalchemy_firebirdsql.ext import similar_to

        t = table("t", column("name", String))
        self.assert_compile(
            select(t).where(similar_to(t.c.name, "[A-Z]+")),
            "SELECT t.name FROM t WHERE t.name SIMILAR TO '[A-Z]+'",
            literal_binds=True,
        )
        self.assert_compile(
            select(t).where(not_similar_to(t.c.name, "[0-9]+")),
            "SELECT t.name FROM t WHERE t.name NOT SIMILAR TO '[0-9]+'",
            literal_binds=True,
        )

    def test_reserved_words(self):
        table = Table(
            "pg_table",
            MetaData(),
            Column("col1", Integer),
            Column("character_length", Integer),
        )
        x = select(table.c.col1, table.c.character_length)

        self.assert_compile(
            x,
            """SELECT pg_table.col1, pg_table."character_length" FROM pg_table""",
        )

    @testing.provide_metadata
    @testing.combinations(
        ("no_persisted", "ignore"), ("persisted", True), id_="ia"
    )
    def test_column_computed(self, persisted):
        kwargs = {"persisted": persisted} if persisted != "ignore" else {}

        t = Table(
            "t",
            self.metadata,
            Column("x", Integer),
            Column("y", Integer, Computed("x + 2", **kwargs)),
        )
        if persisted == "ignore":
            self.assert_compile(
                schema.CreateTable(t),
                "CREATE TABLE t (x INTEGER, y INTEGER GENERATED "
                "ALWAYS AS (x + 2))",
            )
        else:
            assert_raises_message(
                exc.CompileError,
                "Firebird computed columns do not support a persistence method",
                schema.CreateTable(t).compile,
                dialect=self.__dialect__,
            )

    @testing.combinations(True, False)
    def test_column_identity(self, pk):
        # all other tests are in test_identity_column.py
        m = MetaData()
        t = Table(
            "t",
            m,
            Column(
                "y",
                Integer,
                Identity(always=True, start=4, increment=7),
                primary_key=pk,
            ),
        )
        self.assert_compile(
            schema.CreateTable(t),
            "CREATE TABLE t (y INTEGER GENERATED ALWAYS AS IDENTITY "
            "(START WITH 4 INCREMENT BY 7)%s)"
            % (", PRIMARY KEY (y)" if pk else ""),
        )

    def test_column_identity_null(self):
        # all other tests are in test_identity_column.py
        m = MetaData()
        t = Table(
            "t",
            m,
            Column(
                "y",
                Integer,
                Identity(always=True, start=4, increment=7),
                nullable=True,
            ),
        )
        self.assert_compile(
            schema.CreateTable(t),
            "CREATE TABLE t (y INTEGER GENERATED ALWAYS AS IDENTITY "
            "(START WITH 4 INCREMENT BY 7) NULL)",
        )

    @testing.fixture
    def update_tables(self):
        self.weather = table(
            "weather",
            column("temp_lo", Integer),
            column("temp_hi", Integer),
            column("prcp", Integer),
            column("city", String),
            column("date", Date),
        )
        self.accounts = table(
            "accounts",
            column("sales_id", Integer),
            column("sales_person", Integer),
            column("contact_first_name", String),
            column("contact_last_name", String),
            column("name", String),
        )
        self.salesmen = table(
            "salesmen",
            column("id", Integer),
            column("first_name", String),
            column("last_name", String),
        )
        self.employees = table(
            "employees",
            column("id", Integer),
            column("sales_count", String),
        )

    def test_bitwise_xor(self):
        c1 = column("c1", Integer)
        c2 = column("c2", Integer)
        self.assert_compile(
            select(c1.bitwise_xor(c2)),
            "SELECT BIN_XOR(c1, c2) AS anon_1 FROM rdb$database",
        )
