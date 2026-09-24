"""The platform handles corporate, concert, party, festival, wedding and
dry-hire work alike: event types drive labels, run of show and checklists."""

import re

from backline import db as dbm
from backline import services

from .conftest import query


def _type(app, name):
    return query(app, "SELECT * FROM event_types WHERE name = ?", (name,), one=True)


def _checklist_ids(app, type_name):
    with app.app_context():
        return services.event_type_checklist_ids(_type(app, type_name)["id"])


def test_default_event_types_cover_the_business(app):
    names = [r["name"] for r in query(app, "SELECT name FROM event_types ORDER BY sort")]
    for expected in ("Corporate / Speaking", "Live Concert", "Club / Bar Show", "Festival / Outdoor",
                     "Private Party", "Fundraiser / Gala", "Wedding", "Theater / Performance",
                     "Worship / Community", "Backline / Dry Hire", "Other"):
        assert expected in names
    assert names[0] == "Corporate / Speaking"  # weddings aren't the default
    assert _type(app, "Corporate / Speaking")["people_label"] == "Speakers / presenters"
    assert _type(app, "Live Concert")["venue_label"] == "Main stage"


def test_new_event_form_follows_the_type(client, app):
    page = client.get("/events/new?type=Corporate / Speaking").data.decode()
    assert "PRESENTERS &amp; MICS:" in page
    assert '<label for="f-honorees">Speakers / presenters</label>' in page
    corporate = set(_checklist_ids(app, "Corporate / Speaking"))
    for t in query(app, "SELECT id FROM checklist_templates"):
        checked = f'value="{t["id"]}" checked' in page
        assert checked == (t["id"] in corporate)
    assert "event-type-profiles" in page and "Artists / headliner" in page  # profiles for the JS

    plain = client.get("/events/new").data.decode()
    run_of_show = re.search(r'<textarea id="f-run_of_show"[^>]*>(.*?)</textarea>', plain, re.S).group(1)
    assert '<label for="f-honorees">Key people</label>' in plain
    assert "RUN OF SHOW:" in run_of_show and "PRESENTERS" not in run_of_show


def test_checklists_apply_in_the_type_order(client, app):
    concert = _checklist_ids(app, "Live Concert")
    client.post("/events/new", data={
        "title": "Owls at the Hall", "event_type": "Live Concert", "status": "confirmed",
        "event_date": "2030-05-01", "templates": [str(i) for i in reversed(concert)],
    })
    texts = [r["text"] for r in query(app, "SELECT text FROM event_checklist_items ORDER BY sort")]
    assert texts[0] == "Confirm date, times and scope with client"  # Advance & Prep first
    assert texts.index("Stage plot and input list received") < texts.index("Crew arrives at call time")
    assert texts[-1] == "Record crew hours for payroll"  # Load-Out & Return last


def test_worksheet_labels_follow_event_type(anon, app, make):
    venue = make("venues", name="Fulton Market Event Loft", city="Chicago", state="IL")
    speaker_event = make("events", title="All-Hands", event_type="Corporate / Speaking", event_date="2030-03-01",
                         reference_number="R-CORP", venue_id=venue, honorees="CEO keynote: lav 1",
                         service_type="PA + engineer", setting="Indoor", guest_count=400, input_count=14,
                         wireless_count=8, monitor_mixes=1, playback_feeds="Record feed to video")
    party = make("events", title="40th", event_type="Private Party", event_date="2030-03-02",
                 reference_number="R-PARTY", venue_id=venue, venue_label="Roof deck", honorees="Jamal")
    crew = make("crew", name="Maya")
    make("event_crew", event_id=speaker_event, crew_id=crew, worksheet_key="k1")
    make("event_crew", event_id=party, crew_id=crew, worksheet_key="k2")

    page = anon.get("/worksheet/R-CORP/k1").data.decode()
    assert "Speakers / presenters" in page and "CEO keynote: lav 1" in page
    assert "General session" in page  # the type's location label
    assert "Couple" not in page
    for spec in ("PA + engineer", "Indoor", "400", "14", "Wireless mics", "Monitor mixes", "Record feed to video"):
        assert spec in page

    page = anon.get("/worksheet/R-PARTY/k2").data.decode()
    assert "Host / guest of honor" in page
    assert "Roof deck" in page and "Party space" not in page  # the event's own label wins


def test_manage_event_types(client, app, make):
    advance = query(app, "SELECT id FROM checklist_templates WHERE name = 'Advance & Prep'", one=True)["id"]
    resp = client.post("/settings/event-types/new", data={
        "name": "Conference / Multi-room", "people_label": "Speakers", "venue_label": "Plenary",
        "venue2_label": "Breakout", "run_of_show": "ROOMS:", "checklists": [str(advance)],
    })
    assert resp.status_code == 302
    conf = _type(app, "Conference / Multi-room")
    assert conf["people_label"] == "Speakers" and _checklist_ids(app, "Conference / Multi-room") == [advance]
    assert client.post("/settings/event-types/new", data={"name": "Wedding"}).status_code == 200  # duplicate name

    event = make("events", title="Summit", event_type="Conference / Multi-room", event_date="2030-04-01")
    client.post(f"/settings/event-types/{conf['id']}", data={"name": "Conference", "people_label": "Speakers"})
    assert query(app, "SELECT event_type FROM events WHERE id = ?", (event,), one=True)["event_type"] == "Conference"

    # Deleting a type keeps the event's type name, and the event still saves.
    client.post(f"/settings/event-types/{conf['id']}/delete")
    assert _type(app, "Conference") is None
    resp = client.post(f"/events/{event}/edit", data={"title": "Summit", "event_type": "Conference",
                                                      "status": "inquiry", "event_date": "2030-04-01"})
    assert resp.status_code == 302
    assert query(app, "SELECT event_type FROM events WHERE id = ?", (event,), one=True)["event_type"] == "Conference"


def test_events_list_filters_by_type(client, make):
    make("events", title="Keynote Day", event_type="Corporate / Speaking", event_date="2030-01-01")
    make("events", title="Owls Live", event_type="Live Concert", event_date="2030-01-02")
    page = client.get("/events?when=all&type=Live Concert").data.decode()
    assert "Owls Live" in page and "Keynote Day" not in page


def test_contract_mentions_event_type_and_service(client, app, make):
    event = make("events", title="All-Hands", event_type="Corporate / Speaking", service_type="PA + engineer",
                 event_date="2030-03-01")
    client.post("/contracts/new", data={"event_id": event, "title": "A", "total_amount": "100", "deposit_amount": "50"})
    body = query(app, "SELECT body FROM contracts", one=True)["body"]
    assert "All-Hands (Corporate / Speaking)" in body and "Service: PA + engineer" in body


def test_defaults_are_seeded_once(app, ctx):
    before = dbm.scalar("SELECT COUNT(*) FROM event_types")
    dbm.init_db()
    assert dbm.scalar("SELECT COUNT(*) FROM event_types") == before
