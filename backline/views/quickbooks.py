import hmac
import os
import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .. import db
from .. import quickbooks as qb

bp = Blueprint("quickbooks", __name__)

OPTION_FLAGS = [
    ("qbo_auto_push", "Send invoices to QuickBooks automatically when they're marked sent"),
    ("qbo_online_payments", "Let clients pay online by card or bank transfer (needs QuickBooks Payments)"),
    ("qbo_email_invoices", "Have QuickBooks email new invoices to the client too"),
    ("qbo_auto_check", "Check QuickBooks for new payments every 15 minutes while the platform is in use"),
]


def redirect_uri():
    return url_for("quickbooks.callback", _external=True)


def _back(default):
    """Return to the page the button was on (same site only)."""
    target = request.referrer or ""
    return redirect(target if target.startswith(request.host_url) else default)


@bp.route("/settings/quickbooks", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "keys":
            env = request.form.get("environment")
            env = env if env in qb.API_BASE else "sandbox"
            switched = env != qb.environment()
            db.set_setting("qbo_environment", env)
            if "client_id" in request.form:
                db.set_setting("qbo_client_id", request.form["client_id"].strip())
            secret = request.form.get("client_secret", "").strip()
            if secret:
                db.set_setting("qbo_client_secret", secret)
            if switched and qb.is_connected():
                qb.disconnect()
                flash("Switched environments, so QuickBooks was disconnected. Connect again to continue.", "warn")
            flash("QuickBooks app keys saved.", "ok")
        elif action == "options":
            try:
                items = dict(qb.item_choices())
                taxes = dict(qb.tax_code_choices())
            except qb.QuickBooksError as exc:
                flash(f"Couldn't load your QuickBooks lists, so nothing was saved: {exc}", "bad")
                return redirect(url_for("quickbooks.settings"))
            for key, choices in (("qbo_item_id", items), ("qbo_deposit_item_id", items), ("qbo_tax_code_id", taxes)):
                value = request.form.get(key, "")
                value = value if value in choices else ""
                db.set_setting(key, value)
                db.set_setting(key.replace("_id", "_name"), choices.get(value, ""))
            for key, _label in OPTION_FLAGS:
                db.set_setting(key, "1" if request.form.get(key) else "0")
            if not db.get_setting("qbo_item_id"):
                flash("Options saved. Choose a product/service for invoice lines before sending invoices.", "warn")
            else:
                flash("QuickBooks options saved.", "ok")
        return redirect(url_for("quickbooks.settings"))

    connected = qb.is_connected()
    items, taxes, list_error = [], [], None
    if connected:
        try:
            items, taxes = qb.item_choices(), qb.tax_code_choices()
        except qb.QuickBooksError as exc:
            list_error = str(exc)
            connected = qb.is_connected()  # a failed sign-in refresh disconnects
    client_id, secret = qb.credentials()
    return render_template(
        "settings/quickbooks.html", connected=connected, settings=db.get_settings(), items=items, taxes=taxes,
        list_error=list_error, client_id=client_id, has_secret=bool(secret), redirect_uri=redirect_uri(),
        env_keys=bool(os.environ.get("BACKLINE_QBO_CLIENT_ID") or os.environ.get("BACKLINE_QBO_CLIENT_SECRET")),
        environments=qb.ENVIRONMENTS, environment=qb.environment(), flags=OPTION_FLAGS,
        linked=db.scalar("SELECT COUNT(*) FROM invoices WHERE qbo_id IS NOT NULL"),
    )


@bp.route("/settings/quickbooks/connect", methods=["POST"])
def connect():
    client_id, secret = qb.credentials()
    if not client_id or not secret:
        flash("Add your Intuit app's Client ID and Client Secret first.", "bad")
        return redirect(url_for("quickbooks.settings"))
    state = secrets.token_urlsafe(24)
    session["qbo_state"] = state
    return redirect(qb.authorize_url(redirect_uri(), state))


@bp.route("/settings/quickbooks/callback")
def callback():
    """Intuit sends people back here after they approve (or cancel) the connection."""
    expected = session.pop("qbo_state", None)
    if request.args.get("error"):
        flash("The QuickBooks connection was cancelled.", "warn")
        return redirect(url_for("quickbooks.settings"))
    state = request.args.get("state", "")
    if not expected or not hmac.compare_digest(state, expected):
        flash("That QuickBooks sign-in didn't match this browser session. Click Connect again, and make sure you "
              "open the platform at the same address as the Redirect URI below.", "bad")
        return redirect(url_for("quickbooks.settings"))
    code, realm = request.args.get("code", ""), request.args.get("realmId", "")
    if not code or not realm:
        flash("QuickBooks didn't send back a company to connect. Try again.", "bad")
        return redirect(url_for("quickbooks.settings"))
    try:
        name, unlinked = qb.finish_connect(code, realm, redirect_uri())
    except qb.QuickBooksError as exc:
        flash(f"Couldn't connect to QuickBooks: {exc}", "bad")
    else:
        flash(f"Connected to {name}.", "ok")
        if unlinked:
            flash("This is a different QuickBooks company from before, so links to the old one were cleared. "
                  "Choose your products/services again below.", "warn")
    return redirect(url_for("quickbooks.settings"))


@bp.route("/settings/quickbooks/disconnect", methods=["POST"])
def disconnect():
    qb.disconnect()
    flash("Disconnected from QuickBooks. Nothing was deleted in QuickBooks or here.", "ok")
    return redirect(url_for("quickbooks.settings"))


@bp.route("/invoices/<int:invoice_id>/quickbooks", methods=["POST"])
def push(invoice_id):
    invoice = db.query("SELECT status, qbo_id FROM invoices WHERE id = ?", (invoice_id,), one=True)
    if invoice is None:
        return redirect(url_for("invoices.index"))
    if invoice["status"] == "void" and invoice["qbo_id"]:  # a void that didn't reach QuickBooks
        try:
            qb.void_invoice(invoice_id)
        except qb.QuickBooksError as exc:
            flash(f"QuickBooks wasn't updated: {exc}", "bad")
        else:
            flash("Voided in QuickBooks too.", "ok")
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))
    try:
        created = qb.push_invoice(invoice_id)
    except qb.QuickBooksError as exc:
        flash(f"QuickBooks wasn't updated: {exc}", "bad")
    else:
        flash("Sent to QuickBooks." if created else "QuickBooks is up to date.", "ok")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))


@bp.route("/quickbooks/check", methods=["POST"])
def check():
    try:
        summary = qb.check_payments()
    except qb.QuickBooksError as exc:
        flash(f"Couldn't check QuickBooks: {exc}", "bad")
    else:
        db.set_setting("qbo_last_error", "")
        flash(qb.summary_message(summary), "ok")
    return _back(url_for("invoices.index"))
