# Chicago Sound and Backline

The operations platform for Chicago Sound and Backline. It keeps the schedule, the gear inventory, each event's audio and backline needs (with pull/load/return checklists), crew worksheets, contracts and invoices in one place.

It is a small Flask + SQLite app: one Python dependency, one database file, no build step.

## Features

**Scheduling**
- Events with a readable reference number (`2026-10-10-Alvarez-Sofia-RBYC`) and a status (inquiry, hold, confirmed, completed or cancelled).
- Each event records the client, the couple or honorees, guest count and a **producer** (the crew's point person).
- Up to two locations per event, e.g. a ceremony and a reception.
- A day-of timeline (load-in, setup complete, doors, show, end, load-out) plus a free-form **run of show**. New events start from a run-of-show template.
- A month calendar, a searchable event list, and a dashboard that flags what needs attention in the next 14 days: unconfirmed crew, missing gear lists, gear not pulled, open checklists, gear conflicts, gear not returned, unsigned contracts and overdue invoices.
- "Add to calendar" (.ics) for the office and for each crew member.

**Crew worksheets**

These are modeled on the per-musician gig worksheet a band sends its players. Each crew assignment gets a private link, `/worksheet/<event-reference>/<key>`, laid out in the same sections:

| Section | What's in it |
| --- | --- |
| Basic info | Booking status, date and Add to iCal, event type, the producer with Call/Text/Email buttons, dress code, guest count, couple/client, terms of use, payment (their own pay only), and event timings ("You are on A1 / FOH…") |
| Location & venue | Each location with Open in Maps, venue manager contacts, day-of contact |
| Crew | Roster with role, call time, phone and dietary notes, plus the crew meal |
| Special requests | Crew-only notes. Clients never see these. |
| Schedule | Timings, the run of show, and load-in, parking and power notes from the event and the venue |
| Audio & backline | The gear list with Pulled / Loaded / Returned boxes |
| Crew checklist | Crew-visible checklist items only. Office items like "Deposit received" are hidden. |
| Additional notes & FAQs | Standing company policies (call time, power, hard surfaces, weather, meals, gear) |
| Crew chat | A message thread shared by the crew, the producer and the office |

Crew can accept or decline the call from the page. The office copy of the worksheet adds everyone's pay, confirmations and office notes, and doubles as a printable pull sheet.

**Inventory and gear**
- Items with category, make/model, serial and asset tag, quantity owned, condition, status (active / maintenance / retired), location, rental rate and replacement value. CSV import and export are included.
- Each event has an **Audio & backline** list. Add items from inventory, or add free-text needs and sub-rentals for anything you don't stock.
- **Availability and conflicts:** Hold and Confirmed events reserve gear. If overlapping events need more units than you own, or an item is in maintenance, the shortfall is flagged and the other bookings are named.
- **Warehouse checklist:** every gear line has Pulled / Loaded / Returned checkboxes and return/damage notes. Items still out after a show appear on the dashboard.

**Checklists**
- Reusable templates with sections, each marked "show on crew worksheets" or office-only. Three ship with the app: Advance & Prep (office), Show Day, and Load-Out & Return. Ticking an item records who did it and when.

**Contracts**
- Generated from an editable template with merge fields (client, venue, times, gear list, total, deposit, due dates). The total is pre-filled from the gear rental value.
- Workflow: draft → sent → signed (or void). Sent contracts get a client link where the client types their name and ticks "I agree". The app records the name, time and IP address, and signed contracts are locked.

**Invoices**
- Line items can be pre-filled from the event's priced gear list. Each line can be marked taxable or not. You can add a discount and a tax rate, and record payments.
- Status is derived automatically: draft, sent, partial, paid, overdue or void. Sent invoices get a client link.

Contracts, invoices and worksheets all print cleanly and can be saved as PDF from the browser. Other features: multiple users, CSRF protection, and "Email" buttons that open your mail app with the link already written in.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

flask --app backline seed        # optional: demo data for Chicago Sound and Backline
flask --app backline run         # http://127.0.0.1:5000
```

On first visit you'll create the admin account. The company name is pre-filled as Chicago Sound and Backline. Under **Settings** you can set:
- company details and billing defaults
- the contract template
- the crew worksheet text: terms of use, payment, additional notes & FAQs, and the run-of-show starter

The demo data is dated relative to today:
- An Alvarez / Reed wedding with a ceremony at Maplewood Chapel and a reception at Riverbend Country Club. It has a full run of show, special requests and crew chat.
- A Fulton Market corporate show.
- A Lakefront festival hold that conflicts with a Blue Door Lounge gig over Twin Reverbs.
- An overdue invoice and a cymbal pack that was never returned.

All demo people, venues, phone numbers (555-01xx) and emails are fictional.

Other commands:

```bash
flask --app backline create-user <username>   # add a login from the shell
flask --app backline init-db                  # create/upgrade tables (also runs automatically on startup)
```

Upgrading an existing database needs no extra step. New columns are added on startup, and a database still using the old placeholder company name is renamed to Chicago Sound and Backline.

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

The suite covers:
- login, setup and CSRF
- gear conflict rules
- checklist and gear toggles
- invoice math and statuses
- the contract signing flow
- worksheet sections and privacy: only the viewer's own pay, crew-only notes kept from clients, office-only checklist items hidden
- crew chat and calendar invites
- the database migration
- CSV import
- a render check of every page against the demo data

## Project layout

```
backline/
  __init__.py        app factory
  schema.sql         tables
  db.py              database helpers, migrations, default settings/checklists/contract + worksheet text
  auth.py            login, first-run setup, CSRF
  forms.py           declarative form fields + validation
  services.py        gear availability, totals, invoice math, contract rendering, iCal export
  seed.py            Chicago demo data
  views/             dashboard, events (crew/gear/checklists/chat/calendar), inventory,
                     people (clients/venues/crew), contracts, invoices, settings,
                     public (crew worksheets, contract signing, client invoices)
  templates/, static/
tests/
```

## Known limits / ideas for next steps

- Email goes through `mailto:` links. Sending automatically (SMTP, Postmark, etc.), texting crew their worksheet link, and push notifications for new chat messages would be natural additions.
- There are no online payments. A Stripe payment link on the client invoice page would be a small addition.
- The e-signature is a typed name plus an agreement checkbox, with a time and IP audit record. Check that this meets Illinois requirements. The default contract and crew policy text is a starting point, not legal advice.
- Possible additions: a per-crew iCal feed of all their calls, stage plot and input list uploads, gear "kits", and barcode scanning for check-in and check-out.
