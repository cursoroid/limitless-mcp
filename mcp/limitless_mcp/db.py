import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://limitless:limitless@localhost:5432/erp")


def query(sql: str, params: tuple | dict = ()) -> list[dict]:
    # New connection per call so a dead db doesn't take the server down.
    # Fine at this scale, switch to psycopg_pool if load grows.
    with psycopg.connect(DATABASE_URL, connect_timeout=3, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()
