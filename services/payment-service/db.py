"""Postgres helper. Each service has its own DATABASE_URL (database per service)."""
import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor


@contextmanager
def get_conn():
    """Short-lived connection: commits on success, rolls back on error.

    A fresh connection per operation is slower but robust with serverless
    Postgres (e.g. Neon), which closes idle connections.
    """
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10,
                            cursor_factory=RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
