"""The office side of crew offers: offering a gig to the right people,
following up, messaging the crew, and Settings → Crew (skills and email)."""

from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import crew, db, mailer, util
from .events import get_event

bp = Blueprint("offers", __name__)


def _crew_tab(event_id, anchor="openings"):
    return redirect(url_for("events.detail", event_id=event_id, tab="crew") + f"#{anchor}")


def _candidates(event, opening=None):
    """Everyone active, with their skills, rate for each skill, and whether
    they're free on the event's dates."""
    busy = crew.conflicts(event["event_date"], util.event_end(event), exclude_event_id=event["id"])
    on_event = {r["crew_id"] for r in db.query("SELECT crew_id FROM event_crew WHERE event_id = ?", (event["id"],))}
    offered = {}
    if opening:
        offered = {o["crew_id"]: o["status"]
                   for o in db.query("SELECT crew_id, status FROM crew_offers WHERE opening_id = ?", (opening["id"],))}
    skills = crew.skills_by_crew()
    rows = []
    for member in db.query("SELECT * FROM crew WHERE active = 1 ORDER BY name COLLATE NOCASE"):
        mine = skills.get(member["id"], [])
        rates = {skill: crew.rate_text(*crew.rate_for(member, skill, mine))
                 for skill in crew.skill_list() + [s["skill"] for s in mine]}
        rates[""] = crew.rate_text(member["day_rate"], member["hourly_rate"])
        rows.append({"row": member, "skills": [s["skill"] for s in mine], "rates": rates,
                     "busy": busy.get(member["id"], []), "on_event": member["id"] in on_event,
                     "offered": offered.get(member["id"])})
    return rows


@bp.route("/events/<int:event_id>/crew/offer", methods=["GET", "POST"])
def new(event_id):
    event = get_event(event_id)
    opening = None
    opening_id = request.values.get("opening", type=int)
    if opening_id:
        opening = db.query("SELECT * FROM crew_openings WHERE id = ? AND event_id = ? AND status != 'cancelled'",
                           (opening_id, event_id), one=True)
        if opening is None:
            abort(404)
    skill = request.args.get("skill", "")
    values = {"skill": skill, "role": skill, "needed": "1", "call_time": event["load_in_time"] or "",
              "pay_type": "own", "pay_rate": "", "hours": "", "notes": "", "email": "1"}
    errors = {}
    picked = []
    if request.method == "POST":
        values = {k: request.form.get(k, "").strip() for k in values}
        picked = [int(x) for x in request.form.getlist("crew_ids") if x.isdigit()]
        try:
            needed = int(values["needed"])
            if needed < 1:
                raise ValueError
        except ValueError:
            errors["needed"] = "How many people? At least 1."
        if not opening:
            if not values["role"]:
                errors["role"] = "Say what the job is, like “A2” or “Stagehand”."
            if values["call_time"]:
                try:
                    values["call_time"] = datetime.strptime(values["call_time"][:5], "%H:%M").strftime("%H:%M")
                except ValueError:
                    errors["call_time"] = "Enter a time like 4:00 PM."
            rate, rate_error = crew.money_input(values["pay_rate"])
            hours = None
            if values["hours"]:
                try:
                    hours = float(values["hours"])
                except ValueError:
                    errors["hours"] = "Enter hours as a number."
            if values["pay_type"] not in ("own", "flat", "hourly"):
                values["pay_type"] = "own"
            if values["pay_type"] != "own" and (rate is None or rate_error):
                errors["pay_rate"] = rate_error or "Enter the rate, or choose each person's own rate."
        if not picked:
            errors["crew_ids"] = "Tick at least one person to send the offer to."
        if not errors:
            if opening:
                crew.set_needed(opening_id, needed)
            else:
                opening_id = db.insert("crew_openings", {
                    "event_id": event_id, "skill": values["skill"] or None, "role": values["role"][:80],
                    "needed": needed, "call_time": values["call_time"] or None, "pay_type": values["pay_type"],
                    "pay_rate": rate if values["pay_type"] != "own" else None, "hours": hours,
                    "notes": values["notes"][:1000] or None, "created_at": util.now_iso(),
                })
            sent = crew.send_offers(opening_id, picked)
            _report(sent, values["email"] == "1")
            return _crew_tab(event_id)
    if opening and request.method == "GET":
        values["skill"] = opening["skill"] or ""
        values["needed"] = str(opening["needed"])
    return render_template(
        "events/offer.html", event=event, opening=opening, values=values, errors=errors, picked=picked,
        filled=crew.taken(opening["id"]) if opening else 0, days=util.event_days(event),
        skills=crew.skill_list(), candidates=_candidates(event, opening), can_email=mailer.configured(),
        pay_text=crew.pay_text,
    )


def _report(offer_ids, email):
    """Flash what happened after offers were created."""
    if not offer_ids:
        flash("Everyone you picked already has this offer or a spot.", "warn")
        return
    count = f"{len(offer_ids)} {'person' if len(offer_ids) == 1 else 'people'}"
    if not (email and mailer.configured()):
        flash(f"Offer ready for {count}. Send it to each person with the Email or Text buttons below.", "ok")
        return
    sent, missing, error = crew.email_offers(offer_ids)
    if sent:
        flash(f"Offer emailed to {', '.join(sent)}.", "ok")
    if missing:
        flash(f"No email address for {', '.join(missing)}: use the Text button below.", "warn")
    if error:
        flash(f"Some offers weren't emailed. {error}", "bad")


def _offer(event_id, offer_id):
    offer = crew.offer_details(offer_id)
    if offer is None or offer["event_id"] != event_id:
        abort(404)
    return offer


@bp.route("/events/<int:event_id>/crew/offers/<int:offer_id>/email", methods=["POST"])
def email(event_id, offer_id):
    _offer(event_id, offer_id)
    _report([offer_id], True)
    return _crew_tab(event_id)


@bp.route("/events/<int:event_id>/crew/offers/<int:offer_id>/withdraw", methods=["POST"])
def withdraw(event_id, offer_id):
    offer = _offer(event_id, offer_id)
    if offer["status"] == "sent":
        db.update("crew_offers", offer_id, {"status": "withdrawn", "responded_at": util.now_iso()})
        flash(f"Withdrew the offer to {offer['name']}.", "ok")
    return _crew_tab(event_id)


@bp.route("/events/<int:event_id>/crew/openings/<int:opening_id>/cancel", methods=["POST"])
def cancel(event_id, opening_id):
    opening = db.query("SELECT * FROM crew_openings WHERE id = ? AND event_id = ?", (opening_id, event_id), one=True)
    if opening is None:
        abort(404)
    db.update("crew_openings", opening_id, {"status": "cancelled"})
    db.execute("UPDATE crew_offers SET status = 'withdrawn', responded_at = ? WHERE opening_id = ? AND status = 'sent'",
               (util.now_iso(), opening_id))
    flash(f"Closed the {opening['role']} opening. Anyone who already accepted stays on the crew.", "ok")
    return _crew_tab(event_id)


@bp.route("/events/<int:event_id>/crew/message", methods=["POST"])
def message(event_id):
    """Email an update to everyone confirmed on the event, with their job sheet link."""
    event = get_event(event_id)
    text = request.form.get("message", "").strip()
    if not text:
        flash("Write the update first.", "bad")
        return _crew_tab(event_id, "crew-message")
    sent, missing = [], []
    for a in db.query("SELECT a.*, c.name, c.email FROM event_crew a JOIN crew c ON c.id = a.crew_id "
                      "WHERE a.event_id = ? AND a.confirmed = 1 ORDER BY c.name", (event_id,)):
        if not a["email"]:
            missing.append(a["name"])
            continue
        link = url_for("public.worksheet", reference=event["reference_number"], key=a["worksheet_key"], _external=True)
        subject, body = crew.update_message(event, a["name"], text[:4000], link)
        try:
            mailer.send(a["email"], subject, body)
        except mailer.MailError as exc:
            flash(f"The update didn't go out to everyone. {exc}", "bad")
            break
        sent.append(a["name"])
    if sent:
        flash(f"Update emailed to {', '.join(sent)}.", "ok")
    if missing:
        flash(f"No email address for {', '.join(missing)}.", "warn")
    if not sent and not missing:
        flash("Nobody is confirmed on this event yet.", "warn")
    return _crew_tab(event_id, "crew-message")


# --- A crew member's availability and link (from their page in the office) ------------------

def _member(crew_id):
    member = db.query("SELECT * FROM crew WHERE id = ?", (crew_id,), one=True)
    if member is None:
        abort(404)
    return member


@bp.route("/crew/<int:crew_id>/unavailable", methods=["POST"])
def add_unavailable(crew_id):
    _member(crew_id)
    error = crew.add_unavailable(crew_id, request.form.get("start_date"), request.form.get("end_date"),
                                 request.form.get("note"), "office")
    flash(error or "Saved. They won't show as free on those days.", "bad" if error else "ok")
    return redirect(url_for("people.detail", kind="crew", row_id=crew_id) + "#availability")


@bp.route("/crew/<int:crew_id>/unavailable/<int:row_id>/delete", methods=["POST"])
def delete_unavailable(crew_id, row_id):
    db.execute("DELETE FROM crew_unavailable WHERE id = ? AND crew_id = ?", (row_id, crew_id))
    return redirect(url_for("people.detail", kind="crew", row_id=crew_id) + "#availability")


@bp.route("/crew/<int:crew_id>/portal-link", methods=["POST"])
def new_link(crew_id):
    member = _member(crew_id)
    crew.new_portal_key(crew_id)
    flash(f"{member['name']} has a new crew page link. The old one no longer works, so send them the new one.", "ok")
    return redirect(url_for("people.detail", kind="crew", row_id=crew_id) + "#portal")


# --- Settings → Crew -----------------------------------------------------------------

@bp.route("/settings/crew", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        if request.form.get("action") == "test":
            to = request.form.get("to", "").strip()
            try:
                mailer.send(to, "Test email from your operations platform",
                            "It works: offers and crew updates can be emailed from the platform.")
            except mailer.MailError as exc:
                flash(str(exc), "bad")
            else:
                flash(f"Test email sent to {to}. Check that it arrived (and isn't in spam).", "ok")
        else:
            skills = []
            for line in request.form.get("skills", "").splitlines():
                line = line.strip()[:80]
                if line and line.casefold() not in {s.casefold() for s in skills}:
                    skills.append(line)
            db.set_setting("crew_skills", "\n".join(skills))
            flash("Crew skills saved.", "ok")
        return redirect(url_for("offers.settings"))
    counts = {r["skill"]: r["n"] for r in db.query("SELECT skill, COUNT(*) AS n FROM crew_skills GROUP BY skill")}
    return render_template("settings/crew.html", skills=crew.skill_list(), counts=counts,
                           email_ready=mailer.configured(), mail=mailer.config(), sender=mailer.sender(),
                           me=db.get_setting("company_email") or "")
