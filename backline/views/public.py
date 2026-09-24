"""Pages shared outside the office: crew worksheets, contract signing and
client invoices. Each is reached through an unguessable per-record key."""

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from .. import db, services, util
from .events import worksheet_context
from .invoices import invoice_bundle

bp = Blueprint("public", __name__)


def _assignment(reference, key):
    row = db.query(
        """SELECT a.*, c.name, c.phone, c.email FROM event_crew a
           JOIN crew c ON c.id = a.crew_id JOIN events e ON e.id = a.event_id
           WHERE a.worksheet_key = ? AND e.reference_number = ?""",
        (key, reference),
        one=True,
    )
    if row is None:
        abort(404)
    return row


@bp.route("/worksheet/<reference>/<key>")
def worksheet(reference, key):
    assignment = _assignment(reference, key)
    event = db.query("SELECT * FROM events WHERE id = ?", (assignment["event_id"],), one=True)
    return render_template("public/worksheet.html", **worksheet_context(event, assignment), admin=False)


@bp.route("/worksheet/<reference>/<key>/confirm", methods=["POST"])
def confirm(reference, key):
    assignment = _assignment(reference, key)
    confirmed = 0 if request.form.get("decline") else 1
    db.update("event_crew", assignment["id"], {"confirmed": confirmed})
    flash("Thanks — you're confirmed for this event." if confirmed else "Got it — we've marked you as not confirmed.", "ok")
    return redirect(url_for("public.worksheet", reference=reference, key=key))


@bp.route("/worksheet/<reference>/<key>/messages", methods=["POST"])
def post_message(reference, key):
    assignment = _assignment(reference, key)
    body = request.form.get("body", "").strip()
    if body:
        db.insert("event_messages", {
            "event_id": assignment["event_id"], "crew_id": assignment["crew_id"], "author": assignment["name"],
            "body": body[:4000], "created_at": util.now_iso(),
        })
    return redirect(url_for("public.worksheet", reference=reference, key=key) + "#chat")


@bp.route("/worksheet/<reference>/<key>/event.ics")
def worksheet_ics(reference, key):
    assignment = _assignment(reference, key)
    event = db.query("SELECT * FROM events WHERE id = ?", (assignment["event_id"],), one=True)
    company = db.get_setting("company_name")
    role = f" ({assignment['role']})" if assignment["role"] else ""
    body = services.event_ics(
        event, uid=f"{event['reference_number']}-{assignment['id']}@backline",
        summary=f"{company}: {event['title']}{role}",
        description="Worksheet: " + url_for("public.worksheet", reference=reference, key=key, _external=True),
        start_time=assignment["call_time"],
    )
    return Response(body, mimetype="text/calendar",
                    headers={"Content-Disposition": f"attachment; filename={event['reference_number']}.ics"})


def _contract(key):
    contract = db.query("SELECT * FROM contracts WHERE public_key = ?", (key,), one=True)
    if contract is None or contract["status"] == "draft":
        abort(404)
    return contract


@bp.route("/c/<key>")
def contract(key):
    contract = _contract(key)
    event = db.query("SELECT * FROM events WHERE id = ?", (contract["event_id"],), one=True)
    client, _venue = services.event_context(event)
    return render_template("public/contract.html", contract=contract, event=event, client=client,
                           settings=db.get_settings(), error=None)


@bp.route("/c/<key>/sign", methods=["POST"])
def sign_contract(key):
    contract = _contract(key)
    if contract["status"] != "sent":
        flash("This contract can no longer be signed.", "bad")
        return redirect(url_for("public.contract", key=key))
    name = request.form.get("signed_name", "").strip()
    if len(name) < 2 or not request.form.get("agree"):
        event = db.query("SELECT * FROM events WHERE id = ?", (contract["event_id"],), one=True)
        client, _venue = services.event_context(event)
        return render_template("public/contract.html", contract=contract, event=event, client=client,
                               settings=db.get_settings(),
                               error="Type your full name and tick the box to agree."), 400
    db.update("contracts", contract["id"], {
        "status": "signed",
        "signed_name": name,
        "signed_at": util.now_iso(),
        "signed_ip": request.remote_addr,
    })
    flash("Signed. Thank you! Keep this page for your records.", "ok")
    return redirect(url_for("public.contract", key=key))


@bp.route("/i/<key>")
def invoice(key):
    inv = db.query("SELECT * FROM invoices WHERE public_key = ?", (key,), one=True)
    if inv is None or inv["status"] == "draft":
        abort(404)
    return render_template("public/invoice.html", **invoice_bundle(inv))
