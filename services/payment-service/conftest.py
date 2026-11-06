"""Shared test setup for payment-service.

- Puts the service folder on sys.path so `import worker`, `import events`
  and `import db` work (the services use flat, top-level modules).
- Provides a fake Postgres connection so worker.py handlers can be tested
  with no database and no Redis.

Run tests from INSIDE this folder:  cd services/payment-service && python -m pytest
(Every service has its own worker.py / events.py, so never run pytest from the repo root.)
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


class FakeCursor:
    def __init__(self, fetch_results, calls):
        self._fetch = list(fetch_results)
        self._calls = calls

    def execute(self, sql, params=None):
        # collapse whitespace so tests can match on the start of the statement
        self._calls.append(("execute", " ".join(sql.split()), params))

    def fetchone(self):
        return self._fetch.pop(0) if self._fetch else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    """Mimics db.get_conn(): commits on clean exit, rolls back on error."""

    def __init__(self, fetch_results, calls):
        self._cur = FakeCursor(fetch_results, calls)
        self._calls = calls

    def cursor(self):
        return self._cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._calls.append(("commit",) if exc_type is None else ("rollback",))
        return False


@pytest.fixture
def run_worker(monkeypatch):
    """Returns (worker_module, calls).

    `fetch_results` is the list of rows the fake DB returns, in order, for each
    cursor.fetchone() call. `calls` records every SQL execute, commit, publish
    and log in the order they happen.
    """
    import worker

    def _setup(fetch_results):
        calls = []
        monkeypatch.setattr(worker.db, "get_conn",
                            lambda: FakeConn(fetch_results, calls))
        monkeypatch.setattr(
            worker.events, "publish",
            lambda r, stream, event_type, payload:
            calls.append(("publish", stream, event_type, payload)))
        monkeypatch.setattr(worker.events, "log",
                            lambda message: calls.append(("log", message)))
        return worker, calls

    return _setup
