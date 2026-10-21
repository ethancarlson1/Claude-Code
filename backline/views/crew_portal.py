"""Each crew member's own page, at /gigs/<private link>: gig offers to accept
or decline, upcoming gigs with their job sheets and pay, recent pay, a
calendar feed for their phone, and days they can't work. No password: the
link is the key, like the worksheet links."""

from datetime import timedelta

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for

from .. import crew, db, services, util

bp = Blueprint("crew_portal", __name__)


def _member(key):
    member = db.query("SELECT * FROM crew WHERE portal_key = ?", (key,), one=True) if key else None
    if member is None:
        abort(404)
    return member


def _home(key, anchor=None):
    return redirect(url_for("crew_portal.home", key=key) + (f"#{anchor}" if anchor else ""))


@bp.route("/gigs/<key>")
def home(key):
    member = _member(key)
    today = util.today().isoformat()
    offers = []
    for row in db.query("SELECT id FROM crew_offers WHERE crew_id = ? AND status = 'sent' ORDER BY sent_at",
                        (member["id"],)):
        offer = crew.offer_details(row["id"])
        if crew.is_open(offer):
            busy = crew.conflicts(offer["event_date"], offer["end_date"] or offer["event_date"], offer["event_id"])
            offers.append({"row": offer, "busy": busy.get(member["id"], []),
                           "pay": crew.pay_text(offer["pay_type"], offer["pay_rate"], offer["hours"])})
    gigs = []
    for a in services.crew_pay_rows("a.crew_id = ? AND e.status != 'cancelled' AND COALESCE(e.end_date, e.event_date) >= ?",
                                    (member["id"], today), order="e.event_date, a.call_time"):
        event = db.query("SELECT * FROM events WHERE id = ?", (a["event_id"],), one=True)
        _client, venue = services.event_context(event)
        gigs.append({"row": a, "event": event, "venue": venue,
                     "link": url_for("public.worksheet", reference=event["reference_number"], key=a["worksheet_key"])})
    since = (util.today() - timedelta(days=120)).isoformat()
    pay = [p for p in services.crew_pay_rows("a.crew_id = ? AND e.event_date >= ? AND e.status != 'cancelled'",
                                             (member["id"], since))
           if p["pay_status"] != "upcoming"]
    skills = crew.skills_of(member["id"])
    rates = [(s["skill"], *crew.rate_for(member, s["skill"], skills)) for s in skills]
    calendar = url_for("crew_portal.calendar", key=key, _external=True)
    return render_template(
        "crew/portal.html", member=member, key=key, offers=offers, gigs=gigs, pay=pay, rates=rates,
        unavailable=crew.unavailable(member["id"]), calendar=calendar,
        webcal="webcal://" + calendar.split("://", 1)[1], settings=db.get_settings(), pay_text=crew.pay_text,
    )


@bp.route("/gigs/<key>/offers/<int:offer_id>", methods=["POST"])
def answer(key, offer_id):
    member = _member(key)
    offer = db.query("SELECT * FROM crew_offers WHERE id = ? AND crew_id = ?", (offer_id, member["id"]), one=True)
    if offer is None:
        abort(404)
    accept = request.form.get("action") == "accept"
    outcome = crew.answer(offer_id, accept, request.form.get("note"))
    messages = {
        "accepted": ("You're on the crew. It's in your upcoming gigs below, with the full job sheet.", "ok"),
        "declined": ("Thanks for letting us know. We've passed it on.", "ok"),
        "filled": ("Sorry, the spots for that gig have already been filled.", "warn"),
    }
    text, kind = messages.get(outcome, ("That offer has already been answered or closed.", "warn"))
    flash(text, kind)
    if outcome in ("accepted", "declined", "filled"):
        crew.tell_office(offer_id, outcome)
    return _home(key, "gigs" if outcome == "accepted" else None)


@bp.route("/gigs/<key>/unavailable", methods=["POST"])
def add_unavailable(key):
    member = _member(key)
    error = crew.add_unavailable(member["id"], request.form.get("start_date"), request.form.get("end_date"),
                                 request.form.get("note"), "crew")
    flash(error or "Saved. We won't offer you gigs on those days.", "bad" if error else "ok")
    return _home(key, "availability")


@bp.route("/gigs/<key>/unavailable/<int:row_id>/delete", methods=["POST"])
def delete_unavailable(key, row_id):
    member = _member(key)
    db.execute("DELETE FROM crew_unavailable WHERE id = ? AND crew_id = ?", (row_id, member["id"]))
    flash("Removed.", "ok")
    return _home(key, "availability")


@bp.route("/gigs/<key>/calendar.ics")
def calendar(key):
    member = _member(key)
    return Response(crew.calendar(member["id"]), mimetype="text/calendar",
                    headers={"Content-Disposition": "inline; filename=gigs.ics", "Cache-Control": "no-cache"})


@bp.route("/gigs/<key>/manifest.webmanifest")
def manifest(key):
    """Lets crew add their page to their phone's home screen like an app."""
    _member(key)
    company = db.get_setting("company_name") or "Crew"
    icon = url_for("static", filename="brand/apple-touch-icon.png")
    return jsonify({
        "name": f"{company} gigs", "short_name": "Gigs", "start_url": url_for("crew_portal.home", key=key),
        "scope": url_for("crew_portal.home", key=key), "display": "standalone", "background_color": "#ffffff",
        "theme_color": "#0070b8", "icons": [{"src": icon, "sizes": "180x180", "type": "image/png"}],
    })
