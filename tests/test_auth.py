import os
import re

from backline import create_app


def test_first_visit_redirects_to_setup(anon):
    resp = anon.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/setup")


def test_setup_creates_admin_and_company(client):
    assert client.get("/").status_code == 200
    assert b"Test Audio" in client.get("/").data


def test_setup_is_closed_once_a_user_exists(client, anon):
    resp = anon.post("/setup", data={"username": "intruder", "password": "password123"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_required_and_wrong_password(client, app):
    other = app.test_client()
    assert other.get("/events").status_code == 302
    resp = other.post("/login", data={"username": "admin", "password": "wrong"})
    assert b"Incorrect username or password" in resp.data
    resp = other.post("/login", data={"username": "admin", "password": "password123"})
    assert resp.status_code == 302
    assert other.get("/events").status_code == 200


def test_login_ignores_offsite_next(client, app):
    other = app.test_client()
    resp = other.post("/login?next=//evil.example.com/", data={"username": "admin", "password": "password123"})
    assert resp.headers["Location"] == "/"


def test_csrf_enforced(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": os.path.join(tmp_path, "c.db"), "SECRET_KEY": "k"})
    c = app.test_client()
    assert c.post("/setup", data={"username": "a", "password": "password123"}).status_code == 400
    page = c.get("/setup").data.decode()
    token = re.search(r'name="_csrf" value="([^"]+)"', page).group(1)
    resp = c.post("/setup", data={"username": "a", "password": "password123", "_csrf": token})
    assert resp.status_code == 302
