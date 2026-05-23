"""Firebird-specific SQL extensions."""

from sqlalchemy import String
from sqlalchemy import literal


def similar_to(col, pattern):
    """Create a Firebird SIMILAR TO expression."""
    return col.op("SIMILAR TO")(literal(pattern, String(len(pattern))))


def not_similar_to(col, pattern):
    """Create a Firebird NOT SIMILAR TO expression."""
    return col.op("NOT SIMILAR TO")(literal(pattern, String(len(pattern))))
