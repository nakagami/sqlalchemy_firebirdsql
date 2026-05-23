============================
sqlalchemy-firebirdsql
============================

`SQLAlchemy <https://www.sqlalchemy.org/>`_ dialect
for `Firebird <https://firebirdsql.org/en/start/>`_
using `pyfirebirdsql <https://github.com/nakagami/pyfirebirdsql>`_ .

It based on `sqlalchemy-firebird <https://github.com/pauldex/sqlalchemy-firebird>`_ , thanks.

Requirements
++++++++++++++++

It is difficult to support many versions, so I target newer versions.

- Firebird 4.0+
- SQLAlchemy 2.0+
- Python 3.10+

Installation
++++++++++++++++

::

   pip install sqlalchemy_firebirdsql

Connection strings
+++++++++++++++++++

A SQLAlchemy URL has the shape ``dialect+driver://username:password@host:port/database``.
For this dialect:

::

   firebirdsql+syn://user:password@host:port/path/to/db[?key=value&key=value...]

For async:

::

   firebirdsql+asyn://user:password@host:port/path/to/db[?key=value&key=value...]

The bare ``firebirdsql://`` scheme defaults to the synchronous (``syn``) driver.

Examples
--------

Local server, default port::

   firebirdsql+syn://sysdba:masterkey@localhost//home/me/databases/my_project.fdb

Remote server on port 3050::

   firebirdsql+syn://sysdba:masterkey@example.com:3050//srv/databases/my_project.fdb

Usage
++++++++++++++++

Synchronous
-----------

.. code-block:: python

   from sqlalchemy import create_engine, text

   engine = create_engine(
       "firebirdsql+syn://sysdba:masterkey@localhost//home/me/databases/my_project.fdb",
       echo=True,
   )

   with engine.connect() as conn:
       result = conn.execute(text("select 1 from rdb$database"))
       print(result.scalar())

Asynchronous
------------

.. code-block:: python

   import asyncio
   from sqlalchemy import text
   from sqlalchemy.ext.asyncio import create_async_engine

   engine = create_async_engine(
       "firebirdsql+asyn://sysdba:masterkey@localhost//home/me/databases/my_project.fdb",
       echo=True,
   )

   async def main():
       async with engine.connect() as conn:
           result = await conn.execute(text("select 1 from rdb$database"))
           print(result.scalar())

   asyncio.run(main())

How to test
++++++++++++++++

Clone and install
--------------------

::

   git clone git@github.com:nakagami/sqlalchemy_firebirdsql.git
   cd sqlalchemy_firebirdsql
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -e .
   pip install pytest

Create test database and execute pytest
-------------------------------------------

::

   prepare-test-environment
   pytest --db syn
   pytest --db asyn

