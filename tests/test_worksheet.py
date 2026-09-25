import os
import sqlite3

from backline import create_app, util
from backline import db as dbm

from .conftest import query

REF = "2030-11-02-Alvarez-Sofia-TJ1R"
MIGRATED_COLUMNS = {"producer_id", "honorees", "guest_count", "venue_label", "venue2_id", "venue2_label",
                    "crew_meal", "run_of_show", "crew_notes", "service_type", "setting", "input_count",
                    "wireless_count", "monitor_mixes", "playback_feeds"}


def _wedding(make):
    producer = make("crew", name="Dana Kowalski", role="Production Manager", phone="(312) 555-0101",
                    email="dana@example.com")
    maya = make("crew", name="Maya Ortiz", phone="(312) 555-0102", dietary="Vegetarian")
    sam = make("crew", name="Sam Reyes", phone="(312) 555-0106")
    client = make("clients", name="Sofia Alvarez")
    reception = make("venues", name="Riverbend Country Club", city="Elmwood Park", state="IL",
                     contact_name="Tracy Nolan", contact_phone="(708) 555-0150")
    chapel = make("venues", name="Maplewood Chapel", city="Oak Park", state="IL")
    event = make("events", title="Alvarez / Reed Wedding", reference_number=REF, status="confirmed",
                 client_id=client, producer_id=producer, honorees="Sofia & Marcus", guest_count=225,
                 venue_id=reception, venue_label="Reception", venue2_id=chapel, venue2_label="Ceremony",
                 event_date="2030-11-02", load_in_time="13:00", soundcheck_time="16:30", start_time="18:00",
                 end_time="22:15", load_out_time="00:30", attire="Black suit and tie",
                 crew_meal="Hot meal at 6:30 PM", run_of_show="6:15 PM  MC announces the wedding party",
                 crew_notes="No visible cable runs down the aisle", notes="Client is price sensitive")
    make("event_crew", event_id=event, crew_id=maya, role="A1 / FOH (PA duty)", call_time="13:00",
         pay_rate=450, worksheet_key="mayakey")
    make("event_crew", event_id=event, crew_id=sam, role="Stagehand", pay_rate=280, worksheet_key="samkey")
    return event


def test_worksheet_mirrors_band_worksheet_sections(anon, app, make):
    _wedding(make)
    page = anon.get(f"/worksheet/{REF}/mayakey").data.decode()
    for heading in ("Basic info", "Location &amp; venue", "Crew", "Special requests", "Schedule",
                    "Audio &amp; backline", "Additional notes &amp; FAQs", "Crew chat"):
        assert f"<h2>{heading}</h2>" in page, heading
    assert "Sat Nov 2nd 2030" in page
    assert "Confirmed booking" in page and "Schedule subject to change" in page
    assert "Dana Kowalski" in page and 'href="tel:(312) 555-0101"' in page  # producer + contact
    assert "225" in page and "Sofia &amp; Marcus" in page and "Black suit and tie" in page
    assert "Ceremony" in page and "Maplewood Chapel" in page and "Reception" in page
    assert page.count("Open in Maps") == 2
    assert "Tracy Nolan" in page  # venue manager
    assert "You are on <strong>A1 / FOH (PA duty)</strong>" in page
    assert "Guide timings only!" in page
    assert "MC announces the wedding party" in page and "No visible cable runs" in page
    assert "Vegetarian" in page and "Hot meal at 6:30 PM" in page
    assert "Chicago Sound and Backline" in page  # terms / FAQs / footer
    assert "$450.00" in page and "$280.00" not in page
    assert "Client is price sensitive" not in page  # office notes stay in the office


def test_crew_only_notes_never_reach_the_client(client, anon, app, make):
    event = _wedding(make)
    client.post("/contracts/new", data={"event_id": event, "title": "A", "total_amount": "100", "deposit_amount": "50"})
    contract = query(app, "SELECT * FROM contracts", one=True)
    client.post(f"/contracts/{contract['id']}/status", data={"action": "send"})
    page = anon.get(f"/c/{contract['public_key']}").data.decode()
    assert "No visible cable runs" not in page and "Client is price sensitive" not in page


def test_office_worksheet_shows_office_notes(client, make):
    event = _wedding(make)
    page = client.get(f"/events/{event}/worksheet").data.decode()
    assert "Client is price sensitive" in page and "$280.00" in page


def test_crew_chat(client, anon, app, make):
    event = _wedding(make)
    anon.post(f"/worksheet/{REF}/mayakey/messages", data={"body": "Bringing a spare Twin."})
    anon.post(f"/worksheet/{REF}/mayakey/messages", data={"body": "   "})  # ignored
    client.post(f"/events/{event}/messages", data={"body": "Suit and tie, no sneakers."})
    rows = query(app, "SELECT author, crew_id, body FROM event_messages ORDER BY id")
    assert [(r["author"], r["body"]) for r in rows] == [("Maya Ortiz", "Bringing a spare Twin."),
                                                       ("admin", "Suit and tie, no sneakers.")]
    assert rows[0]["crew_id"] is not None and rows[1]["crew_id"] is None
    other = anon.get(f"/worksheet/{REF}/samkey").data.decode()
    assert "Bringing a spare Twin." in other and "Suit and tie, no sneakers." in other
    assert anon.post(f"/worksheet/{REF}/wrongkey/messages", data={"body": "hi"}).status_code == 404
    assert "Bringing a spare Twin." in client.get(f"/events/{event}?tab=chat").data.decode()
    msg_id = query(app, "SELECT id FROM event_messages ORDER BY id LIMIT 1", one=True)["id"]
    client.post(f"/events/{event}/messages/{msg_id}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM event_messages", one=True)["n"] == 1


def test_crew_calendar_invite(anon, client, make):
    event = _wedding(make)
    resp = anon.get(f"/worksheet/{REF}/mayakey/event.ics")
    assert resp.mimetype == "text/calendar"
    ics = resp.data.decode()
    assert "DTSTART:20301102T130000" in ics  # Maya's call time
    assert "DTEND:20301103T003000" in ics  # load-out after midnight rolls to the next day
    assert "SUMMARY:Chicago Sound and Backline: Alvarez / Reed Wedding (A1 / FOH (PA duty))" in ics.replace("\r\n ", "")
    assert "LOCATION:Riverbend Country Club\\, Elmwood Park\\, IL" in ics
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert client.get(f"/events/{event}/event.ics").status_code == 200


def test_all_day_invite_when_no_times(client, make):
    event = make("events", title="TBD times", event_date="2030-05-01", end_date="2030-05-02")
    ics = client.get(f"/events/{event}/event.ics").data.decode()
    assert "DTSTART;VALUE=DATE:20300501" in ics and "DTEND;VALUE=DATE:20300503" in ics


def test_ordinal_dates():
    cases = {"2026-11-07": "Sat Nov 7th 2026", "2026-11-01": "Sun Nov 1st 2026", "2026-11-02": "Mon Nov 2nd 2026",
             "2026-11-03": "Tue Nov 3rd 2026", "2026-11-11": "Wed Nov 11th 2026", "2026-11-12": "Thu Nov 12th 2026",
             "2026-11-13": "Fri Nov 13th 2026", "2026-11-21": "Sat Nov 21st 2026", "2026-11-22": "Sun Nov 22nd 2026"}
    for iso, expected in cases.items():
        assert util.fdate(iso, "ordinal") == expected


def test_new_event_starts_with_run_of_show_template(client):
    page = client.get("/events/new").data.decode()
    assert "LOAD-IN / ACCESS:" in page and "RUN OF SHOW:" in page


def test_company_defaults_to_chicago_sound_and_backline(anon, ctx):
    assert dbm.get_setting("company_name") == "Chicago Sound and Backline"
    assert dbm.get_setting("company_address") == "Chicago, IL"
    assert "Chicago Sound and Backline" in anon.get("/setup").data.decode()


def test_old_database_is_migrated(tmp_path):
    """A database created by the first release upgrades in place on startup."""
    path = os.path.join(tmp_path, "old.db")
    conn = sqlite3.connect(path)
    conn.executescript(open(os.path.join(os.path.dirname(__file__), "fixtures", "schema_v1.sql")).read())
    conn.execute("INSERT INTO settings (key, value) VALUES ('company_name', 'Your Audio & Backline Co.')")
    conn.execute("INSERT INTO events (reference_number, title, event_date, event_type) "
                 "VALUES ('R1', 'Old gig', '2030-01-01', 'Concert')")
    conn.execute("INSERT INTO checklist_templates (id, name) VALUES (1, 'Advance & Prep'), (2, 'Show Day')")
    conn.execute("INSERT INTO checklist_template_items (template_id, text) VALUES (1, 'Deposit received'), (2, 'Line check')")
    conn.execute("INSERT INTO event_checklist_items (event_id, text) VALUES (1, 'Deposit received'), (1, 'Line check')")
    conn.commit()
    conn.close()

    app = create_app({"TESTING": True, "DATABASE": path, "SECRET_KEY": "k"})
    with app.app_context():
        columns = {r[1] for r in dbm.query("PRAGMA table_info(events)")}
        assert MIGRATED_COLUMNS <= columns
        assert {"dietary", "w9_on_file"} <= {r[1] for r in dbm.query("PRAGMA table_info(crew)")}
        assert {"actual_hours", "final_amount", "paid_on", "paid_amount", "paid_method", "paid_reference"} <= \
            {r[1] for r in dbm.query("PRAGMA table_info(event_crew)")}
        assert {"contract_id", "kind"} <= {r[1] for r in dbm.query("PRAGMA table_info(invoices)")}
        assert dbm.get_setting("company_name") == "Chicago Sound and Backline"
        event = dbm.query("SELECT title, event_type FROM events", one=True)
        assert (event["title"], event["event_type"]) == ("Old gig", "Live Concert")
        visible = {r["text"]: r["crew_visible"] for r in dbm.query("SELECT text, crew_visible FROM event_checklist_items")}
        assert visible == {"Deposit received": 0, "Line check": 1}
        # New default checklists and event types arrive; existing templates aren't duplicated.
        names = [r["name"] for r in dbm.query("SELECT name FROM checklist_templates")]
        assert names.count("Advance & Prep") == 1 and "Corporate & Speaking" in names
        assert dbm.scalar("SELECT COUNT(*) FROM event_types") == len(dbm.DEFAULT_EVENT_TYPES)

    # Deleting a default type sticks across restarts.
    with app.app_context():
        dbm.execute("DELETE FROM event_types WHERE name = 'Wedding'")
    app = create_app({"TESTING": True, "DATABASE": path, "SECRET_KEY": "k"})
    with app.app_context():
        assert dbm.scalar("SELECT COUNT(*) FROM event_types WHERE name = 'Wedding'") == 0


def test_office_only_checklist_items_stay_off_crew_worksheets(client, anon, app, make):
    event = _wedding(make)
    templates = {r["name"]: r["id"] for r in query(app, "SELECT id, name FROM checklist_templates")}
    client.post(f"/events/{event}/checklist/template", data={"template_id": templates["Advance & Prep"]})
    client.post(f"/events/{event}/checklist/template", data={"template_id": templates["Show Day"]})
    client.post(f"/events/{event}/checklist", data={"text": "Invoice the balance"})  # box unticked -> office only
    client.post(f"/events/{event}/checklist", data={"text": "Gaff the aisle runner", "crew_visible": "1"})
    crew_page = anon.get(f"/worksheet/{REF}/mayakey").data.decode()
    assert "Deposit received" not in crew_page and "Invoice the balance" not in crew_page
    assert "Line check all inputs" in crew_page and "Gaff the aisle runner" in crew_page
    office_page = client.get(f"/events/{event}/worksheet").data.decode()
    assert "Deposit received" in office_page and "(office only)" in office_page
