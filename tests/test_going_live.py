"""Running on a public server (Render): health checks, https behind the proxy,
the setup code, sign-in lockout, password resets, and backups."""

import io
import os
import sqlite3
import zipfile

import pytest

from backline import create_app
from backline import db as dbm

from .conftest import query

ROOT = os.path.dirname(os.path.dirname(__file__))


def _new_app(tmp_path, name, **config):
    folder = tmp_path / name
    folder.mkdir()
    return create_app({"TESTING": True, "DATABASE": str(folder / "db.sqlite3"), "UPLOAD_FOLDER": str(folder / "uploads"),
                       "SECRET_KEY": "k", "CSRF_ENABLED": False, **config})


def _setup(app, username="admin", password="password123", **extra):
    c = app.test_client()
    resp = c.post("/setup", data={"username": username, "password": password, **extra})
    return c, resp


# --- Hosting ----------------------------------------------------------------------

def test_health_check_is_public(anon):
    resp = anon.get("/healthz")
    assert (resp.status_code, resp.data) == (200, b"ok")


def test_render_blueprint_matches_the_app():
    blueprint = open(os.path.join(ROOT, "render.yaml")).read()
    for text in ("runtime: python", "plan: starter", "--call backline:create_app", "--port=$PORT", "--host=0.0.0.0",
                 "--no-clear-untrusted-proxy-headers",
                 "healthCheckPath: /healthz", "mountPath: /var/data", "value: /var/data/backline.sqlite3",
                 "value: /var/data/uploads", "key: BACKLINE_BEHIND_PROXY", "key: BACKLINE_SECRET_KEY",
                 "key: BACKLINE_SETUP_CODE", "generateValue: true"):
        assert text in blueprint, text
    assert "waitress" in open(os.path.join(ROOT, "requirements.txt")).read()
    assert open(os.path.join(ROOT, ".python-version")).read().strip() == "3.12"


def test_links_use_https_behind_the_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKLINE_BEHIND_PROXY", "1")
    app = _new_app(tmp_path, "live")
    c = app.test_client()
    headers = {"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.9", "X-Forwarded-Host": "ops.example.com"}
    resp = c.post("/setup", data={"username": "admin", "password": "password123"}, headers=headers)
    assert "Secure" in resp.headers["Set-Cookie"]
    page = c.get("/requests", headers=headers).data.decode()
    assert "https://ops.example.com/request" in page
    c.post("/request", data={"name": "A", "phone": "1"}, headers=headers)
    assert query(app, "SELECT ip FROM client_requests", one=True)["ip"] == "203.0.113.9"


# --- The first account ------------------------------------------------------------

def test_setup_code_protects_the_first_account(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKLINE_SETUP_CODE", "s3cret-code")
    app = _new_app(tmp_path, "coded")
    assert "Setup code" in app.test_client().get("/setup").data.decode()
    _c, resp = _setup(app, setup_code="guess")
    assert resp.status_code == 200 and b"setup code doesn" in resp.data
    assert query(app, "SELECT COUNT(*) AS n FROM users", one=True)["n"] == 0
    _c, resp = _setup(app, setup_code=" s3cret-code ")
    assert resp.status_code == 302 and query(app, "SELECT username FROM users", one=True)["username"] == "admin"


def test_no_setup_code_needed_on_your_own_computer(anon):
    assert "Setup code" not in anon.get("/setup").data.decode()


# --- Signing in --------------------------------------------------------------------

def _login(app, password, username="admin", ip="198.51.100.7"):
    return app.test_client().post("/login", data={"username": username, "password": password},
                                  environ_base={"REMOTE_ADDR": ip})


def test_repeated_wrong_passwords_lock_sign_in(client, app):
    for _ in range(5):
        assert b"Incorrect username or password" in _login(app, "wrong-password").data
    resp = _login(app, "password123")  # even the right password waits now
    assert resp.status_code == 429 and b"Too many wrong passwords" in resp.data
    assert _login(app, "password123", ip="192.0.2.44").status_code == 302  # a different network isn't blocked
    with app.app_context():
        dbm.execute("UPDATE login_failures SET at = '2000-01-01T00:00:00'")
    assert _login(app, "password123").status_code == 302  # the lock expires


def test_one_network_guessing_many_usernames_is_locked(client, app):
    for n in range(20):
        _login(app, "nope", username=f"user{n}")
    assert _login(app, "password123").status_code == 429


def test_signing_in_clears_earlier_mistakes(client, app):
    for _ in range(4):
        _login(app, "wrong-password")
    assert _login(app, "password123").status_code == 302
    for _ in range(4):
        _login(app, "wrong-password")
    assert _login(app, "password123").status_code == 302


# --- Forgotten passwords -------------------------------------------------------------

def test_admin_can_set_another_users_password(client, app):
    client.post("/settings/users", data={"action": "add", "username": "dana", "password": "firstpass1"})
    dana = query(app, "SELECT id FROM users WHERE username = 'dana'", one=True)["id"]
    page = client.get("/settings/users").data.decode()
    assert "Set password" in page
    resp = client.post("/settings/users", data={"action": "reset", "user_id": dana, "new_password": "short"},
                       follow_redirects=True)
    assert b"at least 8 characters" in resp.data
    resp = client.post("/settings/users", data={"action": "reset", "user_id": dana, "new_password": "brandnew99"},
                       follow_redirects=True)
    assert b"Set a new password for dana" in resp.data
    assert _login(app, "brandnew99", username="dana").status_code == 302
    me = query(app, "SELECT id FROM users WHERE username = 'admin'", one=True)["id"]
    assert client.post("/settings/users", data={"action": "reset", "user_id": me,
                                                "new_password": "whatever99"}).status_code == 400


def test_reset_password_command(client, app):
    for _ in range(5):
        _login(app, "wrong-password")
    result = app.test_cli_runner().invoke(args=["reset-password", "admin"], input="fresh-pass-1\nfresh-pass-1\n")
    assert "Set a new password for admin." in result.output
    assert _login(app, "fresh-pass-1").status_code == 302  # the lockout is cleared too
    result = app.test_cli_runner().invoke(args=["reset-password", "nobody"], input="fresh-pass-1\nfresh-pass-1\n")
    assert result.exit_code != 0 and "no user called nobody" in result.output


# --- Backups -------------------------------------------------------------------------

@pytest.fixture
def backup_zip(client, app, make):
    """A backup of a platform with a client, an event and an uploaded document."""
    cl = make("clients", name="Sofia Alvarez")
    event = make("events", title="Alvarez Wedding", event_date="2030-06-01", client_id=cl)
    client.post(f"/events/{event}/files", data={"files": (io.BytesIO(b"%PDF plot"), "plot.pdf"), "category": "Stage plot"},
                content_type="multipart/form-data")
    with app.app_context():
        dbm.set_setting("qbo_refresh_token", "laptop-token")
        dbm.set_setting("qbo_realm_id", "9130")
    resp = client.get("/settings/backup/download")
    data = resp.data
    resp.close()
    assert resp.status_code == 200 and resp.mimetype == "application/zip"
    assert "chicago-sound-and-backline-backup-" in resp.headers["Content-Disposition"]
    return data


def test_backup_has_the_database_and_files(app, backup_zip):
    zf = zipfile.ZipFile(io.BytesIO(backup_zip))
    names = zf.namelist()
    stored = query(app, "SELECT stored_name FROM event_files", one=True)["stored_name"]
    assert "backline.sqlite3" in names and f"uploads/{stored}" in names and "README.txt" in names
    assert zf.read(f"uploads/{stored}") == b"%PDF plot"
    assert "events: 1" in zf.read("README.txt").decode()


def test_restore_onto_a_new_empty_platform(tmp_path, backup_zip):
    live = _new_app(tmp_path, "render")
    c, _resp = _setup(live, username="temporary", password="password123")
    page = c.get("/settings/backup").data.decode()
    assert "Restore backup" in page
    resp = c.post("/settings/backup/restore", data={"backup": (io.BytesIO(backup_zip), "backup.zip"), "confirm": "1"},
                  content_type="multipart/form-data", follow_redirects=True)
    assert b"Backup restored, with 1 uploaded file" in resp.data and b"Sign in" in resp.data
    assert c.get("/").status_code == 302  # signed out: the accounts came from the backup
    assert query(live, "SELECT title FROM events", one=True)["title"] == "Alvarez Wedding"
    assert [u["username"] for u in query(live, "SELECT username FROM users")] == ["admin"]
    stored = query(live, "SELECT stored_name FROM event_files", one=True)["stored_name"]
    assert open(os.path.join(live.config["UPLOAD_FOLDER"], stored), "rb").read() == b"%PDF plot"
    with live.app_context():
        assert dbm.get_setting("qbo_refresh_token") == ""  # reconnect QuickBooks on the new copy
    assert _login(live, "password123").status_code == 302


def test_restore_never_overwrites_live_data(client, app, backup_zip):
    page = client.get("/settings/backup").data.decode()
    assert "already has bookings" in page and "Restore backup" not in page
    resp = client.post("/settings/backup/restore", data={"backup": (io.BytesIO(backup_zip), "b.zip"), "confirm": "1"},
                       content_type="multipart/form-data", follow_redirects=True)
    assert b"already has bookings" in resp.data
    assert query(app, "SELECT COUNT(*) AS n FROM events", one=True)["n"] == 1


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_restore_rejects_files_that_arent_backups(tmp_path):
    live = _new_app(tmp_path, "render")
    c, _resp = _setup(live)
    for data, message in ((b"not a zip", b"isn"), (_zip({"notes.txt": "hi"}), b"doesn"),
                          (_zip({"backline.sqlite3": b"garbage" * 100}), b"damaged")):
        resp = c.post("/settings/backup/restore", data={"backup": (io.BytesIO(data), "x.zip"), "confirm": "1"},
                      content_type="multipart/form-data", follow_redirects=True)
        assert message in resp.data, message
    resp = c.post("/settings/backup/restore", data={"backup": (io.BytesIO(b"x"), "x.zip")},
                  content_type="multipart/form-data", follow_redirects=True)
    assert b"Tick the box" in resp.data
    assert [u["username"] for u in query(live, "SELECT username FROM users")] == ["admin"]


def test_restore_upgrades_an_old_backup_and_ignores_unsafe_paths(tmp_path):
    old = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(old)
    conn.executescript(open(os.path.join(ROOT, "tests", "fixtures", "schema_v1.sql")).read())
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('owner', 'x')")
    conn.execute("INSERT INTO events (reference_number, title, event_date) VALUES ('R1', 'Old gig', '2030-01-01')")
    conn.commit()
    conn.close()
    data = _zip({"backline.sqlite3": old.read_bytes(), "uploads/ok.pdf": b"%PDF", "uploads/../escape.txt": b"x",
                 "../outside.txt": b"x", "uploads/.hidden": b"x"})
    live = _new_app(tmp_path, "render", MAX_CONTENT_LENGTH=100)  # restores may be bigger than normal uploads
    c, _resp = _setup(live)
    resp = c.post("/settings/backup/restore", data={"backup": (io.BytesIO(data), "b.zip"), "confirm": "1"},
                  content_type="multipart/form-data", follow_redirects=True)
    assert b"Backup restored, with 1 uploaded file" in resp.data
    with live.app_context():
        assert "discount_type" in {r[1] for r in dbm.query("PRAGMA table_info(invoices)")}  # migrated
        assert dbm.scalar("SELECT title FROM events") == "Old gig"
    assert sorted(os.listdir(live.config["UPLOAD_FOLDER"])) == ["ok.pdf"]
    assert not (tmp_path / "render" / "escape.txt").exists() and not (tmp_path / "outside.txt").exists()
