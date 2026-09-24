"""Business logic shared across views: gear availability, gear totals,
invoice math and contract rendering."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from . import db, util


# --- Gear availability -------------------------------------------------------

def booked_quantities(start, end, exclude_event_id=None):
    """Units of each inventory item reserved by hold/confirmed events that
    overlap [start, end]. Returns {item_id: qty}."""
    placeholders = ", ".join("?" for _ in util.RESERVING_STATUSES)
    rows = db.query(
        f"""
        SELECT g.item_id, SUM(g.quantity) AS qty
        FROM event_gear g JOIN events e ON e.id = g.event_id
        WHERE g.item_id IS NOT NULL
          AND e.status IN ({placeholders})
          AND e.event_date <= ?
          AND COALESCE(e.end_date, e.event_date) >= ?
          AND e.id != ?
        GROUP BY g.item_id
        """,
        (*util.RESERVING_STATUSES, end, start, exclude_event_id or -1),
    )
    return {r["item_id"]: r["qty"] for r in rows}


def item_bookings(item_id, start, end, exclude_event_id=None):
    """The reserving events that use an item in a date window."""
    placeholders = ", ".join("?" for _ in util.RESERVING_STATUSES)
    return db.query(
        f"""
        SELECT e.id, e.reference_number, e.title, e.event_date, e.end_date, e.status,
               SUM(g.quantity) AS qty
        FROM event_gear g JOIN events e ON e.id = g.event_id
        WHERE g.item_id = ?
          AND e.status IN ({placeholders})
          AND e.event_date <= ?
          AND COALESCE(e.end_date, e.event_date) >= ?
          AND e.id != ?
        GROUP BY e.id
        ORDER BY e.event_date
        """,
        (item_id, *util.RESERVING_STATUSES, end, start, exclude_event_id or -1),
    )


def gear_availability(event):
    """For each inventory item on an event's gear list, how many units are
    free once overlapping events are accounted for.

    Returns {item_id: {"requested", "owned", "booked_elsewhere", "available",
    "short", "conflicts"}}.
    """
    start, end = event["event_date"], util.event_end(event)
    rows = db.query(
        """
        SELECT g.item_id, SUM(g.quantity) AS requested, i.quantity AS owned, i.status
        FROM event_gear g JOIN inventory_items i ON i.id = g.item_id
        WHERE g.event_id = ?
        GROUP BY g.item_id
        """,
        (event["id"],),
    )
    if not rows:
        return {}
    booked = booked_quantities(start, end, exclude_event_id=event["id"])
    result = {}
    for r in rows:
        owned = r["owned"] if r["status"] == "active" else 0
        elsewhere = booked.get(r["item_id"], 0)
        available = max(owned - elsewhere, 0)
        short = max(r["requested"] - available, 0)
        result[r["item_id"]] = {
            "requested": r["requested"],
            "owned": r["owned"],
            "item_status": r["status"],
            "booked_elsewhere": elsewhere,
            "available": available,
            "short": short,
            "conflicts": item_bookings(r["item_id"], start, end, event["id"]) if short else [],
        }
    return result


def shortage_count(event):
    return sum(1 for a in gear_availability(event).values() if a["short"])


def upcoming_shortages(start, end):
    """Reserving events in a window that have at least one short item."""
    placeholders = ", ".join("?" for _ in util.RESERVING_STATUSES)
    events = db.query(
        f"""
        SELECT * FROM events
        WHERE status IN ({placeholders})
          AND COALESCE(end_date, event_date) >= ? AND event_date <= ?
        ORDER BY event_date
        """,
        (*util.RESERVING_STATUSES, start, end),
    )
    out = []
    for e in events:
        count = shortage_count(e)
        if count:
            out.append((e, count))
    return out


# --- Gear list ---------------------------------------------------------------

def event_gear(event_id):
    return db.query(
        """
        SELECT g.*, i.name AS item_name, i.category AS item_category, i.make, i.model,
               i.asset_tag, i.location
        FROM event_gear g LEFT JOIN inventory_items i ON i.id = g.item_id
        WHERE g.event_id = ?
        ORDER BY COALESCE(g.category, i.category, 'Other'), g.sort, g.id
        """,
        (event_id,),
    )


def gear_label(row):
    if row["item_id"] and row["item_name"]:
        return row["item_name"]
    return row["description"] or "(unnamed)"


def gear_category(row):
    return row["category"] or row["item_category"] or "Other"


def gear_total(event):
    days = util.event_days(event)
    total = Decimal("0")
    for g in event_gear(event["id"]):
        total += util.to_decimal(g["rate"]) * g["quantity"] * days
    return util.round_money(total)


def gear_progress(event_id):
    row = db.query(
        "SELECT COUNT(*) AS total, SUM(pulled) AS pulled, SUM(loaded) AS loaded, "
        "SUM(returned) AS returned FROM event_gear WHERE event_id = ?",
        (event_id,),
        one=True,
    )
    return {k: row[k] or 0 for k in ("total", "pulled", "loaded", "returned")}


def checklist_progress(event_id):
    row = db.query(
        "SELECT COUNT(*) AS total, SUM(done) AS done FROM event_checklist_items WHERE event_id = ?",
        (event_id,),
        one=True,
    )
    return {"total": row["total"] or 0, "done": row["done"] or 0}


def apply_checklist_template(event_id, template_id):
    start = db.scalar(
        "SELECT COALESCE(MAX(sort), -1) + 1 FROM event_checklist_items WHERE event_id = ?",
        (event_id,),
    )
    crew_visible = db.scalar("SELECT crew_visible FROM checklist_templates WHERE id = ?", (template_id,))
    items = db.query(
        "SELECT section, text FROM checklist_template_items WHERE template_id = ? ORDER BY sort, id",
        (template_id,),
    )
    conn = db.get_db()
    for offset, item in enumerate(items):
        conn.execute(
            "INSERT INTO event_checklist_items (event_id, section, text, crew_visible, sort) VALUES (?, ?, ?, ?, ?)",
            (event_id, item["section"], item["text"], crew_visible, start + offset),
        )
    conn.commit()
    return len(items)


# --- Event types ---------------------------------------------------------------

def event_type(name):
    if not name:
        return None
    return db.query("SELECT * FROM event_types WHERE name = ?", (name,), one=True)


def event_type_checklist_ids(type_id):
    return [r["template_id"] for r in db.query(
        "SELECT template_id FROM event_type_checklists WHERE event_type_id = ? ORDER BY sort, template_id",
        (type_id,),
    )]


def default_checklist_ids():
    """Checklists for an event with no type: the generic office + show day ones."""
    names = ["Advance & Prep", "Show Day", "Load-Out & Return"]
    rows = db.query(
        f"SELECT id, name FROM checklist_templates WHERE name IN ({', '.join('?' for _ in names)})", names
    )
    by_name = {r["name"]: r["id"] for r in rows}
    return [by_name[n] for n in names if n in by_name]


def event_type_profiles():
    """Everything the event form needs to adapt to the chosen type, keyed by
    type name ("" = no type chosen)."""
    profiles = {"": {
        "people_label": "Key people", "venue_label": "", "venue2_label": "",
        "run_of_show": db.get_setting("run_of_show_template") or "", "checklists": default_checklist_ids(),
    }}
    for t in db.query("SELECT * FROM event_types ORDER BY sort, name"):
        profiles[t["name"]] = {
            "people_label": t["people_label"] or "Key people",
            "venue_label": t["venue_label"] or "",
            "venue2_label": t["venue2_label"] or "",
            "run_of_show": t["run_of_show"] or profiles[""]["run_of_show"],
            "checklists": event_type_checklist_ids(t["id"]),
        }
    return profiles


def event_labels(event):
    """Display labels for an event's key people and locations, falling back
    from the event's own labels to its type's defaults."""
    t = event_type(event["event_type"])
    return {
        "people": (t and t["people_label"]) or "Key people",
        "venue": event["venue_label"] or (t and t["venue_label"]) or "Venue",
        "venue2": event["venue2_label"] or (t and t["venue2_label"]) or "Second location",
    }


# --- Invoices ----------------------------------------------------------------

def invoice_totals(invoice, items=None, payments=None):
    if items is None:
        items = db.query("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice["id"],))
    if payments is None:
        payments = db.query("SELECT amount FROM payments WHERE invoice_id = ?", (invoice["id"],))
    subtotal = Decimal("0")
    taxable = Decimal("0")
    for it in items:
        line = util.round_money(util.to_decimal(it["quantity"]) * util.to_decimal(it["unit_price"]))
        subtotal += line
        if it["taxable"]:
            taxable += line
    discount = min(util.round_money(invoice["discount"]), subtotal)
    # Discount is applied before tax, spread proportionally over taxable lines.
    if subtotal > 0 and taxable > 0:
        taxable -= discount * taxable / subtotal
    tax = util.round_money(taxable * util.to_decimal(invoice["tax_rate"]) / 100)
    total = util.round_money(subtotal - discount + tax)
    paid = util.round_money(sum((util.to_decimal(p["amount"]) for p in payments), Decimal("0")))
    return {
        "subtotal": util.round_money(subtotal),
        "discount": discount,
        "tax": tax,
        "total": total,
        "paid": paid,
        "balance": util.round_money(total - paid),
    }


def invoice_status(invoice, totals=None):
    """Effective status: draft, sent, partial, paid, overdue or void."""
    if invoice["status"] in ("draft", "void"):
        return invoice["status"]
    totals = totals or invoice_totals(invoice)
    if totals["balance"] <= 0:
        return "paid"
    if invoice["due_date"] and util.parse_date(invoice["due_date"]) < util.today():
        return "overdue"
    if totals["paid"] > 0:
        return "partial"
    return "sent"


def next_number(table, prefix):
    year = util.today().year
    base = f"{prefix}{year}-"
    last = db.scalar(
        f"SELECT number FROM {table} WHERE number LIKE ? ORDER BY number DESC LIMIT 1",
        (base + "%",),
    )
    seq = 1
    if last:
        tail = last[len(base):]
        seq = int(tail) + 1 if tail.isdigit() else db.scalar(f"SELECT COUNT(*) FROM {table}") + 1
    return f"{base}{seq:04d}"


def invoice_lines_for_event(event):
    """Pre-filled invoice lines from an event's gear list."""
    days = util.event_days(event)
    lines = []
    for g in event_gear(event["id"]):
        rate = util.to_decimal(g["rate"])
        if rate <= 0:
            continue
        desc = gear_label(g)
        if days > 1:
            desc += f" ({days} days @ {util.money(rate)}/day)"
        lines.append(
            {
                "description": desc,
                "quantity": g["quantity"],
                "unit_price": float(util.round_money(rate * days)),
                "taxable": 1,
            }
        )
    return lines


# --- Contracts ---------------------------------------------------------------

MERGE_FIELD = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

MERGE_FIELDS = [
    ("company_name", "Your company name"),
    ("contract_number", "Contract number"),
    ("reference_number", "Event reference number"),
    ("client_name", "Client name"),
    ("client_company", "Client company"),
    ("event_title", "Event title"),
    ("event_type", "Event type, e.g. Corporate / Speaking"),
    ("service_type", "Service, e.g. PA + engineer"),
    ("event_date", "Event date (and end date for multi-day)"),
    ("venue_name", "Venue name"),
    ("venue_address", "Venue address"),
    ("load_in_time", "Load-in time"),
    ("soundcheck_time", "Soundcheck time"),
    ("start_time", "Show start"),
    ("end_time", "Show end"),
    ("load_out_time", "Load-out time"),
    ("gear_list", "Equipment list with quantities"),
    ("total", "Contract total"),
    ("deposit", "Deposit amount"),
    ("deposit_due_date", "Deposit due date"),
    ("balance", "Balance after deposit"),
    ("balance_due_date", "Balance due date"),
]


def event_context(event):
    client = db.query("SELECT * FROM clients WHERE id = ?", (event["client_id"],), one=True)
    venue = db.query("SELECT * FROM venues WHERE id = ?", (event["venue_id"],), one=True)
    return client, venue


def venue_address(venue):
    if not venue:
        return ""
    city_line = " ".join(p for p in [venue["city"] and venue["city"] + ",", venue["state"], venue["postal_code"]] if p)
    return ", ".join(p for p in [venue["address"], city_line] if p)


def render_contract(template, event, number, total, deposit, deposit_due, balance_due):
    client, venue = event_context(event)
    gear_lines = []
    for g in event_gear(event["id"]):
        gear_lines.append(f"  - {g['quantity']} x {gear_label(g)}")
    date_text = util.fdate(event["event_date"])
    if event["end_date"] and event["end_date"] != event["event_date"]:
        date_text += f" through {util.fdate(event['end_date'])}"
    values = {
        "company_name": db.get_setting("company_name"),
        "contract_number": number,
        "reference_number": event["reference_number"],
        "client_name": client["name"] if client else "",
        "client_company": (client["company"] or "") if client else "",
        "event_title": event["title"],
        "event_type": event["event_type"] or "Event",
        "service_type": event["service_type"] or "Audio and backline as listed below",
        "event_date": date_text,
        "venue_name": venue["name"] if venue else "TBD",
        "venue_address": venue_address(venue),
        "load_in_time": util.ftime(event["load_in_time"]) or "TBD",
        "soundcheck_time": util.ftime(event["soundcheck_time"]) or "TBD",
        "start_time": util.ftime(event["start_time"]) or "TBD",
        "end_time": util.ftime(event["end_time"]) or "TBD",
        "load_out_time": util.ftime(event["load_out_time"]) or "TBD",
        "gear_list": "\n".join(gear_lines) or "  (equipment list to be attached)",
        "total": util.money(total),
        "deposit": util.money(deposit),
        "deposit_due_date": util.fdate(deposit_due) or "signing",
        "balance": util.money(util.to_decimal(total) - util.to_decimal(deposit)),
        "balance_due_date": util.fdate(balance_due) or "the event date",
    }
    return MERGE_FIELD.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)


# --- Calendar export -----------------------------------------------------------

def _ics_escape(text):
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line):
    """Fold lines longer than 75 octets, as RFC 5545 requires."""
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n".join(out)


def event_ics(event, uid, summary, description="", start_time=None):
    """A single-event iCalendar file. Times are "floating" (the viewer's local
    time), which is right for crews working in the venue's time zone."""
    _client, venue = event_context(event)
    start_date = util.parse_date(event["event_date"])
    end_date = util.parse_date(util.event_end(event))
    start_time = start_time or event["load_in_time"] or event["start_time"]
    end_time = event["load_out_time"] or event["end_time"]
    if start_time:
        start = datetime.combine(start_date, datetime.strptime(start_time, "%H:%M").time())
        if end_time:
            end = datetime.combine(end_date, datetime.strptime(end_time, "%H:%M").time())
            if end <= start:
                end += timedelta(days=1)  # load-out after midnight
        else:
            end = start + timedelta(hours=4)
        when = [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
    else:
        when = [f"DTSTART;VALUE=DATE:{start_date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{end_date + timedelta(days=1):%Y%m%d}"]
    location = ", ".join(p for p in [venue["name"] if venue else "", venue_address(venue)] if p)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{db.get_setting('company_name')}//Worksheets//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT",
        f"UID:{uid}", f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}", *when,
        f"SUMMARY:{_ics_escape(summary)}",
        f"LOCATION:{_ics_escape(location)}",
        f"DESCRIPTION:{_ics_escape(description)}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"
