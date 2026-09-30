import os
import re

from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for

from .. import backup, db, util

bp = Blueprint("backups", __name__)


@bp.route("/settings/backup")
def index():
    return render_template("settings/backup.html", empty=backup.is_empty(),
                           on_server=bool(os.environ.get("BACKLINE_BEHIND_PROXY")))


@bp.route("/settings/backup/download")
def download():
    path = backup.make_backup()
    slug = re.sub(r"[^a-z0-9]+", "-", (db.get_setting("company_name") or "platform").lower()).strip("-")
    response = send_file(path, mimetype="application/zip", as_attachment=True, max_age=0,
                         download_name=f"{slug}-backup-{util.today().isoformat()}.zip")
    response.call_on_close(lambda: os.path.exists(path) and os.remove(path))
    return response


@bp.route("/settings/backup/restore", methods=["POST"])
def restore():
    upload = request.files.get("backup")
    if not upload or not upload.filename:
        flash("Choose the backup .zip to restore.", "bad")
        return redirect(url_for("backups.index"))
    if not request.form.get("confirm"):
        flash("Tick the box to confirm you want to replace this platform's data.", "bad")
        return redirect(url_for("backups.index"))
    try:
        count = backup.restore(upload)
    except ValueError as exc:
        flash(str(exc), "bad")
        return redirect(url_for("backups.index"))
    session.clear()  # the accounts now come from the backup
    flash(f"Backup restored, with {count} uploaded file{'s' if count != 1 else ''}. Sign in with a username and "
          "password from the copy you backed up. If QuickBooks was connected there, connect it again here.", "ok")
    return redirect(url_for("auth.login"))
