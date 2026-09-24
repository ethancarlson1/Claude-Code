"""Out-of-the-box content: company defaults, contract and crew worksheet text,
checklist templates and event types. Everything here is editable in Settings;
these values only seed a new database (or fill in what an older one lacks)."""

DEFAULT_CONTRACT_TEMPLATE = """\
Agreement {{contract_number}} for event {{reference_number}}

This agreement is made between {{company_name}} ("Provider") and {{client_name}} ("Client") for audio and backline services at the event described below.

EVENT
  Event: {{event_title}} ({{event_type}})
  Service: {{service_type}}
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

COMPANY_NAME = "Chicago Sound and Backline"
# Name used before the Chicago Sound and Backline rebrand; migrated on startup.
_OLD_DEFAULT_COMPANY_NAME = "Your Audio & Backline Co."

DEFAULT_CREW_TERMS = f"""\
By accepting this call you agree to {COMPANY_NAME}'s crew policies: arrive at your call time ready to work, \
wear the listed attire, treat all gear and venue property with care, and report any damage or missing gear \
to the producer before you leave the venue."""

DEFAULT_CREW_PAYMENT = """\
The pay shown is the total for this call (or your hourly rate). After the event, send your invoice or \
confirm your hours within 7 days. If you're unhappy with the pay, talk to the producer before the event, \
ideally with plenty of notice."""

DEFAULT_WORKSHEET_NOTES = f"""\
1. Call time
Call time means on site and ready to work, not parking. For Loop, River North and lakefront venues, allow \
extra time for loading-zone traffic, garage height limits and freight elevators.

2. Power
A standard band or PA setup needs 2 dedicated, non-GFCI 20A circuits close to the stage. GFCI outlets \
trip under audio loads. If power on site doesn't match the worksheet, tell the producer before plugging in.

3. Hard surfaces only
Never set speakers, stands or backline on grass or dirt. Wet ground makes a performer holding a mic or \
guitar the quickest path to ground, and a tripod leg sinking into soft ground can drop an 80 lb speaker. \
Ask for staging, flooring or a patio.

4. Weather
Outdoor gear needs overhead cover. If conditions become unsafe for people or equipment, stop and call \
the producer.

5. Meals
Crew meal details are on the worksheet. Tell the producer about dietary restrictions at least a week out.

6. Gear
Count gear against the gear list before the truck leaves the venue. Log anything damaged or missing in \
the return notes so it can be fixed before the next show.

7. Presenters and performers
Mic presenters at least 15 minutes before they go on, with fresh batteries, and keep a spare handheld \
live at FOH. Mute lavs between speakers. For bands, follow the stage plot and ask before moving \
anyone's gear.

8. Client requests
Be friendly and helpful, but send anything that changes the scope of the show (extra inputs, more time, \
new locations) to the producer. Early setup or overtime can change the client's bill.

Questions? Call the {COMPANY_NAME} office."""

DEFAULT_RUN_OF_SHOW = """\
LOAD-IN / ACCESS:
(When the venue opens to vendors, dock or door, elevator, push distance)

POWER:
(Circuits confirmed, location, distance to stage)

PARKING:
(Where the truck and crew park, loading zone rules, permits)

LOCATIONS:
(Each performance area: main stage, breakout room, second stage, ceremony site, etc.)

RUN OF SHOW:
- 0:00 PM  Setup complete / line check
- 0:00 PM  Doors / guests arrive
- 0:00 PM  Show starts
- 0:00 PM  Show ends, strike
"""

DEFAULT_SETTINGS = {
    "company_name": COMPANY_NAME,
    "company_address": "Chicago, IL",
    "company_phone": "",
    "company_email": "",
    "default_tax_rate": "0",
    "deposit_percent": "50",
    "invoice_prefix": "INV-",
    "contract_prefix": "CT-",
    "invoice_terms": "Payment due within 15 days. Late balances are subject to a 1.5% monthly fee.",
    "contract_template": DEFAULT_CONTRACT_TEMPLATE,
    "crew_terms": DEFAULT_CREW_TERMS,
    "crew_payment_terms": DEFAULT_CREW_PAYMENT,
    "worksheet_notes": DEFAULT_WORKSHEET_NOTES,
    "run_of_show_template": DEFAULT_RUN_OF_SHOW,
}

DEFAULT_CHECKLISTS = [
    # (name, description, shown on crew worksheets, items)
    (
        "Advance & Prep",
        "Office tasks to confirm and prepare before the show date.",
        False,
        [
            ("Advance", "Confirm date, times and scope with client"),
            ("Advance", "Get tech needs: stage plot and input list, or agenda and presenter list"),
            ("Advance", "Confirm other vendors on site (video, lighting, DJ, band) and who patches into whom"),
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
        True,
        [
            ("Load-in", "Crew arrives at call time"),
            ("Load-in", "Walk stage with venue / stage manager"),
            ("Load-in", "Run power and distro"),
            ("Load-in", "Place mains, subs and monitors"),
            ("Load-in", "Set stage and backline per stage plot or room diagram"),
            ("Soundcheck", "Line check all inputs"),
            ("Soundcheck", "Wireless frequency scan and coordination"),
            ("Soundcheck", "Soundcheck / tech check complete with performers or presenters"),
            ("Show", "Log show notes and any equipment issues"),
        ],
    ),
    (
        "Load-Out & Return",
        "Strike, return and close out.",
        True,
        [
            ("Load-out", "Strike stage and coil cables"),
            ("Load-out", "Count gear against gear list before the truck leaves"),
            ("Return", "Unload at shop and check in all gear"),
            ("Return", "Tag damaged items for maintenance"),
            ("Close-out", "Send final invoice"),
            ("Close-out", "Record crew hours for payroll"),
        ],
    ),
    (
        "Corporate & Speaking",
        "Presenters, playback and feeds for corporate programs, conferences and galas.",
        True,
        [
            ("Prep", "Confirm agenda and presenter list"),
            ("Prep", "Assign a mic (lav, headset or handheld) to every presenter"),
            ("Prep", "Fresh batteries for every session; spares at FOH"),
            ("Prep", "Get playback files and the laptop / video audio plan"),
            ("Prep", "Confirm record or stream feed format with the video team"),
            ("Show", "Tech check with each presenter before doors"),
            ("Show", "Walk-in and walk-out music ready"),
            ("Show", "Podium and Q&A mics checked"),
            ("Show", "Mute plan for between speakers"),
        ],
    ),
    (
        "Live Concert",
        "Bands and artists: advance, soundcheck and changeovers.",
        True,
        [
            ("Advance", "Stage plot and input list received"),
            ("Advance", "Backline rider confirmed with the artist"),
            ("Advance", "Monitor mixes per musician confirmed"),
            ("Advance", "Set times, changeovers and curfew confirmed"),
            ("Show", "Ring out monitors"),
            ("Show", "Soundcheck headliner, then openers"),
            ("Show", "Changeover plan and patch notes for each act"),
            ("Show", "Set times posted side stage"),
            ("Show", "SPL limits / sound ordinance checked"),
        ],
    ),
    (
        "Party & Private Event",
        "Birthdays, holiday parties, private celebrations.",
        True,
        [
            ("Prep", "Confirm MC / announcement schedule with the host"),
            ("Prep", "Get playlist or DJ source and connection"),
            ("Show", "Toast / announcement mic ready and tested"),
            ("Show", "Background vs. dance volume plan agreed with host"),
            ("Show", "Noise limits / quiet hours confirmed"),
        ],
    ),
    (
        "Wedding",
        "Ceremony, cocktail hour and reception.",
        True,
        [
            ("Ceremony", "Mics for officiant and readers"),
            ("Ceremony", "Processional and recessional music cues"),
            ("Reception", "Introductions list with pronunciations"),
            ("Reception", "Toasts mic at the head table"),
            ("Reception", "Special dance songs cued"),
            ("Reception", "Ceremony-to-reception changeover plan"),
        ],
    ),
    (
        "Outdoor Event",
        "Weather, power and safety for outdoor stages.",
        True,
        [
            ("Site", "Overhead cover for every piece of gear"),
            ("Site", "Generator or distro placed, fueled and grounded"),
            ("Site", "Cable ramps across walkways"),
            ("Site", "Stands and speakers ballasted / sandbagged"),
            ("Site", "Rain and wind plan agreed with the client"),
        ],
    ),
    (
        "Dry Hire / Backline Rental",
        "Equipment drop-off and pickup without an operator.",
        True,
        [
            ("Delivery", "Gear counted and photographed before it leaves the shop"),
            ("Delivery", "Delivery window and on-site contact confirmed"),
            ("Delivery", "Walkthrough / demo for the client"),
            ("Delivery", "Client signs the delivery receipt"),
            ("Pickup", "Pickup time confirmed"),
            ("Pickup", "Gear counted and checked at pickup"),
        ],
    ),
]

SERVICE_TYPES = [
    "Full production (PA, backline, crew)",
    "PA + engineer",
    "Backline + tech",
    "Backline only",
    "Dry hire (drop-off & pickup)",
]

VENUE_SETTINGS = ["Indoor", "Outdoor", "Indoor + outdoor"]

_CORPORATE_ROS = """\
LOAD-IN / ACCESS:
(Dock, freight elevator, when the room turns over from the venue)

POWER:
(Circuits at the tech table and stage)

AV PARTNERS:
(Video / lighting vendor, who runs the switcher, where our record or stream feed lands)

PRESENTERS & MICS:
- Host: handheld 1
- Keynote: lav 1 (spare lav at FOH)
- Panel: lavs 2-4
- Q&A: aisle handhelds

AGENDA:
- 0:00 AM  Tech check complete, walk-in music
- 0:00 AM  Doors
- 0:00 AM  Welcome (host)
- 0:00 AM  Keynote
- 0:00 AM  Panel + Q&A
- 0:00 PM  Close, walk-out music, strike
"""

_CONCERT_ROS = """\
LOAD-IN / ACCESS:
(Dock or door, stairs, push distance, when the stage is ours)

POWER:
(Company switch or circuits, location, distance to stage)

PARKING:
(Truck, trailer and crew parking, loading zone rules)

ADVANCE:
(Stage plot and input list received? Backline rider confirmed? House console or ours?)

SET TIMES:
- 0:00 PM  Load-in / backline set
- 0:00 PM  Soundcheck: headliner
- 0:00 PM  Soundcheck: opener
- 0:00 PM  Doors
- 0:00 PM  Opener (30 min), changeover (15 min)
- 0:00 PM  Headliner (75 min)
- 0:00 PM  Curfew, strike
"""

_PARTY_ROS = """\
LOAD-IN / ACCESS:
(Door, stairs, elevator, when the space is available)

POWER:
(Outlets near the setup area, separate circuits)

PARKING:
(Where the vehicle and crew park; neighbors, noise limits, quiet hours)

RUN OF SHOW:
- 0:00 PM  Setup complete, background music on
- 0:00 PM  Guests arrive
- 0:00 PM  Welcome / toasts (handheld 1)
- 0:00 PM  Dinner: background volume
- 0:00 PM  Band / DJ / dancing
- 0:00 PM  Last song, strike
"""

_WEDDING_ROS = """\
LOAD-IN / ACCESS:
(When the venue is available for load-in, dock or door)

POWER:
(2 dedicated non-GFCI 20A circuits near the band / DJ area)

PARKING:
(Vendor parking per the venue coordinator)

LOCATIONS:
CEREMONY: (Location, mics for officiant and readers, processional and recessional music)
COCKTAIL HOUR: (Same setup as reception, or separate?)
RECEPTION: (Setup location; must we be set before cocktails?)

RUN OF SHOW:
- 0:00 PM  Setup complete
- 0:00 PM  Ceremony
- 0:00 PM  Cocktail hour
- 0:00 PM  Introductions (MC)
- 0:00 PM  Dinner: background music
- 0:00 PM  Toasts
- 0:00 PM  First dance / special dances
- 0:00 PM  Dancing
- 0:00 PM  Last song, strike
"""

_FESTIVAL_ROS = """\
SITE ACCESS:
(Gate, credentials, escort, truck route)

POWER:
(Generator or company switch, fuel plan, distro placement)

WEATHER PLAN:
(Cover, wind limits, who calls a hold)

STAGE SCHEDULE:
- 0:00 AM  Load-in and system tuning
- 0:00 AM  Gates open
- 0:00 PM  Act 1 / changeover
- 0:00 PM  Act 2 / changeover
- 0:00 PM  Headliner
- 0:00 PM  Curfew, strike
"""

_GALA_ROS = """\
LOAD-IN / ACCESS:
(Dock, when the ballroom turns over)

POWER:
(Circuits at the tech table and stage)

PROGRAM:
- 0:00 PM  Tech check complete, walk-in music
- 0:00 PM  Reception / cocktails
- 0:00 PM  Welcome and honorees (podium + handheld)
- 0:00 PM  Dinner: background music
- 0:00 PM  Auction / paddle raise (auctioneer on headset)
- 0:00 PM  Entertainment / dancing
- 0:00 PM  Close, strike
"""

_THEATER_ROS = """\
LOAD-IN / ACCESS:
(Dock, fly system, house crew and union rules)

SCHEDULE:
- 0:00 PM  Crew call
- 0:00 PM  Sound check / mic check with cast
- 0:00 PM  House opens (preshow music)
- 0:00 PM  Act 1
- 0:00 PM  Intermission
- 0:00 PM  Act 2
- 0:00 PM  Strike (or leave set for the next show)
"""

_WORSHIP_ROS = """\
LOAD-IN / ACCESS:
(Door, sanctuary or hall, when setup can start)

SERVICE ORDER:
- 0:00 AM  Setup complete, line check with musicians
- 0:00 AM  Rehearsal / run-through
- 0:00 AM  Service starts
- 0:00 AM  Message (podium or lav)
- 0:00 AM  Service ends, strike
"""

_DRY_HIRE_ROS = """\
DELIVERY:
(Address, dock or door, who signs for the gear, time window)

WALKTHROUGH:
(Who on the client side needs a demo of the system)

PICKUP:
(Time window, who releases the gear, where it's staged)
"""

_BASE_CHECKLISTS = ["Advance & Prep", "Show Day", "Load-Out & Return"]

# Event types: the label for the event's key people, default names for the
# two locations, a run-of-show starter and the checklists a new event of that
# type starts with.
DEFAULT_EVENT_TYPES = [
    dict(name="Corporate / Speaking", people_label="Speakers / presenters",
         venue_label="General session", venue2_label="Breakout room", run_of_show=_CORPORATE_ROS,
         checklists=["Advance & Prep", "Corporate & Speaking", "Show Day", "Load-Out & Return"]),
    dict(name="Live Concert", people_label="Artists / headliner",
         venue_label="Main stage", venue2_label="Second stage", run_of_show=_CONCERT_ROS,
         checklists=["Advance & Prep", "Live Concert", "Show Day", "Load-Out & Return"]),
    dict(name="Club / Bar Show", people_label="Artists", venue_label="Stage", venue2_label="",
         run_of_show=_CONCERT_ROS, checklists=["Advance & Prep", "Live Concert", "Load-Out & Return"]),
    dict(name="Festival / Outdoor", people_label="Headliners",
         venue_label="Main stage", venue2_label="Second stage", run_of_show=_FESTIVAL_ROS,
         checklists=["Advance & Prep", "Live Concert", "Outdoor Event", "Show Day", "Load-Out & Return"]),
    dict(name="Private Party", people_label="Host / guest of honor",
         venue_label="Party space", venue2_label="Second area", run_of_show=_PARTY_ROS,
         checklists=["Advance & Prep", "Party & Private Event", "Show Day", "Load-Out & Return"]),
    dict(name="Fundraiser / Gala", people_label="Honorees / speakers",
         venue_label="Ballroom", venue2_label="Reception area", run_of_show=_GALA_ROS,
         checklists=["Advance & Prep", "Corporate & Speaking", "Show Day", "Load-Out & Return"]),
    dict(name="Wedding", people_label="Couple", venue_label="Reception", venue2_label="Ceremony",
         run_of_show=_WEDDING_ROS, checklists=["Advance & Prep", "Wedding", "Show Day", "Load-Out & Return"]),
    dict(name="Theater / Performance", people_label="Performers / company",
         venue_label="Theater", venue2_label="Rehearsal space", run_of_show=_THEATER_ROS, checklists=_BASE_CHECKLISTS),
    dict(name="Worship / Community", people_label="Officiant / speakers",
         venue_label="Sanctuary / hall", venue2_label="Second room", run_of_show=_WORSHIP_ROS, checklists=_BASE_CHECKLISTS),
    dict(name="Backline / Dry Hire", people_label="Renting artist / client contact",
         venue_label="Delivery location", venue2_label="", run_of_show=_DRY_HIRE_ROS,
         checklists=["Advance & Prep", "Dry Hire / Backline Rental"]),
    dict(name="Other", people_label="Key people", venue_label="", venue2_label="",
         run_of_show=DEFAULT_RUN_OF_SHOW, checklists=_BASE_CHECKLISTS),
]

# Type names used before event types became editable -> their replacements.
OLD_EVENT_TYPE_NAMES = {
    "Concert": "Live Concert",
    "Corporate": "Corporate / Speaking",
    "Festival": "Festival / Outdoor",
    "Club Night": "Club / Bar Show",
    "Theater": "Theater / Performance",
    "Worship": "Worship / Community",
    "Rehearsal": "Other",
}
