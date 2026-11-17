"""A read-only connection to the Muse warehouse for the Grid Phase 0 scripts.

Every statement these scripts send is a SELECT. The connection is still made read-only three ways, so a mistake
cannot write: psycopg's `read_only` flag (every transaction begins READ ONLY), the session default
`default_transaction_read_only`, and a check after connecting that the server agrees.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from owcsmuse.config import Settings


def connect_readonly() -> psycopg.Connection:
    """One connection, search_path pinned as Muse pins it, unable to write."""
    settings = Settings()
    schema = settings.db_schema
    if not schema.replace("_", "").isalnum():
        raise ValueError(f"invalid schema name: {schema!r}")
    conn = psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=15)
    conn.read_only = True
    conn.execute("SET default_transaction_read_only = on")
    conn.execute(f"SET search_path TO {schema}")
    conn.execute("SET statement_timeout = '120s'")
    state = conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"]
    if state != "on":
        conn.close()
        raise RuntimeError("the transaction is not read-only; refusing to continue")
    conn.commit()
    return conn
