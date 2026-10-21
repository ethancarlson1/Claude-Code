import os

import pytest

from backline import ai_import, create_app, mailer
from backline import db as dbm
from backline import quickbooks


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never talk to Intuit, Anthropic or a mail server. Tests of those
    swap in fakes."""

    def refuse(method, url, *_args, **_kwargs):
        raise AssertionError(f"unexpected network call: {method} {url}")

    def refuse_ai(*_args, **_kwargs):
        raise AssertionError("unexpected call to Anthropic")

    monkeypatch.setattr(quickbooks, "_send", refuse)
    monkeypatch.setattr(ai_import, "_send", refuse_ai)
    monkeypatch.setattr(ai_import, "_check", refuse_ai)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(mailer, "_deliver", lambda msg, _config: refuse("SMTP", msg["To"]))
    for name in ("BACKLINE_SMTP_HOST", "BACKLINE_SMTP_PORT", "BACKLINE_SMTP_USERNAME", "BACKLINE_SMTP_PASSWORD",
                 "BACKLINE_MAIL_FROM"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": os.path.join(tmp_path, "test.sqlite3"),
        "UPLOAD_FOLDER": os.path.join(tmp_path, "uploads"),
        "SECRET_KEY": "test",
        "CSRF_ENABLED": False,
    })
    yield app


@pytest.fixture
def anon(app):
    return app.test_client()


@pytest.fixture
def client(app):
    c = app.test_client()
    resp = c.post("/setup", data={"username": "admin", "password": "password123", "company_name": "Chicago Sound and Backline"})
    assert resp.status_code == 302
    return c


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


@pytest.fixture
def make(app):
    """Insert rows directly: make('clients', name='X') -> id."""

    def _make(table, **values):
        with app.app_context():
            if table == "event_crew":
                values.setdefault("worksheet_key", f"key{values['crew_id']}{values['event_id']}")
            if table == "events":
                values.setdefault("reference_number", f"{values['event_date']}-REF-{values.get('title', 'x')[:4]}")
                values.setdefault("title", "Test event")
            return dbm.insert(table, values)

    return _make


def query(app, sql, args=(), one=False):
    with app.app_context():
        rows = dbm.query(sql, args, one=one)
        if one:
            return dict(rows) if rows else None
        return [dict(r) for r in rows]
