# Chicago Sound and Backline

The operations platform for Chicago Sound and Backline. It keeps the schedule, the gear inventory, each event's audio and backline needs (with pull/load/return checklists), crew worksheets, contracts and invoices in one place.

It covers the full range of sound reinforcement work: corporate programs and keynotes, live concerts and club shows, festivals, private parties, galas, weddings, theater, worship and backline dry hire.

It is a small Flask + SQLite app: one Python dependency, one database file, no build step.

## Features

**Event types**

Each type is editable under Settings → Event types. A type sets:
- what the event's key people are called
- default names for its two locations
- the run-of-show starter
- the checklists a new event starts with

Picking a type on the event form updates all four as you choose.

| Type | Key people | Locations | Starts with |
| --- | --- | --- | --- |
| Corporate / Speaking | Speakers / presenters | General session · Breakout room | Agenda + presenter mic plan; Corporate & Speaking checklist |
| Live Concert / Club / Bar Show | Artists / headliner | Main stage · Second stage | Set times; Live Concert checklist (stage plot, rider, monitor mixes, changeovers) |
| Festival / Outdoor | Headliners | Main stage · Second stage | Stage schedule + weather plan; Live Concert + Outdoor Event checklists |
| Private Party | Host / guest of honor | Party space | Toasts, DJ, volume plan; Party & Private Event checklist |
| Fundraiser / Gala | Honorees / speakers | Ballroom · Reception area | Program with auction; Corporate & Speaking checklist |
| Wedding | Couple | Reception · Ceremony | Ceremony / cocktail / reception run of show; Wedding checklist |
| Theater / Performance, Worship / Community | Performers / company, Officiant / speakers | Theater, Sanctuary / hall | Show or service order |
| Backline / Dry Hire | Renting artist / client contact | Delivery location | Delivery, walkthrough and pickup; Dry Hire checklist |

**Sound reinforcement specs** on every event:
- service (full production, PA + engineer, backline + tech, backline only, or dry hire)
- indoor / outdoor
- audience size
- inputs, wireless mics and monitor mixes
- playback and record/stream feeds

The specs appear as quick-reference tiles on the event page and crew worksheets.

**Scheduling**
- Events with a readable reference number (`2026-10-10-Alvarez-Sofia-RBYC`) and a status (inquiry, hold, confirmed, completed or cancelled).
- Each event records the client, its key people (speakers, headliner, host, couple…), performers, and a **producer** (the crew's point person).
- Up to two locations per event, e.g. a general session and a breakout room, two stages, or a ceremony and a reception.
- A day-of timeline (load-in/delivery, setup complete, doors, show or program start and end, load-out/pickup) plus a free-form **run of show** that starts from the event type's template. Events can span multiple days.
- The events list can be filtered by type.
- A month calendar, a searchable event list, and a dashboard that flags what needs attention in the next 14 days: unconfirmed crew, missing gear lists, gear not pulled, open checklists, gear conflicts, gear not returned, unsigned contracts and overdue invoices.
- "Add to calendar" (.ics) for the office and for each crew member.

**Crew worksheets**

These are modeled on the per-musician gig worksheet a band sends its players. Each crew assignment gets a private link, `/worksheet/<event-reference>/<key>`, laid out in the same sections:

| Section | What's in it |
| --- | --- |
| Basic info | Booking status, date and Add to iCal, event type and service, the producer with Call/Text/Email buttons, dress code, audience size, key people (labelled by type), client, terms of use, payment (their own pay only), and event timings ("You are on A1 / FOH…") |
| Location & venue | Each location, with type-appropriate labels and Open in Maps; venue manager contacts; day-of contact |
| Crew | Roster with role, call time, phone and dietary notes, plus the crew meal |
| Special requests | Crew-only notes. Clients never see these. |
| Schedule | Timings, the run of show, and load-in, parking and power notes from the event and each venue |
| Audio & backline | Spec tiles (service, setting, audience, inputs, wireless, mixes), playback and feeds, and the gear list with Pulled / Loaded / Returned boxes |
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
- Reusable templates with sections, each marked "show on crew worksheets" or office-only. The app ships with:
  - general: Advance & Prep (office), Show Day, Load-Out & Return
  - by kind of work: Corporate & Speaking, Live Concert, Party & Private Event, Wedding, Outdoor Event, Dry Hire / Backline Rental
- Each event type picks its starting set. Ticking an item records who did it and when.

**Contracts**
- Generated from an editable template with merge fields (client, venue, times, gear list, total, deposit, due dates). The total is pre-filled from the gear rental value.
- Workflow: draft → sent → signed (or void). Sent contracts get a client link where the client types their name and ticks "I agree". The app records the name, time and IP address, and signed contracts are locked.
- **Deposits and payments:** each contract has a Payments panel showing the deposit (due, received with its date, or overdue), money received so far and what remains.
  - **Record deposit received** logs a check or transfer in one step; the deposit invoice is created behind the scenes.
  - **Invoice the deposit** and **Invoice the balance** create invoices at the contract amounts.
  - The contracts list shows each contract's deposit status and amount received.

**Invoices**
- Line items can be pre-filled from the event's priced gear list. Each line can be marked taxable or not. You can add a discount and a tax rate, and record payments.
- Record each payment received with its date, amount, method (check, ACH, card, Zelle…) and check or reference number.
- Status is derived automatically: draft, sent, partial, paid, overdue or void. Sent invoices get a client link. The invoices list totals Outstanding, Overdue and Collected this month.

**Crew pay**
- Each crew assignment has an **amount due**: the flat rate, or the hourly rate × hours. After the show, enter actual hours or a final amount (overtime, parking, a bonus) on the event's Crew tab.
- Crew are **owed** once their event is over. They become **overdue** if still unpaid after a set number of days (Settings → Pay crew within, default 14).
- The **Crew pay** page:
  - filter by status, person, event or date range
  - tick the people you paid and **Mark paid** with the date, method and check number (one payroll run can cover many gigs)
  - see totals for owed now, overdue, upcoming and paid this year
  - an "owed by person" list
  - CSV export for your bookkeeper
- Each crew member's page shows what they're owed, their pay history, and **paid by year** totals for contractor tax forms, plus a W-9 on file flag.
- Crew see on their worksheet when they've been paid, or that payment is pending.
- The dashboard shows **Crew owed**, **Crew pay overdue** and **Deposits overdue**.

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
- the crew worksheet text: terms of use, payment, and additional notes & FAQs
- event types
- checklist templates

The demo data is dated relative to today:

| Event | Type | What it shows |
| --- | --- | --- |
| Northbeam Q3 All-Hands | Corporate / Speaking | Presenter mic assignments, record feed to the video team, full agenda |
| The Midnight Arcade rehearsal backline | Backline / Dry Hire | Delivery and pickup, no operator |
| Alvarez / Reed Wedding | Wedding | Ceremony + reception, run of show modeled on a band worksheet |
| Jamal's 40th Birthday | Private Party | Small PA + DJ, toasts, quiet hours |
| Lakefront Harvest Festival | Festival / Outdoor | 3-day outdoor hold that conflicts with a concert over Twin Reverbs |
| The Velvet Owls at Blue Door Lounge | Live Concert | Backline + tech on a house PA, set times with an opener |
| Northbeam Product Launch | Corporate / Speaking | Past show paid in full; two crew paid in a payroll run, one stagehand overdue |
| Blue Door Showcase | Club / Bar Show | Past show: overdue invoice, cymbal pack never returned, one tech paid by Zelle and one still owed |
| Lakeview Youth Arts Spring Gala | Fundraiser / Gala | Inquiry awaiting a quote |

All demo people, venues, phone numbers (555-01xx) and emails are fictional.

Other commands:

```bash
flask --app backline create-user <username>   # add a login from the shell
flask --app backline init-db                  # create/upgrade tables (also runs automatically on startup)
```

Upgrading an existing database needs no extra step. On startup, new columns are added and the new default checklists and event types are filled in once. Old type names like "Concert" map to their new equivalents. A database still using the old placeholder company name is renamed to Chicago Sound and Backline.

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
- the contract signing flow, deposits recorded against contracts, and deposit/balance invoices
- crew pay: amount due, owed/overdue status, batch "mark paid", CSV export, yearly totals, and what crew see
- event types driving labels, the run-of-show starter, checklists (applied in order) and specs, plus managing types
- worksheet sections and privacy: only the viewer's own pay, crew-only notes kept from clients, office-only checklist items hidden
- crew chat and calendar invites
- the database migration from a real first-release database
- CSV import
- a render check of every page against the demo data

## Project layout

```
backline/
  __init__.py        app factory
  schema.sql         tables
  db.py              database helpers, migrations, one-time seeding of defaults
  defaults.py        default settings, contract + worksheet text, checklists, event types
  auth.py            login, first-run setup, CSRF
  forms.py           declarative form fields + validation
  services.py        gear availability, totals, invoice math, contract rendering, iCal export
  seed.py            Chicago demo data
  views/             dashboard, events (crew/gear/checklists/chat/calendar), inventory,
                     people (clients/venues/crew), contracts, invoices, crewpay, settings,
                     public (crew worksheets, contract signing, client invoices)
  templates/, static/
tests/
```

## Known limits / ideas for next steps

- Email goes through `mailto:` links. Sending automatically (SMTP, Postmark, etc.), texting crew their worksheet link, and push notifications for new chat messages would be natural additions.
- There are no online payments. A Stripe payment link on the client invoice page would be a small addition.
- The e-signature is a typed name plus an agreement checkbox, with a time and IP audit record. Check that this meets Illinois requirements. The default contract and crew policy text is a starting point, not legal advice.
- Possible additions: a per-crew iCal feed of all their calls, stage plot and input list uploads, gear "kits", and barcode scanning for check-in and check-out.
