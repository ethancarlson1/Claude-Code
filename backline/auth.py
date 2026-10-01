import hmac
import os
import secrets
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, demo, util

bp = Blueprint("auth", __name__)

# Sign-in lockout: this many wrong passwords within LOCK_MINUTES, for one
# username from one network (or for any usernames from one network).
LOCK_AFTER = 5
LOCK_AFTER_NETWORK = 20
LOCK_MINUTES = 15
# Endpoints that accept bigger uploads than MAX_CONTENT_LENGTH (restoring a backup).
BIG_UPLOADS = {"backups.restore": int(os.environ.get("BACKLINE_MAX_RESTORE_MB", "500")) * 1024 * 1024}

# Endpoints reachable without logging in. Public pages are protected by
# unguessable per-record keys instead.
PUBLIC_BLUEPRINTS = {"auth", "public", "intake"}  # intake: the public event request form


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def _check_csrf():
    if not current_app.config.get("CSRF_ENABLED", True):
        return
    sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Form expired or invalid. Go back, refresh the page and try again.")


def _gate():
    if request.endpoint in BIG_UPLOADS:
        request.max_content_length = BIG_UPLOADS[request.endpoint]  # before the form is read
    if request.method == "POST":
        _check_csrf()
    if request.endpoint is None or request.endpoint == "static":
        return None
    user_id = session.get("user_id")
    g.user = db.query("SELECT id, username FROM users WHERE id = ?", (user_id,), one=True) if user_id else None
    if request.blueprint in PUBLIC_BLUEPRINTS:
        return None
    if g.user is None:
        if db.scalar("SELECT COUNT(*) FROM users") == 0:
            return redirect(url_for("auth.setup"))
        return redirect(url_for("auth.login", next=request.full_path))
    if request.method == "POST" and request.endpoint in demo.BLOCKED and demo.enabled():
        flash(demo.BLOCKED_MESSAGE, "warn")
        back = request.referrer or ""
        return redirect(back if back.startswith(request.host_url) else url_for("dashboard.index"))
    return None


def setup_code():
    """On a public server, the first account needs a code only the owner can see
    (set as BACKLINE_SETUP_CODE), so a stranger can't create it first."""
    return os.environ.get("BACKLINE_SETUP_CODE", "").strip()


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if db.scalar("SELECT COUNT(*) FROM users") > 0:
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        company = request.form.get("company_name", "").strip()
        code = setup_code()
        if code and not hmac.compare_digest(request.form.get("setup_code", "").strip(), code):
            error = ("That setup code doesn't match. Copy BACKLINE_SETUP_CODE from your Render service's "
                     "Environment page.")
        elif not username or len(password) < 8:
            error = "Choose a username and a password of at least 8 characters."
        else:
            user_id = db.insert(
                "users",
                {"username": username, "password_hash": generate_password_hash(password)},
            )
            if company:
                db.set_setting("company_name", company)
            session.clear()
            session["user_id"] = user_id
            flash("Welcome! Your account is ready.", "ok")
            return redirect(url_for("dashboard.index"))
    return render_template("auth/setup.html", error=error, needs_code=bool(setup_code()))


def _locked_out(username, ip):
    since = (datetime.now() - timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
    same_user = db.scalar("SELECT COUNT(*) FROM login_failures WHERE ip IS ? AND lower(username) = lower(?) AND at >= ?",
                          (ip, username, since))
    same_network = db.scalar("SELECT COUNT(*) FROM login_failures WHERE ip IS ? AND at >= ?", (ip, since))
    return same_user >= LOCK_AFTER or same_network >= LOCK_AFTER_NETWORK


def _record_failure(username, ip):
    db.insert("login_failures", {"username": username[:100], "ip": ip, "at": util.now_iso()})
    old = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    db.execute("DELETE FROM login_failures WHERE at < ?", (old,))


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        ip = request.remote_addr
        if _locked_out(username, ip):
            error = f"Too many wrong passwords. Wait {LOCK_MINUTES} minutes, then try again."
            return render_template("auth/login.html", error=error), 429
        user = db.query("SELECT * FROM users WHERE username = ?", (username,), one=True)
        if user is None or not check_password_hash(user["password_hash"], password):
            _record_failure(username, ip)
            error = "Incorrect username or password."
        else:
            db.execute("DELETE FROM login_failures WHERE ip IS ? AND lower(username) = lower(?)", (ip, username))
            session.clear()
            session["user_id"] = user["id"]
            target = request.args.get("next", "")
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("dashboard.index")
            return redirect(target)
    return render_template("auth/login.html", error=error)


@bp.route("/demo/enter", methods=["POST"])
def demo_enter():
    """Demo mode: one click to look around, no account needed."""
    if not demo.enabled():
        abort(404)
    demo.prepare()
    session.clear()
    session["user_id"] = demo.user_id()
    return redirect(url_for("dashboard.index"))


@bp.route("/demo/reset", methods=["POST"])
def demo_reset():
    if not demo.enabled():
        abort(404)
    if g.user is None:
        return redirect(url_for("auth.login"))
    demo.reset()
    session.clear()
    session["user_id"] = demo.user_id()
    flash("The demo is back to its starting point.", "ok")
    return redirect(url_for("dashboard.index"))


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def init_app(app):
    app.before_request(_gate)
    app.register_blueprint(bp)
    # A global (not a context processor) so imported macros can use it too.
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.context_processor
    def inject_globals():
        return {
            "company_name": db.get_setting("company_name"),
            "current_user": g.get("user"),
            "logo_url": url_for("public.logo", v=db.get_setting("logo_file") or "default"),
            "new_requests": db.scalar("SELECT COUNT(*) FROM client_requests WHERE status = 'new'") if g.get("user") else 0,
            "demo": demo.enabled(),
        }
