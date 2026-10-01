"""Demo mode (BACKLINE_DEMO=1): the free showcase site."""

import io
import os

import pytest

from backline import create_app
from backline import db as dbm

from .conftest import query


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKLINE_DEMO", "1")
    monkeypatch.delenv("BACKLINE_MAX_UPLOAD_MB", raising=False)
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "demo.sqlite3"),
                       "UPLOAD_FOLDER": str(tmp_path / "uploads"), "SECRET_KEY": "k", "CSRF_ENABLED": False})


@pytest.fixture
def visitor(demo_app):
    c = demo_app.test_client()
    resp = c.post("/demo/enter")
    assert resp.status_code == 302 and resp.headers["Location"] == "/"
    return c


def _count(app, table):
    return query(app, f"SELECT COUNT(*) AS n FROM {table}", one=True)["n"]


def test_demo_starts_with_sample_data_and_one_click_entry(demo_app):
    assert _count(demo_app, "events") > 5 and _count(demo_app, "client_requests") == 2
    assert [u["username"] for u in query(demo_app, "SELECT username FROM users")] == ["demo"]
    c = demo_app.test_client()
    assert c.get("/setup").headers["Location"] == "/login"
    page = c.get("/login").data.decode()
    assert "Explore the demo" in page and 'name="password"' not in page
    assert '<meta name="robots" content="noindex, nofollow">' in page and "made-up people" in page
    dashboard = demo_app.test_client()
    dashboard.post("/demo/enter")
    page = dashboard.get("/").data.decode()
    assert "Upcoming events" in page and "Start over" in page
    assert demo_app.config["MAX_CONTENT_LENGTH"] == 5 * 1024 * 1024


def test_public_pages_say_its_a_demo(demo_app):
    page = demo_app.test_client().get("/request").data.decode()
    assert "made-up people" in page and "noindex" in page


def test_visitors_can_try_the_real_features(visitor, demo_app):
    resp = visitor.post("/events/new", data={"title": "Visitor test gig", "status": "hold",
                                             "event_date": "2030-05-05"})
    assert resp.status_code == 302
    assert query(demo_app, "SELECT title FROM events WHERE title = 'Visitor test gig'", one=True)
    assert visitor.get("/requests").status_code == 200 and visitor.get("/requests/1/convert").status_code == 200
    assert visitor.get("/settings/quickbooks").status_code == 200  # can look, can't connect


@pytest.mark.parametrize("url, data", [
    ("/settings", {"company_name": "Defaced", "contract_template": "x"}),
    ("/settings/users", {"action": "add", "username": "intruder", "password": "password123"}),
    ("/settings/users", {"action": "password", "current_password": "x", "new_password": "lockedout1"}),
    ("/settings/quickbooks", {"action": "keys", "environment": "sandbox", "client_id": "x", "client_secret": "y"}),
    ("/settings/quickbooks/connect", {}),
    ("/requests/form", {"enabled": "0"}),
    ("/settings/backup/restore", {"confirm": "1"}),
])
def test_some_changes_are_turned_off(visitor, demo_app, url, data):
    before = {t: _count(demo_app, t) for t in ("users", "settings")}
    with demo_app.app_context():
        company, form_on = dbm.get_setting("company_name"), dbm.get_setting("request_form_enabled")
    resp = visitor.post(url, data=data, follow_redirects=True)
    assert b"turned off in the demo" in resp.data
    assert {t: _count(demo_app, t) for t in ("users", "settings")} == before
    with demo_app.app_context():
        assert (dbm.get_setting("company_name"), dbm.get_setting("request_form_enabled")) == (company, form_on)
        assert not dbm.get_setting("qbo_client_id")


def test_start_over_puts_the_sample_data_back(visitor, demo_app):
    events = _count(demo_app, "events")
    visitor.post("/events/new", data={"title": "Scribble", "status": "hold", "event_date": "2030-05-05"})
    with demo_app.app_context():
        dbm.execute("DELETE FROM clients")
    stray = os.path.join(demo_app.config["UPLOAD_FOLDER"], "stray.pdf")
    with open(stray, "wb") as fh:
        fh.write(b"x")
    resp = visitor.post("/demo/reset", follow_redirects=True)
    assert b"back to its starting point" in resp.data and b"Upcoming events" in resp.data  # still in
    assert _count(demo_app, "events") == events and _count(demo_app, "clients") > 0
    assert not query(demo_app, "SELECT 1 FROM events WHERE title = 'Scribble'")
    assert not os.path.exists(stray)
    stored = query(demo_app, "SELECT stored_name FROM event_files LIMIT 1", one=True)["stored_name"]
    assert os.path.exists(os.path.join(demo_app.config["UPLOAD_FOLDER"], stored))  # sample documents are back


def test_start_over_needs_a_visitor(demo_app):
    assert demo_app.test_client().post("/demo/reset").headers["Location"] == "/login"


def test_uploads_are_small_in_the_demo(visitor, demo_app):
    big = io.BytesIO(b"x" * (6 * 1024 * 1024))
    resp = visitor.post("/events/1/files", data={"files": (big, "huge.pdf")}, content_type="multipart/form-data",
                        follow_redirects=True)
    assert b"The limit is 5 MB" in resp.data


def test_demo_routes_dont_exist_on_the_real_platform(anon, client):
    assert anon.post("/demo/enter").status_code == 404
    assert client.post("/demo/reset").status_code == 404
    page = client.get("/").data.decode()
    assert "made-up people" not in page and "noindex" not in page
    assert 'name="password"' in anon.get("/login").data.decode()
