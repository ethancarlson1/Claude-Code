"""Crew: skills and rates, days they can't work, gig offers they accept or
decline, and each person's private crew page.

A gig offer is an *opening* on an event (say, two A2s for Saturday) sent to
several people. The first to accept get the spots: accepting adds them to
the event's crew, and once it's full everyone else's offer closes. Offers
reach crew by email when it's set up (mailer.py), or by a text or email the
office sends from its own phone with one click."""

import threading
from datetime import timedelta

from flask import url_for

from . import db, mailer, services, util
from .defaults import DEFAULT_CREW_SKILLS

OFFER_STATUSES = {"sent": "Waiting", "accepted": "Accepted", "declined": "Declined", "filled": "Spot filled",
                  "withdrawn": "Withdrawn"}
_answering = threading.Lock()  # two people taking the last spot at the same moment


# --- Skills and rates -------------------------------------------------------------

def skill_list():
    text = db.get_setting("crew_skills")
    if text is None:
        return list(DEFAULT_CREW_SKILLS)
    return [line.strip() for line in text.splitlines() if line.strip()]


def skills_of(crew_id):
    return db.query("SELECT * FROM crew_skills WHERE crew_id = ? ORDER BY skill COLLATE NOCASE", (crew_id,))


def skills_by_crew():
    out = {}
    for row in db.query("SELECT * FROM crew_skills ORDER BY skill COLLATE NOCASE"):
        out.setdefault(row["crew_id"], []).append(row)
    return out


def rate_for(member, skill, skills=None):
    """(day rate, hourly rate) for a skill: the person's own rate for it, else their usual rates."""
    rows = skills if skills is not None else skills_of(member["id"])
    row = next((s for s in rows if s["skill"] == skill), None)
    day = row["day_rate"] if row and row["day_rate"] is not None else member["day_rate"]
    hourly = row["hourly_rate"] if row and row["hourly_rate"] is not None else member["hourly_rate"]
    return day, hourly


def money_input(text):
    """A rate typed into a form, like "$350". Returns (value or None, error or None)."""
    text = (text or "").replace("$", "").replace(",", "").strip()
    if not text:
        return None, None
    try:
        value = round(float(text), 2)
    except ValueError:
        return None, "Enter rates as numbers, like 350 or 27.50."
    return (value, None) if value >= 0 else (None, "Rates can't be negative.")


def read_skills(form):
    """Skills ticked on the crew form, with any rate for each. Returns (rows, error)."""
    rows, error = [], None
    for skill in form.getlist("skills"):
        day, e1 = money_input(form.get(f"skill_day:{skill}"))
        hourly, e2 = money_input(form.get(f"skill_hourly:{skill}"))
        error = error or e1 or e2
        rows.append({"skill": skill.strip()[:80], "day_rate": day, "hourly_rate": hourly})
    return [r for r in rows if r["skill"]], error


def save_skills(crew_id, rows):
    db.execute("DELETE FROM crew_skills WHERE crew_id = ?", (crew_id,))
    for row in rows:
        db.insert("crew_skills", {"crew_id": crew_id, **row})


# --- The crew member's own page ---------------------------------------------------------

def portal_key(crew_id):
    key = db.scalar("SELECT portal_key FROM crew WHERE id = ?", (crew_id,))
    if not key:
        key = util.gen_key(18)
        db.update("crew", crew_id, {"portal_key": key})
    return key


def portal_url(crew_id):
    return url_for("crew_portal.home", key=portal_key(crew_id), _external=True)


def new_portal_key(crew_id):
    """A new link, for when the old one went somewhere it shouldn't."""
    db.update("crew", crew_id, {"portal_key": util.gen_key(18)})


# --- Who's free ------------------------------------------------------------------

def unavailable(crew_id, since=None):
    return db.query("SELECT * FROM crew_unavailable WHERE crew_id = ? AND end_date >= ? ORDER BY start_date",
                    (crew_id, since or util.today().isoformat()))


def add_unavailable(crew_id, start, end, note, added_by):
    """Returns an error message, or None when saved."""
    start, end = util.parse_date(start), util.parse_date(end or start)
    if start is None or end is None:
        return "Pick the first and last day."
    if end < start:
        return "The last day can't be before the first."
    if end < util.today():
        return "Those days are already past."
    db.insert("crew_unavailable", {"crew_id": crew_id, "start_date": start.isoformat(), "end_date": end.isoformat(),
                                   "note": (note or "").strip()[:200] or None, "added_by": added_by,
                                   "created_at": util.now_iso()})
    return None


def conflicts(start, end, exclude_event_id=None):
    """{crew_id: [reason, ...]} for crew already working another event or
    marked unavailable on any day in [start, end]."""
    out = {}
    for row in db.query(
            """SELECT a.crew_id, e.title, e.event_date FROM event_crew a JOIN events e ON e.id = a.event_id
               WHERE e.status != 'cancelled' AND e.event_date <= ? AND COALESCE(e.end_date, e.event_date) >= ?
                 AND e.id != ? ORDER BY e.event_date""", (end, start, exclude_event_id or -1)):
        out.setdefault(row["crew_id"], []).append(f"Working {row['title']} ({util.fdate(row['event_date'], 'short')})")
    for row in db.query("SELECT * FROM crew_unavailable WHERE start_date <= ? AND end_date >= ?", (end, start)):
        out.setdefault(row["crew_id"], []).append("Can't work" + (f": {row['note']}" if row["note"] else ""))
    return out


# --- Openings and offers ----------------------------------------------------------------

def pay_text(pay_type, rate, hours):
    if rate is None:
        return "Rate to be confirmed"
    if pay_type == "hourly":
        text = f"{util.money(rate)}/hr"
        if hours:
            text += f" × {hours:g} hrs est. (about {util.money(rate * hours)})"
        return text
    return f"{util.money(rate)} flat"


def rate_text(day, hourly):
    parts = [f"{util.money(day)}/day" if day is not None else None,
             f"{util.money(hourly)}/hr" if hourly is not None else None]
    return " · ".join(p for p in parts if p) or "No rate on file"


def terms_for(opening, member, skills=None, days=1):
    """What one person is offered: (pay type, rate, hours). Their own day rate
    is for each day of the event."""
    if opening["pay_type"] in ("flat", "hourly"):
        return opening["pay_type"], opening["pay_rate"], opening["hours"]
    day, hourly = rate_for(member, opening["skill"], skills)
    if day is not None:
        return "flat", round(day * days, 2), opening["hours"]
    if hourly is not None:
        return "hourly", hourly, opening["hours"]
    return "flat", None, opening["hours"]


def taken(opening_id):
    """Spots filled: people who accepted and are still on the crew."""
    return db.scalar("SELECT COUNT(*) FROM crew_offers WHERE opening_id = ? AND status = 'accepted' "
                     "AND assignment_id IS NOT NULL", (opening_id,))


def set_needed(opening_id, needed):
    """Change how many people an opening needs, reopening it if there's room again."""
    status = "open" if taken(opening_id) < needed else "filled"
    db.execute("UPDATE crew_openings SET needed = ?, status = ? WHERE id = ? AND status != 'cancelled'",
               (needed, status, opening_id))


def left_crew(assignment_id):
    """Someone who accepted an offer was taken off the crew: their spot opens up again."""
    for offer in db.query("SELECT * FROM crew_offers WHERE assignment_id = ?", (assignment_id,)):
        db.update("crew_offers", offer["id"], {"status": "withdrawn"})
        db.execute("UPDATE crew_openings SET status = 'open' WHERE id = ? AND status = 'filled'",
                   (offer["opening_id"],))


def openings(event_id):
    """The event's openings, each with its offers."""
    rows = db.query("SELECT * FROM crew_openings WHERE event_id = ? AND status != 'cancelled' ORDER BY id", (event_id,))
    offers = {}
    for o in db.query(
            """SELECT o.*, c.name, c.email, c.phone FROM crew_offers o JOIN crew c ON c.id = o.crew_id
               JOIN crew_openings p ON p.id = o.opening_id WHERE p.event_id = ?
               ORDER BY CASE o.status WHEN 'accepted' THEN 0 WHEN 'sent' THEN 1 ELSE 2 END, c.name""", (event_id,)):
        offers.setdefault(o["opening_id"], []).append(o)
    return [{"row": r, "offers": offers.get(r["id"], []),
             "taken": sum(1 for o in offers.get(r["id"], []) if o["status"] == "accepted" and o["assignment_id"])}
            for r in rows]


def send_offers(opening_id, crew_ids):
    """Offer an opening to people. Returns the new offer rows (people already
    holding a live offer or spot are skipped; a withdrawn or declined offer is sent again)."""
    opening = db.query("SELECT * FROM crew_openings WHERE id = ?", (opening_id,), one=True)
    days = util.event_days(db.query("SELECT * FROM events WHERE id = ?", (opening["event_id"],), one=True))
    skills = skills_by_crew()
    sent = []
    for member in db.query(f"SELECT * FROM crew WHERE id IN ({', '.join('?' for _ in crew_ids)})", tuple(crew_ids)):
        pay_type, rate, hours = terms_for(opening, member, skills.get(member["id"], []), days)
        existing = db.query("SELECT * FROM crew_offers WHERE opening_id = ? AND crew_id = ?",
                            (opening_id, member["id"]), one=True)
        values = {"status": "sent", "pay_type": pay_type, "pay_rate": rate, "hours": hours, "note": None,
                  "sent_at": util.now_iso(), "responded_at": None, "emailed_at": None}
        if existing is None:
            offer_id = db.insert("crew_offers", {"opening_id": opening_id, "crew_id": member["id"], **values})
        elif existing["status"] in ("withdrawn", "declined", "filled"):
            offer_id = existing["id"]
            db.update("crew_offers", offer_id, values)
        else:
            continue
        sent.append(offer_id)
    return sent


def offer_details(offer_id):
    """An offer with everything a message or page needs about it."""
    return db.query(
        """SELECT o.*, p.event_id, p.role, p.skill, p.needed, p.call_time, p.notes AS opening_notes,
                  p.status AS opening_status, c.name, c.email, c.phone, e.title, e.event_date, e.end_date,
                  e.status AS event_status, e.load_in_time, e.start_time, e.end_time, e.reference_number,
                  v.name AS venue_name, v.address AS venue_address, v.city AS venue_city
           FROM crew_offers o JOIN crew_openings p ON p.id = o.opening_id JOIN crew c ON c.id = o.crew_id
           JOIN events e ON e.id = p.event_id LEFT JOIN venues v ON v.id = e.venue_id
           WHERE o.id = ?""", (offer_id,), one=True)


def is_open(offer):
    """Still waiting for an answer, for an event that's still on and not over."""
    end = offer["end_date"] or offer["event_date"]
    return offer["status"] == "sent" and offer["event_status"] != "cancelled" and end >= util.today().isoformat()


def answer(offer_id, accept, note=""):
    """The crew member's answer. Returns the offer's status afterwards:
    accepted, declined, filled (no spots left), or whatever it already was."""
    with _answering:
        offer = offer_details(offer_id)
        if not is_open(offer):
            return offer["status"]
        now = util.now_iso()
        note = (note or "").strip()[:500] or None
        if not accept:
            db.update("crew_offers", offer_id, {"status": "declined", "note": note, "responded_at": now})
            return "declined"
        filled = taken(offer["opening_id"])
        if offer["opening_status"] != "open" or filled >= offer["needed"]:
            db.update("crew_offers", offer_id, {"status": "filled", "responded_at": now})
            return "filled"
        assignment_id = db.insert("event_crew", {
            "event_id": offer["event_id"], "crew_id": offer["crew_id"], "role": offer["role"],
            "call_time": offer["call_time"], "pay_type": offer["pay_type"], "pay_rate": offer["pay_rate"],
            "hours": offer["hours"], "confirmed": 1, "notes": note, "worksheet_key": util.gen_key(),
        })
        db.update("crew_offers", offer_id, {"status": "accepted", "assignment_id": assignment_id, "note": note,
                                            "responded_at": now})
        if filled + 1 >= offer["needed"]:
            db.update("crew_openings", offer["opening_id"], {"status": "filled"})
            db.execute("UPDATE crew_offers SET status = 'filled' WHERE opening_id = ? AND status = 'sent'",
                       (offer["opening_id"],))
        return "accepted"


# --- Messages -------------------------------------------------------------------------

def _where(offer):
    place = ", ".join(x for x in (offer["venue_name"], offer["venue_address"], offer["venue_city"]) if x)
    return place or "Venue to be confirmed"


def offer_message(offer, link):
    """(subject, email body, text message) for a gig offer."""
    company = db.get_setting("company_name")
    when = util.fdate(offer["event_date"])
    if offer["end_date"] and offer["end_date"] != offer["event_date"]:
        when += f" to {util.fdate(offer['end_date'])}"
    call = f" · call {util.ftime(offer['call_time'])}" if offer["call_time"] else ""
    pay = pay_text(offer["pay_type"], offer["pay_rate"], offer["hours"])
    subject = f"Gig offer: {offer['role']} · {util.fdate(offer['event_date'], 'short')} · {offer['title']}"
    lines = [f"Hi {offer['name'].split()[0]},", "", f"{company} has a gig for you:", "",
             offer["role"], offer["title"], f"{when}{call}", _where(offer), f"Pay: {pay}"]
    if offer["opening_notes"]:
        lines += ["", offer["opening_notes"]]
    lines += ["", f"Accept or decline here (spots go to whoever accepts first): {link}", "", "Thanks,", company]
    phone = db.get_setting("company_phone")
    if phone:
        lines.append(phone)
    text = (f"{company}: gig offer. {offer['role']}, {util.fdate(offer['event_date'], 'short')}{call}, "
            f"{offer['venue_name'] or offer['title']}. {pay}. Accept or decline: {link}")
    return subject, "\n".join(lines), text


def update_message(event, member_name, message, link):
    company = db.get_setting("company_name")
    subject = f"Update: {event['title']} · {util.fdate(event['event_date'], 'short')}"
    body = "\n".join([f"Hi {member_name.split()[0]},", "", message.strip(), "",
                      f"Your job sheet for {event['title']} ({util.fdate(event['event_date'])}) has the latest "
                      f"details: {link}", "", "Thanks,", company])
    return subject, body


def email_offers(offer_ids):
    """Email offers to everyone who has an email address. Returns (sent names,
    names without email, error message or None)."""
    sent, missing, error = [], [], None
    for offer_id in offer_ids:
        offer = offer_details(offer_id)
        if not offer["email"]:
            missing.append(offer["name"])
            continue
        subject, body, _text = offer_message(offer, portal_url(offer["crew_id"]))
        try:
            mailer.send(offer["email"], subject, body)
        except mailer.MailError as exc:
            error = str(exc)
            break
        db.update("crew_offers", offer_id, {"emailed_at": util.now_iso()})
        sent.append(offer["name"])
    return sent, missing, error


def tell_office(offer_id, outcome):
    """A short email to the office when someone answers, if email is set up."""
    office = db.get_setting("company_email")
    if not (mailer.configured() and office):
        return
    offer = offer_details(offer_id)
    word = {"accepted": "accepted", "declined": "declined", "filled": "tried to accept (already filled)"}[outcome]
    subject = f"{offer['name']} {word}: {offer['role']} · {offer['title']}"
    body = f"{offer['name']} {word} the {offer['role']} offer for {offer['title']} on {util.fdate(offer['event_date'])}."
    if offer["note"]:
        body += f"\n\nTheir note: {offer['note']}"
    try:
        mailer.send(office, subject, body)
    except mailer.MailError:
        pass  # the answer is saved either way; the Crew tab shows it


# --- Calendar ---------------------------------------------------------------------------

def calendar(crew_id):
    """Every gig this person is on (from two months back), for their phone's calendar."""
    company = db.get_setting("company_name")
    since = (util.today() - timedelta(days=60)).isoformat()
    entries = []
    for a in db.query(
            """SELECT a.*, e.reference_number FROM event_crew a JOIN events e ON e.id = a.event_id
               WHERE a.crew_id = ? AND e.status != 'cancelled' AND COALESCE(e.end_date, e.event_date) >= ?
               ORDER BY e.event_date""", (crew_id, since)):
        event = db.query("SELECT * FROM events WHERE id = ?", (a["event_id"],), one=True)
        role = f" ({a['role']})" if a["role"] else ""
        link = url_for("public.worksheet", reference=event["reference_number"], key=a["worksheet_key"], _external=True)
        entries.append(services.vevent(event, uid=f"{event['reference_number']}-{a['id']}@backline",
                                       summary=f"{event['title']}{role}", description=f"Job sheet: {link}",
                                       start_time=a["call_time"]))
    return services.calendar_ics(entries, name=f"{company} gigs")
