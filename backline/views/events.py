from datetime import date, timedelta

from flask import Blueprint, Response, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .. import db, forms, services, util
from ..forms import Field

bp = Blueprint("events", __name__)

TABS = ["overview", "crew", "gear", "checklist", "chat", "documents"]


def client_choices():
    return [
        (r["id"], r["name"] + (f" ({r['company']})" if r["company"] else ""))
        for r in db.query("SELECT id, name, company FROM clients ORDER BY name COLLATE NOCASE")
    ]


def venue_choices():
    return [
        (r["id"], r["name"] + (f" — {r['city']}" if r["city"] else ""))
        for r in db.query("SELECT id, name, city FROM venues ORDER BY name COLLATE NOCASE")
    ]


def crew_choices():
    return [
        (r["id"], r["name"] + (f" — {r['role']}" if r["role"] else ""))
        for r in db.query("SELECT id, name, role FROM crew ORDER BY active DESC, name COLLATE NOCASE")
    ]


EVENT_FIELDS = [
    Field("title", "Event title", required=True, section="Event", placeholder="e.g. Alvarez / Reed Wedding"),
    Field("event_type", "Type", type="select", choices=util.EVENT_TYPES, section="Event"),
    Field("status", "Status", type="select", required=True, section="Event",
          choices=[(s, s.title()) for s in util.EVENT_STATUSES], default="inquiry",
          help="Hold and Confirmed events reserve gear."),
    Field("client_id", "Client", type="fk", choices=client_choices, section="Event"),
    Field("honorees", "Couple / honorees", section="Event", placeholder="e.g. Sofia & Marcus"),
    Field("producer_id", "Producer (event lead)", type="fk", choices=crew_choices, section="Event",
          help="Crew's point person. Shown on worksheets with their contact info."),
    Field("guest_count", "Number of guests", type="int", section="Event"),
    Field("performers", "Artist / performers", section="Event"),
    Field("venue_id", "Venue", type="fk", choices=venue_choices, section="Locations"),
    Field("venue_label", "Label", section="Locations", placeholder="e.g. Reception"),
    Field("venue2_id", "Earlier location", type="fk", choices=venue_choices, section="Locations",
          help="Optional, e.g. a ceremony before the reception. Listed first on worksheets."),
    Field("venue2_label", "Label", section="Locations", placeholder="e.g. Ceremony"),
    Field("event_date", "Date", type="date", required=True, section="Schedule"),
    Field("end_date", "End date", type="date", section="Schedule", help="Multi-day events only."),
    Field("load_in_time", "Load-in", type="time", section="Schedule"),
    Field("soundcheck_time", "Setup complete / soundcheck", type="time", section="Schedule"),
    Field("doors_time", "Doors", type="time", section="Schedule"),
    Field("start_time", "Show start", type="time", section="Schedule"),
    Field("end_time", "Show end", type="time", section="Schedule"),
    Field("load_out_time", "Load-out", type="time", section="Schedule"),
    Field("run_of_show", "Run of show", type="textarea", rows=14, section="Schedule",
          help="Shown on every crew worksheet. Load-in, power, parking, locations and the minute-by-minute."),
    Field("on_site_contact", "Day-of contact", section="On site", placeholder="Planner or venue coordinator"),
    Field("on_site_phone", "Day-of phone", type="tel", section="On site"),
    Field("attire", "Dress code", section="On site", placeholder="e.g. Black suit and tie"),
    Field("crew_meal", "Crew meal", section="On site", placeholder="e.g. Hot meal at 6:30 PM in staff dining room"),
    Field("parking", "Parking & load-in directions", type="textarea", section="On site"),
    Field("audio_notes", "Audio needs", type="textarea", section="Production",
          placeholder="PA coverage, input count, monitor mixes, wireless..."),
    Field("backline_notes", "Backline needs", type="textarea", section="Production",
          placeholder="Rider requests, drum kit specs, amp preferences..."),
    Field("power_notes", "Power", type="textarea", section="Production"),
    Field("crew_notes", "Special requests (crew only)", type="textarea", section="Notes",
          help="On crew worksheets. Never shown to the client."),
    Field("notes", "Office notes", type="textarea", section="Notes", help="Only visible when signed in."),
]

CREW_FIELDS = [
    Field("crew_id", "Crew member", type="fk", required=True,
          choices=lambda: [(r["id"], r["name"]) for r in db.query("SELECT id, name FROM crew ORDER BY name COLLATE NOCASE")]),
    Field("role", "Role"),
    Field("call_time", "Call time", type="time"),
    Field("pay_type", "Pay type", type="select", choices=[("flat", "Flat"), ("hourly", "Hourly")], required=True),
    Field("pay_rate", "Rate", type="money"),
    Field("hours", "Hours", type="number"),
    Field("notes", "Notes"),
]

GEAR_FIELDS = [
    Field("quantity", "Qty", type="int", required=True),
    Field("rate", "Rate / day", type="money"),
    Field("notes", "Notes"),
]


def get_event(event_id):
    event = db.query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
    if event is None:
        abort(404)
    return event


def _validate_dates(data, errors):
    if data.get("end_date") and data.get("event_date") and data["end_date"] < data["event_date"]:
        errors["end_date"] = "End date can't be before the start date."
    if data.get("end_date") == data.get("event_date"):
        data["end_date"] = None


def _back(event_id, tab, anchor=None):
    url = url_for("events.detail", event_id=event_id, tab=tab)
    return redirect(url + (f"#{anchor}" if anchor else ""))


# --- List, calendar ----------------------------------------------------------

@bp.route("/events")
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    when = request.args.get("when", "upcoming")
    where, args = [], []
    if q:
        where.append("(e.title LIKE ? OR e.reference_number LIKE ? OR c.name LIKE ? OR v.name LIKE ? "
                     "OR e.performers LIKE ? OR e.honorees LIKE ?)")
        args += [f"%{q}%"] * 6
    if status in util.EVENT_STATUSES:
        where.append("e.status = ?")
        args.append(status)
    today = util.today().isoformat()
    if when == "upcoming":
        where.append("COALESCE(e.end_date, e.event_date) >= ?")
        args.append(today)
    elif when == "past":
        where.append("COALESCE(e.end_date, e.event_date) < ?")
        args.append(today)
    order = "e.event_date DESC" if when == "past" else "e.event_date ASC"
    events = db.query(
        f"""
        SELECT e.*, c.name AS client_name, v.name AS venue_name, v.city AS venue_city,
          (SELECT COUNT(*) FROM event_checklist_items WHERE event_id = e.id) AS check_total,
          (SELECT COALESCE(SUM(done), 0) FROM event_checklist_items WHERE event_id = e.id) AS check_done,
          (SELECT COUNT(*) FROM event_gear WHERE event_id = e.id) AS gear_total,
          (SELECT COALESCE(SUM(pulled), 0) FROM event_gear WHERE event_id = e.id) AS gear_pulled,
          (SELECT COUNT(*) FROM event_crew WHERE event_id = e.id) AS crew_total,
          (SELECT COALESCE(SUM(confirmed), 0) FROM event_crew WHERE event_id = e.id) AS crew_confirmed
        FROM events e
        LEFT JOIN clients c ON c.id = e.client_id
        LEFT JOIN venues v ON v.id = e.venue_id
        {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY {order}, e.start_time
        """,
        args,
    )
    return render_template("events/list.html", events=events, q=q, status=status, when=when,
                           statuses=util.EVENT_STATUSES)


@bp.route("/calendar")
def calendar():
    try:
        year, month = (int(p) for p in request.args.get("month", "").split("-"))
        date(year, month, 1)
    except ValueError:
        year, month = util.today().year, util.today().month
    first, last = util.month_bounds(year, month)
    grid_start = first - timedelta(days=(first.weekday() + 1) % 7)  # weeks start Sunday
    grid_end = last + timedelta(days=(5 - last.weekday()) % 7)
    events = db.query(
        """
        SELECT e.*, v.name AS venue_name FROM events e LEFT JOIN venues v ON v.id = e.venue_id
        WHERE e.event_date <= ? AND COALESCE(e.end_date, e.event_date) >= ?
        ORDER BY e.event_date, e.start_time
        """,
        (grid_end.isoformat(), grid_start.isoformat()),
    )
    by_day = {}
    for e in events:
        d = max(util.parse_date(e["event_date"]), grid_start)
        end = min(util.parse_date(util.event_end(e)), grid_end)
        while d <= end:
            by_day.setdefault(d, []).append(e)
            d += timedelta(days=1)
    days = []
    d = grid_start
    while d <= grid_end:
        days.append(d)
        d += timedelta(days=1)
    prev_month = (first - timedelta(days=1)).strftime("%Y-%m")
    next_month = (last + timedelta(days=1)).strftime("%Y-%m")
    return render_template("events/calendar.html", days=days, by_day=by_day, first=first,
                           prev_month=prev_month, next_month=next_month)


# --- Create / edit -----------------------------------------------------------

@bp.route("/events/new", methods=["GET", "POST"])
def new():
    templates = db.query("SELECT * FROM checklist_templates ORDER BY id")
    values = {"status": "inquiry", "event_date": request.args.get("date", ""),
              "run_of_show": db.get_setting("run_of_show_template")}
    errors = {}
    if request.method == "POST":
        values, errors = forms.parse(EVENT_FIELDS, request.form)
        _validate_dates(values, errors)
        if not errors:
            client = db.query("SELECT name FROM clients WHERE id = ?", (values["client_id"],), one=True)
            values["reference_number"] = _unique_reference(values["event_date"], client and client["name"], values["title"])
            event_id = db.insert("events", values)
            for template_id in request.form.getlist("templates"):
                services.apply_checklist_template(event_id, int(template_id))
            flash(f"Event {values['reference_number']} created.", "ok")
            return redirect(url_for("events.detail", event_id=event_id))
    return render_template("events/form.html", event=None, values=values, errors=errors,
                           grouped=forms.sections(EVENT_FIELDS), templates=templates,
                           selected_templates=[str(t["id"]) for t in templates] if request.method == "GET"
                           else request.form.getlist("templates"))


def _unique_reference(event_date, client_name, title):
    while True:
        ref = util.gen_reference(event_date, client_name, title)
        if not db.scalar("SELECT 1 FROM events WHERE reference_number = ?", (ref,)):
            return ref


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
def edit(event_id):
    event = get_event(event_id)
    values, errors = dict(event), {}
    if request.method == "POST":
        values, errors = forms.parse(EVENT_FIELDS, request.form)
        _validate_dates(values, errors)
        if not errors:
            values["updated_at"] = util.now_iso()
            db.update("events", event_id, values)
            flash("Event saved.", "ok")
            return redirect(url_for("events.detail", event_id=event_id))
    return render_template("events/form.html", event=event, values=values, errors=errors,
                           grouped=forms.sections(EVENT_FIELDS), templates=[], selected_templates=[])


@bp.route("/events/<int:event_id>/status", methods=["POST"])
def set_status(event_id):
    get_event(event_id)
    status = request.form.get("status")
    if status not in util.EVENT_STATUSES:
        abort(400)
    db.update("events", event_id, {"status": status, "updated_at": util.now_iso()})
    flash(f"Status changed to {status}.", "ok")
    return _back(event_id, request.form.get("tab", "overview"))


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
def delete(event_id):
    event = get_event(event_id)
    if db.scalar("SELECT 1 FROM contracts WHERE event_id = ? AND status = 'signed'", (event_id,)):
        flash("This event has a signed contract, so it can't be deleted. Set its status to Cancelled instead.", "bad")
        return _back(event_id, "overview")
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    flash(f"Deleted event {event['reference_number']}.", "ok")
    return redirect(url_for("events.index"))


@bp.route("/events/<int:event_id>/duplicate", methods=["POST"])
def duplicate(event_id):
    event = dict(get_event(event_id))
    new_date = request.form.get("event_date") or event["event_date"]
    try:
        new_date = util.parse_date(new_date).isoformat()
    except ValueError:
        flash("Pick a valid date for the copy.", "bad")
        return _back(event_id, "overview")
    length = util.event_days(event) - 1
    client = db.query("SELECT name FROM clients WHERE id = ?", (event["client_id"],), one=True)
    for key in ("id", "created_at", "updated_at"):
        event.pop(key)
    event.update(
        status="inquiry",
        event_date=new_date,
        end_date=(util.parse_date(new_date) + timedelta(days=length)).isoformat() if length else None,
        reference_number=_unique_reference(new_date, client and client["name"], event["title"]),
    )
    new_id = db.insert("events", event)
    conn = db.get_db()
    conn.execute(
        """INSERT INTO event_gear (event_id, item_id, description, category, quantity, rate, notes, sort)
           SELECT ?, item_id, description, category, quantity, rate, notes, sort FROM event_gear WHERE event_id = ?""",
        (new_id, event_id),
    )
    conn.execute(
        """INSERT INTO event_checklist_items (event_id, section, text, crew_visible, sort)
           SELECT ?, section, text, crew_visible, sort FROM event_checklist_items WHERE event_id = ?""",
        (new_id, event_id),
    )
    conn.commit()
    flash("Event copied with its gear list and checklist. Crew, contracts and invoices were not copied.", "ok")
    return redirect(url_for("events.detail", event_id=new_id))


# --- Detail ------------------------------------------------------------------

@bp.route("/events/<int:event_id>")
def detail(event_id):
    event = get_event(event_id)
    tab = request.args.get("tab", "overview")
    if tab not in TABS:
        tab = "overview"
    crew = db.query(
        """SELECT a.*, c.name, c.phone, c.email FROM event_crew a JOIN crew c ON c.id = a.crew_id
           WHERE a.event_id = ? ORDER BY a.call_time IS NULL, a.call_time, c.name""",
        (event_id,),
    )
    gear = services.event_gear(event_id)
    availability = services.gear_availability(event)
    checklist = db.query(
        "SELECT * FROM event_checklist_items WHERE event_id = ? ORDER BY sort, id", (event_id,)
    )
    contracts = db.query("SELECT * FROM contracts WHERE event_id = ? ORDER BY id DESC", (event_id,))
    invoices = []
    for inv in db.query("SELECT * FROM invoices WHERE event_id = ? ORDER BY id DESC", (event_id,)):
        totals = services.invoice_totals(inv)
        invoices.append({"row": inv, "totals": totals, "status": services.invoice_status(inv, totals)})
    ctx = dict(
        **_people_and_places(event),
        messages=event_messages(event_id),
        event=event, tab=tab, crew=crew, gear=gear,
        availability=availability, checklist=checklist, contracts=contracts, invoices=invoices,
        shortages=[(g, availability[g["item_id"]]) for g in gear
                   if g["item_id"] in availability and availability[g["item_id"]]["short"]],
        gear_progress=services.gear_progress(event_id),
        checklist_progress=services.checklist_progress(event_id),
        gear_total=services.gear_total(event),
        days=util.event_days(event),
        statuses=util.EVENT_STATUSES,
    )
    if tab == "crew":
        ctx["crew_fields"] = CREW_FIELDS
        ctx["crew_options"] = db.query("SELECT * FROM crew WHERE active = 1 ORDER BY name COLLATE NOCASE")
    if tab == "gear":
        booked = services.booked_quantities(event["event_date"], util.event_end(event), event_id)
        items = db.query("SELECT * FROM inventory_items WHERE status = 'active' ORDER BY category, name COLLATE NOCASE")
        ctx["item_groups"] = _group(items, lambda i: i["category"])
        ctx["booked"] = booked
        ctx["other_events"] = db.query(
            "SELECT id, reference_number, title, event_date FROM events WHERE id != ? "
            "AND EXISTS (SELECT 1 FROM event_gear WHERE event_id = events.id) ORDER BY event_date DESC LIMIT 50",
            (event_id,),
        )
        ctx["categories"] = util.INVENTORY_CATEGORIES
    if tab == "checklist":
        ctx["templates"] = db.query("SELECT * FROM checklist_templates ORDER BY id")
    ctx["gear_groups"] = _group(gear, services.gear_category)
    ctx["checklist_groups"] = _group(checklist, lambda c: c["section"] or "General")
    return render_template("events/detail.html", **ctx, gear_label=services.gear_label)


def _group(rows, key):
    groups = []
    for row in rows:
        k = key(row)
        if not groups or groups[-1][0] != k:
            groups.append((k, []))
        groups[-1][1].append(row)
    return groups


@bp.route("/events/<int:event_id>/worksheet")
def worksheet(event_id):
    event = get_event(event_id)
    return render_template("public/worksheet.html", **worksheet_context(event, assignment=None), admin=True)


BOOKING_STATUS = {
    "inquiry": "Inquiry — not booked yet",
    "hold": "On hold — not confirmed yet",
    "confirmed": "Confirmed booking",
    "completed": "Completed",
    "cancelled": "Cancelled — do not report",
}


def _people_and_places(event):
    client, venue = services.event_context(event)
    venue2 = db.query("SELECT * FROM venues WHERE id = ?", (event["venue2_id"],), one=True)
    producer = db.query("SELECT * FROM crew WHERE id = ?", (event["producer_id"],), one=True)
    return dict(
        client=client, venue=venue, venue_address=services.venue_address(venue),
        venue2=venue2, venue2_address=services.venue_address(venue2), producer=producer,
    )


def event_messages(event_id):
    return db.query("SELECT * FROM event_messages WHERE event_id = ? ORDER BY created_at, id", (event_id,))


def worksheet_context(event, assignment):
    crew = db.query(
        """SELECT a.*, c.name, c.phone, c.email, c.dietary FROM event_crew a JOIN crew c ON c.id = a.crew_id
           WHERE a.event_id = ? ORDER BY a.call_time IS NULL, a.call_time, c.name""",
        (event["id"],),
    )
    gear = services.event_gear(event["id"])
    # Crew see only crew-visible checklist items; the office copy shows everything.
    checklist = db.query(
        "SELECT * FROM event_checklist_items WHERE event_id = ? AND (crew_visible = 1 OR ?) ORDER BY sort, id",
        (event["id"], assignment is None),
    )
    return dict(
        **_people_and_places(event),
        event=event, crew=crew, assignment=assignment, booking_status=BOOKING_STATUS[event["status"]],
        gear_groups=_group(gear, services.gear_category), gear_label=services.gear_label,
        checklist_groups=_group(checklist, lambda c: c["section"] or "General"),
        messages=event_messages(event["id"]),
        settings=db.get_settings(),
    )


@bp.route("/events/<int:event_id>/event.ics")
def ics(event_id):
    event = get_event(event_id)
    body = services.event_ics(
        event, uid=f"{event['reference_number']}@backline",
        summary=f"{event['title']}", description=url_for("events.detail", event_id=event_id, _external=True),
    )
    return Response(body, mimetype="text/calendar",
                    headers={"Content-Disposition": f"attachment; filename={event['reference_number']}.ics"})


# --- Crew chat ---------------------------------------------------------------

@bp.route("/events/<int:event_id>/messages", methods=["POST"])
def post_message(event_id):
    get_event(event_id)
    body = request.form.get("body", "").strip()
    if body:
        db.insert("event_messages", {
            "event_id": event_id, "author": g.user["username"], "body": body[:4000], "created_at": util.now_iso(),
        })
    return _back(event_id, "chat", "chat-form")


@bp.route("/events/<int:event_id>/messages/<int:message_id>/delete", methods=["POST"])
def delete_message(event_id, message_id):
    db.execute("DELETE FROM event_messages WHERE id = ? AND event_id = ?", (message_id, event_id))
    return _back(event_id, "chat")


# --- Crew assignments --------------------------------------------------------

@bp.route("/events/<int:event_id>/crew", methods=["POST"])
def add_crew(event_id):
    get_event(event_id)
    data, errors = forms.parse(CREW_FIELDS, request.form)
    if errors:
        flash(" ".join(errors.values()), "bad")
        return _back(event_id, "crew")
    member = db.query("SELECT * FROM crew WHERE id = ?", (data["crew_id"],), one=True)
    if data["pay_rate"] is None:
        data["pay_rate"] = member["hourly_rate"] if data["pay_type"] == "hourly" else member["day_rate"]
    if not data["role"]:
        data["role"] = member["role"]
    data["event_id"] = event_id
    data["worksheet_key"] = util.gen_key()
    db.insert("event_crew", data)
    flash(f"Added {member['name']} to the crew.", "ok")
    return _back(event_id, "crew")


def _get_assignment(event_id, assignment_id):
    row = db.query("SELECT * FROM event_crew WHERE id = ? AND event_id = ?", (assignment_id, event_id), one=True)
    if row is None:
        abort(404)
    return row


@bp.route("/events/<int:event_id>/crew/<int:assignment_id>", methods=["POST"])
def update_crew(event_id, assignment_id):
    _get_assignment(event_id, assignment_id)
    fields = [f for f in CREW_FIELDS if f.name != "crew_id"]
    data, errors = forms.parse(fields, request.form)
    if errors:
        flash(" ".join(errors.values()), "bad")
    else:
        db.update("event_crew", assignment_id, data)
        flash("Crew assignment saved.", "ok")
    return _back(event_id, "crew")


@bp.route("/events/<int:event_id>/crew/<int:assignment_id>/confirm", methods=["POST"])
def confirm_crew(event_id, assignment_id):
    _get_assignment(event_id, assignment_id)
    confirmed = 1 if request.form.get("value") else 0
    db.update("event_crew", assignment_id, {"confirmed": confirmed})
    if util.wants_json():
        return jsonify(ok=True, done=confirmed)
    return _back(event_id, "crew")


@bp.route("/events/<int:event_id>/crew/<int:assignment_id>/delete", methods=["POST"])
def delete_crew(event_id, assignment_id):
    _get_assignment(event_id, assignment_id)
    db.execute("DELETE FROM event_crew WHERE id = ?", (assignment_id,))
    flash("Removed from crew.", "ok")
    return _back(event_id, "crew")


# --- Gear list ---------------------------------------------------------------

@bp.route("/events/<int:event_id>/gear", methods=["POST"])
def add_gear(event_id):
    get_event(event_id)
    data, errors = forms.parse(GEAR_FIELDS, request.form)
    item_id = request.form.get("item_id", type=int)
    description = request.form.get("description", "").strip()
    item = None
    if item_id:
        item = db.query("SELECT * FROM inventory_items WHERE id = ?", (item_id,), one=True)
        if item is None:
            errors["item_id"] = "That inventory item no longer exists."
    elif not description:
        errors["item_id"] = "Pick an inventory item or describe what's needed."
    if not errors and data["quantity"] < 1:
        errors["quantity"] = "Quantity must be at least 1."
    if errors:
        flash(" ".join(errors.values()), "bad")
        return _back(event_id, "gear")
    if item and data["rate"] is None:
        data["rate"] = item["rental_rate"]
    category = request.form.get("category") or None
    if category not in util.INVENTORY_CATEGORIES:
        category = None
    sort = db.scalar("SELECT COALESCE(MAX(sort), -1) + 1 FROM event_gear WHERE event_id = ?", (event_id,))
    db.insert("event_gear", {
        **data,
        "event_id": event_id,
        "item_id": item["id"] if item else None,
        "description": None if item else description,
        "category": None if item else category,
        "sort": sort,
    })
    flash(f"Added {item['name'] if item else description}.", "ok")
    return _back(event_id, "gear", "gear-add")


def _get_gear(event_id, gear_id):
    row = db.query("SELECT * FROM event_gear WHERE id = ? AND event_id = ?", (gear_id, event_id), one=True)
    if row is None:
        abort(404)
    return row


@bp.route("/events/<int:event_id>/gear/<int:gear_id>", methods=["POST"])
def update_gear(event_id, gear_id):
    _get_gear(event_id, gear_id)
    data, errors = forms.parse(GEAR_FIELDS + [Field("return_notes", "Return notes")], request.form)
    if not errors and data["quantity"] < 1:
        errors["quantity"] = "Quantity must be at least 1."
    if errors:
        flash(" ".join(errors.values()), "bad")
    else:
        db.update("event_gear", gear_id, data)
        flash("Gear line saved.", "ok")
    return _back(event_id, "gear", f"gear-{gear_id}")


@bp.route("/events/<int:event_id>/gear/<int:gear_id>/check", methods=["POST"])
def check_gear(event_id, gear_id):
    _get_gear(event_id, gear_id)
    field = request.form.get("field")
    if field not in ("pulled", "loaded", "returned"):
        abort(400)
    value = 1 if request.form.get("value") else 0
    db.update("event_gear", gear_id, {field: value})
    if util.wants_json():
        p = services.gear_progress(event_id)
        return jsonify(ok=True, done=value, progress={
            k: {"done": p[k], "total": p["total"]} for k in ("pulled", "loaded", "returned")
        })
    return _back(event_id, "gear", f"gear-{gear_id}")


@bp.route("/events/<int:event_id>/gear/mark-all", methods=["POST"])
def mark_all_gear(event_id):
    get_event(event_id)
    field = request.form.get("field")
    if field not in ("pulled", "loaded", "returned"):
        abort(400)
    value = 0 if request.form.get("clear") else 1
    db.execute(f"UPDATE event_gear SET {field} = ? WHERE event_id = ?", (value, event_id))
    flash(f"All gear marked {'not ' if not value else ''}{field}.", "ok")
    return _back(event_id, "gear")


@bp.route("/events/<int:event_id>/gear/<int:gear_id>/delete", methods=["POST"])
def delete_gear(event_id, gear_id):
    _get_gear(event_id, gear_id)
    db.execute("DELETE FROM event_gear WHERE id = ?", (gear_id,))
    flash("Removed from gear list.", "ok")
    return _back(event_id, "gear")


@bp.route("/events/<int:event_id>/gear/copy", methods=["POST"])
def copy_gear(event_id):
    get_event(event_id)
    source_id = request.form.get("source_id", type=int)
    if not source_id or source_id == event_id:
        flash("Pick an event to copy from.", "bad")
        return _back(event_id, "gear")
    start = db.scalar("SELECT COALESCE(MAX(sort), -1) + 1 FROM event_gear WHERE event_id = ?", (event_id,))
    db.execute(
        """INSERT INTO event_gear (event_id, item_id, description, category, quantity, rate, notes, sort)
           SELECT ?, item_id, description, category, quantity, rate, notes, sort + ?
           FROM event_gear WHERE event_id = ?""",
        (event_id, start, source_id),
    )
    flash("Gear list copied.", "ok")
    return _back(event_id, "gear")


# --- Checklist ---------------------------------------------------------------

@bp.route("/events/<int:event_id>/checklist", methods=["POST"])
def add_checklist_item(event_id):
    get_event(event_id)
    text = request.form.get("text", "").strip()
    if not text:
        flash("Enter a checklist item.", "bad")
        return _back(event_id, "checklist")
    sort = db.scalar("SELECT COALESCE(MAX(sort), -1) + 1 FROM event_checklist_items WHERE event_id = ?", (event_id,))
    db.insert("event_checklist_items", {
        "event_id": event_id,
        "section": request.form.get("section", "").strip() or None,
        "text": text,
        "crew_visible": 1 if request.form.get("crew_visible") else 0,
        "sort": sort,
    })
    return _back(event_id, "checklist", "checklist-add")


@bp.route("/events/<int:event_id>/checklist/template", methods=["POST"])
def apply_template(event_id):
    get_event(event_id)
    template_id = request.form.get("template_id", type=int)
    if not template_id or not db.scalar("SELECT 1 FROM checklist_templates WHERE id = ?", (template_id,)):
        flash("Pick a checklist template.", "bad")
    else:
        count = services.apply_checklist_template(event_id, template_id)
        flash(f"Added {count} checklist items.", "ok")
    return _back(event_id, "checklist")


@bp.route("/events/<int:event_id>/checklist/<int:item_id>/toggle", methods=["POST"])
def toggle_checklist_item(event_id, item_id):
    item = db.query("SELECT * FROM event_checklist_items WHERE id = ? AND event_id = ?", (item_id, event_id), one=True)
    if item is None:
        abort(404)
    done = 1 if request.form.get("value") else 0
    who = g.user["username"] if g.get("user") else None
    db.update("event_checklist_items", item_id, {
        "done": done,
        "done_by": who if done else None,
        "done_at": util.now_iso() if done else None,
    })
    if util.wants_json():
        p = services.checklist_progress(event_id)
        meta = f"{who} · {util.fdatetime(util.now_iso())}" if done else ""
        return jsonify(ok=True, done=done, meta=meta, progress={"checklist": p})
    return _back(event_id, "checklist")


@bp.route("/events/<int:event_id>/checklist/<int:item_id>/delete", methods=["POST"])
def delete_checklist_item(event_id, item_id):
    db.execute("DELETE FROM event_checklist_items WHERE id = ? AND event_id = ?", (item_id, event_id))
    return _back(event_id, "checklist")


@bp.route("/events/<int:event_id>/checklist/clear", methods=["POST"])
def clear_checklist(event_id):
    get_event(event_id)
    db.execute("DELETE FROM event_checklist_items WHERE event_id = ?", (event_id,))
    flash("Checklist cleared.", "ok")
    return _back(event_id, "checklist")
