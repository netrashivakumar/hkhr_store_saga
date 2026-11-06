"""Shared test setup for notification-worker.

notification-worker has no database, so the only thing to fake is the log:
the `logged` fixture captures every message the worker "sends".

Run tests from INSIDE this folder:  cd services/notification-worker && python -m pytest
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def logged(monkeypatch):
    """List of every message passed to events.log by the worker."""
    import worker

    messages = []
    monkeypatch.setattr(worker.events, "log", messages.append)
    return messages
