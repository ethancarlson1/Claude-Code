"""Crew skills and rates, gig offers they accept or decline on their own crew
page, email to crew, and the calendar feed."""

import html
import json
import smtplib

import pytest

from backline import crew, mailer
from backline import db as dbm

from .conftest import query

DAY = "2030-06-01"


@pytest.fixture
def team(make):
    """An event, and crew in every situation the offer page has to show."""
    event = make("events", title="Velvet Owls", event_date=DAY, status="confirmed", load_in_time="15:00")
    other = make("events", title="Other show", event_date=DAY, status="hold")
    ids = {
        "ana": make("crew", name="Ana Diaz", email="ana@example.com", phone="(312) 555-0110", day_rate=350),
        "ben": make("crew", name="Ben Ito", phone="(312) 555-0111", hourly_rate=30),
        "cy": make("crew", name="Cy Moss", email="cy@example.com", day_rate=500),
        "dee": make("crew", name="Dee Park", email="dee@example.com", day_rate=300),
        "eve": make("crew", name="Eve Lund", email="eve@example.com", day_rate=300),
    }
    for who, rate in (("ana", 400), ("ben", None), ("dee", None), ("eve", None)):
        make("crew_skills", crew_id=ids[who], skill="A2 / mic tech", day_rate=rate)
    make("crew_skills", crew_id=ids["cy"], skill="A1 / FOH engineer")
    make("event_crew", event_id=other, crew_id=ids["dee"], worksheet_key="dee-other")
    make("crew_unavailable", crew_id=ids["eve"], start_date="2030-05-30", end_date="2030-06-02", note="Wedding",
         added_by="crew", created_at="2030-01-01T00:00:00")
    return {"event": event, **ids}


def _offer(client, event, crew_ids, follow=True, **values):
    data = {"skill": "A2 / mic tech", "role": "A2 / mic tech", "needed": "1", "call_time": "15:00",
            "pay_type": "own", "pay_rate": "", "hours": "", "notes": "Black clothes.", "crew_ids": crew_ids, **values}
    return client.post(f"/events/{event}/crew/offer", data=data, follow_redirects=follow)


def _key(app, crew_id):
    with app.test_request_context():
        return crew.portal_key(crew_id)


# --- Skills and rates ----------------------------------------------------------------------

def test_crew_skills_and_rates_on_the_profile(client, app):
    page = client.get("/crew/new").data.decode()
    assert "Skills &amp; rates" in page and 'value="Backline tech"' in page
    resp = client.post("/crew/new", data={
        "name": "Ana Diaz", "day_rate": "350", "active": "1", "skills": ["A2 / mic tech", "Stagehand"],
        "skill_day:A2 / mic tech": "$400", "skill_hourly:Stagehand": "28.50", "skill_day:Backline tech": "999"})
    assert resp.status_code == 302
    rows = query(app, "SELECT skill, day_rate, hourly_rate FROM crew_skills ORDER BY skill")
    assert rows == [{"skill": "A2 / mic tech", "day_rate": 400, "hourly_rate": None},
                    {"skill": "Stagehand", "day_rate": None, "hourly_rate": 28.5}]  # unticked rates ignored
    page = client.get("/crew/1").data.decode()
    assert "$400.00/day" in page and "$28.50/hr" in page and "/gigs/" in page and "Their crew page" in page
    page = client.get("/crew/1/edit").data.decode()
    assert 'name="skill_day:A2 / mic tech" inputmode="decimal" value="400"' in page
    resp = client.post("/crew/1/edit", data={"name": "Ana Diaz", "skills": ["Stagehand"],
                                             "skill_hourly:Stagehand": "lots"})
    assert b"Enter rates as numbers" in resp.data
    assert len(query(app, "SELECT * FROM crew_skills")) == 2  # nothing saved
    client.post("/crew/1/edit", data={"name": "Ana Diaz", "skills": ["Stagehand"]})
    assert [r["skill"] for r in query(app, "SELECT skill FROM crew_skills")] == ["Stagehand"]
    assert "Ana Diaz" in client.get("/crew?skill=Stagehand").data.decode()
    assert "Ana Diaz" not in client.get("/crew?skill=Driver").data.decode()


def test_rate_for_a_skill_falls_back_to_the_usual_rate(app, make):
    member = make("crew", name="Ana", day_rate=350, hourly_rate=30)
    make("crew_skills", crew_id=member, skill="A2", day_rate=400)
    make("crew_skills", crew_id=member, skill="Stagehand", hourly_rate=25)
    with app.app_context():
        row = dbm.query("SELECT * FROM crew WHERE id = ?", (member,), one=True)
        assert crew.rate_for(row, "A2") == (400, 30)
        assert crew.rate_for(row, "Stagehand") == (350, 25)
        assert crew.rate_for(row, "Driver") == (350, 30)


def test_skill_list_in_settings(client, app):
    page = client.get("/settings/crew").data.decode()
    assert "A1 / FOH engineer" in page and "Not set up" in page and "BACKLINE_SMTP_HOST" in page
    client.post("/settings/crew", data={"skills": "A1\n  Stagehand \na1\n\nDriver"})
    with app.app_context():
        assert crew.skill_list() == ["A1", "Stagehand", "Driver"]


# --- Offering a gig ----------------------------------------------------------------------

def test_offer_page_shows_who_is_free_and_their_rate(client, team):
    page = html.unescape(client.get(f"/events/{team['event']}/crew/offer?skill=A2 / mic tech").data.decode())
    assert '<option selected>A2 / mic tech</option>' in page and 'value="15:00"' in page
    rows = page.split("data-candidate")[1:]
    by_name = {n: next(r for r in rows if n in r) for n in ("Ana Diaz", "Ben Ito", "Cy Moss", "Dee Park", "Eve Lund")}
    assert "$400.00/day" in by_name["Ana Diaz"] and "Free" in by_name["Ana Diaz"]
    assert "$30.00/hr" in by_name["Ben Ito"] and "No email: send by text" in by_name["Ben Ito"]
    assert "Working Other show" in by_name["Dee Park"]
    assert "Can't work: Wedding" in by_name["Eve Lund"]
    assert '"A1 / FOH engineer"' in by_name["Cy Moss"]  # filtered out in the browser by skill


def test_offers_go_out_and_the_first_to_accept_gets_the_spot(client, anon, app, team):
    resp = _offer(client, team["event"], [team["ana"], team["ben"]])
    page = html.unescape(resp.data.decode())
    assert "Offer ready for 2 people. Send it to each person with the Email or Text buttons below." in page
    assert "Crew needed" in page and "0 of 1 filled" in page
    assert "mailto:ana%40example.com?subject=Gig%20offer%3A%20A2%20/%20mic%20tech" in page
    assert "sms:3125550111?&body=" in page and "Ben Ito" in page
    offers = query(app, "SELECT * FROM crew_offers ORDER BY crew_id")
    assert [(o["pay_type"], o["pay_rate"]) for o in offers] == [("flat", 400), ("hourly", 30)]

    ana = anon.get(f"/gigs/{_key(app, team['ana'])}").data.decode()
    assert "Hi, Ana" in ana and "A2 / mic tech" in ana and "$400.00 flat" in ana and "call 3:00 PM" in ana
    assert "Black clothes." in ana and "noindex" in ana and "manifest.webmanifest" in ana
    resp = anon.post(f"/gigs/{_key(app, team['ana'])}/offers/{offers[0]['id']}",
                     data={"action": "accept", "note": "See you there"}, follow_redirects=True)
    page = resp.data.decode()
    assert "You&#39;re on the crew." in page and "Job sheet" in page
    (a,) = query(app, "SELECT * FROM event_crew WHERE event_id = ?", (team["event"],))
    assert (a["crew_id"], a["role"], a["call_time"], a["pay_type"], a["pay_rate"], a["confirmed"]) == (
        team["ana"], "A2 / mic tech", "15:00", "flat", 400, 1)
    assert [o["status"] for o in query(app, "SELECT status FROM crew_offers ORDER BY crew_id")] == ["accepted", "filled"]
    assert query(app, "SELECT status FROM crew_openings", one=True)["status"] == "filled"

    ben_key = _key(app, team["ben"])
    assert "No offers waiting" in anon.get(f"/gigs/{ben_key}").data.decode()
    resp = anon.post(f"/gigs/{ben_key}/offers/{offers[1]['id']}", data={"action": "accept"}, follow_redirects=True)
    assert b"already been filled" in resp.data
    assert len(query(app, "SELECT * FROM event_crew WHERE event_id = ?", (team["event"],))) == 1
    page = client.get(f"/events/{team['event']}?tab=crew").data.decode()
    assert "1 of 1 filled" in page and "Spot filled" in page and "“See you there”" in page


def test_declines_withdrawals_and_closing(client, anon, app, team):
    _offer(client, team["event"], [team["ana"], team["ben"], team["cy"]], needed="2", pay_type="flat",
           pay_rate="300")
    offers = {o["crew_id"]: o for o in query(app, "SELECT * FROM crew_offers")}
    assert {o["pay_rate"] for o in offers.values()} == {300}
    anon.post(f"/gigs/{_key(app, team['ana'])}/offers/{offers[team['ana']]['id']}",
              data={"action": "decline", "note": "Out of town"})
    client.post(f"/events/{team['event']}/crew/offers/{offers[team['ben']]['id']}/withdraw")
    anon.post(f"/gigs/{_key(app, team['cy'])}/offers/{offers[team['cy']]['id']}", data={"action": "accept"})
    statuses = {o["crew_id"]: (o["status"], o["note"]) for o in query(app, "SELECT * FROM crew_offers")}
    assert statuses == {team["ana"]: ("declined", "Out of town"), team["ben"]: ("withdrawn", None),
                        team["cy"]: ("accepted", None)}
    assert query(app, "SELECT status FROM crew_openings", one=True)["status"] == "open"  # 1 of 2
    page = client.get(f"/events/{team['event']}?tab=crew").data.decode()
    assert "1 of 2 filled" in page and "“Out of town”" in page
    # Offering again to someone who declined sends them a fresh offer.
    _offer(client, team["event"], [team["ana"]], needed="2",
           opening=str(query(app, "SELECT id FROM crew_openings", one=True)["id"]))
    assert query(app, "SELECT status FROM crew_offers WHERE crew_id = ?", (team["ana"],), one=True)["status"] == "sent"
    opening = query(app, "SELECT id FROM crew_openings", one=True)["id"]
    resp = client.post(f"/events/{team['event']}/crew/openings/{opening}/cancel", follow_redirects=True)
    assert b"Anyone who already accepted stays on the crew" in resp.data
    assert query(app, "SELECT status FROM crew_offers WHERE crew_id = ?", (team["ana"],), one=True)["status"] == "withdrawn"
    assert len(query(app, "SELECT * FROM event_crew WHERE event_id = ?", (team["event"],))) == 1


def test_spots_open_up_when_someone_leaves_and_openings_can_grow(client, anon, app, team):
    _offer(client, team["event"], [team["ana"]])
    opening = query(app, "SELECT id FROM crew_openings", one=True)["id"]
    offer = {"ana": query(app, "SELECT id FROM crew_offers", one=True)["id"]}
    anon.post(f"/gigs/{_key(app, team['ana'])}/offers/{offer['ana']}", data={"action": "accept"})
    page = client.get(f"/events/{team['event']}/crew/offer?opening={opening}").data.decode()
    assert "1 of 1" in page and 'name="needed" type="number" min="1" max="50" value="1"' in page
    # Offered to one more without making room: they can't take a spot.
    _offer(client, team["event"], [team["ben"]], opening=str(opening))
    offer["ben"] = query(app, "SELECT id FROM crew_offers WHERE crew_id = ?", (team["ben"],), one=True)["id"]
    resp = anon.post(f"/gigs/{_key(app, team['ben'])}/offers/{offer['ben']}", data={"action": "accept"},
                     follow_redirects=True)
    assert b"already been filled" in resp.data
    # Ana is taken off the crew: her spot opens up, and Ben can be offered it again.
    assignment = query(app, "SELECT id FROM event_crew WHERE crew_id = ? AND event_id = ?",
                       (team["ana"], team["event"]), one=True)["id"]
    client.post(f"/events/{team['event']}/crew/{assignment}/delete")
    assert query(app, "SELECT status FROM crew_offers WHERE id = ?", (offer["ana"],), one=True)["status"] == "withdrawn"
    assert query(app, "SELECT status FROM crew_openings", one=True)["status"] == "open"
    _offer(client, team["event"], [team["ben"]], opening=str(opening))
    resp = anon.post(f"/gigs/{_key(app, team['ben'])}/offers/{offer['ben']}", data={"action": "accept"},
                     follow_redirects=True)
    assert b"You&#39;re on the crew" in resp.data
    # Need one more: raise the number and offer it to Cy.
    _offer(client, team["event"], [team["cy"]], opening=str(opening), needed="2")
    cy = query(app, "SELECT id FROM crew_offers WHERE crew_id = ?", (team["cy"],), one=True)["id"]
    anon.post(f"/gigs/{_key(app, team['cy'])}/offers/{cy}", data={"action": "accept"})
    assert query(app, "SELECT needed, status FROM crew_openings", one=True) == {"needed": 2, "status": "filled"}
    assert "2 of 2 filled" in client.get(f"/events/{team['event']}?tab=crew").data.decode()


def test_offer_form_checks(client, app, team):
    resp = _offer(client, team["event"], [])
    assert b"Tick at least one person" in resp.data
    resp = _offer(client, team["event"], [team["ana"]], pay_type="flat", pay_rate="", role="", needed="0")
    page = resp.data.decode()
    assert "Enter the rate" in page and "Say what the job is" in page and "At least 1" in page
    assert not query(app, "SELECT * FROM crew_openings")


def test_old_or_cancelled_gigs_cant_be_accepted(client, anon, app, team):
    _offer(client, team["event"], [team["ana"]])
    offer = query(app, "SELECT id FROM crew_offers", one=True)["id"]
    with app.app_context():
        dbm.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (team["event"],))
    key = _key(app, team["ana"])
    assert "No offers waiting" in anon.get(f"/gigs/{key}").data.decode()
    resp = anon.post(f"/gigs/{key}/offers/{offer}", data={"action": "accept"}, follow_redirects=True)
    assert b"already been answered or closed" in resp.data
    assert not query(app, "SELECT * FROM event_crew WHERE event_id = ?", (team["event"],))


# --- Email ---------------------------------------------------------------------------

@pytest.fixture
def outbox(monkeypatch, app):
    monkeypatch.setenv("BACKLINE_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("BACKLINE_SMTP_USERNAME", "crew@example.com")
    monkeypatch.setenv("BACKLINE_SMTP_PASSWORD", "app-password")
    sent = []
    monkeypatch.setattr(mailer, "_deliver", lambda msg, config: sent.append((msg, config)))
    with app.app_context():
        dbm.set_setting("company_email", "office@example.com")
    return sent


def test_offers_are_emailed_when_email_is_set_up(client, anon, app, team, outbox):
    page = client.get(f"/events/{team['event']}/crew/offer").data.decode()
    assert "Email the offer to them now" in page
    resp = _offer(client, team["event"], [team["ana"], team["ben"]], email="1")
    page = html.unescape(resp.data.decode())
    assert "Offer emailed to Ana Diaz." in page and "No email address for Ben Ito: use the Text button below." in page
    (msg, config), = outbox
    assert config["host"] == "smtp.example.com" and config["port"] == 587
    assert msg["To"] == "ana@example.com" and msg["Reply-To"] == "office@example.com"
    assert msg["From"] == "Chicago Sound and Backline <crew@example.com>"
    assert msg["Subject"] == "Gig offer: A2 / mic tech · Jun 1, 2030 · Velvet Owls"
    body = msg.get_content()
    assert "Hi Ana," in body and "Pay: $400.00 flat" in body and "call 3:00 PM" in body
    assert f"/gigs/{_key(app, team['ana'])}" in body and "Black clothes." in body
    assert query(app, "SELECT emailed_at FROM crew_offers WHERE crew_id = ?", (team["ana"],), one=True)["emailed_at"]

    offer = query(app, "SELECT id FROM crew_offers WHERE crew_id = ?", (team["ana"],), one=True)["id"]
    anon.post(f"/gigs/{_key(app, team['ana'])}/offers/{offer}", data={"action": "accept", "note": "Yes!"})
    office = outbox[-1][0]
    assert office["To"] == "office@example.com" and office["Subject"] == "Ana Diaz accepted: A2 / mic tech · Velvet Owls"
    assert "Their note: Yes!" in office.get_content()

    resp = client.post(f"/events/{team['event']}/crew/message", data={"message": "Call moved to 2:30."},
                       follow_redirects=True)
    assert b"Update emailed to Ana Diaz." in resp.data
    update = outbox[-1][0]
    assert update["Subject"] == "Update: Velvet Owls · Jun 1, 2030" and "Call moved to 2:30." in update.get_content()
    assert "/worksheet/" in update.get_content()


def test_email_problems_are_explained(client, app, team, outbox, monkeypatch):
    def refuse(_msg, _config):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(mailer, "_deliver", refuse)
    resp = _offer(client, team["event"], [team["ana"]], email="1")
    page = html.unescape(resp.data.decode())
    assert "Some offers weren't emailed." in page and "app password" in page
    assert query(app, "SELECT status, emailed_at FROM crew_offers", one=True) == {"status": "sent", "emailed_at": None}
    resp = client.post("/settings/crew", data={"action": "test", "to": "me@example.com"}, follow_redirects=True)
    assert b"app password" in resp.data


def test_test_email_from_settings(client, outbox):
    page = client.get("/settings/crew").data.decode()
    assert "Set up" in page and "crew@example.com" in page
    resp = client.post("/settings/crew", data={"action": "test", "to": "me@example.com"}, follow_redirects=True)
    assert b"Test email sent to me@example.com" in resp.data and outbox[0][0]["To"] == "me@example.com"


def test_without_email_set_up_updates_open_the_mail_app(client, app, team, make):
    make("event_crew", event_id=team["event"], crew_id=team["ana"], confirmed=1, worksheet_key="ana-key")
    page = client.get(f"/events/{team['event']}?tab=crew").data.decode()
    assert "mailto:?bcc=ana%40example.com" in page
    with app.app_context():
        assert not mailer.configured()


# --- The crew page ---------------------------------------------------------------------

def test_crew_page_gigs_pay_and_days_off(client, anon, app, team, make):
    make("event_crew", event_id=team["event"], crew_id=team["ana"], role="A2", call_time="14:00", pay_type="hourly",
         pay_rate=40, hours=8, confirmed=1, worksheet_key="ana-key")
    key = _key(app, team["ana"])
    page = anon.get(f"/gigs/{key}").data.decode()
    assert "Velvet Owls" in page and "$320.00" in page and "$40.00/hr × 8 hrs est." in page
    assert "/worksheet/" in page and f"webcal://localhost/gigs/{key}/calendar.ics" in page
    assert "A2 / mic tech" in page and "$400.00/day" in page  # their rates on file

    resp = anon.post(f"/gigs/{key}/unavailable", data={"start_date": "2030-07-04", "end_date": "2030-07-06",
                                                       "note": "Family trip"}, follow_redirects=True)
    assert b"We won&#39;t offer you gigs on those days" in resp.data and b"Family trip" in resp.data
    resp = anon.post(f"/gigs/{key}/unavailable", data={"start_date": "2030-07-06", "end_date": "2030-07-04"},
                     follow_redirects=True)
    assert b"can&#39;t be before the first" in resp.data
    row = query(app, "SELECT * FROM crew_unavailable WHERE crew_id = ?", (team["ana"],), one=True)
    assert row["added_by"] == "crew"
    assert "Family trip" in client.get(f"/crew/{team['ana']}").data.decode()  # the office sees it
    anon.post(f"/gigs/{key}/unavailable/{row['id']}/delete")
    assert not query(app, "SELECT * FROM crew_unavailable WHERE crew_id = ?", (team["ana"],))

    ics = anon.get(f"/gigs/{key}/calendar.ics")
    text = ics.data.decode()
    assert ics.mimetype == "text/calendar" and "X-WR-CALNAME:Chicago Sound and Backline gigs" in text
    assert "SUMMARY:Velvet Owls (A2)" in text and "DTSTART:20300601T140000" in text and "worksheet" in text
    manifest = json.loads(anon.get(f"/gigs/{key}/manifest.webmanifest").data)
    assert manifest["start_url"] == f"/gigs/{key}" and manifest["display"] == "standalone"


def test_crew_page_links_are_private(client, anon, app, team):
    assert anon.get("/gigs/not-a-key").status_code == 404
    key = _key(app, team["ana"])
    client.post(f"/crew/{team['ana']}/portal-link")
    assert anon.get(f"/gigs/{key}").status_code == 404
    assert anon.get(f"/gigs/{_key(app, team['ana'])}").status_code == 200
    assert anon.get(f"/crew/{team['ana']}").status_code == 302  # the office page still needs a sign-in


def test_office_can_mark_days_off(client, app, team):
    resp = client.post(f"/crew/{team['ana']}/unavailable", data={"start_date": "2030-06-01", "note": "Asked off"},
                       follow_redirects=True)
    assert b"Asked off" in resp.data
    page = html.unescape(client.get(f"/events/{team['event']}/crew/offer").data.decode())
    ana_row = next(r for r in page.split("data-candidate")[1:] if "Ana Diaz" in r)
    assert "Can't work: Asked off" in ana_row


def test_own_day_rates_cover_every_day_of_the_event(client, app, make):
    fest = make("events", title="Three-day festival", event_date="2030-08-01", end_date="2030-08-03", status="hold")
    member = make("crew", name="Sam Reyes", day_rate=250, hourly_rate=28)
    hourly_only = make("crew", name="Lee Ray", hourly_rate=30)
    page = client.get(f"/events/{fest}/crew/offer").data.decode()
    assert "day rates × 3 days" in page
    _offer(client, fest, [member, hourly_only], skill="", role="Stagehand", hours="10")
    offers = query(app, "SELECT pay_type, pay_rate, hours FROM crew_offers ORDER BY crew_id")
    assert offers == [{"pay_type": "flat", "pay_rate": 750, "hours": 10}, {"pay_type": "hourly", "pay_rate": 30, "hours": 10}]


def test_dashboard_flags_open_crew_spots(client, app, make):
    from backline import util

    soon = make("events", title="Soon show", event_date=(util.today()).isoformat(), status="confirmed")
    member = make("crew", name="Ana Diaz", day_rate=300)
    _offer(client, soon, [member], skill="", role="A2", needed="2")
    assert "2 crew spots still open for Soon show" in client.get("/").data.decode()
