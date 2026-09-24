from datetime import timedelta
from decimal import Decimal

from flask import Blueprint, render_template

from .. import db, services, util

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    today = util.today()
    soon = today + timedelta(days=14)
    iso = today.isoformat()

    upcoming = db.query(
        """
        SELECT e.*, c.name AS client_name, v.name AS venue_name,
          (SELECT COUNT(*) FROM event_checklist_items WHERE event_id = e.id) AS check_total,
          (SELECT COALESCE(SUM(done), 0) FROM event_checklist_items WHERE event_id = e.id) AS check_done,
          (SELECT COUNT(*) FROM event_gear WHERE event_id = e.id) AS gear_total,
          (SELECT COALESCE(SUM(pulled), 0) FROM event_gear WHERE event_id = e.id) AS gear_pulled,
          (SELECT COUNT(*) FROM event_crew WHERE event_id = e.id) AS crew_total,
          (SELECT COALESCE(SUM(confirmed), 0) FROM event_crew WHERE event_id = e.id) AS crew_confirmed
        FROM events e
        LEFT JOIN clients c ON c.id = e.client_id
        LEFT JOIN venues v ON v.id = e.venue_id
        WHERE COALESCE(e.end_date, e.event_date) >= ? AND e.status != 'cancelled'
        ORDER BY e.event_date, e.start_time LIMIT 12
        """,
        (iso,),
    )
    events_30 = db.scalar(
        "SELECT COUNT(*) FROM events WHERE status IN ('hold', 'confirmed') AND event_date BETWEEN ? AND ?",
        (iso, (today + timedelta(days=30)).isoformat()),
    )
    shortages = services.upcoming_shortages(iso, (today + timedelta(days=90)).isoformat())

    attention = []
    for e in upcoming:
        start = util.parse_date(e["event_date"])
        if start > soon:
            continue
        link = e["id"]
        if e["status"] in ("inquiry", "hold"):
            attention.append((link, "overview", f"{e['title']} isn't confirmed yet ({e['status']})", start))
        if e["crew_total"] == 0:
            attention.append((link, "crew", f"No crew assigned to {e['title']}", start))
        elif e["crew_confirmed"] < e["crew_total"]:
            attention.append((link, "crew", f"{e['crew_total'] - e['crew_confirmed']} crew unconfirmed for {e['title']}", start))
        if e["gear_total"] == 0:
            attention.append((link, "gear", f"No gear list for {e['title']}", start))
        elif start <= today + timedelta(days=2) and e["gear_pulled"] < e["gear_total"]:
            attention.append((link, "gear", f"{e['gear_total'] - e['gear_pulled']} items not pulled for {e['title']}", start))
        if e["check_total"] and e["check_done"] < e["check_total"] and start <= today + timedelta(days=3):
            attention.append((link, "checklist", f"Checklist {e['check_done']}/{e['check_total']} for {e['title']}", start))

    not_returned = db.query(
        """
        SELECT e.id, e.title, e.event_date, COUNT(*) AS items
        FROM event_gear g JOIN events e ON e.id = g.event_id
        WHERE g.pulled = 1 AND g.returned = 0 AND COALESCE(e.end_date, e.event_date) < ?
          AND e.status != 'cancelled'
        GROUP BY e.id ORDER BY e.event_date
        """,
        (iso,),
    )
    unsigned = db.query(
        """SELECT k.*, e.title AS event_title, e.event_date FROM contracts k JOIN events e ON e.id = k.event_id
           WHERE k.status = 'sent' ORDER BY e.event_date""",
    )
    maintenance = db.query("SELECT * FROM inventory_items WHERE status = 'maintenance' ORDER BY name")

    outstanding, overdue_total, overdue = Decimal(0), Decimal(0), []
    for inv in db.query(
        """SELECT i.*, c.name AS client_name FROM invoices i LEFT JOIN clients c ON c.id = i.client_id
           WHERE i.status = 'sent' ORDER BY i.due_date"""
    ):
        totals = services.invoice_totals(inv)
        status = services.invoice_status(inv, totals)
        if status in ("sent", "partial", "overdue"):
            outstanding += totals["balance"]
        if status == "overdue":
            overdue_total += totals["balance"]
            overdue.append((inv, totals))

    return render_template(
        "dashboard.html",
        upcoming=upcoming, events_30=events_30, shortages=shortages, attention=attention,
        not_returned=not_returned, unsigned=unsigned, maintenance=maintenance,
        outstanding=outstanding, overdue_total=overdue_total, overdue=overdue,
    )
