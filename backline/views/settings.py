from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db, forms, services
from ..forms import Field

bp = Blueprint("settings", __name__)

COMPANY_FIELDS = [
    Field("company_name", "Company name", required=True, section="Company"),
    Field("company_phone", "Phone", type="tel", section="Company"),
    Field("company_email", "Email", type="email", section="Company"),
    Field("company_address", "Address", type="textarea", section="Company"),
    Field("default_tax_rate", "Default tax rate (%)", type="number", section="Billing"),
    Field("deposit_percent", "Default deposit (%)", type="number", section="Billing"),
    Field("invoice_prefix", "Invoice number prefix", section="Billing", help="e.g. INV- gives INV-2026-0001"),
    Field("contract_prefix", "Contract number prefix", section="Billing"),
    Field("invoice_terms", "Default invoice terms", type="textarea", section="Billing"),
    Field("crew_pay_days", "Pay crew within (days)", type="int", section="Billing",
          help="Unpaid crew show as overdue this many days after the event."),
    Field("crew_terms", "Terms of use", type="textarea", rows=4, section="Crew worksheets",
          help="Shown to crew under Basic Info. Accepting a call means agreeing to these."),
    Field("crew_payment_terms", "Payment", type="textarea", rows=4, section="Crew worksheets",
          help="How and when crew get paid. Shown next to their pay."),
    Field("worksheet_notes", "Additional notes & FAQs", type="textarea", rows=16, section="Crew worksheets",
          help="Standing policies printed at the bottom of every worksheet."),
    Field("run_of_show_template", "Run-of-show starter", type="textarea", rows=12, section="Crew worksheets",
          help="Pre-filled into new events' run of show."),
]


@bp.route("/settings", methods=["GET", "POST"])
def index():
    values, errors = db.get_settings(), {}
    if request.method == "POST":
        fields = COMPANY_FIELDS + [Field("contract_template", "Contract template", type="textarea", required=True)]
        values, errors = forms.parse(fields, request.form)
        for key in ("default_tax_rate", "deposit_percent"):
            if values.get(key) is not None and not 0 <= values[key] <= 100:
                errors[key] = "Enter a percentage between 0 and 100."
        if not errors:
            for key, value in values.items():
                if isinstance(value, float):
                    value = f"{value:g}"
                db.set_setting(key, "" if value is None else value)
            flash("Settings saved.", "ok")
            return redirect(url_for("settings.index"))
    return render_template("settings/index.html", values=values, errors=errors,
                           grouped=forms.sections(COMPANY_FIELDS), merge_fields=services.MERGE_FIELDS)


# --- Checklist templates -----------------------------------------------------

def _items_to_text(items):
    lines, section = [], None
    for item in items:
        if item["section"] != section:
            section = item["section"]
            if section:
                lines.append(f"# {section}")
        lines.append(item["text"])
    return "\n".join(lines)


def _text_to_items(text):
    items, section = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            section = line.lstrip("#").strip() or None
            continue
        items.append((section, line.lstrip("-*[] ").strip() or line))
    return items


@bp.route("/settings/checklists")
def checklists():
    templates = db.query(
        """SELECT t.*, (SELECT COUNT(*) FROM checklist_template_items WHERE template_id = t.id) AS item_count
           FROM checklist_templates t ORDER BY t.id"""
    )
    return render_template("settings/checklists.html", templates=templates)


@bp.route("/settings/checklists/new", methods=["GET", "POST"])
@bp.route("/settings/checklists/<int:template_id>", methods=["GET", "POST"])
def checklist_form(template_id=None):
    template = None
    if template_id:
        template = db.query("SELECT * FROM checklist_templates WHERE id = ?", (template_id,), one=True)
        if template is None:
            abort(404)
    name = template["name"] if template else ""
    description = (template["description"] or "") if template else ""
    items_text = _items_to_text(db.query(
        "SELECT section, text FROM checklist_template_items WHERE template_id = ? ORDER BY sort, id", (template_id,)
    )) if template else ""
    crew_visible = template["crew_visible"] if template else 1
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        crew_visible = 1 if request.form.get("crew_visible") else 0
        items_text = request.form.get("items", "")
        items = _text_to_items(items_text)
        if not name or not items:
            error = "Give the template a name and at least one item."
        else:
            conn = db.get_db()
            if template:
                conn.execute("UPDATE checklist_templates SET name = ?, description = ?, crew_visible = ? WHERE id = ?",
                             (name, description, crew_visible, template_id))
                conn.execute("DELETE FROM checklist_template_items WHERE template_id = ?", (template_id,))
            else:
                template_id = conn.execute(
                    "INSERT INTO checklist_templates (name, description, crew_visible) VALUES (?, ?, ?)",
                    (name, description, crew_visible)).lastrowid
            for sort, (section, text) in enumerate(items):
                conn.execute(
                    "INSERT INTO checklist_template_items (template_id, section, text, sort) VALUES (?, ?, ?, ?)",
                    (template_id, section, text, sort),
                )
            conn.commit()
            flash(f"Saved checklist template '{name}'.", "ok")
            return redirect(url_for("settings.checklists"))
    return render_template("settings/checklist_form.html", template=template, name=name,
                           description=description, items_text=items_text, crew_visible=crew_visible,
                           error=error)


@bp.route("/settings/checklists/<int:template_id>/delete", methods=["POST"])
def delete_checklist(template_id):
    db.execute("DELETE FROM checklist_templates WHERE id = ?", (template_id,))
    flash("Template deleted. Checklists already added to events are unchanged.", "ok")
    return redirect(url_for("settings.checklists"))


# --- Event types ---------------------------------------------------------------

@bp.route("/settings/event-types")
def event_types():
    types = db.query(
        """SELECT t.*, (SELECT COUNT(*) FROM events e WHERE e.event_type = t.name) AS event_count
           FROM event_types t ORDER BY t.sort, t.name"""
    )
    checklists = {}
    for r in db.query(
        """SELECT x.event_type_id, c.name FROM event_type_checklists x
           JOIN checklist_templates c ON c.id = x.template_id ORDER BY x.sort, c.id"""
    ):
        checklists.setdefault(r["event_type_id"], []).append(r["name"])
    return render_template("settings/event_types.html", types=types, checklists=checklists)


@bp.route("/settings/event-types/new", methods=["GET", "POST"])
@bp.route("/settings/event-types/<int:type_id>", methods=["GET", "POST"])
def event_type_form(type_id=None):
    etype = None
    if type_id:
        etype = db.query("SELECT * FROM event_types WHERE id = ?", (type_id,), one=True)
        if etype is None:
            abort(404)
    linked = services.event_type_checklist_ids(type_id) if etype else []
    values = dict(etype) if etype else {"run_of_show": db.get_setting("run_of_show_template")}
    error = None
    if request.method == "POST":
        values = {k: request.form.get(k, "").strip() for k in ("name", "people_label", "venue_label", "venue2_label")}
        values["run_of_show"] = request.form.get("run_of_show", "")
        chosen = [int(i) for i in request.form.getlist("checklists") if i.isdigit()]
        clash = db.scalar("SELECT id FROM event_types WHERE name = ? AND id != ?", (values["name"], type_id or -1))
        if not values["name"]:
            error = "Give the event type a name."
        elif clash:
            error = "There's already an event type with that name."
        else:
            conn = db.get_db()
            if etype:
                conn.execute(
                    "UPDATE event_types SET name = ?, people_label = ?, venue_label = ?, venue2_label = ?, "
                    "run_of_show = ? WHERE id = ?",
                    (*values.values(), type_id),
                )
                if values["name"] != etype["name"]:
                    conn.execute("UPDATE events SET event_type = ? WHERE event_type = ?", (values["name"], etype["name"]))
                conn.execute("DELETE FROM event_type_checklists WHERE event_type_id = ?", (type_id,))
            else:
                sort = conn.execute("SELECT COALESCE(MAX(sort), -1) + 1 FROM event_types").fetchone()[0]
                type_id = conn.execute(
                    "INSERT INTO event_types (name, people_label, venue_label, venue2_label, run_of_show, sort) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (*values.values(), sort),
                ).lastrowid
            # Keep the existing order for checklists that were already linked; append new ones.
            ordered = [t for t in linked if t in chosen] + [t for t in chosen if t not in linked]
            conn.executemany(
                "INSERT INTO event_type_checklists (event_type_id, template_id, sort) VALUES (?, ?, ?)",
                [(type_id, t, n) for n, t in enumerate(ordered)],
            )
            conn.commit()
            flash(f"Saved event type '{values['name']}'.", "ok")
            return redirect(url_for("settings.event_types"))
        linked = chosen
    templates = db.query("SELECT * FROM checklist_templates ORDER BY id")
    return render_template("settings/event_type_form.html", etype=etype, values=values, error=error,
                           templates=templates, linked=linked)


@bp.route("/settings/event-types/<int:type_id>/delete", methods=["POST"])
def delete_event_type(type_id):
    db.execute("DELETE FROM event_types WHERE id = ?", (type_id,))
    flash("Event type deleted. Events that used it keep their type name.", "ok")
    return redirect(url_for("settings.event_types"))


# --- Users -------------------------------------------------------------------

@bp.route("/settings/users", methods=["GET", "POST"])
def users():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not username or len(password) < 8:
                flash("Choose a username and a password of at least 8 characters.", "bad")
            elif db.scalar("SELECT 1 FROM users WHERE username = ?", (username,)):
                flash("That username is taken.", "bad")
            else:
                db.insert("users", {"username": username, "password_hash": generate_password_hash(password)})
                flash(f"Added user {username}.", "ok")
        elif action == "password":
            me = db.query("SELECT * FROM users WHERE id = ?", (g.user["id"],), one=True)
            new = request.form.get("new_password", "")
            if not check_password_hash(me["password_hash"], request.form.get("current_password", "")):
                flash("Current password is incorrect.", "bad")
            elif len(new) < 8:
                flash("New password must be at least 8 characters.", "bad")
            else:
                db.update("users", me["id"], {"password_hash": generate_password_hash(new)})
                flash("Password changed.", "ok")
        elif action == "delete":
            user_id = request.form.get("user_id", type=int)
            if user_id == g.user["id"]:
                flash("You can't delete your own account.", "bad")
            else:
                db.execute("DELETE FROM users WHERE id = ?", (user_id,))
                flash("User removed.", "ok")
        else:
            abort(400)
        return redirect(url_for("settings.users"))
    return render_template("settings/users.html", users=db.query("SELECT id, username, created_at FROM users ORDER BY username"))
