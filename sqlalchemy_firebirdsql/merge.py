from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.expression import ClauseElement
from sqlalchemy.sql.visitors import InternalTraversal


class MergeInto(Executable, ClauseElement):
    """Firebird MERGE INTO construct for upsert operations."""

    __visit_name__ = "merge_into"
    inherit_cache = True
    _traverse_internals = [
        ("target", InternalTraversal.dp_clauseelement),
        ("_source", InternalTraversal.dp_clauseelement),
        ("_on_clause", InternalTraversal.dp_clauseelement),
        ("_when_matched_update", InternalTraversal.dp_clauseelement_tuples),
        ("_when_not_matched_insert_cols", InternalTraversal.dp_clauseelement_tuple),
        ("_when_not_matched_insert_values", InternalTraversal.dp_clauseelement_tuple),
    ]

    def __init__(self, target):
        self.target = target
        self._source = None
        self._on_clause = None
        self._when_matched_update = None
        self._when_not_matched_insert_cols = None
        self._when_not_matched_insert_values = None

    def using(self, source, on_clause):
        self._source = source
        self._on_clause = on_clause
        return self

    def when_matched_then_update(self, update_values):
        self._when_matched_update = tuple(update_values.items())
        return self

    def when_not_matched_then_insert(self, cols, values):
        self._when_not_matched_insert_cols = tuple(cols)
        self._when_not_matched_insert_values = tuple(values)
        return self


def merge(target):
    """Create a MERGE INTO statement targeting the given table."""
    return MergeInto(target)
