"""The public event request form: its questions, reading the answers, and
turning a request into an event (or adding it to one).

Only a name and an email or phone number are required. Every other answer
is optional, so people can skip whatever they don't know yet."""

import json
import re
from datetime import datetime, timedelta

from . import db, files, services, util

NOT_SURE = "Not sure"

# "What should we bring?" choices. Some also set event fields (see event_fields).
SPEAKERS = "Speakers / sound system"
SPEECH_MICS = "Microphones for speeches"
WIRELESS = "Wireless microphones"
BAND = "Live band support"
DJ = "DJ setup"
PLAYBACK = "Music from a phone or laptop"
BACKLINE = "Backline (amps, drums, keyboards)"
MONITORS = "Stage monitors"
RECORD = "Recording or livestream feed"
HELP_DECIDE = "Not sure yet: help us decide"
NEEDS = [SPEAKERS, SPEECH_MICS, WIRELESS, BAND, DJ, PLAYBACK, BACKLINE, MONITORS, RECORD, HELP_DECIDE]
SOUND_NEEDS = {SPEAKERS, SPEECH_MICS, WIRELESS, BAND, DJ, PLAYBACK, MONITORS, RECORD}

TECH_ON_SITE = "Yes, someone to run the sound"
DROP_OFF = "No, just drop off and pick up"

SETTINGS = {"Indoors": "Indoor", "Outdoors": "Outdoor", "Both": "Indoor + outdoor"}
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
RATE_LIMIT = 5  # requests per network per hour
MAX_FILES = 10


class Q:
    """One question on the form."""

    def __init__(self, name, label, kind="text", choices=None, placeholder=None, hint=None, multiple=False,
                 wide=False, rows=3, autocomplete=None):
        self.name = name
        self.label = label
        self.kind = kind  # text, email, tel, textarea, date, time, int, select, chips
        self.choices = choices
        self.placeholder = placeholder
        self.hint = hint
        self.multiple = multiple
        self.wide = wide or kind == "textarea"
        self.rows = rows
        self.autocomplete = autocomplete

    def options(self):
        return self.choices() if callable(self.choices) else list(self.choices or [])


def _type_names():
    return [r["name"] for r in db.query("SELECT name FROM event_types ORDER BY sort, name")]


def _event_types():
    names = _type_names()
    return names if "Other" in names else names + ["Something else"]


# (key, title, hint, questions)
SECTIONS = [
    ("about", "About you", "We just need your name and an email or phone number. Everything after that is optional.", [
        Q("name", "Your name", autocomplete="name"),
        Q("organization", "Company or organization", hint="Leave blank for a private event.",
          autocomplete="organization"),
        Q("email", "Email", kind="email", autocomplete="email"),
        Q("phone", "Phone", kind="tel", autocomplete="tel"),
    ]),
    ("event", "The event", None, [
        Q("description", "Tell us about it", kind="textarea",
          placeholder="e.g. A company all-hands with three speakers and a Q&A, then a DJ for the happy hour."),
        Q("event_type", "Type of event", kind="select", choices=_event_types),
        Q("event_name", "Event name", placeholder="If it has one"),
        Q("event_date", "Date", kind="date"),
        Q("end_date", "Last day", kind="date", hint="Only for events that run more than one day."),
        Q("attendance", "About how many people?", kind="int", placeholder="e.g. 200"),
        Q("setting", "Indoors or outdoors?", kind="chips", choices=["Indoors", "Outdoors", "Both", NOT_SURE]),
        Q("performers", "Who's speaking or performing?", wide=True,
          placeholder="e.g. Three speakers and a panel · an 8-piece band and a DJ"),
    ]),
    ("place", "Location", None, [
        Q("venue_name", "Venue", placeholder="e.g. Riverbend Country Club"),
        Q("venue_address", "Address", placeholder="Street and city", autocomplete="off"),
        Q("layout", "How is the space laid out?", kind="textarea",
          placeholder="e.g. Ceremony on the lawn, then dinner and dancing in the ballroom. The band sets up "
                      "against the far wall."),
        Q("stage", "Is there a stage?", kind="chips", choices=["Yes", "No", NOT_SURE]),
        Q("power", "Power outlets near where we'll set up?", kind="chips", choices=["Yes", "No", NOT_SURE]),
        Q("venue_contact", "Venue contact", placeholder="Name and phone or email", wide=True),
    ]),
    ("access", "Load-in and parking", None, [
        Q("access", "Getting gear inside", kind="chips", multiple=True, wide=True,
          choices=["Loading dock", "Ground-level door", "Elevator", "Stairs", NOT_SURE]),
        Q("load_in_time", "Earliest we can arrive", kind="time"),
        Q("load_out_time", "Everything out by", kind="time"),
        Q("load_in_notes", "Anything else about getting in?", kind="textarea", rows=2,
          placeholder="e.g. The dock is off the alley; the freight elevator has to be booked."),
        Q("parking", "Where can our truck or van park?", kind="textarea", rows=2,
          placeholder="e.g. Lot behind the building ($20) · street parking only · 30-minute loading zone"),
    ]),
    ("timeline", "Timeline", None, [
        Q("doors_time", "Guests arrive", kind="time"),
        Q("start_time", "Starts", kind="time"),
        Q("end_time", "Ends", kind="time"),
        Q("schedule", "Schedule, if you have one", kind="textarea", rows=5,
          placeholder="5:30 Doors\n6:00 Welcome speech\n7:00 Dinner\n8:30 Band until 11"),
    ]),
    ("needs", "What you need", "Tap everything that applies.", [
        Q("needs", "What should we bring?", kind="chips", multiple=True, wide=True, choices=NEEDS),
        Q("tech", "Do you need a sound tech there?", kind="chips", wide=True,
          choices=[TECH_ON_SITE, DROP_OFF, NOT_SURE]),
        Q("mic_count", "How many microphones?", kind="int", hint="A rough guess is fine."),
        Q("gear_details", "Specific gear or requests", kind="textarea",
          placeholder="e.g. 4 handheld wireless mics and a lectern mic. The band's rider is attached."),
    ]),
    ("people", "Contacts on the day", None, [
        Q("onsite_name", "On-site contact", placeholder="If it's not you"),
        Q("onsite_phone", "Their phone", kind="tel"),
        Q("planner", "Planner or coordinator", placeholder="Name and phone or email", wide=True),
    ]),
    ("extra", "Anything else", None, [
        Q("budget", "Budget", placeholder="Optional, e.g. around $2,500"),
        Q("notes", "Anything else we should know?", kind="textarea"),
    ]),
]

QUESTIONS = {q.name: q for _key, _title, _hint, qs in SECTIONS for q in qs}


# --- Reading answers --------------------------------------------------------------

def parse(form):
    """Returns (answers, errors). Answers only hold what was filled in."""
    answers, errors = {}, {}
    for q in QUESTIONS.values():
        if q.kind == "chips" and q.multiple:
            picked = [v for v in form.getlist(q.name) if v in q.options()]
            if picked:
                answers[q.name] = picked
            continue
        raw = (form.get(q.name) or "").strip()
        if not raw:
            continue
        raw = raw[:4000] if q.kind == "textarea" else raw[:300]
        if q.kind == "email":
            answers[q.name] = raw
            if not EMAIL.fullmatch(raw):
                errors[q.name] = "That email address doesn't look right. Check it, or leave it blank and add a phone number."
        elif q.kind == "date":
            answers[q.name] = raw
            try:
                answers[q.name] = datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
            except ValueError:
                errors[q.name] = "Pick a date from the calendar, or leave it blank."
        elif q.kind == "time":
            answers[q.name] = raw
            try:
                answers[q.name] = datetime.strptime(raw[:5], "%H:%M").strftime("%H:%M")
            except ValueError:
                errors[q.name] = "Enter a time like 6:30 PM, or leave it blank."
        elif q.kind == "int":
            # Forgiving: "about 150", "150-200" and "1,200" all work.
            number = re.search(r"\d[\d,]*", raw)
            if number:
                answers[q.name] = int(number.group().replace(",", ""))
        elif q.kind in ("select", "chips"):
            if raw in q.options():
                answers[q.name] = raw
        else:
            answers[q.name] = raw
    if not answers.get("name"):
        errors["name"] = "Please tell us your name."
    if not answers.get("email") and not answers.get("phone"):
        errors["email"] = "Add an email or a phone number so we can get back to you."
    start, end = answers.get("event_date"), answers.get("end_date")
    if start and end and "event_date" not in errors and "end_date" not in errors:
        if end < start:
            errors["end_date"] = "The last day can't be before the first."
        elif end == start:
            del answers["end_date"]
    return answers, errors


def too_many(ip):
    since = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    return (db.scalar("SELECT COUNT(*) FROM client_requests WHERE ip = ? AND created_at >= ?", (ip, since)) or 0) >= RATE_LIMIT


def save(answers, uploads, ip):
    """Store a request and its files. Returns (request id, files that weren't accepted)."""
    request_id = db.insert("client_requests", {
        "name": answers["name"], "organization": answers.get("organization"), "email": answers.get("email"),
        "phone": answers.get("phone"), "event_date": answers.get("event_date"),
        "event_type": answers.get("event_type"), "answers": json.dumps(answers), "ip": ip,
        "created_at": util.now_iso(),
    })
    skipped = []
    for n, upload in enumerate(u for u in uploads if u and u.filename):
        if n >= MAX_FILES:
            skipped.append(f"{upload.filename} (only {MAX_FILES} files per request)")
            continue
        try:
            original, stored, size = files.store_upload(upload.filename, upload)
        except ValueError as exc:
            skipped.append(str(exc))
            continue
        db.insert("client_request_files", {"request_id": request_id, "original_name": original,
                                           "stored_name": stored, "size": size})
    return request_id, skipped


def answers_of(req):
    try:
        data = json.loads(req["answers"] or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _display(q, value):
    if isinstance(value, list):
        return ", ".join(value)
    if q.kind == "date":
        return util.fdate(value)
    if q.kind == "time":
        return util.ftime(value)
    return str(value)


def summary(answers, skip=()):
    """[(section title, [(question, answer text)])], skipping what was left blank."""
    out = []
    for key, title, _hint, questions in SECTIONS:
        if key in skip:
            continue
        rows = [(q.label, _display(q, answers[q.name])) for q in questions if answers.get(q.name) not in (None, "", [])]
        if rows:
            out.append((title, rows))
    return out


# --- Turning a request into event details -------------------------------------------

def service_type(a):
    if a.get("tech") == DROP_OFF:
        return "Dry hire (drop-off & pickup)"
    if a.get("tech") != TECH_ON_SITE:
        return None
    needs = set(a.get("needs", []))
    if BACKLINE in needs and needs & SOUND_NEEDS:
        return "Full production (PA, backline, crew)"
    if BACKLINE in needs:
        return "Backline + tech"
    return "PA + engineer"


def _join(*parts, sep="\n"):
    return sep.join(p for p in parts if p) or None


def event_fields(a):
    """Event columns this request can fill in (only ones with an answer)."""
    needs = a.get("needs", [])
    requested = [n for n in needs if n != HELP_DECIDE]
    values = {
        "guest_count": a.get("attendance"),
        "setting": SETTINGS.get(a.get("setting")),
        "service_type": service_type(a),
        "performers": a.get("performers"),
        "wireless_count": a.get("mic_count") if WIRELESS in needs else None,
        "playback_feeds": _join(PLAYBACK in needs and "Music from a phone or laptop",
                                RECORD in needs and "Recording or livestream feed", sep="; "),
        "audio_notes": _join(
            requested and "Asked for: " + ", ".join(requested) + ".",
            HELP_DECIDE in needs and "Wants help deciding what they need.",
            a.get("mic_count") and f"Microphones: about {a['mic_count']}.",
            a.get("gear_details"),
        ),
        "power_notes": a.get("power") and f"Power near the setup area: {a['power']}.",
        "load_in_time": a.get("load_in_time"),
        "load_out_time": a.get("load_out_time"),
        "doors_time": a.get("doors_time"),
        "start_time": a.get("start_time"),
        "end_time": a.get("end_time"),
        "run_of_show": a.get("schedule"),
        "on_site_contact": a.get("onsite_name"),
        "on_site_phone": a.get("onsite_phone"),
        "parking": _join(
            a.get("access") and "Access: " + ", ".join(a["access"]) + ".",
            a.get("load_in_notes"),
            a.get("parking") and "Parking: " + a["parking"],
        ),
    }
    return {k: v for k, v in values.items() if v not in (None, "", [])}


# Also kept on a venue created from the request, so they'd show twice on the event.
VENUE_ALSO = ("parking", "power_notes")

FIELD_LABELS = {
    "guest_count": "Audience", "setting": "Setting", "service_type": "Service", "performers": "Performers",
    "wireless_count": "Wireless mics", "playback_feeds": "Playback & feeds", "audio_notes": "Audio needs",
    "power_notes": "Power", "load_in_time": "Earliest arrival", "load_out_time": "Out by",
    "doors_time": "Guests arrive", "start_time": "Starts", "end_time": "Ends", "run_of_show": "Schedule",
    "on_site_contact": "On-site contact", "on_site_phone": "On-site phone", "parking": "Parking & load-in",
}


def client_fields(a):
    return {"name": a["name"], "company": a.get("organization"), "email": a.get("email"), "phone": a.get("phone"),
            "notes": "Added from an online event request."}


def venue_fields(a):
    return {
        "name": a["venue_name"],
        "address": a.get("venue_address"),
        "contact_name": a.get("venue_contact"),
        "load_in_notes": _join(a.get("access") and "Access: " + ", ".join(a["access"]) + ".", a.get("load_in_notes")),
        "parking_notes": a.get("parking"),
        "stage_notes": a.get("stage") and f"Stage: {a['stage']}.",
        "power_notes": a.get("power") and f"Power near the setup area: {a['power']}.",
        "notes": "Added from an online event request.",
    }


def title_for(a):
    if a.get("event_name"):
        return a["event_name"]
    who = a.get("organization") or a["name"]
    kind = a.get("event_type") if a.get("event_type") in _type_names() else None
    return f"{who} — {kind}" if kind else f"{who} event"


def office_notes(req, a, left_out=()):
    """The office-only notes for the event: who asked, plus answers that
    don't have their own place on the event."""
    contact = " · ".join(x for x in (a.get("name"), a.get("organization"), a.get("email"), a.get("phone")) if x)
    lines = [f"From online request #{req['id']}, received {util.fdatetime(req['created_at'])}.", f"Contact: {contact}"]
    for key, label in (("description", "About the event"), ("layout", "Layout"), ("stage", "Stage"),
                       ("venue_contact", "Venue contact"), ("planner", "Planner"), ("budget", "Budget"),
                       ("notes", "Other notes")):
        if a.get(key):
            lines.append(f"{label}: {a[key]}")
    for label, value in left_out:
        lines.append(f"{label} (from the request): {value}")
    return "\n".join(lines)


def matching_client(a):
    """An existing client with the same email, phone or name."""
    if a.get("email"):
        row = db.query("SELECT id FROM clients WHERE lower(email) = lower(?)", (a["email"],), one=True)
        if row:
            return row["id"], "same email"
    digits = re.sub(r"\D", "", a.get("phone") or "")[-10:]
    if len(digits) >= 7:
        for row in db.query("SELECT id, phone FROM clients WHERE phone IS NOT NULL AND phone != ''"):
            if re.sub(r"\D", "", row["phone"])[-10:] == digits:
                return row["id"], "same phone"
    row = db.query("SELECT id FROM clients WHERE lower(name) = lower(?)", (a["name"],), one=True)
    return (row["id"], "same name") if row else (None, None)


def matching_venue(a):
    if not a.get("venue_name"):
        return None
    row = db.query("SELECT id FROM venues WHERE lower(name) = lower(?)", (a["venue_name"].strip(),), one=True)
    return row["id"] if row else None


FILE_GUESSES = [
    (("plot",), "Stage plot"), (("input",), "Input list"), (("rider",), "Rider / tech rider"),
    (("tech pack", "techpack", "tech-pack", "tech_pack"), "Venue tech pack"),
    (("floor", "layout", "site map", "site-map", "seating"), "Floor plan / site map"),
    (("parking", "load", "dock", "map", "directions"), "Parking / load-in map"),
    (("schedule", "agenda", "run of show", "run-of-show", "timeline", "itinerary"), "Run of show / agenda"),
    (("contract", "coi", "insurance"), "Contract / paperwork"),
]


def guess_category(filename):
    name = filename.lower().replace("_", " ")
    for words, category in FILE_GUESSES:
        if any(w in name for w in words):
            return category
    return "Photos" if files.extension(filename) in ("jpg", "jpeg", "png", "gif", "webp", "heic") else "Other"


def move_files(req, event_id):
    """Attach the request's files to the event's documents (office-only until
    someone shares them with crew)."""
    source = req["organization"] or req["name"]
    for f in db.query("SELECT * FROM client_request_files WHERE request_id = ? ORDER BY id", (req["id"],)):
        db.insert("event_files", {
            "event_id": event_id, "category": guess_category(f["original_name"]),
            "description": f"From online request #{req['id']}", "source": source,
            "original_name": f["original_name"], "stored_name": f["stored_name"], "size": f["size"],
            "crew_visible": 0, "uploaded_by": "online request", "uploaded_at": util.now_iso(),
        })
    db.execute("DELETE FROM client_request_files WHERE request_id = ?", (req["id"],))


def _client_for(a, choice):
    if choice == "new":
        return db.insert("clients", client_fields(a))
    return int(choice) if choice else None


def _venue_for(a, choice):
    if choice == "new" and a.get("venue_name"):
        return db.insert("venues", venue_fields(a))
    return int(choice) if choice and choice != "new" else None


def create_event(req, title, event_date, end_date, event_type, client_choice, venue_choice):
    """Make an inquiry from a request. Choices are "new", an id, or "" (none)."""
    a = answers_of(req)
    profiles = services.event_type_profiles()
    profile = profiles.get(event_type or "", profiles[""])
    client_id = _client_for(a, client_choice)
    values = event_fields(a)
    if venue_choice == "new" and a.get("venue_name"):
        for key in VENUE_ALSO:
            values.pop(key, None)
    values.setdefault("run_of_show", profile["run_of_show"])
    client = db.query("SELECT name FROM clients WHERE id = ?", (client_id,), one=True) if client_id else None
    values.update({
        "title": title, "event_type": event_type or None, "status": "inquiry", "client_id": client_id,
        "venue_id": _venue_for(a, venue_choice), "event_date": event_date, "end_date": end_date,
        "notes": office_notes(req, a),
        "reference_number": services.unique_reference(event_date, client and client["name"], title),
    })
    event_id = db.insert("events", values)
    for template_id in profile["checklists"]:
        services.apply_checklist_template(event_id, template_id)
    move_files(req, event_id)
    db.update("client_requests", req["id"], {"status": "converted", "event_id": event_id, "handled_at": util.now_iso()})
    return event_id


def add_to_event(req, event_id):
    """Fill in whatever the event is missing. Answers that differ from what the
    office already entered go into the office notes instead of overwriting."""
    event = db.query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
    a = answers_of(req)
    updates, left_out = {}, []
    fields = event_fields(a)
    new_venue = not event["venue_id"] and a.get("venue_name") and not matching_venue(a)
    if new_venue:
        for key in VENUE_ALSO:
            fields.pop(key, None)
    for key, value in fields.items():
        current = event[key]
        if current in (None, ""):
            updates[key] = value
        elif str(current).strip() != str(value).strip():
            left_out.append((FIELD_LABELS[key], value))
    if a.get("event_date") and a["event_date"] != event["event_date"]:
        left_out.insert(0, ("Date", util.fdate(a["event_date"])))
    if not event["client_id"]:
        match, _why = matching_client(a)
        updates["client_id"] = match or db.insert("clients", client_fields(a))
    if not event["venue_id"] and a.get("venue_name"):
        updates["venue_id"] = matching_venue(a) or db.insert("venues", venue_fields(a))
    note = office_notes(req, a, left_out)
    updates["notes"] = f"{event['notes']}\n\n{note}" if event["notes"] else note
    updates["updated_at"] = util.now_iso()
    db.update("events", event_id, updates)
    move_files(req, event_id)
    db.update("client_requests", req["id"], {"status": "converted", "event_id": event_id, "handled_at": util.now_iso()})
    return [label for key, label in FIELD_LABELS.items() if key in updates]


def delete(req):
    for f in db.query("SELECT stored_name FROM client_request_files WHERE request_id = ?", (req["id"],)):
        files.remove_stored(f["stored_name"])
    db.execute("DELETE FROM client_requests WHERE id = ?", (req["id"],))
