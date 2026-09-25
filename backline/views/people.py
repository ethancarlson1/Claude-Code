"""Clients, venues, crew and company vehicles share one set of list/detail/form views."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db, forms, services, util
from ..defaults import VEHICLE_TYPES
from ..forms import Field

bp = Blueprint("people", __name__)

KINDS = {
    "clients": {
        "table": "clients",
        "title": "Clients",
        "singular": "client",
        "search": ["name", "company", "email", "phone"],
        "columns": [("name", "Name"), ("company", "Company"), ("email", "Email"), ("phone", "Phone")],
        "fields": [
            Field("name", "Name", required=True, placeholder="e.g. Sofia Alvarez"),
            Field("company", "Company / organization"),
            Field("email", "Email", type="email"),
            Field("phone", "Phone", type="tel"),
            Field("address", "Billing address", type="textarea"),
            Field("notes", "Notes", type="textarea"),
        ],
    },
    "venues": {
        "table": "venues",
        "title": "Venues",
        "singular": "venue",
        "search": ["name", "city", "address", "contact_name"],
        "columns": [("name", "Name"), ("city", "City"), ("contact_name", "Contact"), ("contact_phone", "Phone")],
        "fields": [
            Field("name", "Name", required=True, section="Venue"),
            Field("address", "Street address", section="Venue"),
            Field("city", "City", section="Venue"),
            Field("state", "State", section="Venue"),
            Field("postal_code", "ZIP / postal code", section="Venue"),
            Field("contact_name", "Venue contact", section="Contact"),
            Field("contact_phone", "Contact phone", type="tel", section="Contact"),
            Field("contact_email", "Contact email", type="email", section="Contact"),
            Field("load_in_notes", "Load-in (dock, stairs, elevator, push distance)", type="textarea", section="Production"),
            Field("power_notes", "Power (circuits, amperage, cam-lok, distance)", type="textarea", section="Production"),
            Field("stage_notes", "Stage (dimensions, house PA, restrictions)", type="textarea", section="Production"),
            Field("parking_notes", "Parking", type="textarea", section="Production"),
            Field("notes", "Notes", type="textarea", section="Production"),
        ],
    },
    "crew": {
        "table": "crew",
        "title": "Crew",
        "singular": "crew member",
        "search": ["name", "role", "email", "phone"],
        "columns": [("name", "Name"), ("role", "Role"), ("phone", "Phone"), ("email", "Email"),
                    ("day_rate", "Day rate"), ("active", "Active")],
        "fields": [
            Field("name", "Name", required=True),
            Field("role", "Default role", placeholder="e.g. A1, A2, Backline Tech, Stagehand"),
            Field("email", "Email", type="email"),
            Field("phone", "Phone", type="tel"),
            Field("day_rate", "Day rate", type="money"),
            Field("hourly_rate", "Hourly rate", type="money"),
            Field("dietary", "Dietary restrictions", placeholder="For crew meal counts, e.g. vegetarian"),
            Field("w9_on_file", "W-9 on file (for contractor tax forms)", type="checkbox", default=0),
            Field("active", "Active (available for booking)", type="checkbox", default=1),
            Field("notes", "Notes", type="textarea", placeholder="Skills, certifications, vehicle, availability..."),
        ],
    },
    "vehicles": {
        "table": "vehicles",
        "title": "Vehicles",
        "singular": "vehicle",
        "search": ["name", "vehicle_type", "make_model", "plate"],
        "columns": [("name", "Name"), ("vehicle_type", "Type"), ("make_model", "Make / model"), ("plate", "Plate"),
                    ("capacity", "Capacity"), ("status", "Status")],
        "fields": [
            Field("name", "Name", required=True, section="Vehicle", placeholder="e.g. Box Truck 1"),
            Field("vehicle_type", "Type", type="select", choices=VEHICLE_TYPES, section="Vehicle"),
            Field("make_model", "Make / model / year", section="Vehicle", placeholder="e.g. 2021 Isuzu NPR 16'"),
            Field("plate", "License plate", section="Vehicle"),
            Field("capacity", "Capacity / features", section="Vehicle", placeholder="e.g. 16 ft box, liftgate, E-track"),
            Field("status", "Status", type="select", required=True, default="active", section="Vehicle",
                  choices=[("active", "Active"), ("maintenance", "In maintenance"), ("retired", "Retired")],
                  help="Vehicles in maintenance or retired are flagged if booked."),
            Field("registration_expires", "Registration expires", type="date", section="Paperwork"),
            Field("insurance_expires", "Insurance expires", type="date", section="Paperwork",
                  help="The dashboard warns 30 days before either date."),
            Field("notes", "Notes", type="textarea", section="Paperwork",
                  placeholder="Height clearance, fuel card, where the keys live, service schedule…"),
        ],
    },
}

KIND_ROUTE = "<any(clients, venues, crew, vehicles):kind>"


def get_kind(kind):
    spec = KINDS.get(kind)
    if spec is None:
        abort(404)
    return spec


def get_row(spec, row_id):
    row = db.query(f"SELECT * FROM {spec['table']} WHERE id = ?", (row_id,), one=True)
    if row is None:
        abort(404)
    return row


@bp.route(f"/{KIND_ROUTE}")
def index(kind):
    spec = get_kind(kind)
    q = request.args.get("q", "").strip()
    where, args = "", []
    if q:
        where = "WHERE " + " OR ".join(f"{c} LIKE ?" for c in spec["search"])
        args = [f"%{q}%"] * len(spec["search"])
    order = {"crew": "active DESC, name COLLATE NOCASE",
             "vehicles": "status = 'retired', name COLLATE NOCASE"}.get(kind, "name COLLATE NOCASE")
    rows = db.query(f"SELECT * FROM {spec['table']} {where} ORDER BY {order}", args)
    return render_template("people/list.html", kind=kind, spec=spec, rows=rows, q=q)


@bp.route(f"/{KIND_ROUTE}/new", methods=["GET", "POST"])
def new(kind):
    spec = get_kind(kind)
    values, errors = {}, {}
    if request.method == "POST":
        values, errors = forms.parse(spec["fields"], request.form)
        if not errors:
            row_id = db.insert(spec["table"], values)
            flash(f"Added {values['name']}.", "ok")
            return redirect(url_for("people.detail", kind=kind, row_id=row_id))
    return render_template("people/form.html", kind=kind, spec=spec, row=None, values=values,
                           errors=errors, grouped=forms.sections(spec["fields"]))


@bp.route(f"/{KIND_ROUTE}/<int:row_id>/edit", methods=["GET", "POST"])
def edit(kind, row_id):
    spec = get_kind(kind)
    row = get_row(spec, row_id)
    values, errors = dict(row), {}
    if request.method == "POST":
        values, errors = forms.parse(spec["fields"], request.form)
        if not errors:
            db.update(spec["table"], row_id, values)
            flash("Saved.", "ok")
            return redirect(url_for("people.detail", kind=kind, row_id=row_id))
    return render_template("people/form.html", kind=kind, spec=spec, row=row, values=values,
                           errors=errors, grouped=forms.sections(spec["fields"]))


@bp.route(f"/{KIND_ROUTE}/<int:row_id>")
def detail(kind, row_id):
    spec = get_kind(kind)
    row = get_row(spec, row_id)
    events, invoices, assignments, pay, paperwork = [], [], [], None, {}
    if kind == "vehicles":
        events = db.query(
            """SELECT e.*, ev.description, ev.departs, c.name AS driver_name FROM event_vehicles ev
               JOIN events e ON e.id = ev.event_id LEFT JOIN crew c ON c.id = ev.driver_id
               WHERE ev.vehicle_id = ? ORDER BY e.event_date DESC""",
            (row_id,),
        )
        paperwork = {k: services.paperwork_status(row[k]) for k in ("registration_expires", "insurance_expires")}
    elif kind == "clients":
        events = db.query("SELECT * FROM events WHERE client_id = ? ORDER BY event_date DESC", (row_id,))
        for inv in db.query("SELECT * FROM invoices WHERE client_id = ? ORDER BY issue_date DESC", (row_id,)):
            totals = services.invoice_totals(inv)
            invoices.append({"row": inv, "totals": totals, "status": services.invoice_status(inv, totals)})
    elif kind == "venues":
        events = db.query("SELECT * FROM events WHERE venue_id = ? ORDER BY event_date DESC", (row_id,))
    elif kind == "crew":
        assignments = services.crew_pay_rows("a.crew_id = ?", (row_id,))
        pay = {**services.crew_pay_summary(assignments), "by_year": services.paid_by_year(assignments)}
    return render_template("people/detail.html", kind=kind, spec=spec, row=row, events=events,
                           invoices=invoices, assignments=assignments, pay=pay, paperwork=paperwork,
                           today=util.today().isoformat())


@bp.route(f"/{KIND_ROUTE}/<int:row_id>/delete", methods=["POST"])
def delete(kind, row_id):
    spec = get_kind(kind)
    row = get_row(spec, row_id)
    if kind == "vehicles" and db.scalar("SELECT 1 FROM event_vehicles WHERE vehicle_id = ?", (row_id,)):
        flash(f"{row['name']} is on event schedules. Set its status to Retired instead so the history is kept.", "bad")
        return redirect(url_for("people.detail", kind=kind, row_id=row_id))
    db.execute(f"DELETE FROM {spec['table']} WHERE id = ?", (row_id,))
    flash(f"Deleted {row['name']}.", "ok")
    return redirect(url_for("people.index", kind=kind))
