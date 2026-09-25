import hmac
import secrets

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

from . import db

bp = Blueprint("auth", __name__)

# Endpoints reachable without logging in. Public pages are protected by
# unguessable per-record keys instead.
PUBLIC_BLUEPRINTS = {"auth", "public"}


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
    return None


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if db.scalar("SELECT COUNT(*) FROM users") > 0:
        return redirect(url_for("auth.login"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        company = request.form.get("company_name", "").strip()
        if not username or len(password) < 8:
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
    return render_template("auth/setup.html", error=error)


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.query("SELECT * FROM users WHERE username = ?", (username,), one=True)
        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Incorrect username or password."
        else:
            session.clear()
            session["user_id"] = user["id"]
            target = request.args.get("next", "")
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("dashboard.index")
            return redirect(target)
    return render_template("auth/login.html", error=error)


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
        }
