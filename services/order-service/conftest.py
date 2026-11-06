"""Shared test setup for order-service.

order-service is different from the two workers: app.py is a Flask web app, and
importing it has side effects (it creates the table and starts the Redis consumer
thread). So `app_module` imports it ONCE with the database, Redis and the consumer
thread replaced by fakes. Nothing real is ever contacted.

Run tests from INSIDE this folder:  cd services/order-service && python -m pytest
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


@pytest.fixture(scope="session")
def app_module():
    """Import app.py once, with DB / Redis / consumer thread faked."""
    import db
    import events

    with patch.object(events, "get_redis", lambda: MagicMock()), \
         patch.object(events, "consume", lambda *a, **k: None), \
         patch.object(db, "get_conn", lambda: FakeConn([], [])):
        import app
    return app


@pytest.fixture
def run_app(app_module, monkeypatch):
    """Returns (app_module, calls).

    `fetch_results` = rows the fake DB returns, in order, for cursor.fetchone().
    `calls` records every SQL execute, commit, publish, log and wake in order.
    """
    def _setup(fetch_results=()):
        calls = []
        monkeypatch.setattr(app_module.db, "get_conn",
                            lambda: FakeConn(list(fetch_results), calls))
        monkeypatch.setattr(
            app_module.events, "publish",
            lambda r, stream, event_type, payload:
            calls.append(("publish", stream, event_type, payload)))
        monkeypatch.setattr(app_module.events, "log",
                            lambda message: calls.append(("log", message)))
        monkeypatch.setattr(app_module, "wake_services",
                            lambda: calls.append(("wake",)))
        return app_module, calls

    return _setup


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()
