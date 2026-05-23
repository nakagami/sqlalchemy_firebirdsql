# sqlalchemy_firebirdsql/__init__.py
# Copyright (C) 2005-2025 the SQLAlchemy authors and contributors
# <see AUTHORS file>
#
# This module is released under the MIT License: http://www.opensource.org/licenses/mit-license.php
from .ext import not_similar_to
from .ext import similar_to
from .merge import merge

__version__ = "0.1.0"

__all__ = ["merge", "not_similar_to", "similar_to", "__version__"]
