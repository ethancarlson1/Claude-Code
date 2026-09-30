"""QuickBooks Online: connecting, sending invoices and payments, and
bringing payments made in QuickBooks back. Runs against tests/fake_quickbooks."""

import time
from urllib.parse import parse_qs, urlparse

import pytest

from backline import db as dbm
from backline import quickbooks as qb
from backline import services

from .conftest import query
from .fake_quickbooks import CLIENT_ID, CLIENT_SECRET, FakeQuickBooks


@pytest.fixture
def fake(monkeypatch):
    server = FakeQuickBooks()
    monkeypatch.setattr(qb, "_send", server)
    return server


@pytest.fixture
def connected(app, fake):
    """Already connected to the fake company, with a product/service chosen."""
    with app.app_context():
        for key, value in {
            "qbo_client_id": CLIENT_ID, "qbo_client_secret": CLIENT_SECRET, "qbo_realm_id": fake.realm,
            "qbo_linked_realm": fake.realm, "qbo_company_name": fake.company_name,
            "qbo_access_token": fake.access_token, "qbo_access_expires": str(int(time.time()) + 3000),
            "qbo_refresh_token": fake.refresh_token, "qbo_item_id": "2", "qbo_item_name": "Audio & backline rental",
            "qbo_connected_at": "2030-01-01T09:00:00", "qbo_last_check_attempt": "2999-01-01T00:00:00",
        }.items():
            dbm.set_setting(key, value)
    return fake


@pytest.fixture
def invoice(make):
    """A draft invoice for Northbeam: a taxable and a non-taxable line, a discount and tax."""

    def _make(number="INV-2030-0001", company="Northbeam", tax_rate=10, discount=20, **extra):
        client_id = extra.pop("client_id", None) or make(
            "clients", name="Priya Shah", company=company, email="priya@example.com", phone="(312) 555-0142",
            address="200 W Madison St\nChicago, IL 60606")
        event_id = make("events", title="Q3 All-Hands", event_date="2030-03-01", reference_number=f"REF-{number}",
                        client_id=client_id)
        invoice_id = make("invoices", number=number, event_id=event_id, client_id=client_id, status="draft",
                          issue_date="2030-01-15", due_date="2030-02-01", tax_rate=tax_rate, discount=discount,
                          notes="Thanks for choosing us!", public_key=f"pk-{number}", **extra)
        make("invoice_items", invoice_id=invoice_id, description="PA system", quantity=1, unit_price=800, taxable=1, sort=0)
        make("invoice_items", invoice_id=invoice_id, description="Audio engineer", quantity=2, unit_price=150, taxable=0, sort=1)
        return invoice_id

    return _make


def _send(client, invoice_id):
    return client.post(f"/invoices/{invoice_id}/status", data={"action": "send"}, follow_redirects=True)


def _local(app, invoice_id):
    return query(app, "SELECT * FROM invoices WHERE id = ?", (invoice_id,), one=True)


def _payments(app, invoice_id):
    return query(app, "SELECT * FROM payments WHERE invoice_id = ? ORDER BY id", (invoice_id,))


# --- Connecting -----------------------------------------------------------------

def test_connect_flow(client, app, fake):
    page = client.get("/settings/quickbooks").data.decode()
    assert "First add your Intuit app keys" in page and "/settings/quickbooks/callback" in page

    client.post("/settings/quickbooks", data={"action": "keys", "environment": "sandbox",
                                              "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
    assert "Connect to QuickBooks" in client.get("/settings/quickbooks").data.decode()

    resp = client.post("/settings/quickbooks/connect")
    target = urlparse(resp.headers["Location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == qb.AUTH_URL
    args = {k: v[0] for k, v in parse_qs(target.query).items()}
    assert args["client_id"] == CLIENT_ID and args["scope"] == qb.SCOPE and args["response_type"] == "code"
    assert args["redirect_uri"] == "http://localhost/settings/quickbooks/callback"

    # A callback that didn't start from this session is refused.
    resp = client.get("/settings/quickbooks/callback?code=good-code&realmId=9130&state=forged", follow_redirects=True)
    assert b"didn&#39;t match this browser session" in resp.data
    with app.app_context():
        assert not qb.is_connected()

    state = parse_qs(urlparse(client.post("/settings/quickbooks/connect").headers["Location"]).query)["state"][0]
    resp = client.get(f"/settings/quickbooks/callback?code=good-code&realmId=9130&state={state}", follow_redirects=True)
    page = resp.data.decode()
    assert "Connected to Sandbox Company_US_1." in page
    assert "Audio &amp; backline rental" in page and "Hours" not in page  # categories can't go on invoices
    assert "Chicago 10.25%" in page and ">TAX<" not in page
    with app.app_context():
        assert qb.is_connected() and dbm.get_setting("qbo_refresh_token") == fake.refresh_token
        assert dbm.get_setting("qbo_access_token") == fake.access_token

    client.post("/settings/quickbooks", data={"action": "options", "qbo_item_id": "2", "qbo_deposit_item_id": "3",
                                              "qbo_tax_code_id": "", "qbo_auto_push": "1", "qbo_online_payments": "1"})
    with app.app_context():
        s = dbm.get_settings()
    assert (s["qbo_item_id"], s["qbo_item_name"], s["qbo_deposit_item_id"]) == ("2", "Audio & backline rental", "3")
    assert (s["qbo_auto_push"], s["qbo_online_payments"], s["qbo_email_invoices"], s["qbo_auto_check"]) == ("1", "1", "0", "0")


def test_connect_cancelled_or_rejected(client, app, fake):
    client.post("/settings/quickbooks", data={"action": "keys", "environment": "sandbox",
                                              "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
    client.post("/settings/quickbooks/connect")
    assert b"was cancelled" in client.get("/settings/quickbooks/callback?error=access_denied", follow_redirects=True).data
    state = parse_qs(urlparse(client.post("/settings/quickbooks/connect").headers["Location"]).query)["state"][0]
    resp = client.get(f"/settings/quickbooks/callback?code=stale&realmId=9130&state={state}", follow_redirects=True)
    assert b"Couldn&#39;t connect to QuickBooks" in resp.data
    with app.app_context():
        assert not qb.is_connected()


def test_disconnect_revokes_and_keeps_links(client, app, connected, invoice):
    invoice_id = invoice()
    _send(client, invoice_id)
    client.post("/settings/quickbooks/disconnect")
    assert connected.revoked == ["refresh-0"]
    with app.app_context():
        assert not qb.is_connected() and dbm.get_setting("qbo_access_token") == ""
    assert _local(app, invoice_id)["qbo_id"]  # reconnecting to the same company carries on
    page = client.get(f"/invoices/{invoice_id}").data.decode()
    assert "QuickBooks is disconnected" in page


def test_switching_environment_disconnects(client, app, connected):
    client.post("/settings/quickbooks", data={"action": "keys", "environment": "production", "client_id": CLIENT_ID})
    with app.app_context():
        assert not qb.is_connected() and qb.environment() == "production"
        assert dbm.get_setting("qbo_client_secret") == CLIENT_SECRET  # blank secret field keeps the saved one


# --- Sending invoices ------------------------------------------------------------

def test_marking_sent_creates_customer_and_invoice(client, app, connected, invoice):
    connected.tax_rate = 10
    invoice_id = invoice()
    page = _send(client, invoice_id).data.decode()
    assert "QuickBooks wasn" not in page

    (customer,) = connected.customers.values()
    assert customer["DisplayName"] == "Northbeam" and customer["PrimaryEmailAddr"]["Address"] == "priya@example.com"
    assert customer["BillAddr"] == {"Line1": "200 W Madison St", "Line2": "Chicago, IL 60606"}
    (remote,) = connected.invoices.values()
    assert remote["DocNumber"] == "INV-2030-0001" and remote["TxnDate"] == "2030-01-15" and remote["DueDate"] == "2030-02-01"
    assert remote["BillEmail"] == {"Address": "priya@example.com"}
    assert remote["CustomerMemo"] == {"value": "Thanks for choosing us!"}
    assert remote["AllowOnlineCreditCardPayment"] and remote["AllowOnlineACHPayment"]
    assert "Q3 All-Hands" in remote["PrivateNote"]
    pa, engineer, discount = remote["Line"]
    assert (pa["Amount"], pa["SalesItemLineDetail"]["TaxCodeRef"]["value"], pa["SalesItemLineDetail"]["ItemRef"]["value"]) == (800.0, "TAX", "2")
    assert (engineer["Amount"], engineer["SalesItemLineDetail"]["Qty"], engineer["SalesItemLineDetail"]["TaxCodeRef"]["value"]) == (300.0, 2.0, "NON")
    assert discount == {"DetailType": "DiscountLineDetail", "Amount": 20.0, "DiscountLineDetail": {"PercentBased": False}}
    assert not connected.emails  # QuickBooks emailing is off by default

    local = _local(app, invoice_id)
    assert local["qbo_id"] == remote["Id"] and local["qbo_doc_number"] == "INV-2030-0001"
    # 800 + 300 - 20 discount + 10% tax on 800 less its share of the discount
    assert local["qbo_total"] == 1158.55 and local["qbo_balance"] == 1158.55 and local["qbo_error"] is None
    assert local["qbo_pay_link"] == f"https://connect.intuit.com/t/pay-{remote['Id']}"
    page = client.get(f"/invoices/{invoice_id}").data.decode()
    assert "Open in QuickBooks" in page and f"txnId={remote['Id']}" in page and "app.sandbox.qbo.intuit.com" in page
    assert "QuickBooks shows a total" not in page

    # A second invoice for the same client reuses the customer.
    second = invoice(number="INV-2030-0002", client_id=query(app, "SELECT client_id FROM invoices WHERE id = ?",
                                                             (invoice_id,), one=True)["client_id"])
    _send(client, second)
    assert len(connected.customers) == 1 and len(connected.invoices) == 2


def test_existing_customer_is_found_by_name(client, app, connected, invoice):
    connected.customers["7"] = {"Id": "7", "DisplayName": "O'Hare Events", "SyncToken": "0"}
    invoice_id = invoice(company="O'Hare Events")
    _send(client, invoice_id)
    assert len(connected.customers) == 1
    assert next(iter(connected.invoices.values()))["CustomerRef"] == {"value": "7"}
    assert query(app, "SELECT qbo_customer_id FROM clients", one=True)["qbo_customer_id"] == "7"


def test_total_mismatch_is_flagged(client, app, connected, invoice):
    connected.tax_rate = 9  # QuickBooks' automated tax disagrees with the 10% here
    invoice_id = invoice()
    _send(client, invoice_id)
    page = client.get(f"/invoices/{invoice_id}").data.decode()
    assert "QuickBooks shows a total of $1,150.69, but this invoice totals $1,158.55" in page


def test_editing_a_sent_invoice_updates_quickbooks(client, app, connected, invoice):
    invoice_id = invoice(tax_rate=0, discount=0)
    _send(client, invoice_id)
    client.post(f"/invoices/{invoice_id}/edit", data={
        "client_id": query(app, "SELECT client_id FROM invoices", one=True)["client_id"], "issue_date": "2030-01-15",
        "due_date": "2030-02-15", "tax_rate": "0", "discount": "0",
        "item_description": ["PA system", "Backline package"], "item_quantity": ["1", "1"],
        "item_price": ["800", "450"], "item_taxable": ["1", "1"],
    })
    (remote,) = connected.invoices.values()
    assert remote["SyncToken"] == "1" and remote["DueDate"] == "2030-02-15"
    assert [line["Description"] for line in remote["Line"]] == ["PA system", "Backline package"]
    assert [line["SalesItemLineDetail"]["TaxCodeRef"]["value"] for line in remote["Line"]] == ["NON", "NON"]  # no tax rate
    assert _local(app, invoice_id)["qbo_total"] == 1250.0

    # "Update QuickBooks" re-sends without making a duplicate.
    resp = client.post(f"/invoices/{invoice_id}/quickbooks", follow_redirects=True)
    assert b"QuickBooks is up to date." in resp.data and len(connected.invoices) == 1


def test_email_from_quickbooks_and_tax_code_options(client, app, connected, invoice):
    with app.app_context():
        dbm.set_setting("qbo_email_invoices", "1")
        dbm.set_setting("qbo_tax_code_id", "5")
        dbm.set_setting("qbo_online_payments", "0")
    invoice_id = invoice()
    _send(client, invoice_id)
    (remote,) = connected.invoices.values()
    assert connected.emails == [(remote["Id"], "priya@example.com")]
    assert remote["TxnTaxDetail"] == {"TxnTaxCodeRef": {"value": "5"}}
    assert "AllowOnlineCreditCardPayment" not in remote
    assert _local(app, invoice_id)["qbo_pay_link"] is None


def test_manual_send_when_auto_push_is_off(client, app, connected, invoice):
    with app.app_context():
        dbm.set_setting("qbo_auto_push", "0")
    invoice_id = invoice()
    page = _send(client, invoice_id).data.decode()
    assert not connected.invoices and "Not in QuickBooks yet." in page
    resp = client.post(f"/invoices/{invoice_id}/quickbooks", follow_redirects=True)
    assert b"Sent to QuickBooks." in resp.data and len(connected.invoices) == 1


def test_drafts_and_void_rules(client, app, connected, invoice):
    invoice_id = invoice()
    resp = client.post(f"/invoices/{invoice_id}/quickbooks", follow_redirects=True)
    assert b"Mark the invoice as sent first" in resp.data and not connected.invoices

    _send(client, invoice_id)
    resp = client.post(f"/invoices/{invoice_id}/status", data={"action": "unsend"}, follow_redirects=True)
    assert b"can&#39;t go back to a draft" in resp.data and _local(app, invoice_id)["status"] == "sent"

    resp = client.post(f"/invoices/{invoice_id}/status", data={"action": "void"}, follow_redirects=True)
    assert b"Voided in QuickBooks too." in resp.data
    assert next(iter(connected.invoices.values()))["voided"]
    assert _local(app, invoice_id)["qbo_total"] == 0
    resp = client.post(f"/invoices/{invoice_id}/status", data={"action": "reopen"}, follow_redirects=True)
    assert _local(app, invoice_id)["status"] == "void"


def test_a_void_that_misses_quickbooks_stays_visible_until_retried(client, app, connected, invoice):
    invoice_id = invoice()
    _send(client, invoice_id)
    connected.down = True
    page = client.post(f"/invoices/{invoice_id}/status", data={"action": "void"}, follow_redirects=True).data.decode()
    assert "Invoice voided." in page and "Void it in QuickBooks too." in page and "Void in QuickBooks" in page
    assert _local(app, invoice_id)["status"] == "void"
    assert "Voided here, but not in QuickBooks" in client.get("/").data.decode()

    connected.down = False
    resp = client.post(f"/invoices/{invoice_id}/quickbooks", follow_redirects=True)
    assert b"Voided in QuickBooks too." in resp.data
    assert next(iter(connected.invoices.values()))["voided"] and _local(app, invoice_id)["qbo_error"] is None
    assert "Voided here" not in client.get("/").data.decode()


def test_voiding_clears_problems_on_invoices_never_sent(client, app, connected, invoice):
    with app.app_context():
        dbm.set_setting("qbo_item_id", "")
    invoice_id = invoice()
    _send(client, invoice_id)
    assert _local(app, invoice_id)["qbo_error"]
    client.post(f"/invoices/{invoice_id}/status", data={"action": "void"})
    assert _local(app, invoice_id)["qbo_error"] is None and not connected.invoices


def test_problems_are_explained_and_nothing_is_lost(client, app, connected, invoice):
    with app.app_context():
        dbm.set_setting("qbo_item_id", "")
    invoice_id = invoice()
    page = _send(client, invoice_id).data.decode()
    assert "Marked as sent" in page  # the local change always happens
    assert "Saved here, but QuickBooks wasn&#39;t updated: Choose which QuickBooks product/service" in page
    assert _local(app, invoice_id)["status"] == "sent" and "Choose which" in _local(app, invoice_id)["qbo_error"]
    dashboard = client.get("/").data.decode()
    assert "INV-2030-0001" in dashboard and "Choose which QuickBooks product/service" in dashboard
    assert "QB problem" in client.get("/invoices").data.decode()

    assert not connected.customers  # nothing half-made in QuickBooks
    with app.app_context():
        dbm.set_setting("qbo_item_id", "2")
    # QuickBooks refuses a duplicate customer name (e.g. an inactive customer with the same name).
    connected.customers["8"] = {"Id": "8", "DisplayName": "Northbeam", "SyncToken": "0", "Active": False}
    resp = client.post(f"/invoices/{invoice_id}/quickbooks", follow_redirects=True)
    assert b"already has a customer, vendor or employee with this name" in resp.data

    del connected.customers["8"]
    client.post(f"/invoices/{invoice_id}/quickbooks")
    local = _local(app, invoice_id)
    assert local["qbo_id"] and local["qbo_error"] is None
    assert "QB problem" not in client.get("/invoices").data.decode()


# --- Payments --------------------------------------------------------------------

def test_payment_recorded_here_is_added_to_quickbooks(client, app, connected, invoice):
    invoice_id = invoice(tax_rate=0, discount=0)
    _send(client, invoice_id)
    client.post(f"/invoices/{invoice_id}/payments", data={"paid_on": "2030-01-20", "amount": "500", "method": "Check",
                                                          "reference": "1042"})
    (remote_payment,) = connected.payments.values()
    qbo_invoice_id = _local(app, invoice_id)["qbo_id"]
    assert remote_payment["TotalAmt"] == 500.0 and remote_payment["PaymentRefNum"] == "1042"
    assert remote_payment["Line"][0]["LinkedTxn"] == [{"TxnId": qbo_invoice_id, "TxnType": "Invoice"}]
    (payment,) = _payments(app, invoice_id)
    assert payment["qbo_payment_id"] == remote_payment["Id"] and payment["qbo_imported"] == 0
    assert _local(app, invoice_id)["qbo_balance"] == 600.0

    # It's in QuickBooks now, so it's changed or deleted there.
    resp = client.post(f"/invoices/{invoice_id}/payments/{payment['id']}/delete", follow_redirects=True)
    assert b"This payment is in QuickBooks" in resp.data and len(_payments(app, invoice_id)) == 1

    # Checking again doesn't duplicate it.
    resp = client.post("/quickbooks/check", follow_redirects=True)
    assert b"No payment changes." in resp.data and len(_payments(app, invoice_id)) == 1


def test_payments_made_in_quickbooks_come_back(client, app, connected, invoice):
    first = invoice(tax_rate=0, discount=0)
    second = invoice(number="INV-2030-0002", tax_rate=0, discount=0)
    _send(client, first)
    _send(client, second)
    q1, q2 = _local(app, first)["qbo_id"], _local(app, second)["qbo_id"]

    pid = connected.receive_payment((q1, 400), date="2030-01-25", ref="ONLINE-77")
    # One payment covering both invoices, plus an invoice this platform doesn't know about.
    split = connected.receive_payment([(q1, 700), (q2, 250), ("900", 50)], date="2030-01-28")
    resp = client.post("/quickbooks/check", follow_redirects=True)
    assert b"Checked 2 invoices in QuickBooks: 3 new payments." in resp.data
    rows = _payments(app, first)
    assert [(r["paid_on"], r["amount"], r["method"], r["reference"], r["qbo_imported"]) for r in rows] == [
        ("2030-01-25", 400.0, "QuickBooks", "ONLINE-77", 1), ("2030-01-28", 700.0, "QuickBooks", None, 1)]
    assert [r["amount"] for r in _payments(app, second)] == [250.0]
    page = client.get(f"/invoices/{first}").data.decode()
    assert '<span class="badge badge-ok">paid</span>' in page and "not in QuickBooks yet" not in page

    # Changes and deletions in QuickBooks follow.
    connected.payments[pid]["TxnDate"] = "2030-01-26"
    connected.payments[pid]["Line"][0]["Amount"] = 450.0
    del connected.payments[split]
    resp = client.post("/quickbooks/check", follow_redirects=True)
    assert b"1 changed, 2 removed in QuickBooks." in resp.data
    assert [(r["paid_on"], r["amount"]) for r in _payments(app, first)] == [("2030-01-26", 450.0)]
    assert _payments(app, second) == []


def test_payment_recorded_while_offline_is_sent_later(client, app, connected, invoice):
    invoice_id = invoice(tax_rate=0, discount=0)
    _send(client, invoice_id)
    connected.down = True
    resp = client.post(f"/invoices/{invoice_id}/payments", data={"paid_on": "2030-01-20", "amount": "100"},
                       follow_redirects=True)
    assert b"Recorded $100.00 payment." in resp.data and b"Couldn&#39;t reach QuickBooks" in resp.data
    assert b"not in QuickBooks yet" in resp.data
    # A payment made in QuickBooks meanwhile.
    connected.down = False
    connected.receive_payment((_local(app, invoice_id)["qbo_id"], 200))
    client.post("/quickbooks/check")
    rows = _payments(app, invoice_id)
    assert sorted(r["amount"] for r in rows) == [100.0, 200.0] and all(r["qbo_payment_id"] for r in rows)
    assert len(connected.payments) == 2 and _local(app, invoice_id)["qbo_balance"] == 800.0


def test_a_refused_payment_stays_flagged_and_others_still_sync(client, app, connected, invoice):
    first = invoice(tax_rate=0, discount=0)
    second = invoice(number="INV-2030-0002", tax_rate=0, discount=0)
    _send(client, first)
    _send(client, second)
    page = client.post(f"/invoices/{first}/payments", data={"paid_on": "2030-01-20", "amount": "5000"},
                       follow_redirects=True).data.decode()
    assert "The payment amount is more than the invoice balance." in page and "not in QuickBooks yet" in page
    connected.receive_payment((_local(app, second)["qbo_id"], 100))
    resp = client.post("/quickbooks/check", follow_redirects=True)
    assert b"1 new payment, 1 with payments QuickBooks didn&#39;t accept" in resp.data
    assert [p["amount"] for p in _payments(app, second)] == [100.0]
    assert "more than the invoice balance" in _local(app, first)["qbo_error"]  # still showing


def test_contract_deposit_goes_to_quickbooks(client, app, connected, make):
    with app.app_context():
        dbm.set_setting("qbo_deposit_item_id", "3")
    client_id = make("clients", name="Sofia Alvarez", email="sofia@example.com")
    event = make("events", title="Alvarez / Reed Wedding", event_date="2030-06-01", client_id=client_id)
    client.post("/contracts/new", data={"event_id": event, "title": "Wedding", "total_amount": "4000", "deposit_amount": "1000"})
    contract = query(app, "SELECT * FROM contracts", one=True)
    client.post(f"/contracts/{contract['id']}/deposit", data={"paid_on": "2030-01-10", "amount": "1000", "method": "Check"})

    (remote,) = connected.invoices.values()
    assert remote["Line"][0]["SalesItemLineDetail"]["ItemRef"] == {"value": "3"}
    assert remote["Line"][0]["SalesItemLineDetail"]["TaxCodeRef"] == {"value": "NON"}
    (payment,) = connected.payments.values()
    assert payment["TotalAmt"] == 1000.0
    with app.app_context():
        assert services.contract_payments(contract)["deposit_received_on"] == "2030-01-10"
    # Checking QuickBooks afterwards finds the same payment, not a second one.
    client.post("/quickbooks/check")
    assert len(query(app, "SELECT * FROM payments")) == 1


def test_invoice_deleted_in_quickbooks_is_flagged(client, app, connected, invoice):
    invoice_id = invoice()
    _send(client, invoice_id)
    connected.invoices.clear()
    resp = client.post("/quickbooks/check", follow_redirects=True)
    assert b"1 invoice missing from QuickBooks" in resp.data
    assert "QuickBooks no longer has this invoice" in _local(app, invoice_id)["qbo_error"]


def test_pay_online_button_on_client_invoice(client, anon, app, connected, invoice):
    invoice_id = invoice(tax_rate=0, discount=0)
    _send(client, invoice_id)
    link = _local(app, invoice_id)["qbo_pay_link"]
    page = anon.get("/i/pk-INV-2030-0001").data.decode()
    assert f'href="{link}"' in page and "Pay $1,100.00 online" in page

    with app.app_context():  # only https links are ever shown
        dbm.update("invoices", invoice_id, {"qbo_pay_link": "javascript:alert(1)"})
    assert "Pay $1,100.00 online" not in anon.get("/i/pk-INV-2030-0001").data.decode()
    assert qb._safe_link("javascript:alert(1)") is None

    connected.receive_payment((_local(app, invoice_id)["qbo_id"], 1100))
    client.post("/quickbooks/check")
    assert _local(app, invoice_id)["qbo_pay_link"] == link
    assert "Pay $" not in anon.get("/i/pk-INV-2030-0001").data.decode()  # paid in full


# --- Sign-in upkeep ----------------------------------------------------------------

def test_expired_access_token_is_refreshed(client, app, connected, invoice):
    with app.app_context():
        dbm.set_setting("qbo_access_expires", str(int(time.time()) - 10))
    invoice_id = invoice()
    _send(client, invoice_id)
    assert _local(app, invoice_id)["qbo_id"]
    with app.app_context():
        assert dbm.get_setting("qbo_refresh_token") == "refresh-1" and dbm.get_setting("qbo_access_token") == "access-1"

    connected.expire_access = True  # QuickBooks rejects a token early: refresh once and retry
    client.post("/quickbooks/check")
    with app.app_context():
        assert dbm.get_setting("qbo_access_token") == "access-2"


def test_revoked_connection_disconnects_cleanly(client, app, connected, invoice):
    connected.refresh_fails = True
    connected.expire_access = True
    invoice_id = invoice()
    page = _send(client, invoice_id).data.decode()
    assert "Marked as sent" in page and "QuickBooks signed this platform out" in page
    with app.app_context():
        assert not qb.is_connected()
    assert "QuickBooks signed this platform out" in client.get("/settings/quickbooks").data.decode()
    assert "QuickBooks signed this platform out" in client.get("/").data.decode()


def test_automatic_checks_are_throttled(client, app, connected, invoice):
    invoice_id = invoice()
    _send(client, invoice_id)
    with app.app_context():
        dbm.set_setting("qbo_last_check_attempt", "")
    connected.calls.clear()
    client.get("/")
    client.get("/invoices")
    queries = [c for c in connected.api_calls("GET", "query") if "from Invoice" in c[2]["query"]]
    assert len(queries) == 1
    with app.app_context():
        dbm.set_setting("qbo_last_check_attempt", "2000-01-01T00:00:00")
        dbm.set_setting("qbo_auto_check", "0")
    client.get("/")
    assert len([c for c in connected.api_calls("GET", "query") if "from Invoice" in c[2]["query"]]) == 1

    connected.down = True
    with app.app_context():
        dbm.set_setting("qbo_auto_check", "1")
    assert client.get("/").status_code == 200  # an unreachable QuickBooks never breaks a page
    assert "Automatic payment check failed" in client.get("/").data.decode()


def test_switching_companies_clears_old_links(client, app, connected, invoice):
    invoice_id = invoice(tax_rate=0, discount=0)
    _send(client, invoice_id)
    client.post(f"/invoices/{invoice_id}/payments", data={"paid_on": "2030-01-20", "amount": "100"})
    connected.receive_payment((_local(app, invoice_id)["qbo_id"], 300))
    client.post("/quickbooks/check")
    assert len(_payments(app, invoice_id)) == 2

    connected.realm, connected.company_name = "5555", "Chicago Sound and Backline LLC"
    connected.valid_codes.add("prod-code")
    with app.app_context():
        name, unlinked = qb.finish_connect("prod-code", "5555", "http://localhost/settings/quickbooks/callback")
        assert (name, unlinked) == ("Chicago Sound and Backline LLC", True)
        assert dbm.get_setting("qbo_item_id") == ""
    (kept,) = _payments(app, invoice_id)  # the practice payment from the old company is gone
    assert (kept["amount"], kept["qbo_payment_id"]) == (100.0, None)
    local = _local(app, invoice_id)
    assert local["qbo_id"] is None and local["qbo_total"] is None
    assert query(app, "SELECT qbo_customer_id FROM clients", one=True)["qbo_customer_id"] is None


def test_nothing_happens_until_connected(client, app, invoice):
    # The autouse no_network fixture fails the test if anything calls Intuit.
    invoice_id = invoice()
    _send(client, invoice_id)
    client.post(f"/invoices/{invoice_id}/payments", data={"paid_on": "2030-01-20", "amount": "100"})
    client.get("/")
    client.get("/invoices")
    page = client.get(f"/invoices/{invoice_id}").data.decode()
    assert 'id="quickbooks"' not in page and "Check QuickBooks" not in client.get("/invoices").data.decode()
