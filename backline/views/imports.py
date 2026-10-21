"""Import with AI: upload riders, tech packs, emails and the like, and let
Claude fill in an event request for the office to check (see ai_import.py)."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import ai_import, db, demo
from .requests import _event_options

bp = Blueprint("imports", __name__)


@bp.route("/requests/import", methods=["GET", "POST"])
def new():
    event_id = request.values.get("event", type=int)
    if event_id and not db.scalar("SELECT 1 FROM events WHERE id = ?", (event_id,)):
        event_id = None
    error, pasted = None, ""
    if request.method == "POST":
        pasted = request.form.get("pasted", "")
        uploads = [(f.filename, f.read()) for f in request.files.getlist("files") if f and f.filename]
        try:
            request_id, notes = ai_import.run(uploads, pasted, event_id, g.user["username"])
        except ai_import.Problem as exc:
            error = str(exc)
        else:
            flash("Read. Check what the AI found against the quotes, then add it to an event or create an inquiry.",
                  "ok")
            for note in notes:
                flash(note, "warn")
            return redirect(url_for("requests.detail", request_id=request_id))
    model = ai_import.current_model()
    return render_template(
        "requests/import.html", error=error, pasted=pasted, event_id=event_id, events=_event_options(chosen=event_id),
        ready=bool(ai_import.api_key()), model_name=ai_import.model_name(model), typical=ai_import.MODELS[model][4],
        accept=ai_import.ACCEPT, max_files=ai_import.MAX_FILES, max_bytes=ai_import.MAX_TOTAL_MB * 1024 * 1024,
        demo_example=db.scalar("SELECT id FROM client_requests WHERE source = 'import' ORDER BY id LIMIT 1")
        if demo.enabled() else None,
    )


@bp.route("/settings/ai", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        if request.form.get("action") == "check":
            ok, message = ai_import.check_connection(ai_import.current_model())
            flash(message, "ok" if ok else "bad")
        else:
            model = request.form.get("model")
            if model in ai_import.MODELS:
                db.set_setting("ai_model", model)
                flash(f"AI import will use {ai_import.model_name(model)}.", "ok")
        return redirect(url_for("imports.settings"))
    return render_template(
        "settings/ai.html", models=ai_import.MODELS, current=ai_import.current_model(), key_hint=ai_import.key_hint(),
        spending=ai_import.spending(), cost_text=ai_import.cost_text,
    )
