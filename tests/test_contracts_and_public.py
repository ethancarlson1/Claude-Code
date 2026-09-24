from .conftest import query


def _event_with_gear(make):
    cl = make("clients", name="Daniel Lange", email="d@example.com")
    venue = make("venues", name="Bayview Ballroom", address="100 Harbor Way", city="Bayview", state="CA")
    event = make("events", title="Lange Wedding", reference_number="2030-11-07-Lange-Daniel-TJ1R",
                 client_id=cl, venue_id=venue, event_date="2030-11-07", start_time="18:00", status="confirmed")
    make("event_gear", event_id=event, description="Fender Twin Reverb", quantity=1, rate=95)
    make("event_gear", event_id=event, description="Shure SM58", quantity=6, rate=8)
    return event


def test_contract_created_from_template(client, app, make):
    event = _event_with_gear(make)
    page = client.get(f"/contracts/new?event_id={event}").data.decode()
    assert 'value="143.00"' in page  # gear total pre-filled
    resp = client.post("/contracts/new", data={
        "event_id": event, "title": "Agreement", "total_amount": "1000", "deposit_amount": "500",
        "balance_due_date": "2030-10-31",
    })
    assert resp.status_code == 302
    contract = query(app, "SELECT * FROM contracts", one=True)
    body = contract["body"]
    assert "Daniel Lange" in body
    assert "Bayview Ballroom, 100 Harbor Way, Bayview, CA" in body
    assert "6 x Shure SM58" in body
    assert "$1,000.00" in body and "$500.00" in body
    assert "6:00 PM" in body
    assert "{{" not in body
    assert contract["status"] == "draft"


def test_deposit_cannot_exceed_total(client, app, make):
    event = _event_with_gear(make)
    resp = client.post("/contracts/new", data={"event_id": event, "title": "A", "total_amount": "100", "deposit_amount": "200"})
    assert resp.status_code == 200
    assert b"Deposit can&#39;t be more than the total" in resp.data


def test_contract_signing_flow(client, anon, app, make):
    event = _event_with_gear(make)
    client.post("/contracts/new", data={"event_id": event, "title": "A", "total_amount": "100", "deposit_amount": "50"})
    contract = query(app, "SELECT * FROM contracts", one=True)
    key = contract["public_key"]
    assert anon.get(f"/c/{key}").status_code == 404  # drafts aren't shared

    client.post(f"/contracts/{contract['id']}/status", data={"action": "send"})
    page = anon.get(f"/c/{key}")
    assert page.status_code == 200 and b"Sign this agreement" in page.data

    resp = anon.post(f"/c/{key}/sign", data={"signed_name": "Daniel Lange"})
    assert resp.status_code == 400  # must tick agree
    anon.post(f"/c/{key}/sign", data={"signed_name": "Daniel Lange", "agree": "1"})
    contract = query(app, "SELECT * FROM contracts", one=True)
    assert contract["status"] == "signed" and contract["signed_name"] == "Daniel Lange" and contract["signed_at"]

    anon.post(f"/c/{key}/sign", data={"signed_name": "Someone Else", "agree": "1"})
    assert query(app, "SELECT signed_name FROM contracts", one=True)["signed_name"] == "Daniel Lange"
    # Signed contracts are locked.
    assert client.get(f"/contracts/{contract['id']}/edit").status_code == 302
    client.post(f"/contracts/{contract['id']}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM contracts", one=True)["n"] == 1


def test_crew_worksheet_is_private_per_person(anon, app, make):
    event = _event_with_gear(make)
    maya = make("crew", name="Maya Ortiz", phone="555-1111")
    sam = make("crew", name="Sam Reyes", phone="555-2222")
    make("event_crew", event_id=event, crew_id=maya, role="A1", call_time="14:00", pay_rate=450, worksheet_key="mayakey")
    make("event_crew", event_id=event, crew_id=sam, role="Stagehand", pay_rate=280, worksheet_key="samkey")
    ref = "2030-11-07-Lange-Daniel-TJ1R"

    page = anon.get(f"/worksheet/{ref}/mayakey").data.decode()
    assert "PREPARED FOR" in page and "Maya Ortiz" in page and "$450.00" in page
    assert "$280.00" not in page  # other crew pay is hidden
    assert "Sam Reyes" in page and "555-2222" in page  # but the crew list is shared
    assert "Fender Twin Reverb" in page and "2:00 PM" in page

    assert anon.get(f"/worksheet/{ref}/nope").status_code == 404
    assert anon.get("/worksheet/2030-01-01-Other-XXXX/mayakey").status_code == 404

    anon.post(f"/worksheet/{ref}/mayakey/confirm")
    assert query(app, "SELECT confirmed FROM event_crew WHERE worksheet_key = 'mayakey'", one=True)["confirmed"] == 1
    anon.post(f"/worksheet/{ref}/mayakey/confirm", data={"decline": "1"})
    assert query(app, "SELECT confirmed FROM event_crew WHERE worksheet_key = 'mayakey'", one=True)["confirmed"] == 0


def test_admin_worksheet_shows_all_pay(client, make):
    event = _event_with_gear(make)
    crew = make("crew", name="Sam Reyes")
    make("event_crew", event_id=event, crew_id=crew, pay_rate=280)
    page = client.get(f"/events/{event}/worksheet").data.decode()
    assert "$280.00" in page and "PREPARED FOR" not in page


def test_event_with_signed_contract_cannot_be_deleted(client, app, make):
    event = _event_with_gear(make)
    make("contracts", event_id=event, number="K-1", title="A", body="x", status="signed", public_key="k1")
    client.post(f"/events/{event}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM events", one=True)["n"] == 1
    other = make("events", title="Throwaway", event_date="2030-01-01")
    client.post(f"/events/{other}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM events", one=True)["n"] == 1
