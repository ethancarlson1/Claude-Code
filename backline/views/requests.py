"""The office side of the request form: the inbox, and turning a request
into an inquiry (or adding it to an event that already exists)."""

from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db, files, intake, util
from .events import client_choices, event_type_choices, venue_choices

bp = Blueprint("requests", __name__)

STATUSES = [("new", "New"), ("converted", "Became events"), ("archived", "Archived"), ("all", "All")]


def get_request(request_id):
    row = db.query("SELECT * FROM client_requests WHERE id = ?", (request_id,), one=True)
    if row is None:
        abort(404)
    return row


@bp.route("/requests")
def index():
    status = request.args.get("status", "new")
    if status not in dict(STATUSES):
        status = "new"
    where = "" if status == "all" else "WHERE r.status = ?"
    rows = db.query(
        f"""SELECT r.*, e.title AS event_title,
              (SELECT COUNT(*) FROM client_request_files f WHERE f.request_id = r.id) AS file_count
            FROM client_requests r LEFT JOIN events e ON e.id = r.event_id {where}
            ORDER BY r.created_at DESC, r.id DESC""",
        () if status == "all" else (status,),
    )
    counts = {r["status"]: r["n"] for r in db.query("SELECT status, COUNT(*) AS n FROM client_requests GROUP BY status")}
    return render_template("requests/list.html", rows=[(r, intake.answers_of(r)) for r in rows], status=status,
                           statuses=STATUSES, counts=counts, enabled=db.get_setting("request_form_enabled") == "1")


@bp.route("/requests/form", methods=["POST"])
def toggle_form():
    on = request.form.get("enabled") == "1"
    db.set_setting("request_form_enabled", "1" if on else "0")
    flash("The request form is on." if on else "The request form is off. Anyone opening the link is asked to call or email.",
          "ok")
    return redirect(url_for("requests.index"))


def _event_options(near_date=None):
    """Events a request could belong to: recent and upcoming, nearest the requested date first."""
    since = (util.today() - timedelta(days=60)).isoformat()
    rows = db.query(
        """SELECT e.id, e.title, e.event_date, c.name AS client_name FROM events e
           LEFT JOIN clients c ON c.id = e.client_id
           WHERE e.status != 'cancelled' AND COALESCE(e.end_date, e.event_date) >= ? ORDER BY e.event_date""",
        (since,),
    )
    return [(r["id"], f"{util.fdate(r['event_date'], 'short')} — {r['title']}", r["event_date"] == near_date)
            for r in rows]


@bp.route("/requests/<int:request_id>")
def detail(request_id):
    req = get_request(request_id)
    answers = intake.answers_of(req)
    event = db.query("SELECT id, title FROM events WHERE id = ?", (req["event_id"],), one=True) if req["event_id"] else None
    return render_template(
        "requests/detail.html", req=req, answers=answers, summary=intake.summary(answers, skip=("about",)), event=event,
        files=db.query("SELECT * FROM client_request_files WHERE request_id = ? ORDER BY id", (request_id,)),
        events=_event_options(answers.get("event_date")), settings=db.get_settings(),
    )


@bp.route("/requests/<int:request_id>/convert", methods=["GET", "POST"])
def convert(request_id):
    req = get_request(request_id)
    if req["status"] == "converted":
        flash("This request has already been turned into an event.", "bad")
        return redirect(url_for("requests.detail", request_id=request_id))
    a = intake.answers_of(req)
    client_match, client_why = intake.matching_client(a)
    venue_match = intake.matching_venue(a)
    types = event_type_choices()
    values = {
        "title": intake.title_for(a),
        "event_type": a.get("event_type") if a.get("event_type") in types else "",
        "event_date": a.get("event_date") or "",
        "end_date": a.get("end_date") or "",
        "client": str(client_match) if client_match else "new",
        "venue": str(venue_match) if venue_match else ("new" if a.get("venue_name") else ""),
    }
    errors = {}
    if request.method == "POST":
        values = {k: request.form.get(k, "").strip() for k in values}
        if not values["title"]:
            errors["title"] = "Give the event a title."
        for key in ("event_date", "end_date"):
            if values[key]:
                try:
                    values[key] = datetime.strptime(values[key], "%Y-%m-%d").date().isoformat()
                except ValueError:
                    errors[key] = "Enter a valid date."
        if not values["event_date"] and "event_date" not in errors:
            errors["event_date"] = "Events need a date. Pick your best guess; you can change it later."
        if values["end_date"] and values["end_date"] == values["event_date"]:
            values["end_date"] = ""
        elif values["end_date"] and values["event_date"] and values["end_date"] < values["event_date"]:
            errors["end_date"] = "The end date can't be before the start date."
        if values["event_type"] not in [""] + types:
            errors["event_type"] = "Choose an event type."
        clients = {str(c) for c, _label in client_choices()}
        if values["client"] not in clients | {"new", ""}:
            errors["client"] = "Choose a client."
        venues = {str(v) for v, _label in venue_choices()}
        if values["venue"] not in venues | {"new", ""} or (values["venue"] == "new" and not a.get("venue_name")):
            errors["venue"] = "Choose a venue."
        if not errors:
            event_id = intake.create_event(req, values["title"], values["event_date"], values["end_date"] or None,
                                           values["event_type"], values["client"], values["venue"])
            flash(f"Inquiry created from request #{request_id}. Review the details, then build the gear list and quote.",
                  "ok")
            return redirect(url_for("events.detail", event_id=event_id))
    filled = [intake.FIELD_LABELS[k] for k in intake.event_fields(a)]
    return render_template(
        "requests/convert.html", req=req, answers=a, values=values, errors=errors, types=types,
        clients=client_choices(), client_why=client_why if client_match else None, venues=venue_choices(),
        filled=filled, file_count=db.scalar("SELECT COUNT(*) FROM client_request_files WHERE request_id = ?",
                                            (request_id,)),
    )


@bp.route("/requests/<int:request_id>/add-to-event", methods=["POST"])
def add_to_event(request_id):
    req = get_request(request_id)
    event_id = request.form.get("event_id", type=int)
    if req["status"] == "converted" or not event_id or \
            not db.scalar("SELECT 1 FROM events WHERE id = ?", (event_id,)):
        flash("Choose an event to add this request to.", "bad")
        return redirect(url_for("requests.detail", request_id=request_id))
    filled = intake.add_to_event(req, event_id)
    message = f"Added request #{request_id} to this event"
    message += f", filling in {', '.join(filled).lower()}." if filled else "."
    flash(message + " Anything that differed from what was already here is in the office notes.", "ok")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/requests/<int:request_id>/status", methods=["POST"])
def set_status(request_id):
    req = get_request(request_id)
    action = request.form.get("action")
    if action == "archive" and req["status"] == "new":
        db.update("client_requests", request_id, {"status": "archived", "handled_at": util.now_iso()})
        flash("Request archived.", "ok")
    elif action == "reopen" and req["status"] == "archived":
        db.update("client_requests", request_id, {"status": "new", "handled_at": None})
        flash("Request moved back to New.", "ok")
    else:
        abort(400)
    return redirect(url_for("requests.detail", request_id=request_id))


@bp.route("/requests/<int:request_id>/delete", methods=["POST"])
def delete(request_id):
    intake.delete(get_request(request_id))
    flash("Request deleted.", "ok")
    return redirect(url_for("requests.index"))


@bp.route("/requests/<int:request_id>/files/<int:file_id>")
def download_file(request_id, file_id):
    row = db.query("SELECT * FROM client_request_files WHERE id = ? AND request_id = ?", (file_id, request_id), one=True)
    if row is None:
        abort(404)
    return files.send_event_file(row)
