"""Money in (client deposits and payments) and money out (crew pay)."""

from datetime import date, timedelta
from decimal import Decimal

from backline import db as dbm
from backline import services

from .conftest import query

TODAY = date.today()


def day(n):
    return (TODAY + timedelta(days=n)).isoformat()


def _crew_job(make, event_date, pay_type="flat", rate=300, hours=None, status="confirmed", **extra):
    name = extra.pop("name", "Sam Reyes")
    event = make("events", title=f"Gig {event_date}", status=status, event_date=event_date,
                 reference_number=f"R-{event_date}-{name}")
    crew = make("crew", name=name, w9_on_file=extra.pop("w9", 0))
    return make("event_crew", event_id=event, crew_id=crew, pay_type=pay_type, pay_rate=rate, hours=hours,
                worksheet_key=f"k-{event}-{crew}", **extra), event, crew


def _table(resp):
    """The crew pay table (the filter dropdowns list every crew member)."""
    page = resp.data.decode()
    return page[page.index("<table>"):page.index("</table>")]


def _pay_row(app, assignment_id):
    with app.app_context():
        return services.crew_pay_rows("a.id = ?", (assignment_id,))[0]


# --- Crew pay -------------------------------------------------------------------

def test_amount_due(app, make):
    flat, _, _ = _crew_job(make, day(-3), rate=450)
    est, _, _ = _crew_job(make, day(-3), "hourly", 28, hours=10, name="B")
    actual, _, _ = _crew_job(make, day(-3), "hourly", 28, hours=10, actual_hours=11.5, name="C")
    final, _, _ = _crew_job(make, day(-3), "hourly", 28, hours=10, final_amount=400, name="D")
    assert _pay_row(app, flat)["due"] == Decimal("450.00")
    assert _pay_row(app, est)["due"] == Decimal("280.00")
    assert _pay_row(app, actual)["due"] == Decimal("322.00")
    assert _pay_row(app, final)["due"] == Decimal("400.00")


def test_pay_status(app, make):
    upcoming, _, _ = _crew_job(make, day(3))
    today_job, _, _ = _crew_job(make, day(0), name="B")
    owed, _, _ = _crew_job(make, day(-1), name="C")
    overdue, _, _ = _crew_job(make, day(-30), name="D")
    cancelled, _, _ = _crew_job(make, day(-30), status="cancelled", name="E")
    completed_early, _, _ = _crew_job(make, day(2), status="completed", name="F")
    paid, _, _ = _crew_job(make, day(-30), paid_on=day(-20), paid_amount=300, name="G")
    statuses = {k: _pay_row(app, k)["pay_status"] for k in
                (upcoming, today_job, owed, overdue, cancelled, completed_early, paid)}
    assert statuses == {upcoming: "upcoming", today_job: "upcoming", owed: "owed", overdue: "overdue",
                        cancelled: "cancelled", completed_early: "owed", paid: "paid"}


def test_pay_days_setting_moves_the_overdue_line(client, app, make):
    job, _, _ = _crew_job(make, day(-10))
    assert _pay_row(app, job)["pay_status"] == "owed"  # default: 14 days
    with app.app_context():
        dbm.set_setting("crew_pay_days", "7")
    assert _pay_row(app, job)["pay_status"] == "overdue"


def test_crew_pay_page_and_batch_payment(client, app, make):
    a, event_a, crew_a = _crew_job(make, day(-5), rate=450, name="Maya Ortiz")
    b, _, _ = _crew_job(make, day(-40), "hourly", 28, hours=10, actual_hours=9, name="Sam Reyes")
    future, _, _ = _crew_job(make, day(10), rate=300, name="Jordan Pike")

    page = _table(client.get("/crew-pay"))
    assert "Maya Ortiz" in page and "Sam Reyes" in page and "Jordan Pike" not in page  # owed only
    assert "$702.00" in page  # 450 + 28 × 9 owed
    assert "Jordan Pike" in _table(client.get("/crew-pay?status=upcoming"))
    assert "Sam Reyes" not in _table(client.get(f"/crew-pay?event_id={event_a}"))

    resp = client.post("/crew-pay/mark-paid", data={"ids": [str(a), str(b)], "paid_on": day(-1),
                                                     "method": "Zelle", "reference": "Payroll 12", "next": "/crew-pay"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/crew-pay")
    rows = {r["id"]: r for r in query(app, "SELECT * FROM event_crew")}
    assert (rows[a]["paid_on"], rows[a]["paid_amount"], rows[a]["paid_method"], rows[a]["paid_reference"]) == \
        (day(-1), 450, "Zelle", "Payroll 12")
    assert rows[b]["paid_amount"] == 252
    assert rows[future]["paid_on"] is None
    assert "Everyone's paid up." in client.get("/crew-pay").data.decode()

    client.post("/crew-pay/mark-unpaid", data={"ids": [str(b)]})
    assert query(app, "SELECT paid_on FROM event_crew WHERE id = ?", (b,), one=True)["paid_on"] is None


def test_mark_paid_validation(client, app, make):
    a, _, _ = _crew_job(make, day(-5))
    client.post("/crew-pay/mark-paid", data={"ids": [str(a)], "paid_on": ""})
    client.post("/crew-pay/mark-paid", data={"paid_on": day(0)})
    assert query(app, "SELECT paid_on FROM event_crew", one=True)["paid_on"] is None
    resp = client.post("/crew-pay/mark-paid", data={"ids": [str(a)], "paid_on": day(0), "next": "https://evil.example"})
    assert resp.headers["Location"].endswith("/crew-pay")


def test_crew_pay_csv(client, make):
    _crew_job(make, day(-5), rate=450, name="Maya Ortiz", w9=1)
    csv_text = client.get("/crew-pay/export.csv?status=all").data.decode()
    header, row = csv_text.strip().splitlines()
    assert header.startswith("event_date,event,reference,crew")
    assert "Maya Ortiz" in row and "450.00" in row and ",owed," in row and row.endswith(",yes")


def test_after_show_hours_on_event_crew_tab(client, app, make):
    a, event, _ = _crew_job(make, day(-2), "hourly", 30, hours=8)
    client.post(f"/events/{event}/crew/{a}", data={"pay_type": "hourly", "pay_rate": "30", "hours": "8",
                                                    "actual_hours": "10"})
    assert _pay_row(app, a)["due"] == Decimal("300.00")
    page = client.get(f"/events/{event}?tab=crew").data.decode()
    assert "$300.00" in page and "After the show" in page
    client.post(f"/events/{event}/crew/{a}", data={"pay_type": "hourly", "pay_rate": "30", "hours": "8",
                                                    "actual_hours": "10", "final_amount": "340"})
    assert _pay_row(app, a)["due"] == Decimal("340.00")


def test_crew_member_page_totals_and_w9(client, app, make):
    a, _, crew = _crew_job(make, day(-5), rate=450, name="Maya Ortiz",
                           paid_on=f"{TODAY.year}-01-15", paid_amount=450)
    page = client.get(f"/crew/{crew}").data.decode()
    assert "Paid by year" in page and str(TODAY.year) in page and "No W-9 on file" in page
    client.post(f"/crew/{crew}/edit", data={"name": "Maya Ortiz", "w9_on_file": "1", "active": "1"})
    assert query(app, "SELECT w9_on_file FROM crew WHERE id = ?", (crew,), one=True)["w9_on_file"] == 1
    assert "No W-9 on file" not in client.get(f"/crew/{crew}").data.decode()


def test_worksheet_shows_crew_their_payment(client, anon, app, make):
    a, event, _ = _crew_job(make, day(-5), rate=450)
    ref = query(app, "SELECT reference_number FROM events WHERE id = ?", (event,), one=True)["reference_number"]
    key = query(app, "SELECT worksheet_key FROM event_crew WHERE id = ?", (a,), one=True)["worksheet_key"]
    assert "Payment pending" in anon.get(f"/worksheet/{ref}/{key}").data.decode()
    client.post("/crew-pay/mark-paid", data={"ids": [str(a)], "paid_on": day(-1), "method": "Zelle"})
    page = anon.get(f"/worksheet/{ref}/{key}").data.decode()
    assert "Payment pending" not in page and "$450.00 on" in page and "via Zelle" in page


# --- Contract deposits ---------------------------------------------------------------

def _contract(make, total=1000, deposit=500, deposit_due=None, status="signed"):
    client_id = make("clients", name="Priya Shah")
    event = make("events", title="All-Hands", client_id=client_id, event_date=day(20), reference_number="R-K")
    return make("contracts", event_id=event, number="CT-TEST-1", title="Agreement", body="x", status=status,
                total_amount=total, deposit_amount=deposit, deposit_due_date=deposit_due,
                balance_due_date=day(10), public_key="pk-contract"), event


def _money(app, contract_id):
    with app.app_context():
        contract = dbm.query("SELECT * FROM contracts WHERE id = ?", (contract_id,), one=True)
        money = services.contract_payments(contract)
        return money, services.deposit_status(contract, money["deposit_received_on"])


def test_record_deposit_from_contract(client, app, make):
    contract, _ = _contract(make, deposit_due=day(-1))
    assert _money(app, contract)[1] == "overdue"
    client.post(f"/contracts/{contract}/deposit", data={"paid_on": day(-3), "amount": "200", "method": "Check",
                                                        "reference": "1042"})
    money, state = _money(app, contract)
    assert state == "overdue" and money["paid"] == Decimal("200.00")  # partial deposit
    client.post(f"/contracts/{contract}/deposit", data={"paid_on": day(0), "amount": "300"})
    money, state = _money(app, contract)
    assert state == "received" and money["deposit_received_on"] == day(0)
    assert money["remaining"] == Decimal("500.00")
    invoices = query(app, "SELECT * FROM invoices WHERE contract_id = ?", (contract,))
    assert len(invoices) == 1 and invoices[0]["kind"] == "deposit" and invoices[0]["status"] == "sent"
    page = client.get(f"/contracts/{contract}").data.decode()
    assert "Received" in page and "1042" in page
    assert "CT-TEST-1" in client.get(f"/invoices/{invoices[0]['id']}").data.decode()


def test_balance_invoice_from_contract(client, app, make):
    contract, _ = _contract(make, total=1500, deposit=500)
    resp = client.post(f"/contracts/{contract}/invoice/balance")
    invoice = query(app, "SELECT * FROM invoices WHERE contract_id = ?", (contract,), one=True)
    assert resp.headers["Location"].endswith(f"/invoices/{invoice['id']}")
    assert (invoice["kind"], invoice["status"], invoice["tax_rate"], invoice["due_date"]) == ("balance", "draft", 0, day(10))
    line = query(app, "SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice["id"],), one=True)
    assert line["unit_price"] == 1000 and "Balance per contract CT-TEST-1" in line["description"]


def test_void_contract_takes_no_deposits(client, app, make):
    contract, _ = _contract(make, status="void")
    assert client.post(f"/contracts/{contract}/deposit", data={"paid_on": day(0), "amount": "100"}).status_code == 400
    assert client.post(f"/contracts/{contract}/invoice/deposit").status_code == 400


def test_dashboard_money_alerts(client, make):
    _crew_job(make, day(-30), rate=450, name="Sam Reyes")
    _contract(make, deposit_due=day(-2), status="sent")
    page = client.get("/").data.decode()
    assert "Crew owed" in page and "$450.00" in page
    assert "Crew pay overdue" in page and "Sam Reyes" in page
    assert "Deposits overdue" in page and "CT-TEST-1" in page


def test_contracts_list_shows_deposit_state(client, app, make):
    contract, _ = _contract(make, deposit_due=day(5))
    page = client.get("/contracts").data.decode()
    assert "badge-info" in page  # deposit due
    client.post(f"/contracts/{contract}/deposit", data={"paid_on": day(0), "amount": "500"})
    assert ">received<" in client.get("/contracts").data.decode()
