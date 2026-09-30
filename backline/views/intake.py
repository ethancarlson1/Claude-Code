"""The public event request form. Anyone with the link can use it; there's
no sign-in. Requests land in the office's Requests inbox."""

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from .. import db, files, intake

bp = Blueprint("intake", __name__)


@bp.route("/request", methods=["GET", "POST"])
def form():
    if db.get_setting("request_form_enabled") != "1":
        return render_template("intake/closed.html", settings=db.get_settings())
    values, errors = {}, {}
    if request.method == "POST":
        if request.form.get("website"):  # a field people never see: only bots fill it in
            return redirect(url_for("intake.thanks"))
        values, errors = intake.parse(request.form)
        if not errors and intake.too_many(request.remote_addr):
            errors["_form"] = ("We've received several requests from your network in the last hour. "
                               "Please call or email us instead.")
        if not errors:
            request_id, skipped = intake.save(values, request.files.getlist("files"), request.remote_addr)
            session["request_sent"] = {"id": request_id, "name": values["name"], "skipped": skipped}
            return redirect(url_for("intake.thanks"))
    return render_template(
        "intake/form.html", sections=intake.SECTIONS, values=values, errors=errors, fresh=request.method == "GET",
        accept=",".join("." + e for e in sorted(files.ALLOWED_EXTENSIONS)),
        max_bytes=current_app.config["MAX_CONTENT_LENGTH"], max_files=intake.MAX_FILES,
    )


@bp.route("/request/thanks")
def thanks():
    return render_template("intake/thanks.html", sent=session.pop("request_sent", None), settings=db.get_settings())
