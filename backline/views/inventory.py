import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from .. import db, forms, services, util
from ..forms import Field

bp = Blueprint("inventory", __name__)

ITEM_FIELDS = [
    Field("name", "Name", required=True, section="Item", placeholder="e.g. Fender '65 Twin Reverb"),
    Field("category", "Category", type="select", required=True, choices=util.INVENTORY_CATEGORIES, section="Item"),
    Field("make", "Make", section="Item"),
    Field("model", "Model", section="Item"),
    Field("quantity", "Quantity owned", type="int", required=True, default=1, section="Item",
          help="Use more than 1 for interchangeable stock like mics, stands and cables."),
    Field("rental_rate", "Rental rate / day", type="money", section="Item"),
    Field("serial_number", "Serial number", section="Tracking"),
    Field("asset_tag", "Asset tag", section="Tracking"),
    Field("location", "Storage location", section="Tracking", placeholder="e.g. Shop — Rack B"),
    Field("condition", "Condition", type="select", required=True, choices=util.CONDITIONS, default="Good", section="Tracking"),
    Field("status", "Status", type="select", required=True, default="active", section="Tracking",
          choices=[("active", "Active"), ("maintenance", "In maintenance"), ("retired", "Retired")],
          help="Items in maintenance or retired can't be booked."),
    Field("purchase_date", "Purchase date", type="date", section="Value"),
    Field("purchase_price", "Purchase price", type="money", section="Value"),
    Field("replacement_value", "Replacement value", type="money", section="Value"),
    Field("notes", "Notes", type="textarea", section="Value"),
]

CSV_COLUMNS = [f.name for f in ITEM_FIELDS]
IMPORT_DEFAULTS = {"category": "Other", "condition": "Good", "status": "active", "quantity": "1"}
_CHOICES = {
    "category": util.INVENTORY_CATEGORIES,
    "condition": util.CONDITIONS,
    "status": util.INVENTORY_STATUSES,
}


def _canonical(key, value):
    """Match imported select values case-insensitively (e.g. 'microphones')."""
    if not value or key not in _CHOICES:
        return value
    for choice in _CHOICES[key]:
        if choice.lower() == value.lower():
            return choice
    return value


def get_item(item_id):
    item = db.query("SELECT * FROM inventory_items WHERE id = ?", (item_id,), one=True)
    if item is None:
        abort(404)
    return item


@bp.route("/inventory")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    status = request.args.get("status", "current")
    on_date = request.args.get("date", "")
    where, args = [], []
    if q:
        where.append("(name LIKE ? OR make LIKE ? OR model LIKE ? OR serial_number LIKE ? OR asset_tag LIKE ? OR notes LIKE ?)")
        args += [f"%{q}%"] * 6
    if category in util.INVENTORY_CATEGORIES:
        where.append("category = ?")
        args.append(category)
    if status == "current":
        where.append("status != 'retired'")
    elif status in util.INVENTORY_STATUSES:
        where.append("status = ?")
        args.append(status)
    items = db.query(
        f"SELECT * FROM inventory_items {'WHERE ' + ' AND '.join(where) if where else ''} "
        "ORDER BY category, name COLLATE NOCASE",
        args,
    )
    booked = None
    if on_date:
        try:
            on_date = util.parse_date(on_date).isoformat()
            booked = services.booked_quantities(on_date, on_date)
        except ValueError:
            on_date = ""
    summary = db.query(
        "SELECT COUNT(*) AS items, COALESCE(SUM(quantity), 0) AS units, "
        "COALESCE(SUM(quantity * COALESCE(replacement_value, 0)), 0) AS value, "
        "SUM(status = 'maintenance') AS maintenance FROM inventory_items WHERE status != 'retired'",
        one=True,
    )
    return render_template(
        "inventory/list.html", items=items, q=q, category=category, status=status,
        on_date=on_date, booked=booked, summary=summary, categories=util.INVENTORY_CATEGORIES,
    )


@bp.route("/inventory/new", methods=["GET", "POST"])
def new():
    values, errors = {"quantity": 1}, {}
    if request.method == "POST":
        values, errors = forms.parse(ITEM_FIELDS, request.form)
        if not errors:
            item_id = db.insert("inventory_items", values)
            flash(f"Added {values['name']}.", "ok")
            if request.form.get("another"):
                return redirect(url_for("inventory.new"))
            return redirect(url_for("inventory.detail", item_id=item_id))
    return render_template("inventory/form.html", item=None, values=values, errors=errors,
                           grouped=forms.sections(ITEM_FIELDS))


@bp.route("/inventory/<int:item_id>")
def detail(item_id):
    item = get_item(item_id)
    today = util.today().isoformat()
    bookings = db.query(
        """
        SELECT e.id, e.title, e.reference_number, e.event_date, e.end_date, e.status,
               SUM(g.quantity) AS qty, MIN(g.pulled) AS pulled, MIN(g.returned) AS returned
        FROM event_gear g JOIN events e ON e.id = g.event_id
        WHERE g.item_id = ?
        GROUP BY e.id ORDER BY e.event_date DESC LIMIT 100
        """,
        (item_id,),
    )
    upcoming = [b for b in bookings if (b["end_date"] or b["event_date"]) >= today]
    past = [b for b in bookings if (b["end_date"] or b["event_date"]) < today]
    out_now = [b for b in bookings if b["pulled"] and not b["returned"] and b["status"] != "cancelled"]
    damage_notes = db.query(
        """SELECT g.return_notes, e.id AS event_id, e.title, e.event_date FROM event_gear g
           JOIN events e ON e.id = g.event_id
           WHERE g.item_id = ? AND g.return_notes IS NOT NULL AND g.return_notes != ''
           ORDER BY e.event_date DESC""",
        (item_id,),
    )
    return render_template("inventory/detail.html", item=item, fields=ITEM_FIELDS,
                           upcoming=list(reversed(upcoming)), past=past, out_now=out_now,
                           damage_notes=damage_notes)


@bp.route("/inventory/<int:item_id>/edit", methods=["GET", "POST"])
def edit(item_id):
    item = get_item(item_id)
    values, errors = dict(item), {}
    if request.method == "POST":
        values, errors = forms.parse(ITEM_FIELDS, request.form)
        if not errors:
            db.update("inventory_items", item_id, values)
            flash("Item saved.", "ok")
            return redirect(url_for("inventory.detail", item_id=item_id))
    return render_template("inventory/form.html", item=item, values=values, errors=errors,
                           grouped=forms.sections(ITEM_FIELDS))


@bp.route("/inventory/<int:item_id>/delete", methods=["POST"])
def delete(item_id):
    item = get_item(item_id)
    in_use = db.scalar("SELECT COUNT(*) FROM event_gear WHERE item_id = ?", (item_id,))
    if in_use:
        flash(f"{item['name']} is on {in_use} event gear list(s). Mark it Retired instead so history is kept.", "bad")
        return redirect(url_for("inventory.detail", item_id=item_id))
    db.execute("DELETE FROM inventory_items WHERE id = ?", (item_id,))
    flash(f"Deleted {item['name']}.", "ok")
    return redirect(url_for("inventory.index"))


@bp.route("/inventory/export.csv")
def export_csv():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for row in db.query("SELECT * FROM inventory_items ORDER BY category, name"):
        writer.writerow(["" if row[c] is None else row[c] for c in CSV_COLUMNS])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=inventory-{util.today().isoformat()}.csv"},
    )


@bp.route("/inventory/import", methods=["GET", "POST"])
def import_csv():
    results = None
    if request.method == "POST":
        upload = request.files.get("file")
        if not upload or not upload.filename:
            flash("Choose a CSV file to import.", "bad")
            return redirect(url_for("inventory.import_csv"))
        text = upload.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        header_map = {h: h.strip().lower().replace(" ", "_") for h in (reader.fieldnames or [])}
        added, failed = 0, []
        for line_no, raw in enumerate(reader, start=2):
            row = {header_map[k]: (v or "").strip() for k, v in raw.items() if k in header_map}
            for key, default in IMPORT_DEFAULTS.items():
                row[key] = _canonical(key, row.get(key)) or default
            data, errors = forms.parse(ITEM_FIELDS, row)
            if errors:
                failed.append((line_no, "; ".join(errors.values())))
                continue
            db.insert("inventory_items", data)
            added += 1
        results = {"added": added, "failed": failed}
        if added:
            flash(f"Imported {added} item(s).", "ok")
    return render_template("inventory/import.html", columns=CSV_COLUMNS, results=results,
                           categories=util.INVENTORY_CATEGORIES)
