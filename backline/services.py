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


# --- Crew pay ------------------------------------------------------------------

CREW_PAY_SQL = """
    SELECT a.*, c.name AS crew_name, c.email AS crew_email, c.w9_on_file,
           e.title, e.event_date, e.end_date, e.status AS event_status, e.reference_number
    FROM event_crew a
    JOIN crew c ON c.id = a.crew_id
    JOIN events e ON e.id = a.event_id
"""


def crew_amount_due(a):
    """What an assignment pays: the final amount if the office set one,
    otherwise the flat rate, or the hourly rate × hours (actual if entered,
    else estimated)."""
    if a["final_amount"] is not None:
        return util.round_money(a["final_amount"])
    rate = util.to_decimal(a["pay_rate"])
    if a["pay_type"] == "hourly":
        hours = a["actual_hours"] if a["actual_hours"] is not None else a["hours"]
        return util.round_money(rate * util.to_decimal(hours))
    return util.round_money(rate)


def crew_pay_status(a, today=None, pay_days=None):
    """paid | owed | overdue | upcoming | cancelled.

    Crew are owed once the event is over; "overdue" means still unpaid more
    than `crew_pay_days` (a setting) after it ended."""
    if a["paid_on"]:
        return "paid"
    if a["event_status"] == "cancelled":
        return "cancelled"
    today = today or util.today()
    end = util.parse_date(a["end_date"] or a["event_date"])
    if end >= today and a["event_status"] != "completed":
        return "upcoming"
    if pay_days is None:
        pay_days = int(db.get_setting("crew_pay_days") or 14)
    return "overdue" if (today - end).days > pay_days else "owed"


def crew_pay_rows(where="", args=(), order="e.event_date DESC, c.name"):
    """Assignments with crew and event details plus computed `due` and `pay_status`."""
    pay_days = int(db.get_setting("crew_pay_days") or 14)
    today = util.today()
    rows = []
    for r in db.query(f"{CREW_PAY_SQL} {('WHERE ' + where) if where else ''} ORDER BY {order}", args):
        row = dict(r)
        row["due"] = crew_amount_due(r)
        row["pay_status"] = crew_pay_status(r, today, pay_days)
        rows.append(row)
    return rows


def crew_pay_summary(rows):
    """Totals over crew_pay_rows() output."""
    zero = Decimal("0")
    year = str(util.today().year)
    return {
        "owed": sum((r["due"] for r in rows if r["pay_status"] in ("owed", "overdue")), zero),
        "overdue": sum((r["due"] for r in rows if r["pay_status"] == "overdue"), zero),
        "overdue_count": sum(1 for r in rows if r["pay_status"] == "overdue"),
        "upcoming": sum((r["due"] for r in rows if r["pay_status"] == "upcoming"), zero),
        "paid_this_year": sum((util.to_decimal(r["paid_amount"]) for r in rows
                               if r["paid_on"] and r["paid_on"].startswith(year)), zero),
    }


def paid_by_year(rows):
    """{year: total paid} for a crew member, newest year first (for 1099 prep)."""
    totals = {}
    for r in rows:
        if r["paid_on"]:
            year = r["paid_on"][:4]
            totals[year] = totals.get(year, Decimal("0")) + util.to_decimal(r["paid_amount"])
    return dict(sorted(totals.items(), reverse=True))


def mark_crew_paid(assignment_ids, paid_on, method=None, reference=None):
    """Record payment for each assignment at its current amount due."""
    rows = {r["id"]: r for r in crew_pay_rows(
        f"a.id IN ({', '.join('?' for _ in assignment_ids)})", tuple(assignment_ids))} if assignment_ids else {}
    conn = db.get_db()
    for row in rows.values():
        conn.execute(
            "UPDATE event_crew SET paid_on = ?, paid_amount = ?, paid_method = ?, paid_reference = ? WHERE id = ?",
            (paid_on, float(row["due"]), method, reference, row["id"]),
        )
    conn.commit()
    return len(rows)


def mark_crew_unpaid(assignment_ids):
    if not assignment_ids:
        return 0
    marks = ", ".join("?" for _ in assignment_ids)
    db.execute(
        f"UPDATE event_crew SET paid_on = NULL, paid_amount = NULL, paid_method = NULL, paid_reference = NULL "
        f"WHERE id IN ({marks})",
        tuple(assignment_ids),
    )
    return len(assignment_ids)


# --- Contract payments -----------------------------------------------------------

def contract_payments(contract):
    """Money received against a contract through its invoices.

    Returns {"paid", "remaining", "deposit_received_on", "invoices", "payments"}.
    The deposit counts as received on the date cumulative payments first
    reached the deposit amount."""
    invoices = db.query(
        "SELECT * FROM invoices WHERE contract_id = ? AND status != 'void' ORDER BY issue_date, id", (contract["id"],)
    )
    payments = db.query(
        """SELECT p.*, i.number AS invoice_number FROM payments p JOIN invoices i ON i.id = p.invoice_id
           WHERE i.contract_id = ? AND i.status != 'void' ORDER BY p.paid_on, p.id""",
        (contract["id"],),
    )
    deposit = util.round_money(contract["deposit_amount"])
    running, received_on = Decimal("0"), None
    for p in payments:
        running += util.to_decimal(p["amount"])
        if received_on is None and deposit > 0 and running >= deposit:
            received_on = p["paid_on"]
    total = util.round_money(contract["total_amount"])
    return {
        "paid": util.round_money(running),
        "remaining": max(util.round_money(total - running), Decimal("0")),
        "deposit_received_on": received_on,
        "invoices": invoices,
        "payments": payments,
    }


def deposit_status(contract, received_on, today=None):
    """none | received | overdue | due"""
    if util.to_decimal(contract["deposit_amount"]) <= 0:
        return "none"
    if received_on:
        return "received"
    due = contract["deposit_due_date"]
    if due and util.parse_date(due) < (today or util.today()):
        return "overdue"
    return "due"


def create_contract_invoice(contract, kind, status="draft"):
    """An invoice for a contract's deposit or balance, at the contract amounts
    (no extra tax: the signed total is what the client agreed to pay)."""
    event = db.query("SELECT * FROM events WHERE id = ?", (contract["event_id"],), one=True)
    deposit = util.round_money(contract["deposit_amount"])
    if kind == "deposit":
        amount, due = deposit, contract["deposit_due_date"] or util.today().isoformat()
        description = f"Deposit per contract {contract['number']}: {event['title']}"
    else:
        amount = util.round_money(util.to_decimal(contract["total_amount"]) - deposit)
        due = contract["balance_due_date"] or event["event_date"]
        description = f"Balance per contract {contract['number']}: {event['title']}"
    invoice_id = db.insert("invoices", {
        "number": next_number("invoices", db.get_setting("invoice_prefix")),
        "event_id": event["id"], "client_id": event["client_id"], "contract_id": contract["id"], "kind": kind,
        "status": status, "issue_date": util.today().isoformat(), "due_date": due, "tax_rate": 0, "discount": 0,
        "terms": db.get_setting("invoice_terms"), "public_key": util.gen_key(18),
    })
    db.insert("invoice_items", {"invoice_id": invoice_id, "description": description, "quantity": 1,
                                "unit_price": float(amount), "taxable": 0, "sort": 0})
    return invoice_id


def record_contract_deposit(contract, paid_on, amount, method=None, reference=None):
    """Record a deposit payment, creating the deposit invoice if needed."""
    invoice = db.query(
        "SELECT * FROM invoices WHERE contract_id = ? AND kind = 'deposit' AND status != 'void' ORDER BY id LIMIT 1",
        (contract["id"],), one=True,
    )
    invoice_id = invoice["id"] if invoice else create_contract_invoice(contract, "deposit", status="sent")
    if invoice and invoice["status"] == "draft":
        db.update("invoices", invoice_id, {"status": "sent"})
    db.insert("payments", {"invoice_id": invoice_id, "paid_on": paid_on, "amount": float(util.round_money(amount)),
                           "method": method, "reference": reference})
    return invoice_id


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
