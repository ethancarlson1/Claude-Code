import sqlite3

import click
from flask import current_app, g

from .defaults import (  # noqa: F401  (re-exported for callers)
    _OLD_DEFAULT_COMPANY_NAME,
    COMPANY_NAME,
    DEFAULT_CHECKLISTS,
    DEFAULT_EVENT_TYPES,
    DEFAULT_SETTINGS,
    OLD_EVENT_TYPE_NAMES,
)

# Columns added after the first release. init_db adds any that an existing
# database is missing, so upgrading only needs a restart.
MIGRATIONS = {
    "events": [
        ("producer_id", "INTEGER REFERENCES crew(id) ON DELETE SET NULL"),
        ("honorees", "TEXT"),
        ("guest_count", "INTEGER"),
        ("venue_label", "TEXT"),
        ("venue2_id", "INTEGER REFERENCES venues(id) ON DELETE SET NULL"),
        ("venue2_label", "TEXT"),
        ("crew_meal", "TEXT"),
        ("run_of_show", "TEXT"),
        ("crew_notes", "TEXT"),
        ("service_type", "TEXT"),
        ("setting", "TEXT"),
        ("input_count", "INTEGER"),
        ("wireless_count", "INTEGER"),
        ("monitor_mixes", "INTEGER"),
        ("playback_feeds", "TEXT"),
    ],
    "crew": [("dietary", "TEXT"), ("w9_on_file", "INTEGER NOT NULL DEFAULT 0")],
    "event_crew": [
        ("actual_hours", "REAL"),
        ("final_amount", "REAL"),
        ("paid_on", "TEXT"),
        ("paid_amount", "REAL"),
        ("paid_method", "TEXT"),
        ("paid_reference", "TEXT"),
    ],
    "invoices": [
        ("contract_id", "INTEGER REFERENCES contracts(id) ON DELETE SET NULL"),
        ("kind", "TEXT"),
    ],
    "checklist_templates": [("crew_visible", "INTEGER NOT NULL DEFAULT 1")],
    "event_checklist_items": [("crew_visible", "INTEGER NOT NULL DEFAULT 1")],
}

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def scalar(sql, args=()):
    row = query(sql, args, one=True)
    return row[0] if row else None


def execute(sql, args=()):
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def insert(table, data):
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    return execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values()))


def update(table, row_id, data):
    if not data:
        return
    sets = ", ".join(f"{col} = ?" for col in data)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), row_id))


def get_setting(key):
    row = query("SELECT value FROM settings WHERE key = ?", (key,), one=True)
    if row is None:
        return DEFAULT_SETTINGS.get(key)
    return row["value"]


def get_settings():
    values = dict(DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        values[row["key"]] = row["value"]
    return values


def set_setting(key, value):
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _migrate(conn):
    added = set()
    for table, columns in MIGRATIONS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                added.add((table, name))
    if ("checklist_templates", "crew_visible") in added:
        office_only = [name for name, _desc, crew_visible, _items in DEFAULT_CHECKLISTS if not crew_visible]
        conn.executemany("UPDATE checklist_templates SET crew_visible = 0 WHERE name = ?", [(n,) for n in office_only])
    if ("event_checklist_items", "crew_visible") in added:
        # Items already copied from an office-only template stay off worksheets.
        conn.execute(
            """UPDATE event_checklist_items SET crew_visible = 0 WHERE text IN (
                 SELECT i.text FROM checklist_template_items i
                 JOIN checklist_templates t ON t.id = i.template_id WHERE t.crew_visible = 0)"""
        )
    conn.execute(
        "UPDATE settings SET value = ? WHERE key = 'company_name' AND value = ?",
        (COMPANY_NAME, _OLD_DEFAULT_COMPANY_NAME),
    )


def init_db():
    conn = get_db()
    with current_app.open_resource("schema.sql") as fh:
        conn.executescript(fh.read().decode("utf8"))
    _migrate(conn)
    _seed_defaults(conn)
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()


# Bump when DEFAULT_CHECKLISTS / DEFAULT_EVENT_TYPES gain entries that existing
# databases should receive. Each version is applied once, so anything a user
# deletes afterwards stays deleted.
DEFAULTS_VERSION = 2


def _seed_defaults(conn):
    row = conn.execute("SELECT value FROM settings WHERE key = 'defaults_version'").fetchone()
    if row is None:  # new database (0) or one from before versioning (1)
        version = 1 if conn.execute("SELECT COUNT(*) FROM checklist_templates").fetchone()[0] else 0
    else:
        version = int(row[0])
    if version >= DEFAULTS_VERSION:
        return
    existing = {r[0] for r in conn.execute("SELECT name FROM checklist_templates")}
    for name, description, crew_visible, items in DEFAULT_CHECKLISTS:
        if name in existing:
            continue
        template_id = conn.execute(
            "INSERT INTO checklist_templates (name, description, crew_visible) VALUES (?, ?, ?)",
            (name, description, int(crew_visible)),
        ).lastrowid
        for sort, (section, text) in enumerate(items):
            conn.execute(
                "INSERT INTO checklist_template_items (template_id, section, text, sort) VALUES (?, ?, ?, ?)",
                (template_id, section, text, sort),
            )
    template_ids = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM checklist_templates")}
    existing = {r[0] for r in conn.execute("SELECT name FROM event_types")}
    for sort, t in enumerate(DEFAULT_EVENT_TYPES):
        if t["name"] in existing:
            continue
        type_id = conn.execute(
            "INSERT INTO event_types (name, people_label, venue_label, venue2_label, run_of_show, sort) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (t["name"], t["people_label"], t["venue_label"], t["venue2_label"], t["run_of_show"], sort),
        ).lastrowid
        conn.executemany(
            "INSERT INTO event_type_checklists (event_type_id, template_id, sort) VALUES (?, ?, ?)",
            [(type_id, template_ids[c], n) for n, c in enumerate(t["checklists"]) if c in template_ids],
        )
    for old, new in OLD_EVENT_TYPE_NAMES.items():
        conn.execute("UPDATE events SET event_type = ? WHERE event_type = ?", (new, old))
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('defaults_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(DEFAULTS_VERSION),),
    )


@click.command("init-db")
def init_db_command():
    """Create tables (safe to run repeatedly)."""
    init_db()
    click.echo("Database ready.")


@click.command("create-user")
@click.argument("username")
@click.password_option()
def create_user_command(username, password):
    """Create a login user."""
    from werkzeug.security import generate_password_hash

    insert("users", {"username": username, "password_hash": generate_password_hash(password)})
    click.echo(f"Created user {username}.")


@click.command("seed")
def seed_command():
    """Load demo data (inventory, crew, clients, venues, events)."""
    from .seed import seed

    seed()
    click.echo("Demo data loaded.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_user_command)
    app.cli.add_command(seed_command)
