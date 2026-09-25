"""Clients, venues and crew share one set of list/detail/form views."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db, forms, services
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
}


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


@bp.route("/<any(clients, venues, crew):kind>")
def index(kind):
    spec = get_kind(kind)
    q = request.args.get("q", "").strip()
    where, args = "", []
    if q:
        where = "WHERE " + " OR ".join(f"{c} LIKE ?" for c in spec["search"])
        args = [f"%{q}%"] * len(spec["search"])
    order = "active DESC, name COLLATE NOCASE" if kind == "crew" else "name COLLATE NOCASE"
    rows = db.query(f"SELECT * FROM {spec['table']} {where} ORDER BY {order}", args)
    return render_template("people/list.html", kind=kind, spec=spec, rows=rows, q=q)


@bp.route("/<any(clients, venues, crew):kind>/new", methods=["GET", "POST"])
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


@bp.route("/<any(clients, venues, crew):kind>/<int:row_id>/edit", methods=["GET", "POST"])
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


@bp.route("/<any(clients, venues, crew):kind>/<int:row_id>")
def detail(kind, row_id):
    spec = get_kind(kind)
    row = get_row(spec, row_id)
    events, invoices, assignments, pay = [], [], [], None
    if kind == "clients":
        events = db.query("SELECT * FROM events WHERE client_id = ? ORDER BY event_date DESC", (row_id,))
        for inv in db.query("SELECT * FROM invoices WHERE client_id = ? ORDER BY issue_date DESC", (row_id,)):
            totals = services.invoice_totals(inv)
            invoices.append({"row": inv, "totals": totals, "status": services.invoice_status(inv, totals)})
    elif kind == "venues":
        events = db.query("SELECT * FROM events WHERE venue_id = ? ORDER BY event_date DESC", (row_id,))
    else:
        assignments = services.crew_pay_rows("a.crew_id = ?", (row_id,))
        pay = {**services.crew_pay_summary(assignments), "by_year": services.paid_by_year(assignments)}
    return render_template("people/detail.html", kind=kind, spec=spec, row=row, events=events,
                           invoices=invoices, assignments=assignments, pay=pay)


@bp.route("/<any(clients, venues, crew):kind>/<int:row_id>/delete", methods=["POST"])
def delete(kind, row_id):
    spec = get_kind(kind)
    row = get_row(spec, row_id)
    db.execute(f"DELETE FROM {spec['table']} WHERE id = ?", (row_id,))
    flash(f"Deleted {row['name']}.", "ok")
    return redirect(url_for("people.index", kind=kind))
