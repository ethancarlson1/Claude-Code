from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db, forms, services, util
from ..forms import Field

bp = Blueprint("contracts", __name__)

TERMS_FIELDS = [
    Field("title", "Title", required=True, wide=True),
    Field("total_amount", "Contract total", type="money", required=True),
    Field("deposit_amount", "Deposit", type="money", required=True),
    Field("deposit_due_date", "Deposit due", type="date", help="Leave blank for 'due at signing'."),
    Field("balance_due_date", "Balance due", type="date"),
]
EDIT_FIELDS = TERMS_FIELDS + [Field("body", "Contract text", type="textarea", required=True)]


def get_contract(contract_id):
    row = db.query(
        """SELECT k.*, e.title AS event_title, e.reference_number, e.event_date, e.client_id
           FROM contracts k JOIN events e ON e.id = k.event_id WHERE k.id = ?""",
        (contract_id,),
        one=True,
    )
    if row is None:
        abort(404)
    return row


def _validate_amounts(data, errors):
    if not errors and data["deposit_amount"] > data["total_amount"]:
        errors["deposit_amount"] = "Deposit can't be more than the total."


@bp.route("/contracts")
def index():
    status = request.args.get("status", "")
    where, args = "", []
    if status in util.CONTRACT_STATUSES:
        where, args = "WHERE k.status = ?", [status]
    rows = db.query(
        f"""SELECT k.*, e.title AS event_title, e.event_date, c.name AS client_name
            FROM contracts k JOIN events e ON e.id = k.event_id
            LEFT JOIN clients c ON c.id = e.client_id
            {where} ORDER BY e.event_date DESC, k.id DESC""",
        args,
    )
    return render_template("contracts/list.html", rows=rows, status=status, statuses=util.CONTRACT_STATUSES)


@bp.route("/contracts/new", methods=["GET", "POST"])
def new():
    event_id = request.values.get("event_id", type=int)
    if not event_id:
        events = db.query(
            "SELECT id, title, event_date, reference_number FROM events WHERE status != 'cancelled' "
            "ORDER BY event_date DESC LIMIT 200"
        )
        return render_template("contracts/pick_event.html", events=events)
    event = db.query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
    if event is None:
        abort(404)
    settings = db.get_settings()
    total = services.gear_total(event)
    deposit = util.round_money(total * util.to_decimal(settings["deposit_percent"] or 0) / 100)
    event_date = util.parse_date(event["event_date"])
    values = {
        "title": "Equipment Rental & Production Services Agreement",
        "total_amount": f"{total:.2f}",
        "deposit_amount": f"{deposit:.2f}",
        "deposit_due_date": "",
        "balance_due_date": max(event_date - timedelta(days=7), util.today()).isoformat(),
    }
    errors = {}
    if request.method == "POST":
        values, errors = forms.parse(TERMS_FIELDS, request.form)
        _validate_amounts(values, errors)
        if not errors:
            number = services.next_number("contracts", settings["contract_prefix"])
            values["body"] = services.render_contract(
                settings["contract_template"], event, number, values["total_amount"],
                values["deposit_amount"], values["deposit_due_date"], values["balance_due_date"],
            )
            contract_id = db.insert("contracts", {
                **values, "event_id": event_id, "number": number, "public_key": util.gen_key(18),
            })
            flash(f"Contract {number} created. Review the text, then mark it sent to get the signing link.", "ok")
            return redirect(url_for("contracts.detail", contract_id=contract_id))
    return render_template("contracts/new.html", event=event, values=values, errors=errors,
                           fields=TERMS_FIELDS, gear_total=total)


@bp.route("/contracts/<int:contract_id>")
def detail(contract_id):
    contract = get_contract(contract_id)
    event = db.query("SELECT * FROM events WHERE id = ?", (contract["event_id"],), one=True)
    client, venue = services.event_context(event)
    return render_template("contracts/detail.html", contract=contract, event=event, client=client,
                           settings=db.get_settings())


@bp.route("/contracts/<int:contract_id>/edit", methods=["GET", "POST"])
def edit(contract_id):
    contract = get_contract(contract_id)
    if contract["status"] in ("signed", "void"):
        flash(f"This contract is {contract['status']} and can't be edited. Create a new one instead.", "bad")
        return redirect(url_for("contracts.detail", contract_id=contract_id))
    values, errors = dict(contract), {}
    if request.method == "POST":
        values, errors = forms.parse(EDIT_FIELDS, request.form)
        _validate_amounts(values, errors)
        if not errors:
            db.update("contracts", contract_id, values)
            flash("Contract saved.", "ok")
            return redirect(url_for("contracts.detail", contract_id=contract_id))
    return render_template("contracts/edit.html", contract=contract, values=values, errors=errors,
                           fields=EDIT_FIELDS)


@bp.route("/contracts/<int:contract_id>/regenerate", methods=["POST"])
def regenerate(contract_id):
    contract = get_contract(contract_id)
    if contract["status"] != "draft":
        abort(400)
    event = db.query("SELECT * FROM events WHERE id = ?", (contract["event_id"],), one=True)
    body = services.render_contract(
        db.get_setting("contract_template"), event, contract["number"], contract["total_amount"],
        contract["deposit_amount"], contract["deposit_due_date"], contract["balance_due_date"],
    )
    db.update("contracts", contract_id, {"body": body})
    flash("Contract text rebuilt from the current template and event details.", "ok")
    return redirect(url_for("contracts.detail", contract_id=contract_id))


@bp.route("/contracts/<int:contract_id>/status", methods=["POST"])
def set_status(contract_id):
    contract = get_contract(contract_id)
    action = request.form.get("action")
    if action == "send" and contract["status"] == "draft":
        db.update("contracts", contract_id, {"status": "sent", "sent_at": util.now_iso()})
        flash("Marked as sent. Share the signing link with your client.", "ok")
    elif action == "unsend" and contract["status"] == "sent":
        db.update("contracts", contract_id, {"status": "draft", "sent_at": None})
        flash("Back to draft. The signing link is disabled until you send it again.", "ok")
    elif action == "void" and contract["status"] != "void":
        db.update("contracts", contract_id, {"status": "void"})
        flash("Contract voided.", "ok")
    else:
        abort(400)
    return redirect(url_for("contracts.detail", contract_id=contract_id))


@bp.route("/contracts/<int:contract_id>/delete", methods=["POST"])
def delete(contract_id):
    contract = get_contract(contract_id)
    if contract["status"] == "signed":
        flash("Signed contracts can't be deleted. Void it instead.", "bad")
        return redirect(url_for("contracts.detail", contract_id=contract_id))
    db.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
    flash(f"Deleted contract {contract['number']}.", "ok")
    return redirect(url_for("events.detail", event_id=contract["event_id"], tab="documents"))
