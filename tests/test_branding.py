"""The company logo: built in, shown everywhere, replaceable from Settings."""

import io
import os

from backline import db as dbm

from .conftest import query

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"custom logo pixels"


def _static_logo(app):
    with open(os.path.join(app.static_folder, "brand", "logo.png"), "rb") as fh:
        return fh.read()


def _settings_form(**extra):
    data = {"company_name": "Chicago Sound and Backline", "contract_template": "Hi {{client_name}}"}
    data.update(extra)
    return data


def test_builtin_logo_is_public_and_everywhere(anon, client, app, make):
    resp = anon.get("/logo?v=default")
    assert resp.status_code == 200 and resp.mimetype == "image/png" and resp.data == _static_logo(app)

    login = app.test_client().get("/login").data.decode()
    assert 'class="auth-logo"' in login and "/logo?v=default" in login
    assert "brand/favicon.png" in login and "brand/apple-touch-icon.png" in login

    dashboard = client.get("/").data.decode()
    assert 'class="brand-logo"' in dashboard and 'alt="Chicago Sound and Backline"' in dashboard

    event = make("events", title="Gig", event_date="2030-01-01", reference_number="R-LOGO")
    crew = make("crew", name="Maya")
    make("event_crew", event_id=event, crew_id=crew, worksheet_key="k-logo")
    assert 'class="ws-logo"' in anon.get("/worksheet/R-LOGO/k-logo").data.decode()
    client.post("/contracts/new", data={"event_id": event, "title": "A", "total_amount": "100", "deposit_amount": "50"})
    contract = query(app, "SELECT id FROM contracts", one=True)["id"]
    assert 'class="doc-logo"' in client.get(f"/contracts/{contract}").data.decode()


def test_replace_and_reset_logo(client, anon, app):
    client.post("/settings", data=_settings_form(logo=(io.BytesIO(FAKE_PNG), "new-logo.png")),
                content_type="multipart/form-data")
    with app.app_context():
        first = dbm.get_setting("logo_file")
    assert first.startswith("logo-") and first.endswith(".png")
    assert anon.get(f"/logo?v={first}").data == FAKE_PNG
    assert f"/logo?v={first}" in client.get("/").data.decode()  # cache-busting URL follows the file

    client.post("/settings", data=_settings_form(logo=(io.BytesIO(b"\xff\xd8\xff" + b"jpeg"), "second.jpg")),
                content_type="multipart/form-data")
    with app.app_context():
        second = dbm.get_setting("logo_file")
    assert second.endswith(".jpg") and not os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], first))

    client.post("/settings", data=_settings_form(reset_logo="1"), content_type="multipart/form-data")
    with app.app_context():
        assert dbm.get_setting("logo_file") == ""
    assert os.listdir(app.config["UPLOAD_FOLDER"]) == []
    assert anon.get("/logo").data == _static_logo(app)


def test_rejects_non_images_and_keeps_nothing_on_failed_save(client, app):
    for name, data in (("logo.svg", b"<svg onload=alert(1)>"), ("logo.png", b"not really a png")):
        resp = client.post("/settings", data=_settings_form(logo=(io.BytesIO(data), name)),
                           content_type="multipart/form-data")
        assert resp.status_code == 200 and b"The logo must be a PNG, JPG, GIF or WebP image." in resp.data
    # A valid logo with an invalid form elsewhere isn't kept either.
    resp = client.post("/settings", data=_settings_form(company_name="", logo=(io.BytesIO(FAKE_PNG), "ok.png")),
                       content_type="multipart/form-data")
    assert resp.status_code == 200
    with app.app_context():
        assert dbm.get_setting("logo_file") == ""
    folder = app.config["UPLOAD_FOLDER"]
    assert not os.path.exists(folder) or os.listdir(folder) == []
