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

**Vehicles and transport**
- **Vehicles** (in the sidebar) is the company fleet. Each vehicle has a type, make/model, plate, capacity and status (active, in maintenance or retired), plus registration and insurance expiry dates. The dashboard warns 30 days before either date.
- Each event has a **Transport** tab. Assign one or more company vehicles, or a **third-party vehicle** with a free-text description (a rental truck, a crew member's van…). Each vehicle gets a driver, a time it leaves the shop, and notes.
- A company vehicle booked on overlapping Hold or Confirmed events, or one that's in maintenance, is flagged on the event and the dashboard. The vehicle dropdown shows which events each vehicle is already booked on.
- Crew worksheets have a **Transport** section: which vehicle (with plate), who's driving (with phone), and when it leaves.
- The dashboard also warns about events coming up soon that have a gear list but no vehicle. Each vehicle's page shows its upcoming trips and history.

**Event documents**
- Upload stage plots, input lists, riders, venue tech packs, parking and load-in maps, site maps, agendas, paperwork or photos on an event's **Documents** tab. You can upload several files at once.
- Each file gets a type, a "provided by" note (artist, venue, planner…) and a description, e.g. "Rev 3, received Oct 2".
- **Crew can see** is on by default. Shared files appear on crew worksheets, so the crew can open the stage plot from their phone. Untick it for office-only paperwork like insurance certificates.
- Accepted file types: PDF, images, Word/Excel/PowerPoint, Pages/Numbers/Keynote, CSV/TXT/RTF, Vectorworks/DWG/DXF and zip. The limit is 50 MB per upload. PDFs and images open in the browser; other files download.

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
- Line items can be pre-filled from the event's priced gear list. Each line can be marked taxable or not. You can add a tax rate and a discount, either in dollars or as a percentage of the subtotal ("Discount (10%)" on the invoice), and record payments.
- Record each payment received with its date, amount, method (check, ACH, card, Zelle…) and check or reference number.
- Status is derived automatically: draft, sent, partial, paid, overdue or void. Sent invoices get a client link. The invoices list totals Outstanding, Overdue and Collected this month.
- Optional **QuickBooks Online** connection: sent invoices are copied to QuickBooks, clients can pay online, and payments sync both ways (see below).

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

## Event request form

A public page where clients tell you about their event, at **/request** on your site (for example `https://your-site/request`). Share the link from **Requests** in the sidebar: copy it, email it, or add it to your website as a link or button. Don't embed it inside another site's page; it needs to open on its own.

**For the client**
- Only their name and an email or phone number are required. Every other question can be skipped, and the form says so up front.
- Most answers are one tap: event type, indoors or outdoors, stage and power, how gear gets in, what they need and whether they want a tech on site. Numbers can be rough ("about 150").
- It covers:
  - contact details
  - the event: description, type, date, head count, who's speaking or performing
  - location and layout: venue, address, stage, power, venue contact
  - load-in and parking: access, earliest arrival, out-by time
  - the timeline and schedule
  - equipment needs, microphones and specific requests
  - day-of and planner contacts, budget
  - file uploads: stage plots, input lists, riders, floor plans, photos
- What they type is saved on their device as they go, so a closed tab or dropped connection doesn't lose it. Uploads that are too big are caught before sending.
- It works on phones, and in light and dark mode.

**For the office**
- New requests appear under **Requests** (with a count in the sidebar) and on the dashboard.
- **Create inquiry** turns a request into an event in one step:
  - It matches an existing client (by email, phone or name) and venue, or creates new ones.
  - It fills in the head count, setting, service, times, schedule, parking and load-in directions, audio needs, power and day-of contact.
  - It applies the event type's checklists, and puts the rest (description, layout, budget, planner, notes) in the office notes.
  - Attached files move to the event's Documents, office-only until you share them with crew.
  - The event starts as an **inquiry**, so it doesn't reserve gear.
- **Add to an existing event** fills in only what the event is missing. Answers that differ from what you already entered go into the office notes instead of overwriting them.
- Archive requests you won't take on; delete spam. The form can be turned off, in which case the link shows your phone and email instead.
- Spam protection: a hidden field that only bots fill in, and a limit of 5 requests per hour from one network.

## QuickBooks Online

Connect your QuickBooks Online company under **Settings → QuickBooks**. Nothing is sent to QuickBooks until you do.

**How it works once connected**
- **Invoices go to QuickBooks when you mark them sent.**
  - The client becomes a QuickBooks customer, matched by company name (or the person's name when there's no company).
  - The invoice keeps its number, dates, lines, discount and notes.
  - Editing a sent invoice updates QuickBooks, and voiding it voids it there too.
  - Prefer to send by hand? Turn off automatic sending and use the invoice's **Send to QuickBooks** button.
- **Clients can pay online.** With QuickBooks Payments turned on in QuickBooks, the client's invoice link gets a **Pay online** button that opens QuickBooks' payment page.
- **Payments sync both ways.**
  - Payments recorded here, including contract deposits, are added to QuickBooks.
  - Payments made or recorded in QuickBooks show up here, updating the invoice status, contract deposits and the dashboard.
  - The platform checks QuickBooks every 15 minutes while it's in use. You can also click **Check QuickBooks** on the Invoices page.
- **QuickBooks has the final say on payments.** Once a payment is in QuickBooks, change or delete it there. The change shows up here on the next check.
- **Sales tax:** taxable lines are marked taxable, and QuickBooks calculates the tax. If QuickBooks' total differs from this platform's, the invoice shows a warning so you can check it.
- **Nothing fails silently.** If QuickBooks can't be updated, the change is still saved here. The invoice, the Invoices list and the dashboard say what went wrong, and **Update QuickBooks** tries again.

**Setting it up**
1. Sign in at developer.intuit.com with your Intuit account and create an app for QuickBooks Online with the *Accounting* permission. It's free.
2. In **Settings → QuickBooks**:
   - Copy the **Redirect URI** shown there into your Intuit app's keys page.
   - Paste the app's **Client ID** and **Client Secret**, leave the environment on **Sandbox**, and save.
3. Click **Connect to QuickBooks**, sign in, and pick Intuit's sandbox (practice) company.
4. Choose the QuickBooks product/service that invoice lines post to, plus one for contract deposits if your accountant wants that, and save.
5. Try it out, ideally on a demo copy of the database rather than your real bookings. To make one, rename the `instance` folder, then run `flask --app backline seed`.
6. When you're ready for your real books:
   - Switch the environment to **Production** and enter the production keys.
   - Connect your real company.
   - Production keys need the platform online at an https address (see *Going live on Render*).

   Connecting to a different company clears links to the old one, including practice payments that came from the sandbox.

**Limits**
- QuickBooks Online only (not QuickBooks Desktop), with US-style sales tax.
- All invoice lines post to one product/service, with an optional second one for contract deposits and balances.
- Crew payments aren't sent to QuickBooks.
- QuickBooks is checked every 15 minutes rather than notifying the platform instantly.

## Branding

The Chicago Sound & Backline logo appears in the sidebar, on the sign-in page, at the top of crew worksheets, and on contracts and invoices. The browser-tab and phone home-screen icons use the "csb" mark. The app's accent colors match the logo's blue.

To use a different logo, upload it under **Settings → Company & billing → Logo**. It must be a PNG, JPG, GIF or WebP image; one with a white or transparent background works best. Tick "Go back to the built-in … logo" to undo. The built-in images live in `backline/static/brand/`.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # run this again after updating to a new version

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
| Northbeam Q3 All-Hands | Corporate / Speaking | Presenter mic assignments, record feed to the video team, full agenda, agenda + venue tech pack uploaded |
| The Midnight Arcade rehearsal backline | Backline / Dry Hire | Delivery and pickup, no operator |
| Alvarez / Reed Wedding | Wedding | Ceremony + reception, run of show modeled on a band worksheet; box truck plus a rental van; stage plot, input list and dock map uploaded |
| Jamal's 40th Birthday | Private Party | Small PA + DJ, toasts, quiet hours |
| Lakefront Harvest Festival | Festival / Outdoor | 3-day outdoor hold that conflicts with a concert over Twin Reverbs |
| The Velvet Owls at Blue Door Lounge | Live Concert | Backline + tech on a house PA, set times with an opener; Box Truck 1 double-booked with the festival |
| Northbeam Product Launch | Corporate / Speaking | Past show paid in full; two crew paid in a payroll run, one stagehand overdue |
| Blue Door Showcase | Club / Bar Show | Past show: overdue invoice, cymbal pack never returned, one tech paid by Zelle and one still owed |
| Lakeview Youth Arts Spring Gala | Fundraiser / Gala | Inquiry awaiting a quote |

It also has two event requests waiting under **Requests**: a detailed one with a floor plan attached, and one where the client skipped most questions.

All demo people, venues, phone numbers (555-01xx) and emails are fictional.

Other commands:

```bash
flask --app backline create-user <username>   # add a login from the shell
flask --app backline init-db                  # create/upgrade tables (also runs automatically on startup)
```

Upgrading an existing database needs no extra step. On startup, new columns are added and the new default checklists and event types are filled in once. Old type names like "Concert" map to their new equivalents. A database still using the old placeholder company name is renamed to Chicago Sound and Backline.

## Going live on Render

Render runs the platform online at an https address, keeps its database and uploaded files on a disk that survives updates, and copies that disk every day. The `render.yaml` file in this repository sets everything up.

**Cost:** the Starter instance (about $7 a month) plus a 1 GB disk (about $0.25 a month). A free Render account works, but the platform can't run on Render's *free instance*: free instances can't have a disk, so every restart or update would erase your bookings. Check Render's pricing page for current prices.

**1. Get the code onto the branch Render will use.** Render deploys from a GitHub branch. Use `main`, and merge the work you want live into it through a pull request. After that, every merge to `main` updates the live site automatically, with about a minute of downtime.

**2. Create the service from the Blueprint.**
1. In the Render dashboard: **New → Blueprint**.
2. Connect your GitHub account if asked, and give Render access to this repository.
3. Pick the repository and the `main` branch. Render reads `render.yaml` and shows one web service, **chicago-sound-backline** (Starter, Ohio region, 1 GB disk).
4. Click **Apply**. Render asks for a payment method for the Starter instance.
5. Wait for the first deploy to finish (a few minutes). Its status changes to **Live**, and its address appears at the top, like `https://chicago-sound-backline.onrender.com`.

**3. Create your admin account.** In the service, open **Environment**, show the value of `BACKLINE_SETUP_CODE`, and copy it. Then open your site's address. The setup page asks for that code before it creates the first account, so a stranger who finds the new site can't take it over.

**4. Bring your data, or start fresh.**
- **Starting fresh:** go to **Settings** and fill in company details, the logo, users, event types and checklists.
- **Moving from your computer:**
  1. On your computer's copy: **Settings → Backup → Download backup**.
  2. On the Render site, before entering any bookings: **Settings → Backup → Restore** with that file.
  3. Sign in again with a username and password from your computer's copy.

  Restoring only works on a platform with no bookings yet, so it can never overwrite live data.

**5. Use your own domain (optional).**
1. In the service, go to **Settings → Custom Domains** and add something like `ops.yourdomain.com`.
2. At your domain provider, add the CNAME record Render shows (pointing to `chicago-sound-backline.onrender.com`).

Render sets up the https certificate. Then link your website's "Request a quote" button to `https://ops.yourdomain.com/request`.

**6. Connect QuickBooks (optional).** In your Intuit app, add the Redirect URI shown under **Settings → QuickBooks** on the live site. Use the production keys, switch the environment to **Production**, and connect. See *QuickBooks Online* above.

**Day to day**
- **Backups:** Render snapshots the disk daily and keeps snapshots at least a week. Also download a backup from **Settings → Backup** now and then, and keep it somewhere safe.
- **Forgotten passwords:** anyone signed in can set a new password for another user under **Settings → Users**. If nobody can sign in, open the service's **Shell** in Render and run `flask --app backline reset-password <username>`.
- **Sign-in protection:** after 5 wrong passwords for one username from one network (or 20 for any usernames), sign-in from that network pauses for 15 minutes.
- **Logs:** the service's **Logs** tab shows what the platform is doing, which helps when something goes wrong.

## Free demo site

To show people what the platform does without paying for hosting or touching real data, run it in **demo mode** on Render's free plan.

**What visitors get**
- The sample Chicago data: events of every type, crew, gear, contracts, invoices, crew pay and two client requests.
- A sign-in page with one **Explore the demo** button; no account needed.
- They can click through everything and try it: create and edit events, build gear lists, tick checklists, open crew worksheets, send the request form, and turn a request into an inquiry.
- Changes that would lock others out or reach outside services are turned off: users and passwords, company details and logo, QuickBooks, restoring backups, and switching the request form off.
- A banner on every page says it's a demo, with a **Start over** button that puts the sample data back.
- The demo is hidden from search engines, and uploads are limited to 5 MB.

**Setting it up on Render (free)**
1. In Render: **New → Web Service**. Use a plain web service, not a Blueprint, because the Blueprint is for the paid live site.
2. Connect GitHub and pick this repository and its branch.
3. Fill in:
   - **Name:** for example `csb-demo` (the address becomes `https://csb-demo.onrender.com`)
   - **Language:** Python 3
   - **Region:** Ohio
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `waitress-serve --host=0.0.0.0 --port=$PORT --threads=4 --no-clear-untrusted-proxy-headers --call backline:create_app`
   - **Instance type:** Free
4. Under **Environment variables**, add:
   - `BACKLINE_DEMO` = `1`
   - `BACKLINE_BEHIND_PROXY` = `1`
   - `BACKLINE_SECRET_KEY` = any long random text (Render's **Generate** button works)
5. Optional: under **Advanced**, set the **Health Check Path** to `/healthz`.
6. Click **Deploy**. When it says **Live**, open the address and click **Explore the demo**.

**Good to know**
- A free service goes to sleep after about 15 minutes without visitors. The next visit takes up to a minute to wake it, so open the link a minute before a meeting.
- Every time it wakes up or redeploys, it starts again with fresh sample data.
- Never put real bookings in the demo. Use the paid live site for those.

## Running it elsewhere

Any host that runs a Python web app over https and keeps files between restarts works. The platform needs somewhere to keep its SQLite database and uploads. For example, on a small server behind Caddy or nginx:

```bash
pip install -r requirements.txt
BACKLINE_SECRET_KEY=... BACKLINE_DATABASE=/srv/backline/backline.sqlite3 BACKLINE_UPLOADS=/srv/backline/uploads \
  BACKLINE_BEHIND_PROXY=1 waitress-serve --port 8000 --no-clear-untrusted-proxy-headers --call backline:create_app
```

`--no-clear-untrusted-proxy-headers` lets the proxy's `X-Forwarded-*` headers reach the app, so its links and cookies use https.

| Variable | Purpose |
| --- | --- |
| `BACKLINE_SECRET_KEY` | Session signing key. If unset, one is generated and saved in `instance/secret_key`. |
| `BACKLINE_DATABASE` | Path to the SQLite file. Default: `instance/backline.sqlite3`. |
| `BACKLINE_UPLOADS` | Folder for uploaded event documents. Default: `instance/uploads`. |
| `BACKLINE_BEHIND_PROXY` | Set when running behind a reverse proxy. Trusts the last `X-Forwarded-*` values and marks cookies Secure. |
| `BACKLINE_SETUP_CODE` | Recommended on a public server. The code needed to create the first account. |
| `BACKLINE_DEMO` | Set to `1` for the public demo (see *Free demo site*). Never on the live site. |
| `BACKLINE_MAX_UPLOAD_MB` | Largest upload accepted at once, in MB. Default: 50. |
| `BACKLINE_MAX_RESTORE_MB` | Largest backup that can be restored, in MB. Default: 500. |
| `BACKLINE_QBO_CLIENT_ID`, `BACKLINE_QBO_CLIENT_SECRET` | Optional. Your Intuit app's keys, instead of entering them under Settings → QuickBooks. |

**Backups:** **Settings → Backup → Download backup** saves the database and every uploaded file in one .zip. The database also holds the QuickBooks sign-in when connected, so keep backups private.

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
- vehicles and transport: fleet management, company and third-party vehicles on events, double-booking and maintenance warnings, expiring paperwork, and the worksheet section
- documents: upload, download (inline vs. attachment), rejecting unsafe or empty files, crew seeing only shared files, cleanup when files or events are deleted, and the friendly "too large" message
- branding: the logo on every page, replacing and resetting it from Settings, and rejecting files that aren't real images
- the event request form: only name and contact required, forgiving answers, keeping answers on errors, spam protection, uploads, turning it off, the inbox, creating an inquiry (client/venue matching, every mapped field, checklists, files), adding to an existing event without overwriting, archiving and deleting
- demo mode: sample data and one-click entry on startup, the banner and search-engine opt-out, what's turned off, Start over, the 5 MB upload limit, and no demo routes on the real platform
- going live: the health check, https links and Secure cookies behind a proxy, the setup code, sign-in lockout, password resets (in Settings and from the command line), backups, and restoring only onto an empty platform (including an old-version backup and unsafe file paths)
- QuickBooks, against an in-memory stand-in for QuickBooks (tests never touch the network):
  - connecting, and refusing sign-ins that didn't start in this browser
  - customers and invoices (lines, tax flags, discount, deposits), edits and voids
  - payments in both directions, including changes, deletions, split payments and ones QuickBooks refuses
  - sign-in refresh, a revoked connection, throttled automatic checks, and switching companies
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
  services.py        gear and vehicle availability, totals, invoice math, crew pay, contract rendering, iCal export
  files.py           event document storage (uploads folder, allowed types, downloads)
  quickbooks.py      QuickBooks Online: sign-in, sending invoices and payments, bringing payments back
  intake.py          the event request form: questions, reading answers, turning a request into an event
  backup.py          backup downloads and restoring onto an empty platform
  demo.py            demo mode for the free showcase site
  seed.py            Chicago demo data
  views/             dashboard, events (crew/gear/checklists/chat/calendar), inventory,
                     people (clients/venues/crew), contracts, invoices, crewpay, settings, quickbooks,
                     requests (the office inbox), intake (the public request form), backups,
                     public (crew worksheets, contract signing, client invoices)
  templates/, static/ (static/brand/ holds the logo and icons)
render.yaml          Render Blueprint for the live site
tests/
```

## Known limits / ideas for next steps

- Email goes through `mailto:` links. Sending automatically (SMTP, Postmark, etc.), texting crew their worksheet link, and push notifications for new chat messages would be natural additions.
- Online payments go through QuickBooks Payments when QuickBooks is connected. Paying crew through Zelle, Venmo or similar is on hold.
- The e-signature is a typed name plus an agreement checkbox, with a time and IP audit record. Check that this meets Illinois requirements. The default contract and crew policy text is a starting point, not legal advice.
- Possible additions: a per-crew iCal feed of all their calls, gear "kits", and barcode scanning for check-in and check-out.
- Planned: an AI import page that reads emails, input lists, schedules and tech packs and proposes changes for you to approve.
