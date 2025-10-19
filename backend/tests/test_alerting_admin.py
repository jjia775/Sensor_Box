import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import alerting


@pytest.fixture(autouse=True)
def reload_alerting():
    """Ensure a fresh view of the alerting module for each test."""

    importlib.reload(alerting)
    yield
    importlib.reload(alerting)


def test_get_admin_recipients_prefers_dedicated_admin_addresses(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin1@example.com, admin2@example.com")
    monkeypatch.setenv("SMTP_TO", "general@example.com")

    assert alerting.get_admin_recipients() == [
        "admin1@example.com",
        "admin2@example.com",
    ]


def test_get_admin_recipients_falls_back_to_smtp_recipients(monkeypatch):
    for env_var in ("ADMIN_EMAILS", "ADMIN_EMAIL", "SMTP_ADMIN_TO"):
        monkeypatch.delenv(env_var, raising=False)

    monkeypatch.setenv("SMTP_TO", "general@example.com, second@example.com")

    assert alerting.get_admin_recipients() == [
        "general@example.com",
        "second@example.com",
    ]
