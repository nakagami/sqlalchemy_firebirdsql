import firebirdsql

def prepare_test_environment(force=True):
    firebirdsql.create_database(
        host="localhost",
        user="sysdba",
        password="masterkey",
        database="/tmp/test_firebirdsql_syn.fdb",
    ).close()
    firebirdsql.create_database(
        host="localhost",
        user="sysdba",
        password="masterkey",
        database="/tmp/test_firebirdsql_asyn.fdb",
    ).close()
