# Allow circular references between FBDialect and FBInspector
from typing import List
from typing import Optional
from typing import TypedDict

from sqlalchemy import exc
from sqlalchemy import schema as sa_schema
from sqlalchemy import sql
from sqlalchemy import text
from sqlalchemy import types as sa_types
from sqlalchemy import util
from sqlalchemy.engine import default
from sqlalchemy.engine import reflection
from sqlalchemy.engine.reflection import ObjectKind
from sqlalchemy.engine.reflection import ObjectScope
from sqlalchemy.engine.interfaces import BindTyping
from sqlalchemy.sql import coercions
from sqlalchemy.sql import compiler
from sqlalchemy.sql import expression
from sqlalchemy.sql import roles

import sqlalchemy_firebirdsql.types as fb_types


MAX_IDENTIFIER_LENGTH = 63


RESERVED_WORDS = {
    "add",
    "admin",
    "all",
    "alter",
    "and",
    "any",
    "as",
    "at",
    "avg",
    "begin",
    "between",
    "bigint",
    "binary",
    "bit_length",
    "blob",
    "boolean",
    "both",
    "by",
    "case",
    "cast",
    "char",
    "character",
    "character_length",
    "char_length",
    "check",
    "close",
    "collate",
    "column",
    "comment",
    "commit",
    "connect",
    "constraint",
    "corr",
    "count",
    "covar_pop",
    "covar_samp",
    "create",
    "cross",
    "current",
    "current_connection",
    "current_date",
    "current_role",
    "current_time",
    "current_timestamp",
    "current_transaction",
    "current_user",
    "cursor",
    "date",
    "day",
    "dec",
    "decfloat",
    "decimal",
    "declare",
    "default",
    "delete",
    "deleting",
    "deterministic",
    "disconnect",
    "distinct",
    "double",
    "drop",
    "else",
    "end",
    "escape",
    "execute",
    "exists",
    "external",
    "extract",
    "false",
    "fetch",
    "filter",
    "float",
    "for",
    "foreign",
    "from",
    "full",
    "function",
    "gdscode",
    "global",
    "grant",
    "group",
    "having",
    "hour",
    "in",
    "index",
    "inner",
    "insensitive",
    "insert",
    "inserting",
    "int",
    "int128",
    "integer",
    "into",
    "is",
    "join",
    "lateral",
    "leading",
    "left",
    "like",
    "local",
    "localtime",
    "localtimestamp",
    "long",
    "lower",
    "max",
    "merge",
    "min",
    "minute",
    "month",
    "national",
    "natural",
    "nchar",
    "no",
    "not",
    "null",
    "numeric",
    "octet_length",
    "of",
    "offset",
    "on",
    "only",
    "open",
    "or",
    "order",
    "outer",
    "over",
    "parameter",
    "plan",
    "position",
    "post_event",
    "precision",
    "primary",
    "procedure",
    "publication",
    "rdb$db_key",
    "rdb$error",
    "rdb$get_context",
    "rdb$get_transaction_cn",
    "rdb$record_version",
    "rdb$role_in_use",
    "rdb$set_context",
    "rdb$system_privilege",
    "real",
    "record_version",
    "recreate",
    "recursive",
    "references",
    "regr_avgx",
    "regr_avgy",
    "regr_count",
    "regr_intercept",
    "regr_r2",
    "regr_slope",
    "regr_sxx",
    "regr_sxy",
    "regr_syy",
    "release",
    "resetting",
    "return",
    "returning_values",
    "returns",
    "revoke",
    "right",
    "rollback",
    "row",
    "rows",
    "row_count",
    "savepoint",
    "scroll",
    "second",
    "select",
    "sensitive",
    "set",
    "similar",
    "smallint",
    "some",
    "sqlcode",
    "sqlstate",
    "start",
    "stddev_pop",
    "stddev_samp",
    "sum",
    "table",
    "then",
    "time",
    "timestamp",
    "timezone_hour",
    "timezone_minute",
    "to",
    "trailing",
    "trigger",
    "trim",
    "true",
    "unbounded",
    "union",
    "unique",
    "unknown",
    "update",
    "updating",
    "upper",
    "user",
    "using",
    "value",
    "values",
    "varbinary",
    "varchar",
    "variable",
    "varying",
    "var_pop",
    "var_samp",
    "view",
    "when",
    "where",
    "while",
    "window",
    "with",
    "without",
    "year",
}


# Expression separator for COMPUTED BY expressions
EXPRESSION_SEPARATOR = "||"


def coalesce(*arg):
    # https://stackoverflow.com/questions/4978738/is-there-a-python-equivalent-of-the-c-sharp-null-coalescing-operator#comment37717570_16247152
    return next((a for a in arg if a is not None), None)


class FBCompiler(sql.compiler.SQLCompiler):
    def render_bind_cast(self, type_, dbapi_type, sqltext):
        return f"""CAST({sqltext} AS {
            self.dialect.type_compiler_instance.process(
                dbapi_type, identifier_preparer=self.preparer
            )
        })"""

    def visit_empty_set_expr(self, element_types, **kw):
        return "SELECT 1 FROM rdb$database WHERE 1 != 1"

    def visit_sequence(self, sequence, **kw):
        return "GEN_ID(%s, 1)" % self.preparer.format_sequence(sequence)

    def limit_clause(self, select, **kw):
        return self._handle_limit_fetch_clause(
            None, select._offset_clause, select._limit_clause, **kw
        )

    def for_update_clause(self, select, **kw):
        if select._for_update_arg.skip_locked:
            raise exc.CompileError(
                "Firebird does not support SELECT ... FOR UPDATE SKIP LOCKED"
            )
        if select._for_update_arg.read:
            raise exc.CompileError(
                "Firebird does not support shared/read-only row locking "
                "(FOR UPDATE OF ... READ ONLY)"
            )
        # Firebird row-level locking: WITH LOCK acquires an exclusive lock.
        # FOR UPDATE WITH LOCK is equivalent and is the most portable form.
        # The 'of' (specific-column) locking hint is not supported by Firebird;
        # it is silently ignored and all selected rows are locked instead.
        if select._for_update_arg.nowait:
            return " WITH LOCK"
        return " FOR UPDATE WITH LOCK"

    def visit_merge_into(self, merge, **kw):
        target = merge.target
        source = merge._source
        on_clause = merge._on_clause

        target_str = self.process(target, asfrom=True, **kw)
        source_str = self.process(source, asfrom=True, **kw)
        on_str = self.process(on_clause, **kw)

        clauses = [
            f"MERGE INTO {target_str}",
            f"USING {source_str}",
            f"ON ({on_str})",
        ]

        if merge._when_matched_update is not None:
            set_parts = []
            for col, val in merge._when_matched_update:
                col_name = self.process(col, **kw).split(".")[-1]
                val_str = self.process(val, **kw)
                set_parts.append(f"{col_name} = {val_str}")
            clauses.append(
                "WHEN MATCHED THEN UPDATE SET " + ", ".join(set_parts)
            )

        if merge._when_not_matched_insert_cols is not None:
            cols_str = ", ".join(
                self.process(col, **kw).split(".")[-1]
                for col in merge._when_not_matched_insert_cols
            )
            vals_str = ", ".join(
                self.process(val, **kw)
                for val in merge._when_not_matched_insert_values
            )
            clauses.append(
                f"WHEN NOT MATCHED THEN INSERT ({cols_str}) VALUES ({vals_str})"
            )

        return "\n".join(clauses)

    def fetch_clause(
        self,
        select,
        fetch_clause=None,
        require_offset=False,
        use_literal_execute_for_simple_int=False,
        **kw,
    ):
        if fetch_clause is None:
            fetch_clause = select._fetch_clause

        return self._handle_limit_fetch_clause(
            fetch_clause, select._offset_clause, None, **kw
        )

    def _handle_limit_fetch_clause(
        self, fetch_clause, offset_clause, limit_clause, **kw
    ):
        # Albeit non-standard, ROWS is a better choice than OFFSET / FETCH in Firebird since
        #   it is supported since Firebird 2.5 and it works with expressions.
        # https://firebirdsql.org/file/documentation/html/en/refdocs/fblangref40/firebird-40-language-reference.html#fblangref40-dml-select-rows
        text = ""

        if (fetch_clause is not None) and (offset_clause is not None):
            # OFFSET 2 ROWS FETCH NEXT 5 ROWS ONLY  =>  ROWS 2 + 1 TO 2 + 5
            text += (
                " \n ROWS "
                + self.process(offset_clause, **kw)
                + " + 1 TO "
                + self.process(offset_clause, **kw)
                + " + "
                + self.process(fetch_clause, **kw)
            )
        elif (limit_clause is not None) and (offset_clause is not None):
            # LIMIT 5 OFFSET 2  =>  ROWS 2 + 1 TO 2 + 5
            text += (
                " \n ROWS "
                + self.process(offset_clause, **kw)
                + " + 1 TO "
                + self.process(offset_clause, **kw)
                + " + "
                + self.process(limit_clause, **kw)
            )
        elif fetch_clause is not None:
            # FETCH NEXT 5 ROWS ONLY  =>  ROWS 1 TO 5
            text += " \n ROWS 1 TO " + self.process(fetch_clause, **kw)
        elif limit_clause is not None:
            # LIMIT 5  =>  ROWS 1 TO 5
            text += " \n ROWS 1 TO " + self.process(limit_clause, **kw)
        elif offset_clause is not None:
            # OFFSET 2 ROWS  =>  ROWS 2 + 1 TO 9223372036854775807
            text += (
                " \n ROWS "
                + self.process(offset_clause, **kw)
                + " + 1 TO 9223372036854775807"
            )

        return text

    def visit_substring_func(self, func, **kw):
        s = self.process(func.clauses.clauses[0])
        start = self.process(func.clauses.clauses[1])
        if len(func.clauses.clauses) > 2:
            length = self.process(func.clauses.clauses[2])
            return f"SUBSTRING({s} FROM {start} FOR {length})"

        return f"SUBSTRING({s} FROM {start})"

    def visit_truediv_binary(self, binary, operator, **kw):
        return (
            self.process(binary.left, **kw)
            + " / "
            + "(%s + 0.0)" % self.process(binary.right, **kw)
        )

    def visit_mod_binary(self, binary, operator, **kw):
        return "MOD(%s, %s)" % (
            self.process(binary.left, **kw),
            self.process(binary.right, **kw),
        )

    def visit_bitwise_xor_op_binary(self, binary, operator, **kw):
        return "BIN_XOR(%s, %s)" % (
            self.process(binary.left, **kw),
            self.process(binary.right, **kw),
        )

    def visit_now_func(self, fn, **kw):
        return "CURRENT_TIMESTAMP"

    def function_argspec(self, fn, **kw):
        if fn.clauses is not None and len(fn.clauses) > 0:
            return self.process(fn.clause_expr, **kw)

        return ""

    def visit_char_length_func(self, fn, **kw):
        return "CHAR_LENGTH" + self.function_argspec(fn, **kw)

    def visit_length_func(self, fn, **kw):
        return "CHAR_LENGTH" + self.function_argspec(fn, **kw)

    def default_from(self):
        return " FROM rdb$database"

class FBDDLCompiler(sql.compiler.DDLCompiler):
    def get_column_specification(self, column, **kwargs):
        colspec = self.preparer.format_column(column)

        impl_type = column.type.dialect_impl(self.dialect)
        if isinstance(impl_type, sa_types.TypeDecorator):
            impl_type = impl_type.impl

        has_identity = column.identity is not None

        if (
            column.primary_key
            and column is column.table._autoincrement_column
            and not has_identity
            and (
                column.default is None
                or (
                    isinstance(column.default, sa_schema.Sequence)
                    and column.default.optional
                )
            )
            and self.dialect.supports_identity_columns
        ):
            colspec += " INTEGER GENERATED BY DEFAULT AS IDENTITY"
        else:
            type_compiler_instance = self.dialect.type_compiler_instance

            colspec += " " + type_compiler_instance.process(
                column.type,
                type_expression=column,
                identifier_preparer=self.preparer,
            )
            default_ = self.get_column_default_string(column)
            if default_ is not None:
                colspec += " DEFAULT " + default_

            if column.computed is not None:
                colspec += " " + self.process(column.computed)
            if has_identity:
                colspec += " " + self.process(column.identity)

            if not column.nullable and not has_identity:
                colspec += " NOT NULL"
            elif column.nullable and has_identity:
                colspec += " NULL"

        return colspec

    def visit_create_index(
        self, create, include_schema=False, include_table_schema=True, **kw
    ):
        preparer = self.preparer
        index = create.element
        self._verify_index_table(index)

        if index.name is None:
            raise exc.CompileError(
                "CREATE INDEX requires that the index have a name."
            )

        txt = "CREATE "
        if index.unique:
            txt += "UNIQUE "
        descending = index.dialect_options["firebirdsql"]["descending"]
        if descending is True:
            txt += "DESCENDING "

        txt += "INDEX %s ON %s " % (
            self._prepared_index_name(index, include_schema=include_schema),
            preparer.format_table(
                index.table, use_schema=include_table_schema
            ),
        )

        if index.expressions is None:
            raise exc.CompileError(
                "CREATE INDEX requires at least one column or expression."
            )

        first_expression = (
            index.expressions[0]
            if len(index.expressions) > 0
            else index.expressions
        )

        if isinstance(first_expression, expression.ColumnClause):
            # INDEX on columns
            txt += "(%s)" % (
                ", ".join(
                    self.sql_compiler.process(
                        expr, include_table=False, literal_binds=True
                    )
                    for expr in index.expressions
                )
            )
        else:
            # INDEX on expression
            txt += "COMPUTED BY (%s)" % EXPRESSION_SEPARATOR.join(
                self.sql_compiler.process(
                    expr, include_table=False, literal_binds=True
                )
                for expr in index.expressions
            )

        # Partial indices (Firebird 5.0+)
        whereclause = index.dialect_options["firebirdsql"]["where"]
        if whereclause is not None:
            whereclause = coercions.expect(
                roles.DDLExpressionRole, whereclause
            )

            where_compiled = self.sql_compiler.process(
                whereclause, include_table=False, literal_binds=True
            )
            txt += " WHERE " + where_compiled

        return txt

    def post_create_table(self, table):
        table_opts = []
        fb_opts = table.dialect_options["firebirdsql"]

        if fb_opts["on_commit"]:
            on_commit_options = fb_opts["on_commit"]
            table_opts.append("\n ON COMMIT %s" % on_commit_options)

        return "".join(table_opts)

    def visit_computed_column(self, generated, **kw):
        if generated.persisted is not None:
            raise exc.CompileError(
                "Firebird computed columns do not support a persistence "
                "method setting; set the 'persisted' flag to None for "
                "Firebird support."
            )

        return "GENERATED ALWAYS AS (%s)" % self.sql_compiler.process(
            generated.sqltext, include_table=False, literal_binds=True
        )

    def get_identity_options(self, identity_options):
        txt = []
        if identity_options.start is not None:
            start = identity_options.start

            # Firebird 3 has distinct START WITH semantic.
            # https://firebirdsql.org/file/documentation/release_notes/html/en/4_0/rlsnotes40.html#rnfb40-compat-sql-sequence-start-value
            # Previous versions of dialect tried to hide this (adjusting here the reflected start value).
            # This was removed since it opens a can of worms (e.g. when reading databases NOT created by SQLAlchemy).

            txt.append("START WITH %d" % start)

        if identity_options.increment is not None:
            txt.append("INCREMENT BY %d" % identity_options.increment)

        return " ".join(txt)

    def visit_identity_column(self, identity, **kw):
        kind = (
            "ALWAYS"
            if identity.always
            else "BY DEFAULT"
        )
        text = "GENERATED %s AS IDENTITY" % kind

        options = self.get_identity_options(identity)
        if options:
            text += " (%s)" % options

        return text


class FBTypeCompiler(compiler.GenericTypeCompiler):
    def visit_boolean(self, type_, **kw):
        return self.visit_BOOLEAN(type_, **kw)

    def visit_datetime(self, type_, **kw):
        return self.visit_TIMESTAMP(type_, **kw)

    def _render_string_type(self, type_, name, length_override=None, collation=None):
        length = coalesce(
            length_override,
            getattr(type_, "length", None),
        )
        charset = getattr(type_, "charset", None)

        if name in ["BINARY", "VARBINARY", "NCHAR", "NVARCHAR"]:
            charset = None
            collation = None

        if name == "NVARCHAR":
            name = "NATIONAL CHARACTER VARYING"

        text = name
        if length is None:
            if name == "VARBINARY" or (
                name == "VARCHAR" and charset == fb_types.BINARY_CHARSET
            ):
                text = "BLOB SUB_TYPE BINARY"
                charset = fb_types.BINARY_CHARSET
                collation = None
            elif name == "VARCHAR":
                text = "BLOB SUB_TYPE TEXT"
            elif name == "NATIONAL CHARACTER VARYING":
                text = "BLOB SUB_TYPE TEXT"
                charset = fb_types.NATIONAL_CHARSET
                collation = None

        text = text + (length and "(%d)" % length or "")

        if charset is not None:
            text += f" CHARACTER SET {charset}"

        if collation is not None:
            text += f" COLLATE {collation}"

        return text

    def visit_BINARY(self, type_, **kw):
        return self._render_string_type(type_, "BINARY")

    def visit_VARBINARY(self, type_, **kw):
        return self._render_string_type(type_, "VARBINARY")

    def visit_CHAR(self, type_, **kw) -> str:
        return self._render_string_type(type_, "CHAR", type_.length, type_.collation)

    def visit_NCHAR(self, type_, **kw) -> str:
        return self._render_string_type(type_, "NCHAR", type_.length, type_.collation)

    def visit_VARCHAR(self, type_, **kw) -> str:
        return self._render_string_type(
            type_, "VARCHAR", type_.length, type_.collation
        )

    def visit_NVARCHAR(self, type_, **kw) -> str:
        return self._render_string_type(
            type_, "NVARCHAR", type_.length, type_.collation
        )

    def visit_TEXT(self, type_, **kw):
        return self.visit_BLOB(type_, override_subtype=1, **kw)

    def visit_BLOB(self, type_, override_subtype=None, **kw):
        text = "BLOB"

        subtype = coalesce(override_subtype, getattr(type_, "subtype", None))
        if subtype is not None:
            text += " SUB_TYPE TEXT" if subtype == 1 else " SUB_TYPE BINARY"

        segment_size = getattr(type_, "segment_size", None)
        if segment_size is not None:
            text += f" SEGMENT SIZE {segment_size}"

        charset = getattr(type_, "charset", None)
        if charset is not None:
            text += f" CHARACTER SET {charset}"

        collation = getattr(type_, "collation", None)
        if collation is not None:
            text += f" COLLATE {collation}"

        return text

    def visit_INT128(self, type_, **kw):
        return "INT128"

    def visit_FLOAT(self, type_, **kw):
        return "FLOAT" + (type_.precision and "(%d)" % type_.precision or "")

    def visit_DOUBLE(self, type_, **kw):
        return "DOUBLE PRECISION"

    def visit_DOUBLE_PRECISION(self, type_, **kw):
        return "DOUBLE PRECISION"

    def visit_double(self, type_, **kw):
        return "DOUBLE PRECISION"

    def visit_DECFLOAT(self, type_, **kw):
        return "DECFLOAT" + (
            type_.precision and "(%d)" % type_.precision or ""
        )

    def visit_NUMERIC(self, type_, **kw):
        return "NUMERIC(%(precision)s, %(scale)s)" % {
            "precision": coalesce(type_.precision, 18),
            "scale": coalesce(type_.scale, 4),
        }

    def visit_DECIMAL(self, type_, **kw):
        return "DECIMAL(%(precision)s, %(scale)s)" % {
            "precision": coalesce(type_.precision, 18),
            "scale": coalesce(type_.scale, 4),
        }

    def visit_TIMESTAMP(self, type_, **kw):
        return "TIMESTAMP%s %s" % (
            "(%d)" % type_.precision
            if getattr(type_, "precision", None) is not None
            else "",
            (type_.timezone and "WITH" or "WITHOUT") + " TIME ZONE",
        )

    def visit_TIME(self, type_, **kw):
        return "TIME%s %s" % (
            "(%d)" % type_.precision
            if getattr(type_, "precision", None) is not None
            else "",
            (type_.timezone and "WITH" or "WITHOUT") + " TIME ZONE",
        )


class FBIdentifierPreparer(sql.compiler.IdentifierPreparer):
    illegal_initial_characters = compiler.ILLEGAL_INITIAL_CHARACTERS.union(
        ["_"]
    )

    def __init__(self, dialect):
        super().__init__(dialect, omit_schema=True)


class FBExecutionContext(default.DefaultExecutionContext):
    def fire_sequence(self, seq, type_):
        return self._execute_scalar(
            (
                "SELECT GEN_ID(%s, 1) FROM rdb$database"
                % self.dialect.identifier_preparer.format_sequence(seq)
            ),
            type_,
        )


class ReflectedDomain(TypedDict):
    """Represents a reflected domain."""

    name: str
    """The string name of the underlying data type of the domain."""
    nullable: bool
    """Indicates if the domain allows null or not."""
    default: Optional[str]
    """The string representation of the default value of this domain
    or ``None`` if none present.
    """
    check: Optional[str]
    """The constraint defined in the domain, if any.
    """
    comment: Optional[str]
    """The comment of the domain, if any.
    """


class FBInspector(reflection.Inspector):
    def get_domains(
        self, schema: Optional[str] = None
    ) -> List[ReflectedDomain]:
        with self._operation_context() as conn:
            return self.dialect._load_domains(
                conn, schema, info_cache=self.info_cache
            )

    def get_sequences(self, schema: Optional[str] = None):
        with self._operation_context() as conn:
            return self.dialect.get_sequences(
                conn, schema, info_cache=self.info_cache
            )

    def get_stored_procedures(self, schema: Optional[str] = None):
        with self._operation_context() as conn:
            return self.dialect._get_stored_procedure_names(
                conn, schema, info_cache=self.info_cache
            )

    def get_stored_procedure_definition(
        self, procedure_name: str, schema: Optional[str] = None
    ):
        with self._operation_context() as conn:
            return self.dialect._get_stored_procedure_definition(
                conn,
                procedure_name,
                schema,
                info_cache=self.info_cache,
            )


class FBDialect(default.DefaultDialect):
    name = "firebirdsql"

    bind_typing = BindTyping.RENDER_CASTS

    supports_alter = True
    supports_sane_rowcount = True
    supports_sane_multi_rowcount = False

    supports_native_boolean = True  # False for Firebird 2.5
    supports_native_decimal = True

    supports_schemas = False
    supports_sequences = True
    sequences_optional = False
    postfetch_lastrowid = False
    use_insertmanyvalues = False

    supports_comments = True
    supports_default_values = True
    supports_default_metavalue = True
    supports_empty_insert = True
    supports_identity_columns = True  # False for Firebird 2.5

    statement_compiler = FBCompiler
    ddl_compiler = FBDDLCompiler
    type_compiler_cls = FBTypeCompiler
    preparer = FBIdentifierPreparer
    execution_ctx_cls = FBExecutionContext
    inspector = FBInspector

    update_returning = True
    delete_returning = True
    insert_returning = True

    supports_unicode_binds = True
    supports_is_distinct_from = True

    requires_name_normalize = True

    colspecs = {
        sa_types.String: fb_types._FBString,
        sa_types.Numeric: fb_types._FBNumeric,
        sa_types.Float: fb_types.FBFLOAT,
        sa_types.Double: fb_types.FBDOUBLE_PRECISION,
        sa_types.Date: fb_types.FBDATE,
        sa_types.Time: fb_types.FBTIME,
        sa_types.DateTime: fb_types.FBTIMESTAMP,
        sa_types.Interval: fb_types._FBInterval,
        sa_types.BigInteger: fb_types.FBBIGINT,
        sa_types.Integer: fb_types.FBINTEGER,
        sa_types.SmallInteger: fb_types.FBSMALLINT,
        sa_types.BINARY: fb_types._FBLargeBinary,
        sa_types.VARBINARY: fb_types._FBLargeBinary,
        sa_types.LargeBinary: fb_types._FBLargeBinary,
    }

    # SELECT TRIM(rdb$type_name) FROM rdb$types WHERE rdb$field_name = 'RDB$FIELD_TYPE' ORDER BY 1
    ischema_names = {
        "BLOB": fb_types._FBLargeBinary,
        # "BLOB_ID": unused
        "BOOLEAN": fb_types.FBBOOLEAN,
        "CSTRING": fb_types.FBVARCHAR,
        "DATE": fb_types.FBDATE,
        "DECFLOAT(16)": fb_types.FBDECFLOAT,
        "DECFLOAT(34)": fb_types.FBDECFLOAT,
        "DOUBLE": fb_types.FBDOUBLE_PRECISION,
        "FLOAT": fb_types.FBFLOAT,
        "INT128": fb_types.FBINT128,
        "INT64": fb_types.FBBIGINT,
        "LONG": fb_types.FBINTEGER,
        # "QUAD": unused,
        "SHORT": fb_types.FBSMALLINT,
        "TEXT": fb_types.FBCHAR,
        "TIME": fb_types.FBTIME,
        "TIME WITH TIME ZONE": fb_types.FBTIME,
        "TIMESTAMP": fb_types.FBTIMESTAMP,
        "TIMESTAMP WITH TIME ZONE": fb_types.FBTIMESTAMP,
        "VARYING": fb_types.FBVARCHAR,
    }

    construct_arguments = [
        (
            sa_schema.Table,
            {
                "on_commit": None,
            },
        ),
        (
            sa_schema.Index,
            {
                "descending": None,
                "where": None,
            },
        ),
    ]

    def initialize(self, connection):
        super().initialize(connection)
        self.max_identifier_length = MAX_IDENTIFIER_LENGTH
        self.preparer.reserved_words = RESERVED_WORDS

    @reflection.cache
    def has_table(self, connection, table_name, schema=None, **kw):
        has_table_query = """
            SELECT 1 AS has_table
            FROM rdb$relations
            WHERE rdb$relation_name = ?
        """
        tablename = self.denormalize_name(table_name)
        c = connection.exec_driver_sql(has_table_query, (tablename,))
        return c.first() is not None

    @reflection.cache
    def has_sequence(self, connection, sequence_name, schema=None, **kw):
        has_sequence_query = """
            SELECT 1 AS has_sequence 
            FROM rdb$generators
            WHERE rdb$generator_name = ?
        """
        sequencename = self.denormalize_name(sequence_name)
        c = connection.exec_driver_sql(has_sequence_query, (sequencename,))
        return c.first() is not None

    @reflection.cache
    def get_table_names(self, connection, schema=None, **kw):
        tables_query = """
            SELECT TRIM(rdb$relation_name) AS relation_name
            FROM rdb$relations
            WHERE rdb$relation_type IN (0 /* TABLE */)
              AND COALESCE(rdb$system_flag, 0) = 0
            ORDER BY 1
        """

        return [
            self.normalize_name(row.relation_name)
            for row in connection.exec_driver_sql(tables_query)
        ]

    @reflection.cache
    def get_temp_table_names(self, connection, schema=None, **kw):
        temp_tables_query = """
            SELECT TRIM(rdb$relation_name) AS relation_name
            FROM rdb$relations
            WHERE rdb$relation_type IN (4 /* TEMPORARY_TABLE_PRESERVE */, 
                                        5 /* TEMPORARY_TABLE_DELETE */)
              AND COALESCE(rdb$system_flag, 0) = 0
            ORDER BY 1
        """
        return [
            self.normalize_name(row.relation_name)
            for row in connection.exec_driver_sql(temp_tables_query)
        ]

    @reflection.cache
    def get_view_names(self, connection, schema=None, **kw):
        views_query = """
            SELECT TRIM(rdb$relation_name) AS relation_name
            FROM rdb$relations
            WHERE rdb$relation_type IN (1 /* VIEW */)
              AND COALESCE(rdb$system_flag, 0) = 0
            ORDER BY 1
        """
        return [
            self.normalize_name(row.relation_name)
            for row in connection.exec_driver_sql(views_query)
        ]

    @reflection.cache
    def get_sequence_names(self, connection, schema=None, **kw):
        sequences_query = """
            SELECT TRIM(rdb$generator_name) AS generator_name
            FROM rdb$generators
            WHERE COALESCE(rdb$system_flag, 0) = 0
        """
        # Do not need ORDER BY
        return [
            self.normalize_name(row.generator_name)
            for row in connection.exec_driver_sql(sequences_query)
        ]

    @reflection.cache
    def get_sequences(self, connection, schema=None, **kw):
        """Return information about all sequences (generators) in the database.

        Firebird generators do not have min/max/cycle attributes (unlike
        PostgreSQL sequences); those fields are therefore not included.
        ``rdb$initial_value`` and ``rdb$generator_increment`` are available
        from Firebird 3.0 onward.
        """
        sequences_query = """
            SELECT TRIM(rdb$generator_name) AS generator_name,
                   rdb$initial_value AS initial_value,
                   rdb$generator_increment AS increment
            FROM rdb$generators
            WHERE COALESCE(rdb$system_flag, 0) = 0
            ORDER BY rdb$generator_name
        """
        result = []
        for row in connection.exec_driver_sql(sequences_query):
            result.append(
                {
                    "name": self.normalize_name(row.generator_name),
                    "start": row.initial_value
                    if row.initial_value is not None
                    else 0,
                    "increment": row.increment if row.increment is not None else 1,
                    "schema": schema,
                }
            )
        return result

    def _multi_reflect(self, single_method, connection, **kw):
        schema = kw.pop("schema", None)
        filter_names = kw.pop("filter_names", None)
        kind = kw.pop("kind", ObjectKind.TABLE)
        scope = kw.pop("scope", ObjectScope.DEFAULT)
        unreflectable = kw.pop("unreflectable", {})

        if filter_names and scope == ObjectScope.ANY and kind == ObjectKind.ANY:
            names = filter_names
        else:
            names = []
            name_kw = {"schema": schema, **kw}
            if ObjectScope.DEFAULT in scope:
                if ObjectKind.TABLE in kind:
                    names.extend(self.get_table_names(connection, **name_kw))
                if ObjectKind.VIEW in kind:
                    names.extend(self.get_view_names(connection, **name_kw))
                if ObjectKind.MATERIALIZED_VIEW in kind:
                    try:
                        names.extend(
                            self.get_materialized_view_names(
                                connection, **name_kw
                            )
                        )
                    except NotImplementedError:
                        pass
            if ObjectScope.TEMPORARY in scope:
                if ObjectKind.TABLE in kind:
                    try:
                        names.extend(
                            self.get_temp_table_names(connection, **name_kw)
                        )
                    except NotImplementedError:
                        pass
                if ObjectKind.VIEW in kind:
                    try:
                        names.extend(
                            self.get_temp_view_names(connection, **name_kw)
                        )
                    except NotImplementedError:
                        pass
                if ObjectKind.MATERIALIZED_VIEW in kind:
                    try:
                        names.extend(
                            self.get_temp_materialized_view_names(
                                connection, **name_kw
                            )
                        )
                    except NotImplementedError:
                        pass

        result = {}
        filter_names_set = set(filter_names) if filter_names else None
        for table in names:
            if filter_names_set and table not in filter_names_set:
                continue

            key = (schema, table)
            try:
                result[key] = single_method(
                    connection, table, schema=schema, **kw
                )
            except exc.UnreflectableTableError as err:
                if key not in unreflectable:
                    unreflectable[key] = err
            except exc.NoSuchTableError:
                pass

        return result

    def get_multi_columns(self, connection, **kw):
        return self._multi_reflect(self.get_columns, connection, **kw)

    def get_multi_pk_constraint(self, connection, **kw):
        return self._multi_reflect(self.get_pk_constraint, connection, **kw)

    def get_multi_foreign_keys(self, connection, **kw):
        return self._multi_reflect(self.get_foreign_keys, connection, **kw)

    def get_multi_indexes(self, connection, **kw):
        return self._multi_reflect(self.get_indexes, connection, **kw)

    def get_multi_unique_constraints(self, connection, **kw):
        return self._multi_reflect(
            self.get_unique_constraints, connection, **kw
        )

    def get_multi_check_constraints(self, connection, **kw):
        return self._multi_reflect(self.get_check_constraints, connection, **kw)

    def get_multi_table_comment(self, connection, **kw):
        return self._multi_reflect(self.get_table_comment, connection, **kw)

    def get_multi_table_options(self, connection, **kw):
        return self._multi_reflect(self.get_table_options, connection, **kw)

    @reflection.cache
    def get_table_options(self, connection, table_name, schema=None, **kw):
        """Return Firebird-specific table options.

        For global temporary tables this includes the ``firebirdsql_on_commit``
        option (``'PRESERVE ROWS'`` or ``'DELETE ROWS'``).  Regular tables
        return an empty dict.
        """
        opts_query = """
            SELECT rdb$relation_type AS relation_type
            FROM rdb$relations
            WHERE rdb$relation_name = ?
              AND COALESCE(rdb$system_flag, 0) = 0
        """
        tblname = self.denormalize_name(table_name)
        row = connection.exec_driver_sql(opts_query, (tblname,)).fetchone()
        if row is None:
            raise exc.NoSuchTableError(table_name)
        opts = {}
        # rdb$relation_type: 4 = GLOBAL TEMPORARY ON COMMIT PRESERVE ROWS
        #                     5 = GLOBAL TEMPORARY ON COMMIT DELETE ROWS
        if row.relation_type == 4:
            opts["firebirdsql_on_commit"] = "PRESERVE ROWS"
        elif row.relation_type == 5:
            opts["firebirdsql_on_commit"] = "DELETE ROWS"
        return opts

    @reflection.cache
    def get_view_definition(self, connection, view_name, schema=None, **kw):
        view_query = """
            SELECT rdb$view_source AS view_source
            FROM rdb$relations
            WHERE rdb$relation_type IN (1 /* VIEW */)
              AND rdb$relation_name = ?
        """
        viewname = self.denormalize_name(view_name)
        c = connection.exec_driver_sql(view_query, (viewname,))
        row = c.fetchone()
        if row:
            return row.view_source

        raise exc.NoSuchTableError(view_name)

    @reflection.cache
    def get_columns(  # noqa: C901
        self, connection, table_name, schema=None, **kw
    ):
        columns_query = """
            SELECT TRIM(rf.rdb$field_name) AS field_name,
                   COALESCE(rf.rdb$null_flag, f.rdb$null_flag) AS null_flag,
                   TRIM(t.rdb$type_name) AS field_type,
                   f.rdb$field_length / COALESCE(cs.rdb$bytes_per_character, 1) AS field_length,
                   f.rdb$field_precision AS field_precision,
                   f.rdb$field_scale * -1 AS field_scale,
                   f.rdb$field_sub_type AS field_sub_type,
                   f.rdb$segment_length AS segment_length,
                   TRIM(cs.rdb$character_set_name) as character_set_name,
                   TRIM(cl.rdb$collation_name) as collation_name,
                   COALESCE(rf.rdb$default_source, f.rdb$default_source) AS default_source,
                   TRIM(rf.rdb$description) AS description,
                   f.rdb$computed_source AS computed_source
                  ,rf.rdb$identity_type AS identity_type,                      -- [fb3+]
                   g.rdb$initial_value AS initial_value,                       -- [fb3+]
                   g.rdb$generator_increment AS generator_increment            -- [fb3+]
            FROM rdb$relation_fields rf
                 JOIN rdb$fields f
                   ON f.rdb$field_name = rf.rdb$field_source
                 JOIN rdb$types t
                   ON t.rdb$type = f.rdb$field_type 
                  AND t.rdb$field_name = 'RDB$FIELD_TYPE'
                 LEFT JOIN rdb$character_sets cs
                        ON cs.rdb$character_set_id = f.rdb$character_set_id
                 LEFT JOIN rdb$collations cl
                        ON cl.rdb$collation_id = rf.rdb$collation_id
                       AND cl.rdb$character_set_id = cs.rdb$character_set_id
                 LEFT JOIN rdb$generators g                                    -- [fb3+]
                        ON g.rdb$generator_name = rf.rdb$generator_name        -- [fb3+]
            WHERE COALESCE(f.rdb$system_flag, 0) = 0
              AND rf.rdb$relation_name = ?
            ORDER BY rf.rdb$field_position
        """
        tablename = self.denormalize_name(table_name)
        c = list(connection.exec_driver_sql(columns_query, (tablename,)))

        cols = []
        for row in c:
            orig_colname = row.field_name
            colname = self.normalize_name(orig_colname)

            # Extract data type
            colclass = self.ischema_names.get(row.field_type)
            if colclass is None:
                util.warn(
                    "Unknown type '%s' in column '%s'. Check FBDialect.ischema_names."
                    % (row.field_type, colname)
                )
                coltype = sa_types.NULLTYPE
            elif issubclass(colclass, fb_types._FBString):
                if row.character_set_name == fb_types.BINARY_CHARSET:
                    if colclass == fb_types.FBCHAR:
                        colclass = fb_types.FBBINARY
                    elif colclass == fb_types.FBVARCHAR:
                        colclass = fb_types.FBVARBINARY
                if row.character_set_name == fb_types.NATIONAL_CHARSET:
                    if colclass == fb_types.FBCHAR:
                        colclass = fb_types.FBNCHAR
                    elif colclass == fb_types.FBVARCHAR:
                        colclass = fb_types.FBNVARCHAR

                coltype = colclass(
                    length=row.field_length,
                    charset=row.character_set_name,
                    collation=row.collation_name,
                )
            elif issubclass(colclass, fb_types._FBNumeric):
                # FLOAT, DOUBLE PRECISION or DECFLOAT
                coltype = colclass(row.field_precision)
            elif issubclass(colclass, fb_types._FBInteger):
                # NUMERIC / DECIMAL types are stored as INTEGER types
                if row.field_sub_type == 0:
                    # INTEGERs
                    coltype = colclass()
                elif row.field_sub_type == 1:
                    # NUMERIC
                    coltype = fb_types.FBNUMERIC(
                        precision=row.field_precision, scale=row.field_scale
                    )
                else:
                    # DECIMAL
                    coltype = fb_types.FBDECIMAL(
                        precision=row.field_precision, scale=row.field_scale
                    )
            elif issubclass(colclass, sa_types.DateTime):
                has_timezone = "WITH TIME ZONE" in row.field_type
                coltype = colclass(timezone=has_timezone)
            elif issubclass(colclass, fb_types._FBLargeBinary):
                if row.field_sub_type == 1:
                    coltype = fb_types.FBTEXT(
                        row.segment_length,
                        row.character_set_name,
                        row.collation_name,
                    )
                else:
                    coltype = fb_types.FBBLOB(row.segment_length)
            else:
                coltype = colclass()

            # Extract default value
            defvalue = None
            if row.default_source is not None:
                # the value comes down as "DEFAULT 'value'": there may be
                # more than one whitespace around the "DEFAULT" keyword
                # and it may also be lower case
                # (see also http://tracker.firebirdsql.org/browse/CORE-356)
                defexpr = row.default_source.lstrip()
                assert defexpr[:8].rstrip().upper() == "DEFAULT", (
                    "Unrecognized default value: %s" % defexpr
                )
                defvalue = defexpr[8:].strip()
                defvalue = defvalue if defvalue != "NULL" else None

            col_d = {
                "name": colname,
                "type": coltype,
                "nullable": not bool(row.null_flag),
                "default": defvalue,
            }

            if orig_colname.lower() == orig_colname:
                col_d["quote"] = True

            if row.computed_source is not None:
                col_d["computed"] = {"sqltext": row.computed_source}

            if row.description is not None:
                col_d["comment"] = row.description

            if row.identity_type is not None:
                col_d["identity"] = {
                    "always": row.identity_type == 0,
                    "start": row.initial_value,
                    "increment": row.generator_increment,
                }

                col_d["autoincrement"] = "identity" in col_d
            else:
                # For Firebird 2.5

                # A backend is better off not returning "autoincrement" at all,
                # instead of potentially returning "False" for an auto-incrementing
                # primary key column. (see test_autoincrement_col)
                pass

            cols.append(col_d)

        if cols:
            return cols

        if not self.has_table(connection, table_name, schema):
            raise exc.NoSuchTableError(table_name)

        return reflection.ReflectionDefaults.columns()

    @reflection.cache
    def get_pk_constraint(self, connection, table_name, schema=None, **kw):
        pk_query = """
            SELECT TRIM(rc.rdb$constraint_name) AS cname, TRIM(se.rdb$field_name) AS fname
            FROM rdb$relation_constraints rc
                 JOIN rdb$index_segments se
                   ON se.rdb$index_name = rc.rdb$index_name
            WHERE rc.rdb$constraint_type = 'PRIMARY KEY'
              AND rc.rdb$relation_name = ?
            ORDER BY se.rdb$field_position
        """
        tablename = self.denormalize_name(table_name)
        c = connection.exec_driver_sql(pk_query, (tablename,))

        rows = c.fetchall()
        pkfields = (
            [self.normalize_name(r.fname) for r in rows] if rows else None
        )
        if pkfields:
            return {
                "constrained_columns": pkfields,
                "name": self.normalize_name(rows[0].cname) if rows else None,
            }

        if not self.has_table(connection, table_name, schema):
            raise exc.NoSuchTableError(table_name)

        return reflection.ReflectionDefaults.pk_constraint()

    @reflection.cache
    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        fk_query = """
            SELECT TRIM(rc.rdb$constraint_name) AS cname,
                   TRIM(cse.rdb$field_name) AS fname,
                   TRIM(ix2.rdb$relation_name) AS targetrname,
                   TRIM(se.rdb$field_name) AS targetfname,
                   TRIM(rfc.rdb$update_rule) AS update_rule,
                   TRIM(rfc.rdb$delete_rule) AS delete_rule
            FROM rdb$relation_constraints rc
                 JOIN rdb$ref_constraints rfc 
                   ON rfc.rdb$constraint_name = rc.rdb$constraint_name
                 JOIN rdb$indices ix1 
                   ON ix1.rdb$index_name = rc.rdb$index_name
                 JOIN rdb$indices ix2 
                   ON ix2.rdb$index_name = ix1.rdb$foreign_key
                 JOIN rdb$index_segments cse 
                   ON cse.rdb$index_name = ix1.rdb$index_name
                 JOIN rdb$index_segments se 
                   ON se.rdb$index_name = ix2.rdb$index_name
                  AND se.rdb$field_position = cse.rdb$field_position
            WHERE rc.rdb$constraint_type = 'FOREIGN KEY'
              AND rc.rdb$relation_name = ?
            ORDER BY rc.rdb$constraint_name, se.rdb$field_position
        """
        tablename = self.denormalize_name(table_name)
        c = connection.exec_driver_sql(fk_query, (tablename,))

        fks = util.defaultdict(
            lambda: {
                "name": None,
                "constrained_columns": [],
                "referred_schema": None,
                "referred_table": None,
                "referred_columns": [],
                "options": {},
            }
        )

        for row in c:
            cname = self.normalize_name(row.cname)
            fk = fks[cname]
            if not fk["name"]:
                fk["name"] = cname
                fk["referred_table"] = self.normalize_name(row.targetrname)
            fk["constrained_columns"].append(self.normalize_name(row.fname))
            fk["referred_columns"].append(self.normalize_name(row.targetfname))
            if row.update_rule not in ["NO ACTION", "RESTRICT"]:
                fk["options"]["onupdate"] = row.update_rule
            if row.delete_rule not in ["NO ACTION", "RESTRICT"]:
                fk["options"]["ondelete"] = row.delete_rule

        result = list(fks.values())
        if result:
            return result

        if not self.has_table(connection, table_name, schema):
            raise exc.NoSuchTableError(table_name)

        return reflection.ReflectionDefaults.foreign_keys()

    @reflection.cache
    def get_indexes(self, connection, table_name, schema=None, **kw):
        def _indexes_query(condition_source_expr):
            return f"""
                SELECT TRIM(ix.rdb$index_name) AS index_name,
                       ix.rdb$unique_flag AS unique_flag,
                       ix.rdb$index_type AS descending_flag,
                       TRIM(ic.rdb$field_name) AS field_name,
                       TRIM(ix.rdb$expression_source) expression_source,
                       {condition_source_expr} condition_source
                FROM rdb$indices ix
                    LEFT OUTER JOIN rdb$index_segments ic
                      ON ic.rdb$index_name = ix.rdb$index_name
                    LEFT OUTER JOIN rdb$relation_constraints rc
                                 ON rc.rdb$index_name = ic.rdb$index_name
                WHERE ix.rdb$relation_name = :relation_name
                  AND ix.rdb$foreign_key IS NULL
                  AND COALESCE(rc.rdb$constraint_type, '') <> 'PRIMARY KEY'
                ORDER BY ix.rdb$index_name, ic.rdb$field_position
            """

        tablename = self.denormalize_name(table_name)

        has_condition_source = connection.exec_driver_sql(
            """
            SELECT 1
            FROM rdb$relation_fields
            WHERE rdb$relation_name = 'RDB$INDICES'
              AND rdb$field_name = 'RDB$CONDITION_SOURCE'
            """
        ).scalar()
        condition_source_expr = (
            "TRIM(ix.rdb$condition_source)"
            if has_condition_source
            else "CAST(NULL AS BLOB SUB_TYPE TEXT)"
        )

        # Do not use connection.exec_driver_sql() here.
        #    During tests we need to commit CREATE INDEX before this query. See provision.py listener.
        c = connection.execute(
            text(_indexes_query(condition_source_expr)),
            {"relation_name": tablename},
        )

        indexes = util.defaultdict(dict)
        for row in c:
            indexrec = indexes[row.index_name]
            if "name" not in indexrec:
                indexrec["name"] = self.normalize_name(row.index_name)
                indexrec["column_names"] = []
                indexrec["unique"] = bool(row.unique_flag)
                indexrec["dialect_options"] = {
                    "firebirdsql_descending": bool(row.descending_flag),
                    "firebirdsql_where": row.condition_source,
                }
                if row.expression_source is not None:
                    expr = row.expression_source[
                        1:-1
                    ]  # Remove outermost parenthesis added by Firebird
                    indexrec["expressions"] = expr.split(EXPRESSION_SEPARATOR)

            indexrec["column_names"].append(
                self.normalize_name(row.field_name)
            )

        def _get_column_set(tablename):
            colqry = """
                SELECT TRIM(r.rdb$field_name) AS fname
                FROM rdb$relation_fields r
                WHERE r.rdb$relation_name = ?
            """
            return {
                self.normalize_name(row.fname)
                for row in connection.exec_driver_sql(colqry, (tablename,))
            }

        def _adjust_column_names_for_expressions(result, tablename):
            # Identify which expression elements are columns
            colset = _get_column_set(tablename)
            for i in result:
                expr = i.get("expressions")
                if expr is not None:
                    i["column_names"] = [
                        x if self.normalize_name(x) in colset else None
                        for x in expr
                    ]
            return result

        result = list(indexes.values())
        if result:
            return _adjust_column_names_for_expressions(result, tablename)

        if not self.has_table(connection, table_name, schema):
            raise exc.NoSuchTableError(table_name)

        return reflection.ReflectionDefaults.indexes()

    @reflection.cache
    def get_unique_constraints(
        self, connection, table_name, schema=None, **kw
    ):
        unique_constraints_query = """
            SELECT TRIM(rc.rdb$constraint_name) AS cname,
                   TRIM(se.rdb$field_name) AS column_name
            FROM rdb$index_segments se
                 JOIN rdb$relation_constraints rc
                   ON rc.rdb$index_name = se.rdb$index_name
                 JOIN rdb$relations r
                   ON r.rdb$relation_name = rc.rdb$relation_name
                  AND COALESCE(r.rdb$system_flag, 0) = 0
            WHERE rc.rdb$constraint_type = 'UNIQUE'
              AND r.rdb$relation_name = ?
            ORDER BY rc.rdb$constraint_name, se.rdb$field_position
        """
        tablename = self.denormalize_name(table_name)
        c = connection.exec_driver_sql(unique_constraints_query, (tablename,))

        ucs = util.defaultdict(lambda: {"name": None, "column_names": []})

        for row in c:
            cname = self.normalize_name(row.cname)
            cc = ucs[cname]
            if not cc["name"]:
                cc["name"] = cname
            cc["column_names"].append(self.normalize_name(row.column_name))

        result = list(ucs.values())
        if result:
            return result

        if not self.has_table(connection, table_name, schema):
            raise exc.NoSuchTableError(table_name)

        return reflection.ReflectionDefaults.unique_constraints()

    @reflection.cache
    def get_table_comment(self, connection, table_name, schema=None, **kw):
        table_comment_query = """
            SELECT TRIM(rdb$description) AS comment
            FROM rdb$relations
            WHERE rdb$relation_name = ?
        """
        tablename = self.denormalize_name(table_name)
        c = connection.exec_driver_sql(table_comment_query, (tablename,))

        row = c.fetchone()
        if row:
            return {"text": row[0]}

        raise exc.NoSuchTableError(table_name)

    @reflection.cache
    def get_check_constraints(self, connection, table_name, schema=None, **kw):
        check_constraints_query = """
            SELECT TRIM(rc.rdb$constraint_name) AS cname,
                   TRIM(SUBSTRING(tr.rdb$trigger_source FROM 8 FOR CHAR_LENGTH(tr.rdb$trigger_source) - 8)) AS sqltext
            FROM rdb$relation_constraints rc
                 JOIN rdb$check_constraints ck
                   ON ck.rdb$constraint_name = rc.rdb$constraint_name
                 JOIN rdb$triggers tr
                   ON tr.rdb$trigger_name = ck.rdb$trigger_name AND
                      tr.rdb$trigger_type = 1 /* BEFORE INSERT */
            WHERE rc.rdb$constraint_type = 'CHECK' AND
                  rc.rdb$relation_name = ?
            ORDER BY 1
        """
        tablename = self.denormalize_name(table_name)
        c = connection.exec_driver_sql(check_constraints_query, (tablename,))

        ccs = util.defaultdict(
            lambda: {
                "name": None,
                "sqltext": None,
            }
        )

        for row in c:
            cname = self.normalize_name(row.cname)
            cc = ccs[cname]
            if not cc["name"]:
                cc["name"] = cname
                cc["sqltext"] = row.sqltext

        result = list(ccs.values())
        if result:
            return result

        if not self.has_table(connection, table_name, schema):
            raise exc.NoSuchTableError(table_name)

        return reflection.ReflectionDefaults.check_constraints()

    @reflection.cache
    def _load_domains(self, connection, schema=None, **kw):
        domains_query = """
            SELECT TRIM(f.rdb$field_name) AS fname,
                   f.rdb$null_flag AS null_flag,
                   NULLIF(TRIM(SUBSTRING(f.rdb$default_source FROM 8 FOR CHAR_LENGTH(f.rdb$default_source) - 7)), 'NULL') fdefault,
                   TRIM(SUBSTRING(f.rdb$validation_source FROM 8 FOR CHAR_LENGTH(f.rdb$validation_source) - 8)) fcheck,
                   TRIM(f.rdb$description) fcomment,
                   TRIM(t.rdb$type_name) AS field_type,
                   f.rdb$field_length AS field_length,
                   f.rdb$field_precision AS field_precision,
                   f.rdb$field_scale AS field_scale,
                   f.rdb$field_sub_type AS field_sub_type,
                   TRIM(cs.rdb$character_set_name) AS character_set_name
            FROM rdb$fields f
              JOIN rdb$types t
                ON t.rdb$type = f.rdb$field_type
               AND t.rdb$field_name = 'RDB$FIELD_TYPE'
              LEFT JOIN rdb$character_sets cs
                     ON cs.rdb$character_set_id = f.rdb$character_set_id
            WHERE COALESCE(f.rdb$system_flag, 0) = 0
              AND f.rdb$field_name NOT STARTING WITH 'RDB$'
            ORDER BY 1
        """
        result = connection.exec_driver_sql(domains_query)
        domains = []
        for row in result.mappings():
            # Build a SQLAlchemy type object for the domain's base type
            colclass = self.ischema_names.get(row["field_type"])
            coltype = None
            if colclass is not None:
                try:
                    if issubclass(colclass, fb_types._FBString):
                        coltype = colclass(
                            length=row["field_length"],
                            charset=row["character_set_name"],
                        )
                    elif issubclass(colclass, fb_types._FBNumeric):
                        coltype = colclass(row["field_precision"])
                    elif issubclass(colclass, fb_types._FBInteger):
                        sub = row["field_sub_type"] or 0
                        if sub == 1:
                            coltype = fb_types.FBNUMERIC(
                                precision=row["field_precision"],
                                scale=row["field_scale"],
                            )
                        elif sub == 2:
                            coltype = fb_types.FBDECIMAL(
                                precision=row["field_precision"],
                                scale=row["field_scale"],
                            )
                        else:
                            coltype = colclass()
                    else:
                        coltype = colclass()
                except Exception:
                    coltype = sa_types.NULLTYPE
            domains.append(
                {
                    "name": self.normalize_name(row["fname"]),
                    "nullable": not bool(row["null_flag"]),
                    "default": row["fdefault"],
                    "check": row["fcheck"],
                    "comment": row["fcomment"],
                    "type": coltype,
                }
            )
        return domains

    @reflection.cache
    def _get_stored_procedure_names(self, connection, schema=None, **kw):
        query = """
            SELECT TRIM(rdb$procedure_name) AS procedure_name
            FROM rdb$procedures
            WHERE COALESCE(rdb$system_flag, 0) = 0
            ORDER BY rdb$procedure_name
        """
        return [
            self.normalize_name(row.procedure_name)
            for row in connection.exec_driver_sql(query)
        ]

    @reflection.cache
    def _get_stored_procedure_definition(
        self, connection, procedure_name, schema=None, **kw
    ):
        query = """
            SELECT rdb$procedure_source AS proc_source
            FROM rdb$procedures
            WHERE rdb$procedure_name = ?
        """
        procname = self.denormalize_name(procedure_name)
        row = connection.exec_driver_sql(query, (procname,)).fetchone()
        if row:
            return row.proc_source

        raise exc.NoSuchTableError(procedure_name)

    def is_disconnect(self, e, connection, cursor):
        if connection is None or isinstance(e, self.dbapi.OperationalError):
            return True

        if isinstance(e, (self.dbapi.DatabaseError)):
            return e.sql_code == -902 and e.gds_codes & set([
                335544726,  # net_read_err     Error reading data from the connection
                335544727,  # net_write_err    Error writing data to the connection
                335544721,  # network_error    Unable to complete network request to host "@1"
                335544856,  # att_shutdown     Connection shutdown
            ])

        return False
