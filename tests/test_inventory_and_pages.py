import io
import re
from datetime import date

import pytest

from backline import util
from backline import db as dbm
from backline.seed import seed

from .conftest import query


def test_csv_import_and_export(client, app):
    csv_text = (
        "Name,Category,Quantity,Rental Rate,Status\n"
        "Shure SM58,microphones,20,8,\n"
        "Mystery box,Not A Category,1,,\n"
        ",Drums,1,,\n"
    )
    resp = client.post("/inventory/import", data={"file": (io.BytesIO(csv_text.encode()), "gear.csv")},
                       content_type="multipart/form-data")
    page = resp.data.decode()
    assert "1 item(s) added" in page
    assert "Row 3" in page and "Row 4" in page
    item = query(app, "SELECT name, category, quantity, rental_rate, status FROM inventory_items", one=True)
    assert item == {"name": "Shure SM58", "category": "Microphones", "quantity": 20, "rental_rate": 8, "status": "active"}
    export = client.get("/inventory/export.csv").data.decode()
    assert export.splitlines()[0].startswith("name,category,make")
    assert "Shure SM58,Microphones" in export


def test_inventory_availability_filter(client, make):
    item = make("inventory_items", name="Twin", category="Guitar Amps", quantity=3)
    event = make("events", title="Gig", status="confirmed", event_date="2030-03-03")
    make("event_gear", event_id=event, item_id=item, quantity=2)
    page = client.get("/inventory?date=2030-03-03").data.decode()
    assert "Booked Mar 3, 2030" in page
    assert re.search(r"<strong class=\"\">1</strong>", page)


def test_cannot_delete_item_used_on_events(client, app, make):
    item = make("inventory_items", name="Twin", category="Guitar Amps", quantity=1)
    event = make("events", title="Gig", event_date="2030-03-03")
    make("event_gear", event_id=event, item_id=item, quantity=1)
    client.post(f"/inventory/{item}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM inventory_items", one=True)["n"] == 1


def test_people_crud(client, app):
    resp = client.post("/venues/new", data={"name": "Blue Door", "city": "Chicago"})
    venue_id = int(resp.headers["Location"].rsplit("/", 1)[1])
    client.post(f"/venues/{venue_id}/edit", data={"name": "Blue Door Lounge", "city": "Chicago"})
    assert query(app, "SELECT name FROM venues", one=True)["name"] == "Blue Door Lounge"
    client.post("/crew/new", data={"name": "Jordan", "day_rate": "300"})  # active unchecked -> 0
    assert query(app, "SELECT active, day_rate FROM crew", one=True) == {"active": 0, "day_rate": 300}
    assert client.get("/nope/1").status_code == 404
    client.post(f"/venues/{venue_id}/delete")
    assert query(app, "SELECT COUNT(*) AS n FROM venues", one=True)["n"] == 0


def test_settings_and_checklist_templates(client, app):
    client.post("/settings", data={
        "company_name": "Chicago Sound and Backline", "default_tax_rate": "8.5", "deposit_percent": "40",
        "invoice_prefix": "CA-", "contract_prefix": "K-", "contract_template": "Hi {{client_name}}",
    })
    with app.app_context():
        assert dbm.get_setting("company_name") == "Chicago Sound and Backline"
        assert dbm.get_setting("default_tax_rate") == "8.5"
    client.post("/settings/checklists/new", data={
        "name": "Festival", "items": "# Advance\n- [ ] Get rider\nConfirm power\n\n# Show\nLine check",
    })
    items = query(app, """SELECT i.section, i.text FROM checklist_template_items i
                          JOIN checklist_templates t ON t.id = i.template_id WHERE t.name = 'Festival' ORDER BY sort""")
    assert [(i["section"], i["text"]) for i in items] == [
        ("Advance", "Get rider"), ("Advance", "Confirm power"), ("Show", "Line check")]


def test_util_formatting():
    assert util.ftime("19:05") == "7:05 PM"
    assert util.ftime("00:30") == "12:30 AM"
    assert util.money(1234.5) == "$1,234.50"
    assert util.money(-3) == "-$3.00"
    assert util.fdate("2026-11-07") == "Sat, Nov 7, 2026"
    assert re.fullmatch(r"2026-11-07-Alvarez-Sofia-[A-Z0-9]{4}", util.gen_reference("2026-11-07", "Sofia Alvarez"))
    assert re.fullmatch(r"2026-11-07-Lakefront-Harvest-Festival-[A-Z0-9]{4}",
                        util.gen_reference("2026-11-07", "Lakefront Harvest Festival"))
    assert re.fullmatch(r"2026-11-07-Spring-Gala-[A-Z0-9]{4}", util.gen_reference("2026-11-07", None, "Spring Gala"))


@pytest.fixture
def seeded(client, app):
    with app.app_context():
        seed()
    return client


def test_every_page_renders_with_demo_data(seeded, app):
    with app.app_context():
        events = [r["id"] for r in dbm.query("SELECT id FROM events")]
        contracts = [r["id"] for r in dbm.query("SELECT id FROM contracts")]
        invoices = [r["id"] for r in dbm.query("SELECT id FROM invoices")]
        items = [r["id"] for r in dbm.query("SELECT id FROM inventory_items")]
    pages = ["/", "/calendar", "/events?when=all", "/inventory", f"/inventory?date={date.today()}", "/inventory/import",
             "/crew", "/clients", "/venues", "/crew/1", "/clients/1", "/venues/1", "/contracts", "/contracts/new",
             "/invoices", "/invoices/new", "/settings", "/settings/checklists", "/settings/checklists/1", "/settings/users",
             "/settings/event-types", "/crew-pay", "/crew-pay?status=all", "/crew-pay?status=paid",
             "/crew-pay?status=upcoming", "/crew-pay/export.csv"]
    for e in events:
        pages += [f"/events/{e}?tab={t}" for t in ("overview", "crew", "gear", "transport", "checklist", "chat",
                                                    "documents")]
        pages += [f"/events/{e}/edit", f"/events/{e}/worksheet", f"/contracts/new?event_id={e}", f"/invoices/new?event_id={e}"]
    pages += [f"/contracts/{c}" for c in contracts] + [f"/invoices/{i}" for i in invoices]
    pages += [f"/invoices/{i}/edit" for i in invoices] + [f"/inventory/{i}" for i in items[:5]]
    pages += [f"/crew/{c}" for c in range(1, 7)]
    pages += ["/vehicles", "/vehicles/new"] + [f"/vehicles/{v}" for v in range(1, 5)] + [f"/vehicles/{v}/edit" for v in (1, 2)]
    with app.app_context():
        pages += [f"/events/{f['event_id']}/files/{f['id']}" for f in dbm.query("SELECT id, event_id FROM event_files")]
    failures = [(p, seeded.get(p).status_code) for p in pages if seeded.get(p).status_code != 200]
    assert failures == []


def test_demo_data_shows_expected_alerts(seeded):
    page = seeded.get("/").data.decode()
    assert "Gear conflicts" in page and "Lakefront Harvest Festival" in page
    assert "Gear not checked back in" in page
    assert "Overdue invoices" in page
    assert "Deposits overdue" in page and "Crew pay overdue" in page and "Sam Reyes" in page
    assert "Vehicle conflicts" in page and "Box Truck 1" in page
    assert "Vehicle paperwork" in page and "Sprinter Van" in page
    crew_pay = seeded.get("/crew-pay?status=all").data.decode()
    assert "Payroll run" in crew_pay and "overdue" in crew_pay and "upcoming" in crew_pay
