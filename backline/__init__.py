"""Chicago Sound and Backline: scheduling, inventory, crew worksheets,
contracts and invoicing for an audio and backline rental company."""

import os
import secrets

from flask import Flask

from . import db, util


def _load_secret_key(instance_path):
    env_key = os.environ.get("BACKLINE_SECRET_KEY")
    if env_key:
        return env_key
    path = os.path.join(instance_path, "secret_key")
    if os.path.exists(path):
        with open(path) as fh:
            return fh.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as fh:
        fh.write(key)
    os.chmod(path, 0o600)
    return key


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        DATABASE=os.environ.get(
            "BACKLINE_DATABASE", os.path.join(app.instance_path, "backline.sqlite3")
        ),
        CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _load_secret_key(app.instance_path)

    if os.environ.get("BACKLINE_BEHIND_PROXY"):
        # Trust one reverse proxy's X-Forwarded-* headers (client IP, https).
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        app.config["SESSION_COOKIE_SECURE"] = True

    db.init_app(app)
    util.init_app(app)

    from . import auth
    from .views import (
        contracts,
        crewpay,
        dashboard,
        events,
        inventory,
        invoices,
        people,
        public,
        settings,
    )

    auth.init_app(app)
    for module in (dashboard, events, inventory, people, contracts, invoices, crewpay, public, settings):
        app.register_blueprint(module.bp)

    with app.app_context():
        db.init_db()

    return app
