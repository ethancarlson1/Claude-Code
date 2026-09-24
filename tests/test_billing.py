from datetime import date, timedelta
from decimal import Decimal

from backline import services
from backline import db as dbm

from .conftest import query


def _totals(app, invoice_id):
    with app.app_context():
        inv = dbm.query("SELECT * FROM invoices WHERE id = ?", (invoice_id,), one=True)
        totals = services.invoice_totals(inv)
        return totals, services.invoice_status(inv, totals)


def _invoice(make, **values):
    values.setdefault("number", f"T-{values.get('status', 'draft')}-{len(values)}")
    values.setdefault("issue_date", date.today().isoformat())
    values.setdefault("public_key", values["number"] + "-key")
    return make("invoices", **values)


def test_totals_with_discount_tax_and_non_taxable_lines(app, make):
    inv = _invoice(make, tax_rate=10, discount=100)
    make("invoice_items", invoice_id=inv, description="Backline", quantity=2, unit_price=150)   # 300 taxable
    make("invoice_items", invoice_id=inv, description="Labor", quantity=1, unit_price=100, taxable=0)  # 100
    totals, status = _totals(app, inv)
    # Discount of 100 spread 3:1 across taxable/non-taxable -> taxable base 225 -> tax 22.50
    assert totals["subtotal"] == Decimal("400.00")
    assert totals["tax"] == Decimal("22.50")
    assert totals["total"] == Decimal("322.50")
    assert status == "draft"


def test_status_progression(app, make):
    today = date.today()
    inv = _invoice(make, status="sent", due_date=(today + timedelta(days=5)).isoformat())
    make("invoice_items", invoice_id=inv, description="PA", quantity=1, unit_price=500)
    assert _totals(app, inv)[1] == "sent"
    make("payments", invoice_id=inv, paid_on=today.isoformat(), amount=200)
    totals, status = _totals(app, inv)
    assert (status, totals["balance"]) == ("partial", Decimal("300.00"))
    with app.app_context():
        dbm.update("invoices", inv, {"due_date": (today - timedelta(days=1)).isoformat()})
    assert _totals(app, inv)[1] == "overdue"
    make("payments", invoice_id=inv, paid_on=today.isoformat(), amount=300)
    assert _totals(app, inv)[1] == "paid"
    with app.app_context():
        dbm.update("invoices", inv, {"status": "void"})
    assert _totals(app, inv)[1] == "void"


def test_new_invoice_prefills_from_event_gear(client, app, make):
    cl = make("clients", name="Ruby")
    event = make("events", title="Fest", client_id=cl, event_date="2030-06-10", end_date="2030-06-11")
    make("event_gear", event_id=event, description="Twin Reverb", quantity=2, rate=95)
    make("event_gear", event_id=event, description="Free loaner", quantity=1, rate=0)
    resp = client.post("/invoices/new", data={
        "event_id": event, "client_id": cl, "issue_date": "2030-05-01", "due_date": "2030-05-15", "prefill": "1",
    })
    assert resp.status_code == 302
    inv = query(app, "SELECT * FROM invoices", one=True)
    assert inv["number"] == f"INV-{date.today().year}-0001"
    items = query(app, "SELECT description, quantity, unit_price FROM invoice_items")
    assert items == [{"description": "Twin Reverb (2 days @ $95.00/day)", "quantity": 2, "unit_price": 190}]


def test_invoice_numbers_increment(app, ctx):
    year = date.today().year
    assert services.next_number("invoices", "INV-") == f"INV-{year}-0001"
    dbm.insert("invoices", {"number": f"INV-{year}-0009", "issue_date": "2030-01-01", "public_key": "k"})
    assert services.next_number("invoices", "INV-") == f"INV-{year}-0010"


def test_edit_replaces_line_items(client, app, make):
    inv = _invoice(make)
    make("invoice_items", invoice_id=inv, description="Old", quantity=1, unit_price=1)
    resp = client.post(f"/invoices/{inv}/edit", data={
        "issue_date": "2030-01-01", "tax_rate": "8.25", "discount": "",
        "item_description": ["Drum kit", "", "Delivery"],
        "item_quantity": ["1", "", "1"],
        "item_price": ["175", "", "$1,200.50"],
        "item_taxable": ["1", "1", "0"],
    })
    assert resp.status_code == 302
    items = query(app, "SELECT description, unit_price, taxable FROM invoice_items ORDER BY sort")
    assert items == [
        {"description": "Drum kit", "unit_price": 175, "taxable": 1},
        {"description": "Delivery", "unit_price": 1200.5, "taxable": 0},
    ]
    assert query(app, "SELECT tax_rate, discount FROM invoices", one=True) == {"tax_rate": 8.25, "discount": 0}


def test_edit_rejects_bad_lines(client, app, make):
    inv = _invoice(make)
    resp = client.post(f"/invoices/{inv}/edit", data={
        "issue_date": "2030-01-01", "item_description": ["Kit"], "item_quantity": ["abc"], "item_price": ["1"],
    })
    assert resp.status_code == 200
    assert b"must be numbers" in resp.data


def test_payments_and_status_actions(client, app, make):
    inv = _invoice(make)
    make("invoice_items", invoice_id=inv, description="PA", quantity=1, unit_price=500)
    client.post(f"/invoices/{inv}/payments", data={"paid_on": "2030-01-02", "amount": "500", "method": "Check"})
    totals, status = _totals(app, inv)
    assert status == "paid"  # recording a payment on a draft marks it sent
    assert client.post(f"/invoices/{inv}/delete").status_code == 302
    assert query(app, "SELECT COUNT(*) AS n FROM invoices", one=True)["n"] == 1  # only drafts delete
    client.post(f"/invoices/{inv}/status", data={"action": "void"})
    assert _totals(app, inv)[1] == "void"
    assert client.post(f"/invoices/{inv}/status", data={"action": "send"}).status_code == 400


def test_public_invoice_hidden_until_sent(client, anon, app, make):
    inv = _invoice(make, number="INV-X", public_key="pubkey123")
    assert anon.get("/i/pubkey123").status_code == 404
    client.post(f"/invoices/{inv}/status", data={"action": "send"})
    resp = anon.get("/i/pubkey123")
    assert resp.status_code == 200 and b"INV-X" in resp.data
