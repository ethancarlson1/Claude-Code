import re

from backline import services
from backline import db as dbm

from .conftest import query


def _event_form(**overrides):
    data = {"title": "Alvarez / Reed Wedding", "status": "confirmed", "event_date": "2030-11-07"}
    data.update(overrides)
    return data


def test_create_event_builds_reference_and_checklists(client, app, make):
    client_id = make("clients", name="Sofia Alvarez")
    resp = client.post("/events/new", data={**_event_form(client_id=client_id), "templates": ["1", "2"]})
    assert resp.status_code == 302
    event = query(app, "SELECT * FROM events", one=True)
    assert re.fullmatch(r"2030-11-07-Alvarez-Sofia-[A-Z0-9]{4}", event["reference_number"])
    counts = query(app, "SELECT COUNT(*) AS n FROM event_checklist_items WHERE event_id = ?", (event["id"],), one=True)
    template_items = query(app, "SELECT COUNT(*) AS n FROM checklist_template_items WHERE template_id IN (1, 2)", one=True)
    assert counts["n"] == template_items["n"] > 0


def test_event_validation(client, app):
    resp = client.post("/events/new", data=_event_form(title="", end_date="2030-11-01"))
    assert resp.status_code == 200
    assert b"Event title is required" in resp.data
    assert b"End date can&#39;t be before the start date" in resp.data
    assert query(app, "SELECT COUNT(*) AS n FROM events", one=True)["n"] == 0


def _gear_setup(make, twin_qty=3):
    twin = make("inventory_items", name="Fender Twin", category="Guitar Amps", quantity=twin_qty, rental_rate=95)
    festival = make("events", title="Festival", status="hold", event_date="2030-06-10", end_date="2030-06-12")
    club = make("events", title="Club", status="confirmed", event_date="2030-06-11")
    make("event_gear", event_id=festival, item_id=twin, quantity=2)
    make("event_gear", event_id=club, item_id=twin, quantity=2)
    return twin, festival, club


def _availability(app, event_id):
    with app.app_context():
        event = dbm.query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
        return services.gear_availability(event)


def test_overlapping_events_conflict(app, make):
    twin, festival, club = _gear_setup(make)
    a = _availability(app, club)[twin]
    assert (a["owned"], a["booked_elsewhere"], a["available"], a["short"]) == (3, 2, 1, 1)
    assert [c["title"] for c in a["conflicts"]] == ["Festival"]
    assert _availability(app, festival)[twin]["short"] == 1


def test_inquiries_and_cancelled_events_do_not_reserve(app, make):
    twin, festival, club = _gear_setup(make)
    with app.app_context():
        dbm.update("events", festival, {"status": "inquiry"})
    assert _availability(app, club)[twin]["short"] == 0
    with app.app_context():
        dbm.update("events", festival, {"status": "cancelled"})
    assert _availability(app, club)[twin]["short"] == 0


def test_non_overlapping_dates_do_not_conflict(app, make):
    twin, festival, club = _gear_setup(make)
    with app.app_context():
        dbm.update("events", club, {"event_date": "2030-06-13"})
    assert _availability(app, club)[twin]["short"] == 0


def test_items_in_maintenance_are_unavailable(app, make):
    twin, festival, club = _gear_setup(make, twin_qty=10)
    with app.app_context():
        dbm.update("inventory_items", twin, {"status": "maintenance"})
    a = _availability(app, club)[twin]
    assert a["available"] == 0 and a["short"] == 2


def test_gear_page_shows_conflict(client, make):
    twin, festival, club = _gear_setup(make)
    resp = client.get(f"/events/{club}?tab=gear")
    assert b"Gear conflict" in resp.data
    assert b"Festival" in resp.data


def test_add_gear_defaults_rate_and_supports_sub_rentals(client, app, make):
    event = make("events", title="Gig", event_date="2030-01-01")
    item = make("inventory_items", name="Nord Stage", category="Keyboards", quantity=1, rental_rate=150)
    client.post(f"/events/{event}/gear", data={"item_id": item, "quantity": "1"})
    client.post(f"/events/{event}/gear", data={"description": "Hammond B3 (sub-rent)", "category": "Keyboards", "quantity": "1", "rate": "300"})
    resp = client.post(f"/events/{event}/gear", data={"quantity": "1"})
    rows = query(app, "SELECT item_id, description, rate FROM event_gear WHERE event_id = ? ORDER BY id", (event,))
    assert rows == [
        {"item_id": item, "description": None, "rate": 150},
        {"item_id": None, "description": "Hammond B3 (sub-rent)", "rate": 300},
    ]
    assert resp.status_code == 302


def test_gear_check_toggle_returns_progress(client, app, make):
    event = make("events", title="Gig", event_date="2030-01-01")
    gear = make("event_gear", event_id=event, description="Snare", quantity=1)
    make("event_gear", event_id=event, description="Kick", quantity=1)
    resp = client.post(f"/events/{event}/gear/{gear}/check", data={"field": "pulled", "value": "1"},
                       headers={"Accept": "application/json"})
    assert resp.get_json()["progress"]["pulled"] == {"done": 1, "total": 2}
    assert client.post(f"/events/{event}/gear/{gear}/check", data={"field": "bogus"}).status_code == 400
    client.post(f"/events/{event}/gear/mark-all", data={"field": "returned"})
    assert query(app, "SELECT SUM(returned) AS n FROM event_gear", one=True)["n"] == 2


def test_gear_total_counts_every_day(app, make):
    event = make("events", title="Fest", event_date="2030-06-10", end_date="2030-06-12")
    make("event_gear", event_id=event, description="Amp", quantity=2, rate=50)
    with app.app_context():
        row = dbm.query("SELECT * FROM events WHERE id = ?", (event,), one=True)
        assert services.gear_total(row) == 300


def test_checklist_toggle_records_who(client, app, make):
    event = make("events", title="Gig", event_date="2030-01-01")
    client.post(f"/events/{event}/checklist", data={"section": "Advance", "text": "Get stage plot"})
    item = query(app, "SELECT * FROM event_checklist_items", one=True)
    resp = client.post(f"/events/{event}/checklist/{item['id']}/toggle", data={"value": "1"},
                       headers={"Accept": "application/json"})
    assert resp.get_json()["progress"]["checklist"] == {"total": 1, "done": 1}
    item = query(app, "SELECT * FROM event_checklist_items", one=True)
    assert item["done"] == 1 and item["done_by"] == "admin" and item["done_at"]
    client.post(f"/events/{event}/checklist/{item['id']}/toggle", data={})
    item = query(app, "SELECT * FROM event_checklist_items", one=True)
    assert item["done"] == 0 and item["done_by"] is None


def test_crew_assignment_defaults_from_profile(client, app, make):
    event = make("events", title="Gig", event_date="2030-01-01")
    crew = make("crew", name="Maya", role="A1", day_rate=450, hourly_rate=40)
    client.post(f"/events/{event}/crew", data={"crew_id": crew, "pay_type": "flat"})
    client.post(f"/events/{event}/crew", data={"crew_id": crew, "pay_type": "hourly", "role": "A2"})
    rows = query(app, "SELECT role, pay_type, pay_rate, worksheet_key FROM event_crew ORDER BY id")
    assert [(r["role"], r["pay_type"], r["pay_rate"]) for r in rows] == [("A1", "flat", 450), ("A2", "hourly", 40)]
    assert rows[0]["worksheet_key"] != rows[1]["worksheet_key"]


def test_duplicate_copies_gear_and_checklist_not_crew(client, app, make):
    event = make("events", title="Residency", status="confirmed", event_date="2030-01-01", end_date="2030-01-02")
    make("event_gear", event_id=event, description="Amp", quantity=1, pulled=1)
    make("event_checklist_items", event_id=event, text="Advance", done=1)
    crew = make("crew", name="Sam")
    make("event_crew", event_id=event, crew_id=crew)
    resp = client.post(f"/events/{event}/duplicate", data={"event_date": "2030-02-01"})
    new_id = int(resp.headers["Location"].rsplit("/", 1)[1])
    new = query(app, "SELECT * FROM events WHERE id = ?", (new_id,), one=True)
    assert (new["status"], new["event_date"], new["end_date"]) == ("inquiry", "2030-02-01", "2030-02-02")
    assert query(app, "SELECT pulled FROM event_gear WHERE event_id = ?", (new_id,)) == [{"pulled": 0}]
    assert query(app, "SELECT done FROM event_checklist_items WHERE event_id = ?", (new_id,)) == [{"done": 0}]
    assert query(app, "SELECT * FROM event_crew WHERE event_id = ?", (new_id,)) == []


def test_calendar_spans_multi_day_events(client, make):
    make("events", title="Three Day Fest", event_date="2030-06-10", end_date="2030-06-12")
    page = client.get("/calendar?month=2030-06").data.decode()
    assert page.count('title="Three Day Fest') == 3  # one entry per day
