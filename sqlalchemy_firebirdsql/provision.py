from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateTable, DropTable, CreateIndex, DropIndex
from sqlalchemy.testing.provision import temp_table_keyword_args


@temp_table_keyword_args.for_db("firebirdsql")
def _firebird_temp_table_keyword_args(cfg, eng):
    return {
        "prefixes": ["GLOBAL TEMPORARY"],
        "firebirdsql_on_commit": "PRESERVE ROWS",
    }


@event.listens_for(Engine, "before_execute")
def receive_before_execute(connection, statement, *arg):
    if isinstance(statement, DropTable):
        pass
        #dbapi_conn = connection.connection.dbapi_connection
        #dbapi_conn.execute_immediate("""
        #    DELETE FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID <> CURRENT_CONNECTION
        #""")


@event.listens_for(Engine, "after_execute")
def receive_after_execute(connection, statement, *arg):
    #
    # Important: Statements executed with connection.exec_driver_sql() don't pass through here.
    #            Use connection.execute(text()) instead.
    #
    if isinstance(statement, (CreateTable, DropTable, CreateIndex, DropIndex)):
        # Using Connection protected methods here because the public ones cause errors with TransactionManager
        connection._commit_impl()
        # Don't start a new transaction after DropTable: doing so can keep
        # the table locked and cause "object in use" errors during teardown.
        if not isinstance(statement, DropTable):
            connection._begin_impl(connection._transaction)
