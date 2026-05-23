import pytest

# Register assert rewrite BEFORE any other imports
pytest.register_assert_rewrite("sqlalchemy.testing.assertions")

from sqlalchemy.dialects import registry

# setup default dialect for sqlalchemy
# ベースとなる "firebirdsql" の登録を追加
registry.register(
    "firebirdsql", "sqlalchemy_firebirdsql.syn", "FBDialect_syn"
)
registry.register(
    "firebirdsql.syn", "sqlalchemy_firebirdsql.syn", "FBDialect_syn"
)
registry.register(
    "firebirdsql.asyn", "sqlalchemy_firebirdsql.asyn", "FBDialect_asyn"
)

import sqlalchemy_firebirdsql.provision # noqa

from sqlalchemy.testing.plugin.pytestplugin import *  # noqa: F401, E402, F403
