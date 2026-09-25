from datetime import timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db, forms, services, util
from ..forms import Field
from .events import client_choices

bp = Blueprint("invoices", __name__)


def event_choices():
    return [
        (r["id"], f"{util.fdate(r['event_date'], 'short')} — {r['title']}")
        for r in db.query("SELECT id, title, event_date FROM events ORDER BY event_date DESC LIMIT 300")
    ]


HEADER_FIELDS = [
    Field("client_id", "Bill to", type="fk", choices=client_choices),
    Field("event_id", "Event", type="fk", choices=event_choices),
    Field("issue_date", "Issue date", type="date", required=True),
    Field("due_date", "Due date", type="date"),
    Field("tax_rate", "Tax rate (%)", type="number"),
    Field("discount", "Discount ($)", type="money"),
    Field("notes", "Notes to client", type="textarea"),
    Field("terms", "Terms", type="textarea"),
]

PAYMENT_FIELDS = [
    Field("paid_on", "Date", type="date", required=True),
    Field("amount", "Amount", type="money", required=True),
    Field("method", "Method", type="select", choices=util.PAYMENT_METHODS),
    Field("reference", "Reference / check #"),
    Field("notes", "Notes"),
]


def get_invoice(invoice_id):
    row = db.query("SELECT * FROM invoices WHERE id = ?", (invoice_id,), one=True)
    if row is None:
        abort(404)
    return row


def invoice_bundle(invoice):
    items = db.query("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY sort, id", (invoice["id"],))
    payments = db.query("SELECT * FROM payments WHERE invoice_id = ? ORDER BY paid_on, id", (invoice["id"],))
    totals = services.invoice_totals(invoice, items, payments)
    client = db.query("SELECT * FROM clients WHERE id = ?", (invoice["client_id"],), one=True)
    event = db.query("SELECT * FROM events WHERE id = ?", (invoice["event_id"],), one=True)
    venue = db.query("SELECT * FROM venues WHERE id = ?", (event["venue_id"],), one=True) if event else None
    contract = db.query("SELECT id, number FROM contracts WHERE id = ?", (invoice["contract_id"],), one=True)
    return dict(
        invoice=invoice, items=items, payments=payments, totals=totals, client=client, event=event, contract=contract,
        venue=venue, status=services.invoice_status(invoice, totals), settings=db.get_settings(),
    )


def _clean_header(data, errors):
    if data.get("tax_rate") is None:
        data["tax_rate"] = 0
    elif not 0 <= data["tax_rate"] <= 100:
        errors["tax_rate"] = "Tax rate must be between 0 and 100."
    if data.get("discount") is None:
        data["discount"] = 0
    if data.get("due_date") and data.get("issue_date") and data["due_date"] < data["issue_date"]:
        errors["due_date"] = "Due date can't be before the issue date."


@bp.route("/invoices")
def index():
    status_filter = request.args.get("status", "")
    rows = []
    for inv in db.query(
        """SELECT i.*, c.name AS client_name, e.title AS event_title FROM invoices i
           LEFT JOIN clients c ON c.id = i.client_id LEFT JOIN events e ON e.id = i.event_id
           ORDER BY i.issue_date DESC, i.id DESC"""
    ):
        totals = services.invoice_totals(inv)
        status = services.invoice_status(inv, totals)
        rows.append({"row": inv, "totals": totals, "status": status})
    outstanding = sum((r["totals"]["balance"] for r in rows if r["status"] in ("sent", "partial", "overdue")), Decimal(0))
    overdue = sum((r["totals"]["balance"] for r in rows if r["status"] == "overdue"), Decimal(0))
    month = util.today().strftime("%Y-%m")
    collected = util.to_decimal(db.scalar(
        "SELECT COALESCE(SUM(p.amount), 0) FROM payments p JOIN invoices i ON i.id = p.invoice_id "
        "WHERE i.status != 'void' AND p.paid_on LIKE ?",
        (month + "%",),
    ))
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]
    return render_template(
        "invoices/list.html", rows=rows, status=status_filter, outstanding=outstanding, overdue=overdue,
        collected=collected, statuses=["draft", "sent", "partial", "overdue", "paid", "void"],
    )


@bp.route("/invoices/new", methods=["GET", "POST"])
def new():
    event_id = request.values.get("event_id", type=int)
    event = db.query("SELECT * FROM events WHERE id = ?", (event_id,), one=True) if event_id else None
    today = util.today()
    values = {
        "client_id": event["client_id"] if event else None,
        "event_id": event["id"] if event else None,
        "issue_date": today.isoformat(),
        "due_date": (today + timedelta(days=15)).isoformat(),
        "tax_rate": db.get_setting("default_tax_rate"),
        "discount": 0,
        "terms": db.get_setting("invoice_terms"),
    }
    if event and util.parse_date(event["event_date"]) > today + timedelta(days=15):
        values["due_date"] = event["event_date"]
    errors = {}
    if request.method == "POST":
        values, errors = forms.parse(HEADER_FIELDS, request.form)
        _clean_header(values, errors)
        if not errors:
            values["number"] = services.next_number("invoices", db.get_setting("invoice_prefix"))
            values["public_key"] = util.gen_key(18)
            invoice_id = db.insert("invoices", values)
            linked = db.query("SELECT * FROM events WHERE id = ?", (values["event_id"],), one=True) if values["event_id"] else None
            if linked and request.form.get("prefill"):
                for sort, line in enumerate(services.invoice_lines_for_event(linked)):
                    db.insert("invoice_items", {**line, "invoice_id": invoice_id, "sort": sort})
            flash(f"Invoice {values['number']} created as a draft.", "ok")
            return redirect(url_for("invoices.edit", invoice_id=invoice_id))
    return render_template("invoices/new.html", values=values, errors=errors, fields=HEADER_FIELDS, event=event)


def _parse_lines(form):
    descriptions = form.getlist("item_description")
    quantities = form.getlist("item_quantity")
    prices = form.getlist("item_price")
    taxable = form.getlist("item_taxable")
    lines, errors = [], []
    for i, desc in enumerate(descriptions):
        desc = desc.strip()
        qty_raw = quantities[i] if i < len(quantities) else ""
        price_raw = prices[i] if i < len(prices) else ""
        if not desc and not qty_raw.strip() and not price_raw.strip():
            continue  # blank row
        try:
            qty = Decimal(qty_raw or "1")
            price = Decimal((price_raw or "0").replace(",", "").replace("$", ""))
        except InvalidOperation:
            errors.append(f"Line {i + 1}: quantity and price must be numbers.")
            continue
        if not desc:
            errors.append(f"Line {i + 1}: description is required.")
            continue
        lines.append({
            "description": desc,
            "quantity": float(qty),
            "unit_price": float(util.round_money(price)),
            "taxable": 0 if i < len(taxable) and taxable[i] == "0" else 1,
            "sort": len(lines),
        })
    return lines, errors


@bp.route("/invoices/<int:invoice_id>/edit", methods=["GET", "POST"])
def edit(invoice_id):
    invoice = get_invoice(invoice_id)
    if invoice["status"] == "void":
        flash("Void invoices can't be edited.", "bad")
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))
    values, errors = dict(invoice), {}
    items = db.query("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY sort, id", (invoice_id,))
    line_errors = []
    if request.method == "POST":
        values, errors = forms.parse(HEADER_FIELDS, request.form)
        _clean_header(values, errors)
        lines, line_errors = _parse_lines(request.form)
        if not errors and not line_errors:
            conn = db.get_db()
            db.update("invoices", invoice_id, values)
            conn.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
            for line in lines:
                conn.execute(
                    "INSERT INTO invoice_items (invoice_id, description, quantity, unit_price, taxable, sort) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (invoice_id, line["description"], line["quantity"], line["unit_price"], line["taxable"], line["sort"]),
                )
            conn.commit()
            flash("Invoice saved.", "ok")
            return redirect(url_for("invoices.detail", invoice_id=invoice_id))
        items = lines
    return render_template("invoices/edit.html", invoice=invoice, values=values, errors=errors,
                           line_errors=line_errors, items=items, fields=HEADER_FIELDS)


@bp.route("/invoices/<int:invoice_id>")
def detail(invoice_id):
    bundle = invoice_bundle(get_invoice(invoice_id))
    return render_template("invoices/detail.html", **bundle, payment_fields=PAYMENT_FIELDS,
                           payment_defaults={"paid_on": util.today().isoformat(),
                                             "amount": f"{max(bundle['totals']['balance'], 0):.2f}"})


@bp.route("/invoices/<int:invoice_id>/status", methods=["POST"])
def set_status(invoice_id):
    invoice = get_invoice(invoice_id)
    action = request.form.get("action")
    transitions = {"send": ("draft", "sent"), "unsend": ("sent", "draft"), "void": (None, "void"), "reopen": ("void", "draft")}
    if action not in transitions:
        abort(400)
    source, target = transitions[action]
    if (source and invoice["status"] != source) or invoice["status"] == target:
        abort(400)
    db.update("invoices", invoice_id, {"status": target})
    flash({"send": "Marked as sent. Share the invoice link with your client.",
           "unsend": "Back to draft.", "void": "Invoice voided.", "reopen": "Invoice reopened as a draft."}[action], "ok")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/payments", methods=["POST"])
def add_payment(invoice_id):
    invoice = get_invoice(invoice_id)
    data, errors = forms.parse(PAYMENT_FIELDS, request.form)
    if not errors and data["amount"] <= 0:
        errors["amount"] = "Amount must be more than zero."
    if errors:
        flash(" ".join(errors.values()), "bad")
    else:
        db.insert("payments", {**data, "invoice_id": invoice_id})
        if invoice["status"] == "draft":
            db.update("invoices", invoice_id, {"status": "sent"})
        flash(f"Recorded {util.money(data['amount'])} payment.", "ok")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/payments/<int:payment_id>/delete", methods=["POST"])
def delete_payment(invoice_id, payment_id):
    get_invoice(invoice_id)
    db.execute("DELETE FROM payments WHERE id = ? AND invoice_id = ?", (payment_id, invoice_id))
    flash("Payment removed.", "ok")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/delete", methods=["POST"])
def delete(invoice_id):
    invoice = get_invoice(invoice_id)
    if invoice["status"] != "draft":
        flash("Only draft invoices can be deleted. Void it instead to keep a record.", "bad")
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))
    db.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    flash(f"Deleted invoice {invoice['number']}.", "ok")
    return redirect(url_for("invoices.index"))
