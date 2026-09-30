"""The public event request form and the office's Requests inbox."""

import io
import os

import pytest

from backline import db as dbm
from backline import intake

from .conftest import query

FULL = {
    "name": "Grace Okafor", "organization": "Brightline Analytics", "email": "Grace.Okafor@example.com",
    "phone": "(312) 555-0177", "description": "Summer party on a rooftop with a DJ and a toast.",
    "event_type": "Private Party", "event_name": "Brightline Summer Party", "event_date": "2030-07-18",
    "attendance": "about 180 people", "setting": "Outdoors", "performers": "A DJ and our CEO",
    "venue_name": "Kinzie Rooftop Terrace", "venue_address": "River North, Chicago",
    "layout": "Open deck, bar on the north side, DJ in the corner.", "stage": "No", "power": "Not sure",
    "venue_contact": "Evan, (312) 555-0181", "access": ["Loading dock", "Elevator"], "load_in_time": "14:00",
    "load_out_time": "23:30", "load_in_notes": "Freight elevator must be reserved.",
    "parking": "Loading zone in the alley.", "doors_time": "17:30", "start_time": "18:00", "end_time": "22:00",
    "schedule": "5:30 Guests arrive\n7:00 Toast\n7:10 DJ", "needs": [intake.SPEAKERS, intake.WIRELESS, intake.BACKLINE],
    "tech": intake.TECH_ON_SITE, "mic_count": "2", "gear_details": "Wireless handheld for the toast.",
    "onsite_name": "Sam Lee", "onsite_phone": "(312) 555-0190", "planner": "Rita at Party Co, rita@example.com",
    "budget": "Around $2,000", "notes": "It can get windy.",
}


def _submit(anon, data=None, files=(), **extra):
    payload = dict(FULL if data is None else data, **extra)
    if files:
        payload["files"] = [(io.BytesIO(content), name) for name, content in files]
    return anon.post("/request", data=payload, content_type="multipart/form-data", follow_redirects=True)


def _requests(app):
    return query(app, "SELECT * FROM client_requests ORDER BY id")


@pytest.fixture
def submitted(anon, app):
    resp = _submit(anon, files=[("Velvet stage plot.pdf", b"%PDF-1.4 plot"), ("rooftop.jpg", b"\xff\xd8\xff photo")])
    assert b"Thanks, Grace!" in resp.data
    return query(app, "SELECT * FROM client_requests", one=True)


# --- The public form ---------------------------------------------------------------

def test_form_is_public_and_needs_only_a_name_and_contact(anon, app):
    page = anon.get("/request").data.decode()
    assert "Tell us about your event" in page and "Skip anything you" in page
    for heading in ("About you", "The event", "Location", "Load-in and parking", "Timeline", "What you need",
                    "Contacts on the day", "Anything else"):
        assert heading in page
    assert "Private Party" in page and page.count(">Other<") == 1  # event types come from Settings

    resp = _submit(anon, {"name": "Dev Patel", "phone": "(773) 555-0163"})
    assert b"Thanks, Dev!" in resp.data and b"(#1)" in resp.data
    (row,) = _requests(app)
    assert (row["name"], row["phone"], row["status"], row["email"], row["event_date"]) == \
        ("Dev Patel", "(773) 555-0163", "new", None, None)
    assert intake.answers_of(row) == {"name": "Dev Patel", "phone": "(773) 555-0163"}
    assert b"Thanks!" in anon.get("/request/thanks").data  # a refresh doesn't repeat the details


def test_missing_or_wrong_answers_are_explained_and_kept(anon, app):
    page = _submit(anon, {"venue_name": "The Loft", "needs": [intake.DJ]}).data.decode()
    assert "Please tell us your name." in page and "Add an email or a phone number" in page
    assert 'value="The Loft"' in page and f'value="{intake.DJ}" checked' in page  # nothing typed is lost
    page = _submit(anon, {"name": "A", "email": "not-an-email", "event_date": "2030-05-02",
                          "end_date": "2030-05-01"}).data.decode()
    assert "email address doesn" in page and "last day can" in page
    assert _requests(app) == []


def test_answers_are_read_forgivingly(anon, app):
    _submit(anon, {"name": "A", "phone": "1", "attendance": "1,200-ish", "mic_count": "maybe 3 or 4",
                   "setting": "On the moon", "needs": ["Fog machine", intake.DJ], "event_type": "Made up",
                   "event_date": "2030-05-02", "end_date": "2030-05-02"})
    a = intake.answers_of(_requests(app)[0])
    assert a["attendance"] == 1200 and a["mic_count"] == 3 and a["needs"] == [intake.DJ]
    assert "setting" not in a and "event_type" not in a and "end_date" not in a


def test_spam_protection(anon, app):
    resp = _submit(anon, {"name": "Bot", "email": "bot@example.com", "website": "http://spam.example"})
    assert b"Thanks!" in resp.data and _requests(app) == []
    for n in range(intake.RATE_LIMIT):
        _submit(anon, {"name": f"Person {n}", "phone": "555"})
    page = _submit(anon, {"name": "One too many", "phone": "555"}).data.decode()
    assert "several requests from your network" in page and len(_requests(app)) == intake.RATE_LIMIT


def test_files_are_kept_and_unsafe_ones_skipped(anon, app, submitted):
    resp = _submit(anon, {"name": "B", "phone": "1"}, files=[("rider.pdf", b"%PDF"), ("evil.html", b"<script>"),
                                                              ("empty.pdf", b"")])
    page = resp.data.decode()
    assert "couldn" in page and "evil.html: this file type isn" in page and "empty.pdf is empty" in page
    rows = query(app, "SELECT * FROM client_request_files ORDER BY id")
    assert [r["original_name"] for r in rows] == ["Velvet stage plot.pdf", "rooftop.jpg", "rider.pdf"]
    assert all(os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], r["stored_name"])) for r in rows)


def test_form_can_be_turned_off(client, anon, app):
    client.post("/requests/form", data={"enabled": "0"})
    page = anon.get("/request").data.decode()
    assert "not taking requests online" in page and "Send request" not in page
    _submit(anon, {"name": "A", "phone": "1"})
    assert _requests(app) == []
    client.post("/requests/form", data={"enabled": "1"})
    assert "Send request" in anon.get("/request").data.decode()


# --- The office inbox --------------------------------------------------------------

def test_office_pages_need_a_login(anon, submitted):
    for url in ("/requests", f"/requests/{submitted['id']}", f"/requests/{submitted['id']}/convert",
                f"/requests/{submitted['id']}/files/1"):
        assert anon.get(url).status_code == 302


def test_inbox_dashboard_and_detail(client, submitted):
    assert '<span class="nav-count" title="1 new">1</span>' in client.get("/").data.decode()
    dashboard = client.get("/").data.decode()
    assert "New event requests" in dashboard and "Grace Okafor · Brightline Analytics" in dashboard
    listing = client.get("/requests").data.decode()
    assert "Brightline Summer Party" in listing and "2 files attached" in listing and "/request" in listing
    page = client.get(f"/requests/{submitted['id']}").data.decode()
    for text in ("Earliest we can arrive", "2:00 PM", "Loading dock, Elevator", "Around $2,000", "180",
                 "Velvet stage plot.pdf", "mailto:Grace.Okafor@example.com"):
        assert text in page, text
    assert "Their phone" in page and "How many microphones?" in page
    resp = client.get(f"/requests/{submitted['id']}/files/1")
    assert resp.status_code == 200 and resp.data == b"%PDF-1.4 plot"


def test_answers_are_escaped(client, anon, app):
    _submit(anon, {"name": "<script>alert(1)</script>", "phone": "1", "notes": "<b>hi</b>"})
    page = client.get("/requests/1").data.decode()
    assert "<script>alert(1)" not in page and "&lt;script&gt;alert(1)" in page and "&lt;b&gt;hi" in page


def test_create_inquiry_from_a_request(client, app, submitted):
    page = client.get(f"/requests/{submitted['id']}/convert").data.decode()
    assert 'value="Brightline Summer Party"' in page and "New client: Grace Okafor (Brightline Analytics)" in page
    assert "New venue: Kinzie Rooftop Terrace" in page and "Audience" in page and "Parking &amp; load-in" in page

    resp = client.post(f"/requests/{submitted['id']}/convert", data={
        "title": "Brightline Summer Party", "event_type": "Private Party", "event_date": "2030-07-18",
        "end_date": "", "client": "new", "venue": "new"}, follow_redirects=True)
    assert b"Inquiry created from request #1" in resp.data
    event = query(app, "SELECT * FROM events", one=True)
    assert (event["status"], event["event_type"], event["event_date"], event["guest_count"]) == \
        ("inquiry", "Private Party", "2030-07-18", 180)
    assert event["setting"] == "Outdoor" and event["service_type"] == "Full production (PA, backline, crew)"
    assert event["wireless_count"] == 2 and event["performers"] == "A DJ and our CEO"
    assert (event["load_in_time"], event["doors_time"], event["start_time"], event["end_time"], event["load_out_time"]) == \
        ("14:00", "17:30", "18:00", "22:00", "23:30")
    assert event["run_of_show"] == "5:30 Guests arrive\n7:00 Toast\n7:10 DJ"
    # Load-in, parking and power live on the new venue, so the event page doesn't repeat them.
    assert event["parking"] is None and event["power_notes"] is None
    assert "Asked for: Speakers / sound system, Wireless microphones, Backline" in event["audio_notes"]
    assert "Microphones: about 2." in event["audio_notes"] and "Wireless handheld" in event["audio_notes"]
    assert (event["on_site_contact"], event["on_site_phone"]) == ("Sam Lee", "(312) 555-0190")
    for text in ("From online request #1", "Budget: Around $2,000", "Layout: Open deck", "Planner: Rita",
                 "Other notes: It can get windy.", "About the event: Summer party"):
        assert text in event["notes"], text
    assert query(app, "SELECT COUNT(*) AS n FROM event_checklist_items WHERE event_id = ?", (event["id"],), one=True)["n"] > 0

    client_row = query(app, "SELECT * FROM clients", one=True)
    assert (client_row["name"], client_row["company"], client_row["email"]) == \
        ("Grace Okafor", "Brightline Analytics", "Grace.Okafor@example.com")
    venue = query(app, "SELECT * FROM venues", one=True)
    assert venue["name"] == "Kinzie Rooftop Terrace" and venue["parking_notes"] == "Loading zone in the alley."
    assert venue["stage_notes"] == "Stage: No." and venue["power_notes"] == "Power near the setup area: Not sure."
    assert venue["load_in_notes"] == "Access: Loading dock, Elevator.\nFreight elevator must be reserved."
    assert (event["client_id"], event["venue_id"]) == (client_row["id"], venue["id"])

    docs = query(app, "SELECT * FROM event_files ORDER BY id")
    assert [(d["original_name"], d["category"], d["crew_visible"]) for d in docs] == [
        ("Velvet stage plot.pdf", "Stage plot", 0), ("rooftop.jpg", "Photos", 0)]
    assert all(os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], d["stored_name"])) for d in docs)
    assert query(app, "SELECT COUNT(*) AS n FROM client_request_files", one=True)["n"] == 0
    req = query(app, "SELECT * FROM client_requests", one=True)
    assert (req["status"], req["event_id"]) == ("converted", event["id"])
    overview = client.get(f"/events/{event['id']}").data.decode()
    for text in ("Venue load-in", "Freight elevator must be reserved.", "Venue parking", "Loading zone in the alley.",
                 "Venue power", "Stage: No."):
        assert overview.count(text) == 1, text  # shown once, from the venue
    assert "Brightline Summer Party" in client.get("/requests?status=converted").data.decode()
    assert "nav-count" not in client.get("/").data.decode()

    resp = client.get(f"/requests/{submitted['id']}/convert", follow_redirects=True)
    assert b"already been turned into an event" in resp.data


def test_existing_client_and_venue_are_matched(client, app, make, submitted):
    existing = make("clients", name="G. Okafor", email="grace.okafor@EXAMPLE.com")
    venue = make("venues", name="kinzie rooftop terrace")
    page = client.get(f"/requests/{submitted['id']}/convert").data.decode()
    assert f'<option value="{existing}" selected' in page and "Matched an existing client by same email" in page
    assert f'<option value="{venue}" selected' in page
    client.post(f"/requests/{submitted['id']}/convert", data={
        "title": "Party", "event_type": "", "event_date": "2030-07-18", "client": str(existing), "venue": str(venue)})
    assert query(app, "SELECT COUNT(*) AS n FROM clients", one=True)["n"] == 1
    assert query(app, "SELECT COUNT(*) AS n FROM venues", one=True)["n"] == 1
    event = query(app, "SELECT * FROM events", one=True)
    assert (event["client_id"], event["venue_id"]) == (existing, venue)
    # A venue already on file keeps its own notes; this event's specifics go on the event.
    assert event["parking"] == ("Access: Loading dock, Elevator.\nFreight elevator must be reserved.\n"
                                "Parking: Loading zone in the alley.")
    assert event["power_notes"] == "Power near the setup area: Not sure."


def test_matching_by_phone_and_a_request_without_a_date(client, anon, app, make):
    existing = make("clients", name="Devesh Patel", phone="773.555.0163")
    _submit(anon, {"name": "Dev Patel", "phone": "(773) 555-0163", "description": "Quinceañera"})
    page = client.get("/requests/1/convert").data.decode()
    assert f'<option value="{existing}" selected' in page and "same phone" in page
    assert "They didn't give a date yet." in page and 'value="Dev Patel event"' in page
    page = client.post("/requests/1/convert", data={"title": "Quinceañera", "event_date": "", "client": "new",
                                                    "venue": ""}).data.decode()
    assert "Events need a date" in page and query(app, "SELECT COUNT(*) AS n FROM events", one=True)["n"] == 0


def test_add_to_an_existing_event_fills_only_blanks(client, app, make, submitted):
    venue = make("venues", name="Kinzie Rooftop Terrace")
    event = make("events", title="Brightline party (phone call)", event_date="2030-07-19", guest_count=150,
                 run_of_show="Office draft schedule", notes="Called in on Monday.")
    page = client.get(f"/requests/{submitted['id']}").data.decode()
    assert "Brightline party (phone call)" in page
    resp = client.post(f"/requests/{submitted['id']}/add-to-event", data={"event_id": event}, follow_redirects=True)
    assert b"Added request #1 to this event, filling in" in resp.data
    row = query(app, "SELECT * FROM events WHERE id = ?", (event,), one=True)
    assert row["guest_count"] == 150 and row["run_of_show"] == "Office draft schedule"  # office values kept
    assert row["setting"] == "Outdoor" and row["parking"].startswith("Access: Loading dock")  # blanks filled
    assert row["notes"].startswith("Called in on Monday.\n\nFrom online request #1")
    for text in ("Date (from the request): Thu, Jul 18, 2030", "Audience (from the request): 180",
                 "Schedule (from the request): 5:30 Guests arrive"):
        assert text in row["notes"], text
    assert row["client_id"] and row["venue_id"] == venue
    assert len(query(app, "SELECT * FROM event_files WHERE event_id = ?", (event,))) == 2
    assert query(app, "SELECT status, event_id FROM client_requests", one=True) == {"status": "converted", "event_id": event}


def test_add_to_an_event_without_a_venue_creates_it_once(client, app, make, submitted):
    event = make("events", title="Brightline party", event_date="2030-07-18")
    client.post(f"/requests/{submitted['id']}/add-to-event", data={"event_id": event})
    row = query(app, "SELECT * FROM events WHERE id = ?", (event,), one=True)
    venue = query(app, "SELECT * FROM venues", one=True)
    assert row["venue_id"] == venue["id"] and venue["parking_notes"] == "Loading zone in the alley."
    assert row["parking"] is None and row["power_notes"] is None  # shown from the venue instead
    assert "Date (from the request)" not in row["notes"]  # same date, nothing to flag


def test_archive_reopen_and_delete(client, app, submitted):
    rid = submitted["id"]
    client.post(f"/requests/{rid}/status", data={"action": "archive"})
    assert query(app, "SELECT status FROM client_requests", one=True)["status"] == "archived"
    assert "Grace Okafor" not in client.get("/requests").data.decode()
    assert "Grace Okafor" in client.get("/requests?status=archived").data.decode()
    client.post(f"/requests/{rid}/status", data={"action": "reopen"})
    assert query(app, "SELECT status FROM client_requests", one=True)["status"] == "new"

    stored = [r["stored_name"] for r in query(app, "SELECT stored_name FROM client_request_files")]
    client.post(f"/requests/{rid}/delete")
    assert _requests(app) == [] and query(app, "SELECT * FROM client_request_files") == []
    assert not any(os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], s)) for s in stored)


def test_service_type_from_answers():
    assert intake.service_type({"tech": intake.DROP_OFF, "needs": [intake.SPEAKERS]}) == "Dry hire (drop-off & pickup)"
    assert intake.service_type({"tech": intake.TECH_ON_SITE, "needs": [intake.SPEAKERS]}) == "PA + engineer"
    assert intake.service_type({"tech": intake.TECH_ON_SITE, "needs": [intake.BACKLINE]}) == "Backline + tech"
    assert intake.service_type({"tech": intake.NOT_SURE, "needs": [intake.BACKLINE]}) is None


def test_guessing_document_categories():
    guesses = {name: intake.guess_category(name) for name in (
        "Band_Input_List.xlsx", "Rider 2030.pdf", "Venue tech pack.pdf", "Ballroom floor plan.pdf",
        "loading dock map.png", "Agenda v3.docx", "IMG_2041.HEIC", "notes.txt")}
    assert guesses == {"Band_Input_List.xlsx": "Input list", "Rider 2030.pdf": "Rider / tech rider",
                       "Venue tech pack.pdf": "Venue tech pack", "Ballroom floor plan.pdf": "Floor plan / site map",
                       "loading dock map.png": "Parking / load-in map", "Agenda v3.docx": "Run of show / agenda",
                       "IMG_2041.HEIC": "Photos", "notes.txt": "Other"}


def test_demo_requests(client, app):
    from backline.seed import seed

    with app.app_context():
        seed()
        rows = dbm.query("SELECT * FROM client_requests ORDER BY id")
    assert [r["name"] for r in rows] == ["Grace Okafor", "Dev Patel"]
    for r in rows:
        assert client.get(f"/requests/{r['id']}").status_code == 200
        assert client.get(f"/requests/{r['id']}/convert").status_code == 200
    assert client.get("/requests/1/files/1").status_code == 200
