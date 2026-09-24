# Backline Ops

A web app for an audio and backline rental company. It keeps the schedule, the gear inventory, each event's audio and backline needs (with pull/load/return checklists), crew worksheets, contracts and invoices in one place.

It is a small Flask + SQLite app: one Python dependency, one database file, no build step.

## Features

**Scheduling**
- Events with a readable reference number (`2026-11-07-Lange-Daniel-TJ1R`), status (inquiry → hold → confirmed → completed / cancelled), client, venue, performers and a full day-of timeline (load-in, soundcheck, doors, show, end, load-out). Multi-day events are supported.
- Month calendar, a searchable event list, and a dashboard that flags what needs attention in the next 14 days: unconfirmed crew, missing gear lists, gear not pulled, open checklists, gear conflicts, gear not returned, unsigned contracts and overdue invoices.
- Duplicate an event to a new date. The gear list and checklist are copied; crew, contracts and invoices are not.

**Crew worksheets** (modeled on a band's per-musician worksheet)
- Assign crew with a role, call time and pay (flat or hourly). If you leave the rate blank, it defaults from the crew member's profile.
- Each assignment gets a private worksheet link: `/worksheet/<event-reference>/<key>`. The page shows the schedule, venue and load-in details, production notes, the crew list, the gear list and the checklist. It shows only that person's pay, and they can confirm or decline from the page.
- A full admin worksheet with everyone's pay doubles as a printable pull sheet.

**Inventory and gear**
- Items with category, make/model, serial and asset tag, quantity owned, condition, status (active / maintenance / retired), location, rental rate and replacement value. CSV import and export are included.
- Each event has an **Audio & backline** list. Add items from inventory, or add free-text needs and sub-rentals for anything you don't stock.
- **Availability and conflicts:** Hold and Confirmed events reserve gear. If overlapping events need more units than you own, or an item is in maintenance, the shortfall is flagged and the other bookings are named.
- **Warehouse checklist:** every gear line has Pulled / Loaded / Returned checkboxes, plus return and damage notes. "Mark all" buttons are included, and items still out after a show appear on the dashboard.
- Each item's page shows its upcoming bookings, history and damage notes.

**Checklists**
- Reusable checklist templates with sections. Three defaults ship with the app: Advance & Prep, Show Day, and Load-Out & Return. You can edit them or add your own under Settings.
- Apply templates when creating an event or later. Items can be added one at a time. Ticking an item records who did it and when.

**Contracts**
- Generated from an editable template with merge fields (client, venue, times, gear list, total, deposit, due dates). The total is pre-filled from the event's gear rental value, and the deposit uses your default percentage.
- Workflow: draft → sent → signed (or void). Sent contracts get a client link where the client types their name and ticks "I agree". The app records the name, time and IP address. Signed contracts are locked.

**Invoices**
- Line items can be pre-filled from the event's priced gear list, with multi-day rates handled. Each line can be marked taxable or not. You can add a discount and a tax rate.
- Record payments. Status is derived automatically: draft, sent, partial, paid, overdue or void. The invoice list shows totals for outstanding, overdue and collected this month.
- Sent invoices get a client link. Contracts, invoices and worksheets all print cleanly and can be saved as PDF from the browser.

**Other**
- Login with multiple users, and CSRF protection on every form.
- "Email" buttons open your mail app with the link already written in. No mail server is needed.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

flask --app backline seed        # optional: load demo inventory, crew, events, contracts, invoices
flask --app backline run         # http://127.0.0.1:5000
```

On first visit you'll be asked to create the admin account and company name. Company details, tax rate, deposit %, number prefixes, invoice terms and the contract template are under **Settings**.

The demo data is dated relative to today. It includes a Twin Reverb conflict between a festival hold and a club gig, a wedding contract waiting for signature, an overdue invoice and a cymbal pack not yet returned, so every dashboard alert has something to show.

Other commands:

```bash
flask --app backline create-user <username>   # add a login from the shell
flask --app backline init-db                  # create tables (also runs automatically on startup)
```

## Running it for real

Crew and clients open links from their phones, so host it somewhere reachable over **HTTPS**. For example, a small VPS behind Caddy or nginx, or any platform that runs a Python web app:

```bash
pip install waitress
BACKLINE_SECRET_KEY=... BACKLINE_DATABASE=/srv/backline/backline.sqlite3 BACKLINE_BEHIND_PROXY=1 \
  waitress-serve --port 8000 --call backline:create_app
```

| Variable | Purpose |
| --- | --- |
| `BACKLINE_SECRET_KEY` | Session signing key. If unset, one is generated and saved in `instance/secret_key`. |
| `BACKLINE_DATABASE` | Path to the SQLite file. Default: `instance/backline.sqlite3`. |
| `BACKLINE_BEHIND_PROXY` | Set when running behind a reverse proxy. Trusts `X-Forwarded-*` headers and marks cookies Secure. |

**Backups:** all data lives in the one SQLite file. Back it up on a schedule, for example with `sqlite3 backline.sqlite3 ".backup backup.sqlite3"`.

## Tests

```bash
pip install pytest
pytest
```

The suite covers login, setup and CSRF; reference numbers; gear conflict rules (overlapping dates, inquiries and cancellations not reserving, maintenance items); checklist and gear toggles; crew defaults; event duplication; invoice math (pre-tax discount across taxable and non-taxable lines), status derivation and numbering; contract merge fields and the signing flow; worksheet privacy; CSV import; and a render check of every page against the demo data.

## Project layout

```
backline/
  __init__.py        app factory
  schema.sql         tables
  db.py              database helpers, default settings/checklists/contract template, CLI commands
  auth.py            login, first-run setup, CSRF
  forms.py           declarative form fields + validation
  services.py        gear availability, totals, invoice math, contract rendering
  seed.py            demo data
  views/             dashboard, events (crew/gear/checklists/calendar), inventory,
                     people (clients/venues/crew), contracts, invoices, settings,
                     public (worksheets, contract signing, client invoices)
  templates/, static/
tests/
```

## Known limits / ideas for next steps

- Email goes through `mailto:` links. Sending automatically (SMTP, Postmark, etc.) and reminders for unsigned contracts or overdue invoices would be natural additions.
- There are no online payments. A Stripe payment link on the client invoice page would be a small addition.
- The e-signature is a typed name plus an agreement checkbox, with a time and IP audit record. Check that this meets your jurisdiction's requirements. The default contract text is a starting point, not legal advice.
- Possible additions: an iCal feed per crew member, stage plot and input list uploads, gear "kits" (e.g. a standard drum package), and barcode scanning for check-in and check-out.
