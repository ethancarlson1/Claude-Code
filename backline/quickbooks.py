"""QuickBooks Online connection.

Signing in (OAuth 2.0), sending invoices and payments to QuickBooks, and
bringing payments recorded in QuickBooks back. Nothing here runs until
someone connects under Settings → QuickBooks.

Invoices go one way: they're written here and copied to QuickBooks.
Payments go both ways. A payment recorded here is added to QuickBooks,
and a payment recorded in QuickBooks shows up here. Once a payment is in
QuickBooks, QuickBooks has the final say: change or delete it there.
"""

import base64
import json
import os
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

from . import db, services, util

AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
SCOPE = "com.intuit.quickbooks.accounting"
API_BASE = {
    "sandbox": "https://sandbox-quickbooks.api.intuit.com",
    "production": "https://quickbooks.api.intuit.com",
}
APP_BASE = {  # QuickBooks' own website, for "Open in QuickBooks" links
    "sandbox": "https://app.sandbox.qbo.intuit.com",
    "production": "https://app.qbo.intuit.com",
}
ENVIRONMENTS = [("sandbox", "Sandbox (Intuit's test company)"), ("production", "Production (your real books)")]
MINOR_VERSION = "75"
TIMEOUT = 15  # seconds per request
CHECK_EVERY = timedelta(minutes=15)
QUERY_CHUNK = 30  # ids per "Id IN (...)" query
# Paid-off invoices older than this stop being checked for payment changes.
RECHECK_DAYS = 120

TOKEN_SETTINGS = ("qbo_access_token", "qbo_access_expires", "qbo_refresh_token", "qbo_refresh_expires",
                  "qbo_realm_id", "qbo_company_name", "qbo_connected_at")
MAPPING_SETTINGS = ("qbo_item_id", "qbo_item_name", "qbo_deposit_item_id", "qbo_deposit_item_name",
                    "qbo_tax_code_id", "qbo_tax_code_name")


class QuickBooksError(Exception):
    """Something went wrong talking to QuickBooks. The message is written
    for the person using the platform."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class NotConnected(QuickBooksError):
    pass


class _TokenRejected(QuickBooksError):
    pass


# --- Settings -----------------------------------------------------------------

def credentials():
    """The Intuit app's Client ID and Secret. Environment variables win over
    the values saved in Settings."""
    client_id = os.environ.get("BACKLINE_QBO_CLIENT_ID") or db.get_setting("qbo_client_id") or ""
    secret = os.environ.get("BACKLINE_QBO_CLIENT_SECRET") or db.get_setting("qbo_client_secret") or ""
    return client_id.strip(), secret.strip()


def environment():
    env = db.get_setting("qbo_environment")
    return env if env in API_BASE else "sandbox"


def is_connected():
    return bool(db.get_setting("qbo_realm_id") and db.get_setting("qbo_refresh_token"))


def invoice_url(qbo_id):
    return f"{APP_BASE[environment()]}/app/invoice?txnId={qbo_id}"


# --- HTTP ---------------------------------------------------------------------

def _send(method, url, headers, body=None):
    """Make one HTTP request and return (status code, response text).

    Everything that talks to Intuit goes through here; the tests replace it."""
    try:
        import requests
    except ImportError as exc:  # an older install that hasn't re-run pip
        raise QuickBooksError(
            "The QuickBooks connection needs one more package. Stop the platform, run "
            "“pip install -r requirements.txt”, then start it again."
        ) from exc
    try:
        resp = requests.request(method, url, headers=headers, data=body, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise QuickBooksError("Couldn't reach QuickBooks. Check the internet connection and try again.") from exc
    return resp.status_code, resp.text


def _json(text):
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# Intuit error codes worth explaining in plain words.
FRIENDLY_ERRORS = {
    "610": "QuickBooks couldn't find that record. It may have been deleted in QuickBooks.",
    "5010": "The record changed in QuickBooks while this was being saved. Try again.",
    "6140": "QuickBooks already has an invoice with this number. Change the invoice number prefix under "
            "Settings → Company & billing, or turn off QuickBooks' duplicate-number warning.",
    "6240": "QuickBooks already has a customer, vendor or employee with this name (it may be inactive). "
            "Rename one of them in QuickBooks, then try again.",
}


def _fault(data, status):
    """A readable message (and Intuit's error code) from an error response."""
    fault = data.get("Fault") or data.get("fault") or {}
    errors = fault.get("Error") or fault.get("error") or []
    code, parts = None, []
    for err in errors:
        code = code or str(err.get("code") or "")
        message = (err.get("Message") or err.get("message") or "").strip()
        detail = (err.get("Detail") or err.get("detail") or "").strip()
        parts.append(detail if detail and message.lower() in detail.lower() else ": ".join(p for p in (message, detail) if p))
    if code in FRIENDLY_ERRORS:
        return FRIENDLY_ERRORS[code], code
    if status == 429:
        return "QuickBooks is receiving too many requests right now. Wait a minute and try again.", code
    if status >= 500 and not parts:
        return f"QuickBooks had a problem (error {status}). Try again in a few minutes.", code
    return ("QuickBooks said: " + "; ".join(p for p in parts if p)) if parts else f"QuickBooks error {status}.", code


# --- Signing in ---------------------------------------------------------------

def authorize_url(redirect_uri, state):
    client_id, _secret = credentials()
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "response_type": "code", "scope": SCOPE,
        "redirect_uri": redirect_uri, "state": state,
    })


def _token_request(form):
    client_id, secret = credentials()
    if not client_id or not secret:
        raise QuickBooksError("Add your Intuit app's Client ID and Client Secret first.")
    basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    status, text = _send("POST", TOKEN_URL, {
        "Authorization": f"Basic {basic}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }, urlencode(form))
    data = _json(text)
    if status == 200 and data.get("access_token"):
        _store_tokens(data)
        return
    error = data.get("error", "")
    if status in (400, 401) and error in ("invalid_grant", "invalid_client", "unauthorized_client"):
        if error == "invalid_grant":
            raise _TokenRejected("QuickBooks didn't accept the sign-in. It may have expired or been revoked.")
        raise _TokenRejected("QuickBooks didn't recognize the Client ID and Secret. Check them against your "
                             "Intuit app's keys, and that the environment (sandbox or production) matches.")
    raise QuickBooksError(f"QuickBooks sign-in failed ({error or 'error ' + str(status)}). Try again.")


def _store_tokens(data):
    now = time.time()
    db.set_setting("qbo_access_token", data["access_token"])
    db.set_setting("qbo_access_expires", str(int(now + int(data.get("expires_in") or 3600))))
    if data.get("refresh_token"):  # Intuit rotates this; always keep the newest
        db.set_setting("qbo_refresh_token", data["refresh_token"])
    if data.get("x_refresh_token_expires_in"):
        db.set_setting("qbo_refresh_expires", str(int(now + int(data["x_refresh_token_expires_in"]))))


def finish_connect(code, realm_id, redirect_uri):
    """Second half of Connect: trade Intuit's one-time code for tokens.

    Returns (company name, whether links to a different company were cleared)."""
    _token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})
    unlinked = False
    linked_realm = db.get_setting("qbo_linked_realm")
    if linked_realm and linked_realm != realm_id:
        unlink_all()
        unlinked = True
    db.set_setting("qbo_realm_id", realm_id)
    db.set_setting("qbo_linked_realm", realm_id)
    info = api("GET", f"companyinfo/{realm_id}").get("CompanyInfo", {})
    name = info.get("CompanyName") or "your QuickBooks company"
    db.set_setting("qbo_company_name", name)
    db.set_setting("qbo_connected_at", util.now_iso())
    db.set_setting("qbo_last_error", "")
    return name, unlinked


def _refresh():
    token = db.get_setting("qbo_refresh_token")
    if not token:
        raise NotConnected("QuickBooks isn't connected. Connect it under Settings → QuickBooks.")
    try:
        _token_request({"grant_type": "refresh_token", "refresh_token": token})
    except _TokenRejected:
        forget_connection("QuickBooks signed this platform out (the connection expired or was revoked). "
                          "Reconnect under Settings → QuickBooks.")
        raise NotConnected(db.get_setting("qbo_last_error")) from None


def forget_connection(message=""):
    """Drop the stored sign-in. Links between records stay, so reconnecting
    to the same QuickBooks company picks up where it left off."""
    for key in TOKEN_SETTINGS:
        db.set_setting(key, "")
    db.set_setting("qbo_last_error", message)


def disconnect():
    token = db.get_setting("qbo_refresh_token")
    if token:
        client_id, secret = credentials()
        basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
        try:
            _send("POST", REVOKE_URL, {"Authorization": f"Basic {basic}", "Accept": "application/json",
                                       "Content-Type": "application/json"}, json.dumps({"token": token}))
        except QuickBooksError:
            pass  # disconnect here regardless; the token expires on its own
    forget_connection()


def unlink_all():
    """Forget every link to QuickBooks records (used when switching to a
    different QuickBooks company, e.g. from the sandbox to your real books).
    Payments that came from the old company are removed; payments recorded
    here stay."""
    conn = db.get_db()
    conn.execute("DELETE FROM payments WHERE qbo_imported = 1")
    conn.execute("UPDATE payments SET qbo_payment_id = NULL")
    conn.execute("UPDATE clients SET qbo_customer_id = NULL")
    conn.execute(
        "UPDATE invoices SET qbo_id = NULL, qbo_doc_number = NULL, qbo_synced_at = NULL, qbo_checked_at = NULL, "
        "qbo_total = NULL, qbo_balance = NULL, qbo_pay_link = NULL, qbo_error = NULL"
    )
    conn.commit()
    for key in MAPPING_SETTINGS + ("qbo_linked_realm",):
        db.set_setting(key, "")


# --- API calls ------------------------------------------------------------------

def api(method, path, payload=None, params=None, _retry=True):
    """Call the QuickBooks Accounting API and return the parsed JSON."""
    realm = db.get_setting("qbo_realm_id")
    if not realm or not db.get_setting("qbo_refresh_token"):
        raise NotConnected("QuickBooks isn't connected. Connect it under Settings → QuickBooks.")
    if int(db.get_setting("qbo_access_expires") or 0) - 60 < time.time():
        _refresh()
    url = f"{API_BASE[environment()]}/v3/company/{realm}/{path}?" + urlencode(
        {"minorversion": MINOR_VERSION, **(params or {})})
    headers = {"Authorization": "Bearer " + (db.get_setting("qbo_access_token") or ""), "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload)
    elif method == "POST":
        headers["Content-Type"] = "application/octet-stream"  # e.g. invoice/<id>/send
    status, text = _send(method, url, headers, body)
    if status == 401 and _retry:
        _refresh()
        return api(method, path, payload, params, _retry=False)
    data = _json(text)
    if status >= 400 or data.get("Fault"):
        message, code = _fault(data, status)
        raise QuickBooksError(message, code)
    return data


def _q(value):
    """Quote a value for a QuickBooks query."""
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def query(sql, params=None):
    data = api("GET", "query", params={"query": sql, **(params or {})})
    for value in data.get("QueryResponse", {}).values():
        if isinstance(value, list):
            return value
    return []


def _by_ids(entity, ids, params=None):
    found = {}
    ids = list(ids)
    for start in range(0, len(ids), QUERY_CHUNK):
        chunk = ids[start:start + QUERY_CHUNK]
        sql = f"select * from {entity} where Id in ({', '.join(_q(i) for i in chunk)})"
        for row in query(sql, params):
            found[str(row["Id"])] = row
    return found


def item_choices():
    """Products/services an invoice line can post to."""
    items = query("select * from Item where Active = true maxresults 1000")
    choices = [(str(i["Id"]), i.get("FullyQualifiedName") or i.get("Name") or str(i["Id"]))
               for i in items if i.get("Type") in ("Service", "NonInventory", "Inventory")]
    return sorted(choices, key=lambda c: c[1].lower())


def tax_code_choices():
    """Sales tax codes, for companies that don't use QuickBooks' automated tax."""
    codes = query("select * from TaxCode where Active = true maxresults 1000")
    return sorted(((str(c["Id"]), c.get("Name") or str(c["Id"])) for c in codes if str(c["Id"]) not in ("TAX", "NON")),
                  key=lambda c: c[1].lower())


# --- Customers -----------------------------------------------------------------

def display_name(client):
    """QuickBooks customer name: the company if there is one, else the person.
    QuickBooks reserves ":" for sub-customers."""
    name = (client["company"] or client["name"] or "").strip()
    return " ".join(name.replace(":", " -").split())[:100]


def customer_id(client):
    """The QuickBooks customer for a client, found by name or created."""
    if client["qbo_customer_id"]:
        return client["qbo_customer_id"]
    name = display_name(client)
    found = query(f"select * from Customer where DisplayName = {_q(name)}")
    if found:
        cid = str(found[0]["Id"])
    else:
        payload = {"DisplayName": name}
        if client["company"]:
            payload["CompanyName"] = client["company"][:100]
        if client["email"]:
            payload["PrimaryEmailAddr"] = {"Address": client["email"]}
        if client["phone"]:
            payload["PrimaryPhone"] = {"FreeFormNumber": client["phone"][:30]}
        lines = [line.strip() for line in (client["address"] or "").splitlines() if line.strip()][:5]
        if lines:
            payload["BillAddr"] = {f"Line{n}": line[:500] for n, line in enumerate(lines, start=1)}
        cid = str(api("POST", "customer", payload)["Customer"]["Id"])
    db.update("clients", client["id"], {"qbo_customer_id": cid})
    return cid


# --- Invoices ------------------------------------------------------------------

def _get_invoice(invoice_id):
    return db.query("SELECT * FROM invoices WHERE id = ?", (invoice_id,), one=True)


def line_item_id(invoice):
    """The QuickBooks product/service this invoice's lines post to."""
    contract_line = invoice["kind"] in ("deposit", "balance")
    item_id = (contract_line and db.get_setting("qbo_deposit_item_id")) or db.get_setting("qbo_item_id")
    if not item_id:
        raise QuickBooksError("Choose which QuickBooks product/service invoice lines go to, "
                              "under Settings → QuickBooks.")
    return item_id


def invoice_payload(invoice, items, cust_id, item_id):
    """The QuickBooks version of an invoice."""
    settings = db.get_settings()
    taxed = util.to_decimal(invoice["tax_rate"]) > 0
    lines = []
    for it in items:
        qty, price = util.to_decimal(it["quantity"]), util.to_decimal(it["unit_price"])
        lines.append({
            "DetailType": "SalesItemLineDetail",
            "Amount": float(util.round_money(qty * price)),
            "Description": it["description"][:4000],
            "SalesItemLineDetail": {
                "ItemRef": {"value": item_id},
                "Qty": float(qty),
                "UnitPrice": float(price),
                "TaxCodeRef": {"value": "TAX" if taxed and it["taxable"] else "NON"},
            },
        })
    totals = services.invoice_totals(invoice, items, [])
    if totals["discount"] > 0:
        lines.append({"DetailType": "DiscountLineDetail", "Amount": float(totals["discount"]),
                      "DiscountLineDetail": {"PercentBased": False}})
    event = db.query("SELECT title, reference_number FROM events WHERE id = ?", (invoice["event_id"],), one=True)
    note = f"From {settings['company_name']}, invoice {invoice['number']}"
    if event:
        note += f" · {event['title']} (ref {event['reference_number']})"
    payload = {
        "CustomerRef": {"value": cust_id},
        "DocNumber": invoice["number"][:21],
        "TxnDate": invoice["issue_date"],
        "Line": lines,
        "PrivateNote": note[:4000],
    }
    if invoice["due_date"]:
        payload["DueDate"] = invoice["due_date"]
    client = db.query("SELECT email FROM clients WHERE id = ?", (invoice["client_id"],), one=True)
    if client and client["email"]:
        payload["BillEmail"] = {"Address": client["email"]}
    if invoice["notes"]:
        payload["CustomerMemo"] = {"value": invoice["notes"][:1000]}
    if settings.get("qbo_online_payments") == "1":
        payload["AllowOnlineCreditCardPayment"] = True
        payload["AllowOnlineACHPayment"] = True
    if taxed and settings.get("qbo_tax_code_id"):
        payload["TxnTaxDetail"] = {"TxnTaxCodeRef": {"value": settings["qbo_tax_code_id"]}}
    return payload


def push_invoice(invoice_id):
    """Create or update the invoice in QuickBooks, add payments recorded here
    that QuickBooks doesn't have yet, then read back QuickBooks' totals.

    Returns True if the invoice was new to QuickBooks."""
    invoice = _get_invoice(invoice_id)
    if invoice["status"] == "draft":
        raise QuickBooksError("Mark the invoice as sent first. Drafts stay here until they're ready.")
    if invoice["status"] == "void":
        raise QuickBooksError("This invoice is void.")
    client = db.query("SELECT * FROM clients WHERE id = ?", (invoice["client_id"],), one=True)
    items = db.query("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY sort, id", (invoice_id,))
    try:
        # Check everything that can be checked here before creating anything in QuickBooks.
        if client is None:
            raise QuickBooksError("Choose who the invoice is billed to before sending it to QuickBooks.")
        if not items:
            raise QuickBooksError("Add at least one line item before sending this invoice to QuickBooks.")
        item_id = line_item_id(invoice)
        cust_id = customer_id(client)
        payload = invoice_payload(invoice, items, cust_id, item_id)
        created = not invoice["qbo_id"]
        if created:
            remote = api("POST", "invoice", payload)["Invoice"]
        else:
            current = api("GET", f"invoice/{invoice['qbo_id']}")["Invoice"]
            remote = api("POST", "invoice", {**payload, "Id": current["Id"], "SyncToken": current["SyncToken"],
                                             "sparse": True})["Invoice"]
        db.update("invoices", invoice_id, {"qbo_id": str(remote["Id"]), "qbo_synced_at": util.now_iso(), "qbo_error": None})
        if created and db.get_setting("qbo_email_invoices") == "1" and payload.get("BillEmail"):
            api("POST", f"invoice/{remote['Id']}/send")
        push_payments(invoice_id)
    except QuickBooksError as exc:
        note_error(invoice_id, exc)
        raise
    return created


def push_payments(invoice_id):
    """Add this invoice's payments that QuickBooks doesn't have yet, then
    bring the invoice's QuickBooks state (balance, payments, pay link) back."""
    invoice = _get_invoice(invoice_id)
    if not invoice["qbo_id"]:
        return 0
    pending = db.query("SELECT * FROM payments WHERE invoice_id = ? AND qbo_payment_id IS NULL ORDER BY paid_on, id",
                       (invoice_id,))
    try:
        if pending:
            # A payment must belong to the same QuickBooks customer as its invoice.
            cust_id = str(api("GET", f"invoice/{invoice['qbo_id']}")["Invoice"]["CustomerRef"]["value"])
            company = db.get_setting("company_name")
            for p in pending:
                amount = float(util.round_money(p["amount"]))
                payload = {
                    "CustomerRef": {"value": cust_id},
                    "TotalAmt": amount,
                    "TxnDate": p["paid_on"],
                    "Line": [{"Amount": amount, "LinkedTxn": [{"TxnId": invoice["qbo_id"], "TxnType": "Invoice"}]}],
                    "PrivateNote": " · ".join(x for x in (p["method"], p["notes"], f"Recorded in {company}") if x)[:4000],
                }
                if p["reference"]:
                    payload["PaymentRefNum"] = p["reference"][:21]
                result = api("POST", "payment", payload)["Payment"]
                db.update("payments", p["id"], {"qbo_payment_id": str(result["Id"])})
        remote = api("GET", f"invoice/{invoice['qbo_id']}", params={"include": "invoiceLink"})["Invoice"]
        payments = _by_ids("Payment", _linked_payment_ids(remote))
        _apply_remote(_get_invoice(invoice_id), remote, payments)
    except QuickBooksError as exc:
        note_error(invoice_id, exc)
        raise
    return len(pending)


def void_invoice(invoice_id):
    invoice = _get_invoice(invoice_id)
    try:
        current = api("GET", f"invoice/{invoice['qbo_id']}")["Invoice"]
        remote = api("POST", "invoice", {"Id": current["Id"], "SyncToken": current["SyncToken"]},
                     params={"operation": "void"})["Invoice"]
    except QuickBooksError as exc:
        note_error(invoice_id, QuickBooksError(f"Voided here, but not in QuickBooks: {exc} "
                                               "Void it in QuickBooks too."))
        raise
    db.update("invoices", invoice_id, {"qbo_total": remote.get("TotalAmt"), "qbo_balance": remote.get("Balance"),
                                       "qbo_pay_link": None, "qbo_error": None, "qbo_checked_at": util.now_iso()})


def note_error(invoice_id, exc):
    db.update("invoices", invoice_id, {"qbo_error": str(exc)})


def after_change(invoice_id, payment_only=False):
    """Keep QuickBooks current after an invoice or payment changes here.

    Never raises: returns a warning for the person, or None."""
    if not is_connected():
        return None
    invoice = _get_invoice(invoice_id)
    if invoice is None or invoice["status"] != "sent":
        return None
    if not invoice["qbo_id"] and db.get_setting("qbo_auto_push") != "1":
        return None
    try:
        if payment_only and invoice["qbo_id"]:
            push_payments(invoice_id)
        else:
            push_invoice(invoice_id)
    except QuickBooksError as exc:
        return f"Saved here, but QuickBooks wasn't updated: {exc}"
    return None


# --- Payments from QuickBooks ----------------------------------------------------

def _linked_payment_ids(remote):
    return [str(t["TxnId"]) for t in remote.get("LinkedTxn") or [] if t.get("TxnType") == "Payment"]


def _safe_link(url):
    return url if isinstance(url, str) and url.startswith("https://") and len(url) < 2000 else None


def _apply_remote(local, remote, payments):
    """Match this invoice's payments to QuickBooks. Returns (added, updated, removed)."""
    linked = _linked_payment_ids(remote)
    applied = {}
    for pid in linked:
        payment = payments.get(pid)
        if payment is None:
            continue
        amount = sum(
            (util.to_decimal(line.get("Amount")) for line in payment.get("Line") or []
             if any(t.get("TxnType") == "Invoice" and str(t.get("TxnId")) == str(remote["Id"])
                    for t in line.get("LinkedTxn") or [])),
            util.to_decimal(0),
        )
        applied[pid] = (payment, util.round_money(amount))
    existing = {r["qbo_payment_id"]: r for r in db.query(
        "SELECT * FROM payments WHERE invoice_id = ? AND qbo_payment_id IS NOT NULL", (local["id"],))}
    added = updated = removed = 0
    for pid, (payment, amount) in applied.items():
        row = existing.pop(pid, None)
        if amount <= 0:  # voided in QuickBooks
            if row:
                db.execute("DELETE FROM payments WHERE id = ?", (row["id"],))
                removed += 1
            continue
        values = {"paid_on": payment.get("TxnDate") or util.today().isoformat(), "amount": float(amount)}
        if row is None:
            db.insert("payments", {**values, "invoice_id": local["id"], "method": "QuickBooks",
                                   "reference": (payment.get("PaymentRefNum") or "")[:60] or None,
                                   "qbo_payment_id": pid, "qbo_imported": 1})
            added += 1
        elif (row["paid_on"], util.round_money(row["amount"])) != (values["paid_on"], amount):
            db.update("payments", row["id"], values)
            updated += 1
    for pid, row in existing.items():
        if pid not in linked:  # deleted in QuickBooks
            db.execute("DELETE FROM payments WHERE id = ?", (row["id"],))
            removed += 1
    state = {
        "qbo_doc_number": remote.get("DocNumber"),
        "qbo_total": remote.get("TotalAmt"),
        "qbo_balance": remote.get("Balance"),
        "qbo_pay_link": _safe_link(remote.get("InvoiceLink")),
        "qbo_checked_at": util.now_iso(),
    }
    # A payment that couldn't be sent keeps its error showing until it goes through.
    if not db.scalar("SELECT 1 FROM payments WHERE invoice_id = ? AND qbo_payment_id IS NULL", (local["id"],)):
        state["qbo_error"] = None
    db.update("invoices", local["id"], state)
    return added, updated, removed


def check_payments():
    """Bring payment changes over from QuickBooks for open and recent invoices."""
    cutoff = (util.today() - timedelta(days=RECHECK_DAYS)).isoformat()
    rows = db.query(
        """SELECT * FROM invoices WHERE qbo_id IS NOT NULL AND status != 'void'
           AND (qbo_balance IS NULL OR qbo_balance > 0 OR issue_date >= ?) ORDER BY id""",
        (cutoff,),
    )
    summary = {"checked": len(rows), "added": 0, "updated": 0, "removed": 0, "missing": 0, "problems": 0}
    # Payments recorded here but not yet in QuickBooks go first. (Ones that
    # still can't be sent stay here, marked, and are tried again next time.)
    for row in rows:
        if db.scalar("SELECT 1 FROM payments WHERE invoice_id = ? AND qbo_payment_id IS NULL", (row["id"],)):
            try:
                push_payments(row["id"])
            except NotConnected:
                raise
            except QuickBooksError:
                summary["problems"] += 1  # the reason is shown on the invoice
    rows = [_get_invoice(r["id"]) for r in rows]
    remote = _by_ids("Invoice", [r["qbo_id"] for r in rows], params={"include": "invoiceLink"})
    payments = _by_ids("Payment", sorted({pid for inv in remote.values() for pid in _linked_payment_ids(inv)}))
    for row in rows:
        if row["qbo_id"] not in remote:
            note_error(row["id"], QuickBooksError(
                "QuickBooks no longer has this invoice (it may have been deleted there). "
                "Send it again, or void it here."))
            summary["missing"] += 1
            continue
        added, updated, removed = _apply_remote(row, remote[row["qbo_id"]], payments)
        summary["added"] += added
        summary["updated"] += updated
        summary["removed"] += removed
    db.set_setting("qbo_last_check", util.now_iso())
    return summary


def maybe_check():
    """Called when busy pages load: checks for payments at most every 15
    minutes. Never raises; problems are shown under Settings → QuickBooks."""
    if not is_connected() or db.get_setting("qbo_auto_check") != "1":
        return
    now = datetime.now()
    last = db.get_setting("qbo_last_check_attempt")
    try:
        if last and datetime.fromisoformat(last) > now - CHECK_EVERY:
            return
    except ValueError:
        pass
    db.set_setting("qbo_last_check_attempt", now.isoformat(timespec="seconds"))
    try:
        check_payments()
    except QuickBooksError as exc:
        if is_connected():
            db.set_setting("qbo_last_error", f"Automatic payment check failed: {exc}")
    else:
        db.set_setting("qbo_last_error", "")


def summary_message(summary):
    parts = []
    if summary["added"]:
        parts.append(f"{summary['added']} new payment{'s' if summary['added'] != 1 else ''}")
    if summary["updated"]:
        parts.append(f"{summary['updated']} changed")
    if summary["removed"]:
        parts.append(f"{summary['removed']} removed in QuickBooks")
    if summary["missing"]:
        parts.append(f"{summary['missing']} invoice{'s' if summary['missing'] != 1 else ''} missing from QuickBooks")
    if summary["problems"]:
        parts.append(f"{summary['problems']} with payments QuickBooks didn't accept (see those invoices)")
    checked = f"Checked {summary['checked']} invoice{'s' if summary['checked'] != 1 else ''} in QuickBooks"
    return f"{checked}: {', '.join(parts)}." if parts else f"{checked}. No payment changes."
