"""Crew pay: what's owed to whom, and a record of when each person was paid."""

import csv
import io

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from .. import db, services, util

bp = Blueprint("crewpay", __name__)

STATUS_FILTERS = [
    ("owed", "Owed (event over, unpaid)"),
    ("overdue", "Overdue"),
    ("upcoming", "Upcoming events"),
    ("paid", "Paid"),
    ("all", "All"),
]


def _filtered_rows(args):
    """Crew pay rows for the page's filters: status, crew member, event, date range."""
    where, params = [], []
    crew_id = args.get("crew_id", type=int)
    event_id = args.get("event_id", type=int)
    if crew_id:
        where.append("a.crew_id = ?")
        params.append(crew_id)
    if event_id:
        where.append("a.event_id = ?")
        params.append(event_id)
    for key, clause in (("start", "e.event_date >= ?"), ("end", "e.event_date <= ?")):
        value = args.get(key, "")
        if value:
            try:
                params.append(util.parse_date(value).isoformat())
                where.append(clause)
            except ValueError:
                pass
    rows = services.crew_pay_rows(" AND ".join(where), tuple(params))
    status = args.get("status") or ("all" if event_id else "owed")
    if status == "owed":
        rows = [r for r in rows if r["pay_status"] in ("owed", "overdue")]
    elif status in ("overdue", "upcoming", "paid"):
        rows = [r for r in rows if r["pay_status"] == status]
    return rows, status


@bp.route("/crew-pay")
def index():
    rows, status = _filtered_rows(request.args)
    everyone = services.crew_pay_rows()
    by_person = {}
    for r in everyone:
        if r["pay_status"] in ("owed", "overdue"):
            person = by_person.setdefault(r["crew_id"], {"name": r["crew_name"], "owed": 0, "count": 0})
            person["owed"] += r["due"]
            person["count"] += 1
    return render_template(
        "crewpay/index.html", rows=rows, status=status, statuses=STATUS_FILTERS,
        summary=services.crew_pay_summary(everyone), shown_total=sum(r["due"] for r in rows),
        by_person=sorted(by_person.items(), key=lambda kv: -kv[1]["owed"]),
        crew=db.query("SELECT id, name FROM crew ORDER BY name COLLATE NOCASE"),
        events=db.query("SELECT id, title, event_date FROM events ORDER BY event_date DESC LIMIT 200"),
        methods=util.PAYMENT_METHODS, filters=request.args, today=util.today().isoformat(),
        pay_days=db.get_setting("crew_pay_days"),
    )


def _back():
    target = request.form.get("next", "")
    if not target.startswith("/crew-pay") and not target.startswith("/events/"):
        target = url_for("crewpay.index")
    return redirect(target)


def _selected_ids():
    return [int(i) for i in request.form.getlist("ids") if i.isdigit()]


@bp.route("/crew-pay/mark-paid", methods=["POST"])
def mark_paid():
    ids = _selected_ids()
    try:
        paid_on = util.parse_date(request.form.get("paid_on", "").strip()).isoformat()
    except (ValueError, AttributeError):  # malformed, or blank (parse_date returns None)
        flash("Pick the date you paid.", "bad")
        return _back()
    if not ids:
        flash("Tick the crew you paid first.", "bad")
        return _back()
    method = request.form.get("method") or None
    if method and method not in util.PAYMENT_METHODS:
        method = None
    count = services.mark_crew_paid(ids, paid_on, method, request.form.get("reference", "").strip() or None)
    flash(f"Marked {count} crew payment{'s' if count != 1 else ''} as paid on {util.fdate(paid_on, 'short')}.", "ok")
    return _back()


@bp.route("/crew-pay/mark-unpaid", methods=["POST"])
def mark_unpaid():
    ids = _selected_ids()
    if not ids:
        flash("Tick the payments to undo first.", "bad")
        return _back()
    services.mark_crew_unpaid(ids)
    flash(f"Marked {len(ids)} crew payment{'s' if len(ids) != 1 else ''} as unpaid.", "ok")
    return _back()


@bp.route("/crew-pay/export.csv")
def export_csv():
    rows, _status = _filtered_rows(request.args)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["event_date", "event", "reference", "crew", "role", "pay_type", "rate", "est_hours",
                     "actual_hours", "amount_due", "status", "paid_on", "paid_amount", "method", "reference_no",
                     "w9_on_file"])
    for r in rows:
        writer.writerow([
            r["event_date"], r["title"], r["reference_number"], r["crew_name"], r["role"] or "", r["pay_type"],
            r["pay_rate"] if r["pay_rate"] is not None else "", r["hours"] if r["hours"] is not None else "",
            r["actual_hours"] if r["actual_hours"] is not None else "", f"{r['due']:.2f}", r["pay_status"],
            r["paid_on"] or "", f"{r['paid_amount']:.2f}" if r["paid_amount"] is not None else "",
            r["paid_method"] or "", r["paid_reference"] or "", "yes" if r["w9_on_file"] else "no",
        ])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=crew-pay-{util.today().isoformat()}.csv"})
