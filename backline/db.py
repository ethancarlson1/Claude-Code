import sqlite3

import click
from flask import current_app, g

DEFAULT_CONTRACT_TEMPLATE = """\
Agreement {{contract_number}} for event {{reference_number}}

This agreement is made between {{company_name}} ("Provider") and {{client_name}} ("Client") for audio and backline services at the event described below.

EVENT
  Event: {{event_title}}
  Date: {{event_date}}
  Venue: {{venue_name}}, {{venue_address}}
  Load-in: {{load_in_time}}    Show: {{start_time}} - {{end_time}}    Load-out: {{load_out_time}}

EQUIPMENT & SERVICES
{{gear_list}}

FEES & PAYMENT
  Total fee: {{total}}
  Deposit of {{deposit}} is due by {{deposit_due_date}} to reserve the date. The date is not held until the deposit is received.
  The remaining balance of {{balance}} is due by {{balance_due_date}}.

TERMS
  1. Client will provide safe, dry, level staging and adequate grounded power as described in the event advance.
  2. Client is responsible for loss of or damage to equipment caused by Client, performers, guests or venue staff, at replacement value.
  3. Weather: outdoor events require overhead cover for all equipment. Provider may halt service if conditions are unsafe for crew or equipment.
  4. Cancellation: deposits are non-refundable within 30 days of the event date.
  5. Changes to the equipment list after signing may change the total fee.

By signing below, Client agrees to the terms of this agreement.
"""

DEFAULT_SETTINGS = {
    "company_name": "Your Audio & Backline Co.",
    "company_address": "",
    "company_phone": "",
    "company_email": "",
    "default_tax_rate": "0",
    "deposit_percent": "50",
    "invoice_prefix": "INV-",
    "contract_prefix": "CT-",
    "invoice_terms": "Payment due within 15 days. Late balances are subject to a 1.5% monthly fee.",
    "contract_template": DEFAULT_CONTRACT_TEMPLATE,
}

DEFAULT_CHECKLISTS = [
    (
        "Advance & Prep",
        "Everything to confirm and prepare before the show date.",
        [
            ("Advance", "Confirm date, times and scope with client"),
            ("Advance", "Receive stage plot and input list"),
            ("Advance", "Confirm backline rider with artist / band leader"),
            ("Advance", "Confirm venue power (circuits, amperage, distance to stage)"),
            ("Advance", "Confirm load-in access, dock and parking"),
            ("Advance", "Contract signed"),
            ("Advance", "Deposit received"),
            ("Prep", "Build gear list and resolve availability conflicts"),
            ("Prep", "Book sub-rentals for anything not in stock"),
            ("Prep", "Test consoles, amps and speakers going out"),
            ("Prep", "Charge wireless packs and stock batteries"),
            ("Prep", "Prep cable trunk, DI box and stand counts"),
            ("Prep", "Send worksheets to crew and confirm call times"),
        ],
    ),
    (
        "Show Day",
        "Load-in, soundcheck and show.",
        [
            ("Load-in", "Crew arrives at call time"),
            ("Load-in", "Walk stage with venue / stage manager"),
            ("Load-in", "Run power and distro"),
            ("Load-in", "Place mains, subs and monitors"),
            ("Load-in", "Set backline per stage plot"),
            ("Soundcheck", "Line check all inputs"),
            ("Soundcheck", "Wireless frequency scan and coordination"),
            ("Soundcheck", "Soundcheck complete with artist"),
            ("Show", "Log show notes and any equipment issues"),
        ],
    ),
    (
        "Load-Out & Return",
        "Strike, return and close out.",
        [
            ("Load-out", "Strike stage and coil cables"),
            ("Load-out", "Count gear against gear list before the truck leaves"),
            ("Return", "Unload at shop and check in all gear"),
            ("Return", "Tag damaged items for maintenance"),
            ("Close-out", "Send final invoice"),
            ("Close-out", "Record crew hours for payroll"),
        ],
    ),
]


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


def init_db():
    conn = get_db()
    with current_app.open_resource("schema.sql") as fh:
        conn.executescript(fh.read().decode("utf8"))
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    if conn.execute("SELECT COUNT(*) FROM checklist_templates").fetchone()[0] == 0:
        for name, description, items in DEFAULT_CHECKLISTS:
            template_id = conn.execute(
                "INSERT INTO checklist_templates (name, description) VALUES (?, ?)",
                (name, description),
            ).lastrowid
            for sort, (section, text) in enumerate(items):
                conn.execute(
                    "INSERT INTO checklist_template_items (template_id, section, text, sort) "
                    "VALUES (?, ?, ?, ?)",
                    (template_id, section, text, sort),
                )
    conn.commit()


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
