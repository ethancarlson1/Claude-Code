"""Company vehicles, event transport and event documents."""

import io
import os
from datetime import date, timedelta

from backline import create_app, services
from backline import db as dbm

from .conftest import query

TODAY = date.today()


def day(n):
    return (TODAY + timedelta(days=n)).isoformat()


def _truck(make, **extra):
    values = dict(name="Box Truck 1", vehicle_type="Box truck", plate="DEMO-101", status="active")
    values.update(extra)
    return make("vehicles", **values)


# --- Vehicles ---------------------------------------------------------------------

def test_vehicle_crud(client, app, make):
    resp = client.post("/vehicles/new", data={"name": "Sprinter Van", "vehicle_type": "Cargo van", "plate": "DEMO-102",
                                              "status": "active", "registration_expires": day(10)})
    vehicle = int(resp.headers["Location"].rsplit("/", 1)[1])
    listing = client.get("/vehicles").data.decode()
    assert "Sprinter Van" in listing and "DEMO-102" in listing
    page = client.get(f"/vehicles/{vehicle}").data.decode()
    assert "badge-warn" in page and "expiring" in page  # registration within 30 days

    event = make("events", title="Gig", event_date=day(3), status="confirmed")
    client.post(f"/events/{event}/vehicles", data={"kind": "company", "vehicle_id": str(vehicle)})
    client.post(f"/vehicles/{vehicle}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM vehicles", one=True)["n"] == 1  # used vehicles are kept
    assert "Gig" in client.get(f"/vehicles/{vehicle}").data.decode()


def test_company_and_third_party_vehicles_on_an_event(client, app, make):
    truck = _truck(make)
    driver = make("crew", name="Sam Reyes", phone="(312) 555-0106")
    event = make("events", title="Gig", event_date=day(3), status="confirmed")
    client.post(f"/events/{event}/vehicles", data={"kind": "company", "vehicle_id": str(truck),
                                                   "driver_id": str(driver), "departs": "06:15"})
    client.post(f"/events/{event}/vehicles", data={"kind": "third_party", "description": "Penske 16' rental #4471",
                                                   "notes": "Return by 10 PM"})
    client.post(f"/events/{event}/vehicles", data={"kind": "third_party", "description": "  "})  # rejected
    client.post(f"/events/{event}/vehicles", data={"kind": "company", "vehicle_id": "999"})  # rejected
    rows = query(app, "SELECT * FROM event_vehicles ORDER BY id")
    assert [(r["vehicle_id"], r["description"], r["driver_id"], r["departs"]) for r in rows] == [
        (truck, None, driver, "06:15"), (None, "Penske 16' rental #4471", None, None)]

    third = rows[1]["id"]
    client.post(f"/events/{event}/vehicles/{third}", data={"description": "Penske 20' rental #4471",
                                                           "driver_id": str(driver)})
    assert query(app, "SELECT description, driver_id FROM event_vehicles WHERE id = ?", (third,), one=True) == \
        {"description": "Penske 20' rental #4471", "driver_id": driver}

    page = client.get(f"/events/{event}?tab=transport").data.decode()
    assert "Box Truck 1" in page and "Penske 20&#39; rental #4471" in page
    assert "Box Truck 1 · DEMO-101" in client.get(f"/events/{event}").data.decode()  # overview

    client.post(f"/events/{event}/vehicles/{third}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM event_vehicles", one=True)["n"] == 1


def test_vehicle_double_booking(client, app, make):
    truck = _truck(make)
    fest = make("events", title="Festival", event_date=day(20), end_date=day(22), status="hold")
    club = make("events", title="Club", event_date=day(21), status="confirmed")
    inquiry = make("events", title="Maybe", event_date=day(21), status="inquiry")
    for e in (fest, club, inquiry):
        make("event_vehicles", event_id=e, vehicle_id=truck)

    with app.app_context():
        club_row = dbm.query("SELECT * FROM events WHERE id = ?", (club,), one=True)
        problems = services.vehicle_problems(club_row)
    assert [c["title"] for p in problems.values() for c in p["conflicts"]] == ["Festival"]  # inquiries don't reserve
    page = client.get(f"/events/{club}?tab=transport").data.decode()
    assert "Vehicle problem" in page and "Festival" in page
    assert "Vehicle conflicts" in client.get("/").data.decode()

    with app.app_context():
        dbm.update("events", fest, {"event_date": day(30), "end_date": day(31)})
        dbm.update("vehicles", truck, {"status": "maintenance"})
        problems = services.vehicle_problems(dbm.query("SELECT * FROM events WHERE id = ?", (club,), one=True))
    assert [(p["unavailable"], p["conflicts"]) for p in problems.values()] == [("maintenance", [])]


def test_worksheet_shows_transport(anon, make):
    truck = _truck(make, capacity="16 ft box, liftgate")
    driver = make("crew", name="Sam Reyes", phone="(312) 555-0106")
    event = make("events", title="Gig", event_date=day(3), reference_number="R-TRUCK")
    make("event_vehicles", event_id=event, vehicle_id=truck, driver_id=driver, departs="06:15", notes="Dock by 7")
    make("event_vehicles", event_id=event, description="Enterprise cargo van (res. E-5521)")
    make("event_crew", event_id=event, crew_id=driver, worksheet_key="k-truck")
    page = anon.get("/worksheet/R-TRUCK/k-truck").data.decode()
    assert "<h2>Transport</h2>" in page
    assert "DEMO-101" in page and "Driver: Sam Reyes" in page and "6:15 AM" in page and "Dock by 7" in page
    assert "Enterprise cargo van (res. E-5521)" in page and "Driver TBD" in page


def test_dashboard_vehicle_alerts(client, make):
    _truck(make, registration_expires=day(-1), insurance_expires=day(12))
    event = make("events", title="Soon Gig", event_date=day(4), status="confirmed")
    make("event_gear", event_id=event, description="PA", quantity=1)
    page = client.get("/").data.decode()
    assert "Vehicle paperwork" in page and "Registration expired" in page and "Insurance expires soon" in page
    assert "No vehicle assigned for Soon Gig" in page


def test_duplicate_copies_vehicles_without_drivers(client, app, make):
    truck = _truck(make)
    driver = make("crew", name="Sam")
    event = make("events", title="Residency", event_date=day(5))
    make("event_vehicles", event_id=event, vehicle_id=truck, driver_id=driver, departs="06:00")
    resp = client.post(f"/events/{event}/duplicate", data={"event_date": day(12)})
    new_id = int(resp.headers["Location"].rsplit("/", 1)[1])
    assert query(app, "SELECT vehicle_id, driver_id, departs FROM event_vehicles WHERE event_id = ?", (new_id,)) == \
        [{"vehicle_id": truck, "driver_id": None, "departs": "06:00"}]


# --- Documents --------------------------------------------------------------------

PDF = b"%PDF-1.4 fake stage plot"


def _upload(client, event, files, **form):
    data = {"files": [(io.BytesIO(content), name) for name, content in files], "category": "Stage plot",
            "crew_visible": "1"}
    data.update(form)
    return client.post(f"/events/{event}/files", data=data, content_type="multipart/form-data")


def test_upload_list_download_and_delete(client, app, make):
    event = make("events", title="Gig", event_date=day(3))
    _upload(client, event, [("Stage plot rev2.pdf", PDF), ("input list.csv", b"Ch,Source\n1,Kick\n")],
            source="Artist management", description="Rev 2")
    rows = query(app, "SELECT * FROM event_files ORDER BY id")
    assert [(r["original_name"], r["category"], r["source"], r["uploaded_by"]) for r in rows] == [
        ("Stage plot rev2.pdf", "Stage plot", "Artist management", "admin"),
        ("input list.csv", "Stage plot", "Artist management", "admin")]
    folder = app.config["UPLOAD_FOLDER"]
    assert sorted(os.listdir(folder)) == sorted(r["stored_name"] for r in rows)
    assert all(r["stored_name"] != r["original_name"] for r in rows)  # stored under random names

    page = client.get(f"/events/{event}?tab=documents").data.decode()
    assert "Stage plot rev2.pdf" in page and "Artist management" in page

    pdf = client.get(f"/events/{event}/files/{rows[0]['id']}")
    assert pdf.data == PDF and pdf.mimetype == "application/pdf"
    assert pdf.headers["Content-Disposition"].startswith("inline")
    assert pdf.headers["X-Content-Type-Options"] == "nosniff"
    csv = client.get(f"/events/{event}/files/{rows[1]['id']}")
    assert csv.headers["Content-Disposition"].startswith("attachment")

    client.post(f"/events/{event}/files/{rows[1]['id']}", data={"category": "Input list", "description": "",
                                                                "source": ""})
    updated = query(app, "SELECT category, crew_visible FROM event_files WHERE id = ?", (rows[1]["id"],), one=True)
    assert updated == {"category": "Input list", "crew_visible": 0}

    client.post(f"/events/{event}/files/{rows[0]['id']}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM event_files", one=True)["n"] == 1
    assert os.listdir(folder) == [rows[1]["stored_name"]]


def test_rejects_unsafe_or_empty_files(client, app, make):
    event = make("events", title="Gig", event_date=day(3))
    resp = _upload(client, event, [("run.exe", b"MZ"), ("page.html", b"<script>"), ("plot.svg", b"<svg/>"),
                                   ("empty.pdf", b""), ("ok.pdf", PDF)])
    assert resp.status_code == 302
    assert [r["original_name"] for r in query(app, "SELECT original_name FROM event_files")] == ["ok.pdf"]
    assert len(os.listdir(app.config["UPLOAD_FOLDER"])) == 1
    page = client.get(f"/events/{event}?tab=documents").data.decode()
    assert "this file type isn&#39;t accepted" in page and "empty.pdf is empty" in page


def test_crew_see_only_shared_documents(client, anon, app, make):
    event = make("events", title="Gig", event_date=day(3), reference_number="R-DOCS")
    other = make("events", title="Other", event_date=day(3), reference_number="R-OTHER")
    crew = make("crew", name="Maya")
    make("event_crew", event_id=event, crew_id=crew, worksheet_key="k-docs")
    _upload(client, event, [("Stage plot.pdf", PDF)])
    _upload(client, event, [("COI.pdf", b"%PDF office only")], category="Contract / paperwork", crew_visible="")
    _upload(client, other, [("Other event.pdf", b"%PDF other")])
    shared, private, foreign = [r["id"] for r in query(app, "SELECT id FROM event_files ORDER BY id")]

    page = anon.get("/worksheet/R-DOCS/k-docs").data.decode()
    assert "Stage plot.pdf" in page and "COI.pdf" not in page
    assert anon.get(f"/worksheet/R-DOCS/k-docs/files/{shared}").data == PDF
    assert anon.get(f"/worksheet/R-DOCS/k-docs/files/{private}").status_code == 404
    assert anon.get(f"/worksheet/R-DOCS/k-docs/files/{foreign}").status_code == 404
    assert anon.get(f"/worksheet/R-DOCS/wrong/files/{shared}").status_code == 404
    assert anon.get(f"/events/{event}/files/{shared}").status_code == 302  # office link needs a login
    assert "COI.pdf" in client.get(f"/events/{event}/worksheet").data.decode()  # office copy lists everything


def test_deleting_an_event_removes_its_files(client, app, make):
    event = make("events", title="Gig", event_date=day(3))
    _upload(client, event, [("a.pdf", PDF), ("b.png", b"\x89PNG fake")])
    assert len(os.listdir(app.config["UPLOAD_FOLDER"])) == 2
    client.post(f"/events/{event}/delete")
    assert os.listdir(app.config["UPLOAD_FOLDER"]) == []
    assert query(app, "SELECT COUNT(*) AS n FROM event_files", one=True)["n"] == 0


def test_too_large_upload_gets_a_friendly_message(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "t.db"), "SECRET_KEY": "k", "CSRF_ENABLED": False,
                      "UPLOAD_FOLDER": str(tmp_path / "up"), "MAX_CONTENT_LENGTH": 1024})
    c = app.test_client()
    c.post("/setup", data={"username": "admin", "password": "password123"})
    with app.app_context():
        event = dbm.insert("events", {"title": "Gig", "event_date": day(3), "reference_number": "R-BIG"})
    resp = c.post(f"/events/{event}/files", data={"files": [(io.BytesIO(b"x" * 5000), "big.pdf")]},
                  content_type="multipart/form-data", headers={"Referer": f"http://localhost/events/{event}?tab=documents"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("tab=documents")
    assert "too large" in c.get(resp.headers["Location"]).data.decode()
