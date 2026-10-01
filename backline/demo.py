"""Demo mode (BACKLINE_DEMO=1): a public showcase filled with made-up data.

Visitors get in with one click, can try everything that matters for a tour,
and can't change anything that would lock others out, reach outside
services or change the branding. Start over puts the sample data back. On
a host without a persistent disk (such as Render's free plan) the demo also
resets itself whenever the server restarts."""

import os
import secrets
import shutil

from flask import current_app
from werkzeug.security import generate_password_hash

from . import db, util

USERNAME = "demo"
UPLOAD_LIMIT_MB = "5"  # demo visitors don't need big uploads

# POSTs to these are turned off in the demo.
BLOCKED = {
    "settings.index",       # company details and the logo
    "settings.users",       # adding users, passwords
    "quickbooks.settings", "quickbooks.connect", "quickbooks.disconnect", "quickbooks.push", "quickbooks.check",
    "backups.restore",
    "requests.toggle_form",
}
BLOCKED_MESSAGE = ("That's turned off in the demo, so nobody can change sign-ins, branding or outside "
                   "connections. Everything else works.")


def enabled():
    return os.environ.get("BACKLINE_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


def prepare():
    """Fill an empty demo with the sample data and the demo account."""
    if db.scalar("SELECT COUNT(*) FROM users"):
        return
    if not db.scalar("SELECT COUNT(*) FROM events"):
        from .seed import seed

        seed()
    # Nobody types this password: visitors come in through "Explore the demo".
    db.insert("users", {"username": USERNAME, "password_hash": generate_password_hash(secrets.token_urlsafe(24))})
    db.set_setting("demo_started_at", util.now_iso())


def user_id():
    return db.scalar("SELECT id FROM users WHERE username = ?", (USERNAME,))


def reset():
    """Throw away everything visitors changed and put the sample data back."""
    db.close_db()
    path = current_app.config["DATABASE"]
    for suffix in ("", "-journal", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
    shutil.rmtree(current_app.config["UPLOAD_FOLDER"], ignore_errors=True)
    db.init_db()
    prepare()
