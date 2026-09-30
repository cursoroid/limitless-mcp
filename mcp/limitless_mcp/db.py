import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://limitless:limitless@localhost:5432/erp")


def query(sql: str, params: tuple | dict = ()) -> list[dict]:
    """Run one query on a fresh connection; the server stays up while the DB is down."""
    # ponytail: connect per call; pool (psycopg_pool) if concurrent load matters
    with psycopg.connect(DATABASE_URL, connect_timeout=3, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()
