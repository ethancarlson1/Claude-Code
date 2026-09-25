import re
import secrets
import string
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote

from flask import request

EVENT_STATUSES = ["inquiry", "hold", "confirmed", "completed", "cancelled"]
# Statuses that reserve gear for availability / conflict checks.
RESERVING_STATUSES = ("hold", "confirmed")
INVENTORY_CATEGORIES = [
    "Consoles",
    "Speakers",
    "Monitors",
    "Amplifiers & Processing",
    "Microphones",
    "Wireless",
    "DI & Stage Boxes",
    "Cables & Snakes",
    "Stands & Hardware",
    "Guitar Amps",
    "Bass Amps",
    "Drums",
    "Cymbals",
    "Keyboards",
    "Power & Distro",
    "Lighting",
    "Staging",
    "Cases & Carts",
    "Other",
]
CONDITIONS = ["New", "Excellent", "Good", "Fair", "Needs Repair"]
INVENTORY_STATUSES = ["active", "maintenance", "retired"]
CONTRACT_STATUSES = ["draft", "sent", "signed", "void"]
PAYMENT_METHODS = ["Check", "ACH / Bank Transfer", "Credit Card", "Cash", "Venmo", "Zelle", "PayPal", "Other"]

CENT = Decimal("0.01")


def to_decimal(value):
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def round_money(value):
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def money(value):
    amount = round_money(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def fdate(value, fmt="long"):
    d = parse_date(value)
    if d is None:
        return ""
    if fmt == "short":
        return f"{d:%b} {d.day}, {d.year}"
    if fmt == "iso":
        return d.isoformat()
    if fmt == "ordinal":  # "Sat Nov 7th 2026", as on a band worksheet
        suffix = "th" if 11 <= d.day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
        return f"{d:%a} {d:%b} {d.day}{suffix} {d.year}"
    return f"{d:%a}, {d:%b} {d.day}, {d.year}"


def ftime(value):
    if not value:
        return ""
    try:
        t = datetime.strptime(value[:5], "%H:%M")
    except ValueError:
        return value
    hour = t.hour % 12 or 12
    return f"{hour}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"


def fdatetime(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return f"{fdate(dt.date(), 'short')} {ftime(dt.strftime('%H:%M'))}"


def today():
    return date.today()


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def gen_key(nbytes=12):
    return secrets.token_urlsafe(nbytes)


def _slug_words(text):
    return [w for w in re.split(r"[^A-Za-z0-9]+", text or "") if w]


def gen_reference(event_date, client_name=None, title=None):
    """Build a human-readable event reference like 2026-11-07-Alvarez-Sofia-TJ1R."""
    words = _slug_words(client_name)
    if len(words) == 2:
        words = [words[1], words[0]]  # "Sofia Alvarez" -> "Alvarez-Sofia"
    if not words:
        words = _slug_words(title)[:3]
    name_part = "-".join(w.capitalize() if w.islower() else w for w in words)[:32].strip("-")
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    parts = [parse_date(event_date).isoformat()]
    if name_part:
        parts.append(name_part)
    parts.append(suffix)
    return "-".join(parts)


def event_end(event):
    return event["end_date"] or event["event_date"]


def event_days(event):
    start = parse_date(event["event_date"])
    end = parse_date(event_end(event))
    return max((end - start).days + 1, 1)


def month_bounds(year, month):
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def wants_json():
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def mailto(to, subject, body):
    return f"mailto:{quote(to or '')}?subject={quote(subject)}&body={quote(body)}"


def maps_url(*parts):
    query = ", ".join(p for p in parts if p)
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}" if query else ""


def status_class(status):
    return {
        "inquiry": "muted",
        "hold": "warn",
        "confirmed": "ok",
        "completed": "info",
        "cancelled": "bad",
        "draft": "muted",
        "sent": "info",
        "signed": "ok",
        "void": "bad",
        "partial": "warn",
        "paid": "ok",
        "overdue": "bad",
        "owed": "warn",
        "upcoming": "muted",
        "received": "ok",
        "due": "info",
        "active": "ok",
        "maintenance": "warn",
        "retired": "muted",
    }.get(status, "muted")


def init_app(app):
    app.jinja_env.filters.update(
        money=money,
        fdate=fdate,
        ftime=ftime,
        fdatetime=fdatetime,
        status_class=status_class,
    )
    app.jinja_env.globals.update(mailto=mailto, today=today, maps_url=maps_url)
