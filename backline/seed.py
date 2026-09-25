"""Demo data for Chicago Sound and Backline: inventory, crew, clients,
Chicago-area venues and a few weeks of bookings. Dates are relative to today
so the demo always looks current. People, venues, phone numbers (555-01xx)
and emails are fictional placeholders."""

from datetime import datetime, timedelta

from . import db, services, util

INVENTORY = [
    # name, category, make, model, qty, rate/day, replacement value, location
    ("Midas M32 console", "Consoles", "Midas", "M32", 1, 250, 4500, "Shop: Console cage"),
    ("Allen & Heath SQ-6 console", "Consoles", "Allen & Heath", "SQ-6", 1, 225, 5000, "Shop: Console cage"),
    ("QSC K12.2 powered speaker", "Speakers", "QSC", "K12.2", 8, 60, 900, "Shop: Bay 1"),
    ("QSC KS118 powered sub", "Speakers", "QSC", "KS118", 4, 85, 1600, "Shop: Bay 1"),
    ("JBL SRX835P 3-way", "Speakers", "JBL", "SRX835P", 4, 150, 3000, "Shop: Bay 1"),
    ("QSC K10.2 wedge", "Monitors", "QSC", "K10.2", 6, 45, 750, "Shop: Bay 2"),
    ("Shure PSM1000 IEM system", "Wireless", "Shure", "PSM1000", 4, 120, 3500, "Shop: Wireless rack"),
    ("Shure ULXD2 / Beta 58 handheld", "Wireless", "Shure", "ULXD2/B58", 8, 65, 1500, "Shop: Wireless rack"),
    ("Shure SM58", "Microphones", "Shure", "SM58", 20, 8, 100, "Mic case A"),
    ("Shure SM57", "Microphones", "Shure", "SM57", 16, 8, 100, "Mic case A"),
    ("Shure Beta 52A kick mic", "Microphones", "Shure", "Beta 52A", 2, 12, 190, "Mic case B"),
    ("Sennheiser e604 drum clip mic", "Microphones", "Sennheiser", "e604", 6, 10, 150, "Mic case B"),
    ("Neumann KM184 condenser", "Microphones", "Neumann", "KM184", 4, 25, 900, "Mic case C"),
    ("Radial J48 active DI", "DI & Stage Boxes", "Radial", "J48", 8, 10, 200, "DI case"),
    ("Radial ProDI passive DI", "DI & Stage Boxes", "Radial", "ProDI", 8, 6, 100, "DI case"),
    ("Whirlwind 32x8 snake, 150'", "Cables & Snakes", "Whirlwind", "Medusa 32x8", 2, 75, 1800, "Cable trunk"),
    ("XLR cable 25'", "Cables & Snakes", "Mogami", "", 80, 2, 35, "Cable trunk"),
    ("K&M boom mic stand", "Stands & Hardware", "K&M", "210/9", 40, 3, 50, "Stand cart"),
    ("Fender '65 Twin Reverb", "Guitar Amps", "Fender", "'65 Twin Reverb Reissue", 3, 95, 1600, "Backline room"),
    ("Fender Hot Rod Deluxe", "Guitar Amps", "Fender", "Hot Rod Deluxe IV", 2, 60, 900, "Backline room"),
    ("Vox AC30", "Guitar Amps", "Vox", "AC30C2", 2, 90, 1400, "Backline room"),
    ("Marshall JCM800 + 1960A cab", "Guitar Amps", "Marshall", "2203 / 1960A", 1, 125, 3000, "Backline room"),
    ("Ampeg SVT-CL + SVT-810E", "Bass Amps", "Ampeg", "SVT-CL / 810E", 2, 125, 3500, "Backline room"),
    ("Aguilar Tone Hammer 500 + DB410", "Bass Amps", "Aguilar", "TH500 / DB410", 1, 85, 2000, "Backline room"),
    ("DW Collector's 5-pc kit", "Drums", "DW", "Collector's Maple", 2, 175, 5000, "Drum room"),
    ("Ludwig Classic Maple 4-pc kit", "Drums", "Ludwig", "Classic Maple", 1, 150, 3500, "Drum room"),
    ("Snare drum 14x6.5", "Drums", "Ludwig", "Black Beauty", 3, 25, 900, "Drum room"),
    ("Drum hardware pack", "Drums", "DW", "9000 series", 3, 40, 800, "Drum room"),
    ("Zildjian K cymbal pack", "Cymbals", "Zildjian", "K Custom pack", 2, 50, 1500, "Drum room"),
    ("Nord Stage 4 88", "Keyboards", "Nord", "Stage 4 88", 2, 150, 5000, "Keys shelf"),
    ("Yamaha CP88 stage piano", "Keyboards", "Yamaha", "CP88", 1, 125, 2500, "Keys shelf"),
    ("Hammond XK-5 + Leslie 3300", "Keyboards", "Hammond", "XK-5 / 3300", 1, 200, 6000, "Keys shelf"),
    ("Keyboard stand (double X)", "Stands & Hardware", "K&M", "18953", 6, 10, 150, "Stand cart"),
    ("Motion Labs 100A distro", "Power & Distro", "Motion Labs", "100A 3-phase", 1, 150, 3500, "Power cage"),
    ("Drum riser 8x8", "Staging", "StageRight", "8x8x16in", 2, 75, 1200, "Staging bay"),
]

CREW = [
    # name, role, email, phone, day rate, hourly rate, dietary
    ("Dana Kowalski", "Production Manager", "dana@example.com", "(312) 555-0101", 400, None, None),
    ("Maya Ortiz", "A1 / FOH Engineer", "maya@example.com", "(312) 555-0102", 450, None, "Vegetarian"),
    ("Chris Bell", "A2 / Monitors", "chris@example.com", "(773) 555-0103", 350, None, None),
    ("Jordan Pike", "Backline Tech", "jordan@example.com", "(773) 555-0104", 300, None, None),
    ("Taylor Nguyen", "Drum Tech", "taylor@example.com", "(773) 555-0105", 300, None, "No shellfish"),
    ("Sam Reyes", "Stagehand", "sam@example.com", "(312) 555-0106", None, 28, None),
]

CLIENTS = [
    ("Sofia Alvarez", None, "sofia.alvarez@example.com", "(312) 555-0142"),
    ("Priya Shah", "Northbeam Corporate Events", "priya@example.com", "(312) 555-0143"),
    ("Lakefront Harvest Festival", "Lakefront Harvest Music Festival LLC", "production@example.com", "(312) 555-0144"),
    ("Ruby Carter", "The Velvet Owls", "ruby@example.com", "(773) 555-0145"),
    ("Jamal Wright", None, "jamal@example.com", "(773) 555-0146"),
    ("Leah Park", "The Midnight Arcade (touring)", "leah@example.com", "(312) 555-0147"),
    ("Lakeview Youth Arts Fund", "Lakeview Youth Arts Fund", "events@example.com", "(773) 555-0148"),
]

VENUES = [
    dict(name="Riverbend Country Club", city="Elmwood Park", state="IL",
         contact_name="Tracy Nolan (events manager)", contact_phone="(708) 555-0150", contact_email="events@example.com",
         load_in_notes="West service door by the kitchen, no stairs. Vendors can load in from 1:00 PM.",
         power_notes="Two dedicated non-GFCI 20A circuits on the wall behind the stage.",
         parking_notes="Gravel lot behind the maintenance building. Keep the front circle clear for guests.",
         stage_notes="Built-in 16' x 12' stage in the main ballroom."),
    dict(name="Maplewood Chapel", city="Oak Park", state="IL",
         contact_name="Father Luis (parish office)", contact_phone="(708) 555-0151",
         load_in_notes="Side door on the north lawn. Small PA only; no subs in the sanctuary.",
         power_notes="Two 15A outlets at the front of the nave."),
    dict(name="Fulton Market Event Loft", address="W Fulton Market", city="Chicago", state="IL",
         contact_name="Luis Ramos (building engineer)", contact_phone="(312) 555-0152",
         load_in_notes="Alley dock off N Carpenter St. Freight elevator to 3rd floor; 8' door height.",
         power_notes="60A 1-phase disconnect stage left, plus two 20A circuits.",
         parking_notes="Truck on the dock until 8 AM, then the Carpenter St lot."),
    dict(name="Lakefront Park Bandshell", address="S Lake Shore Dr", city="Chicago", state="IL",
         contact_name="Dana Wu (festival production)", contact_phone="(312) 555-0153",
         load_in_notes="Truck access via the service drive behind the bandshell. Park District escort required.",
         power_notes="400A 3-phase company switch, cam-lok.", stage_notes="40' x 32' covered stage. No house PA."),
    dict(name="Blue Door Lounge", address="N Milwaukee Ave", city="Chicago", state="IL",
         contact_name="Eli (GM)", contact_phone="(773) 555-0154",
         load_in_notes="Front door only, 3 steps. Loading zone on Milwaukee after 4 PM.",
         stage_notes="16' x 12' stage. House console is a Midas M32; we bring backline only unless noted."),
    dict(name="Northside Rehearsal Studios", address="N Ravenswood Ave", city="Chicago", state="IL",
         contact_name="Front desk", contact_phone="(773) 555-0155",
         load_in_notes="Ground-floor roll-up door on the alley. Room B is at the end of the hall."),
    dict(name="Pilsen Rooftop Loft", address="W 18th St", city="Chicago", state="IL",
         contact_name="Marisol (events)", contact_phone="(312) 555-0156",
         load_in_notes="Freight elevator to the 5th floor, then 20 ft push to the roof deck door.",
         power_notes="Two 20A circuits inside by the bar; one outdoor 20A GFCI on the deck (use indoor circuits for audio).",
         parking_notes="Street parking only; unload on Halsted side, then move the van.",
         stage_notes="No stage. DJ table by the windows; speakers on sticks inside, one pair of fills on the deck."),
]


def _item(name):
    return db.scalar("SELECT id FROM inventory_items WHERE name = ?", (name,))


def _add_gear(event_id, items):
    for sort, (name, qty, *rest) in enumerate(items):
        item = db.query("SELECT * FROM inventory_items WHERE name = ?", (name,), one=True)
        row = {"event_id": event_id, "quantity": qty, "sort": sort, "notes": rest[0] if rest else None}
        if item:
            row.update(item_id=item["id"], rate=item["rental_rate"])
        else:  # sub-rental / not stocked: (name, qty, notes, category)
            row.update(description=name, category=rest[1] if len(rest) > 1 else "Other", rate=None)
        db.insert("event_gear", row)


def _crew_id(name):
    return db.scalar("SELECT id FROM crew WHERE name = ?", (name,))


def _add_crew(event_id, name, role, call, paid=None, **extra):
    """paid = (date, method, reference) records the crew member as paid."""
    member = db.query("SELECT * FROM crew WHERE name = ?", (name,), one=True)
    pay_type = "hourly" if member["hourly_rate"] and not member["day_rate"] else "flat"
    assignment_id = db.insert("event_crew", {
        "event_id": event_id, "crew_id": member["id"], "role": role, "call_time": call,
        "pay_type": pay_type, "pay_rate": member["hourly_rate"] if pay_type == "hourly" else member["day_rate"],
        "hours": extra.get("hours"), "actual_hours": extra.get("actual_hours"),
        "confirmed": extra.get("confirmed", 0), "worksheet_key": util.gen_key(),
    })
    if paid:
        services.mark_crew_paid([assignment_id], *paid)
    return assignment_id


def _message(event_id, author, body, minutes_ago, crew=True):
    created = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
    db.insert("event_messages", {"event_id": event_id, "crew_id": _crew_id(author) if crew else None,
                                 "author": author, "body": body, "created_at": created})


def _event(**values):
    client = db.query("SELECT name FROM clients WHERE id = ?", (values.get("client_id"),), one=True)
    values["reference_number"] = util.gen_reference(values["event_date"], client and client["name"], values["title"])
    return db.insert("events", values)


def _tick(event_id, count):
    ids = [r["id"] for r in db.query(
        "SELECT id FROM event_checklist_items WHERE event_id = ? ORDER BY sort LIMIT ?", (event_id, count))]
    for i in ids:
        db.update("event_checklist_items", i, {"done": 1, "done_by": "office", "done_at": util.now_iso()})


def _contract(event_id, status, deposit_pct=50, deposit_due=None, deposit_paid=None):
    """deposit_paid = (date, method, reference) records the deposit as received."""
    event = db.query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
    total = services.gear_total(event)
    deposit = util.round_money(total * deposit_pct / 100)
    number = services.next_number("contracts", db.get_setting("contract_prefix"))
    balance_due = (util.parse_date(event["event_date"]) - timedelta(days=14)).isoformat()
    body = services.render_contract(db.get_setting("contract_template"), event, number, total, deposit, None, balance_due)
    row = {"event_id": event_id, "number": number, "title": "Equipment Rental & Production Services Agreement",
           "status": status, "body": body, "total_amount": float(total), "deposit_amount": float(deposit),
           "deposit_due_date": deposit_due, "balance_due_date": balance_due, "public_key": util.gen_key(18)}
    if status in ("sent", "signed"):
        row["sent_at"] = util.now_iso()
    if status == "signed":
        client = db.query("SELECT c.name FROM clients c JOIN events e ON e.client_id = c.id WHERE e.id = ?",
                          (event_id,), one=True)
        row.update(signed_at=util.now_iso(), signed_name=client["name"], signed_ip="203.0.113.10")
    contract_id = db.insert("contracts", row)
    if deposit_paid:
        contract = db.query("SELECT * FROM contracts WHERE id = ?", (contract_id,), one=True)
        services.record_contract_deposit(contract, deposit_paid[0], deposit, *deposit_paid[1:])
    return contract_id


def _invoice(event_id, status, issue, due, payments=()):
    event = db.query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
    invoice_id = db.insert("invoices", {
        "number": services.next_number("invoices", db.get_setting("invoice_prefix")),
        "event_id": event_id, "client_id": event["client_id"], "status": status,
        "issue_date": issue.isoformat(), "due_date": due.isoformat(), "tax_rate": 0, "discount": 0,
        "terms": db.get_setting("invoice_terms"), "public_key": util.gen_key(18),
    })
    for sort, line in enumerate(services.invoice_lines_for_event(event)):
        db.insert("invoice_items", {**line, "invoice_id": invoice_id, "sort": sort})
    db.insert("invoice_items", {"invoice_id": invoice_id, "description": "Delivery, setup & strike",
                                "quantity": 1, "unit_price": 350, "taxable": 0, "sort": 99})
    for paid_on, amount, method in payments:
        db.insert("payments", {"invoice_id": invoice_id, "paid_on": paid_on.isoformat(), "amount": amount, "method": method})
    return invoice_id


def _apply_type_checklists(event_id, type_name):
    etype = services.event_type(type_name)
    for template_id in services.event_type_checklist_ids(etype["id"]):
        services.apply_checklist_template(event_id, template_id)


def _next_saturday(after):
    return after + timedelta(days=(5 - after.weekday()) % 7)


CORPORATE_RUN_OF_SHOW = """\
LOAD-IN / ACCESS:
Alley dock off N Carpenter St until 8 AM, then freight elevator to the 3rd floor.

POWER:
60A disconnect stage left for the PA; tech table on the 20A circuit by the back wall.

AV PARTNERS:
Video: Brightline Media runs cameras and the switcher. Our 2-ch record feed lands at their switcher (XLR, line level).

PRESENTERS & MICS:
- Host (Priya Shah): handheld 1
- CEO keynote (Dr. Alana Brooks): lav 1, spare lav live at FOH
- Leadership panel: lavs 2-4
- Audience Q&A: aisle handhelds 5-6

AGENDA:
- 9:30 AM  Tech check with presenters, walk-in music
- 10:30 AM Doors
- 11:00 AM Welcome (host)
- 11:10 AM CEO keynote
- 12:00 PM Lunch (background playlist)
- 1:00 PM  Leadership panel + Q&A
- 2:45 PM  Close, walk-out music
- 3:00 PM  Strike; off the dock by 3:30
"""

WEDDING_RUN_OF_SHOW = """\
LOAD-IN / ACCESS:
Riverbend opens to vendors at 1:00 PM. West service door by the kitchen, no stairs.
Chapel crew (Chris) loads in at 1:30 PM through the north lawn side door.

POWER:
Reception: 2 dedicated non-GFCI 20A circuits behind the stage (confirmed with Tracy).
Chapel: 2 x 15A at the front of the nave. Small PA only, no subs.

PARKING:
Gravel lot behind the maintenance building. Keep the front circle clear for guests.

LOCATIONS:
CEREMONY (Maplewood Chapel, 3:00 PM): 2 wireless (officiant + reader), 2 K12s on sticks, small mixer.
COCKTAIL HOUR (Riverbend terrace, 4:30 PM): piano DI into the house system.
RECEPTION (Riverbend ballroom): band is set up on the main stage BEFORE cocktails.

RUN OF SHOW:
- 2:30 PM  Ceremony line check done
- 3:00 PM  Ceremony; strike the chapel and move to Riverbend by 4:00
- 4:30 PM  Band setup complete / cocktail hour
- 6:00 PM  Band plays light instrumental while guests are seated
- 6:15 PM  MC announces the wedding party (wireless 1)
- 6:30 PM  Dinner; background playlist from FOH. Crew meal.
- 7:15 PM  Toasts (wireless 2), then first dance and first set
- 8:10 PM  Break (DJ)
- 8:25 PM  Second set
- 9:20 PM  Break (DJ)
- 9:30 PM  Final set
- 10:15 PM Band ends; DJ on console ch 31/32 until 11:00
- 11:00 PM Strike; truck loaded and out by 12:30 AM
"""


def seed():
    if db.scalar("SELECT COUNT(*) FROM events") or db.scalar("SELECT COUNT(*) FROM inventory_items"):
        raise SystemExit("Database already has data; demo seed skipped.")

    db.set_setting("company_name", db.COMPANY_NAME)
    db.set_setting("company_phone", db.get_setting("company_phone") or "(312) 555-0100")
    db.set_setting("company_email", db.get_setting("company_email") or "office@example.com")

    for n, (name, category, make, model, qty, rate, value, location) in enumerate(INVENTORY, start=1):
        db.insert("inventory_items", {
            "name": name, "category": category, "make": make, "model": model or None, "quantity": qty,
            "rental_rate": rate, "replacement_value": value, "location": location,
            "asset_tag": f"CSB-{n:04d}" if qty == 1 else None, "condition": "Good", "status": "active",
        })
    db.execute("UPDATE inventory_items SET status = 'maintenance', condition = 'Needs Repair', "
               "notes = 'Channel 2 crackle; at the amp tech since last week.' WHERE name = 'Vox AC30'")

    for name, role, email, phone, day, hourly, dietary in CREW:
        db.insert("crew", {"name": name, "role": role, "email": email, "phone": phone, "day_rate": day,
                           "hourly_rate": hourly, "dietary": dietary, "w9_on_file": 0 if name == "Sam Reyes" else 1})
    for name, company, email, phone in CLIENTS:
        db.insert("clients", {"name": name, "company": company, "email": email, "phone": phone})
    for v in VENUES:
        db.insert("venues", v)

    client = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM clients")}
    venue = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM venues")}
    today = util.today()
    day = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
    producer = _crew_id("Dana Kowalski")

    # 1. Corporate speaking program next week: confirmed, contract signed, deposit paid.
    corp = _event(title="Northbeam Q3 All-Hands", event_type="Corporate / Speaking", status="confirmed",
                  client_id=client["Priya Shah"], venue_id=venue["Fulton Market Event Loft"], producer_id=producer,
                  honorees="Priya Shah (host): handheld 1\nDr. Alana Brooks, CEO keynote: lav 1 (spare lav live at FOH)\n"
                           "Leadership panel (3): lavs 2-4\nAudience Q&A: aisle handhelds 5-6",
                  service_type="PA + engineer", setting="Indoor", guest_count=400, input_count=14, wireless_count=8,
                  monitor_mixes=1,
                  playback_feeds="Laptop playback via DI (walk-in, walk-out, video audio)\n"
                                 "2-ch record feed (XLR, line level) to Brightline Media's switcher",
                  event_date=day(5), load_in_time="07:00", soundcheck_time="09:30",
                  doors_time="10:30", start_time="11:00", end_time="15:00", load_out_time="15:30",
                  on_site_contact="Priya Shah", on_site_phone="(312) 555-0143", attire="Business casual, all black",
                  crew_meal="Boxed lunches at 12:00 PM in the green room",
                  audio_notes="PA covers 400 seated, two delay speakers at the back. Confidence wedge for the keynote.",
                  run_of_show=CORPORATE_RUN_OF_SHOW)
    _add_gear(corp, [("Allen & Heath SQ-6 console", 1), ("QSC K12.2 powered speaker", 4, "2 mains + 2 delays"),
                     ("QSC KS118 powered sub", 2), ("QSC K10.2 wedge", 1, "confidence wedge"),
                     ("Shure ULXD2 / Beta 58 handheld", 4), ("Shure SM58", 2, "podium + spare"),
                     ("Radial ProDI passive DI", 2, "laptop playback"), ("XLR cable 25'", 16), ("K&M boom mic stand", 4)])
    _add_gear(corp, [("Lavalier kits x4 (sub-rent)", 1, "Countryman B6 + ULXD1 packs; sub-rent from partner shop", "Wireless")])
    _add_crew(corp, "Maya Ortiz", "A1 / FOH", "07:00", confirmed=1)
    _add_crew(corp, "Chris Bell", "A2 / mic wrangler", "08:30", confirmed=1)
    _add_crew(corp, "Sam Reyes", "Stagehand", "07:00", hours=9, confirmed=1)
    _apply_type_checklists(corp, "Corporate / Speaking")
    _tick(corp, 11)
    _message(corp, "Maya Ortiz", "Brightline confirmed they want the record feed at line level on XLR. I'll bring two DI "
             "boxes in case their switcher only has unbalanced inputs.", 60 * 30)
    _contract(corp, "signed", deposit_due=day(-14), deposit_paid=(day(-18), "ACH / Bank Transfer", "NB-44120"))

    # 2. Dry hire: backline dropped off for a touring band's rehearsal day.
    rental = _event(title="The Midnight Arcade — rehearsal backline", event_type="Backline / Dry Hire",
                    status="confirmed", client_id=client["Leah Park"], venue_id=venue["Northside Rehearsal Studios"],
                    honorees="Leah Park (tour manager)", service_type="Dry hire (drop-off & pickup)", setting="Indoor",
                    event_date=day(8), end_date=day(9), load_in_time="10:00", load_out_time="12:00",
                    on_site_contact="Leah Park", on_site_phone="(312) 555-0147",
                    backline_notes="Drummer brings cymbals and pedal. Keys player wants the Nord with a sustain pedal.",
                    run_of_show="DELIVERY:\nRoom B, day 1 at 10:00 AM. Leah signs for the gear.\n\n"
                                "WALKTHROUGH:\nQuick demo of the Nord and SVT settings for the band's tech.\n\n"
                                "PICKUP:\nDay 2 at 12:00 PM from Room B.")
    _add_gear(rental, [("Ludwig Classic Maple 4-pc kit", 1), ("Drum hardware pack", 1), ("Snare drum 14x6.5", 1),
                       ("Fender '65 Twin Reverb", 1), ("Ampeg SVT-CL + SVT-810E", 1), ("Nord Stage 4 88", 1),
                       ("Keyboard stand (double X)", 1)])
    _add_crew(rental, "Jordan Pike", "Delivery + walkthrough", "09:00", confirmed=1)
    _apply_type_checklists(rental, "Backline / Dry Hire")
    _tick(rental, 7)
    _contract(rental, "signed", deposit_due=day(1), deposit_paid=(day(-3), "Zelle", None))

    # 3. Wedding with ceremony + reception, like a band's gig worksheet.
    wedding_date = _next_saturday(today + timedelta(days=10)).isoformat()
    wedding = _event(title="Alvarez / Reed Wedding", event_type="Wedding", status="confirmed",
                     client_id=client["Sofia Alvarez"], honorees="Sofia & Marcus", producer_id=producer,
                     service_type="Full production (PA, backline, crew)", setting="Indoor", guest_count=225,
                     input_count=24, wireless_count=4, monitor_mixes=6,
                     playback_feeds="DJ on console ch 31/32. Ceremony music from the FOH laptop.",
                     venue_id=venue["Riverbend Country Club"], venue_label="Reception",
                     venue2_id=venue["Maplewood Chapel"], venue2_label="Ceremony",
                     event_date=wedding_date, load_in_time="13:00", soundcheck_time="16:30", doors_time="16:30",
                     start_time="18:00", end_time="22:15", load_out_time="23:00",
                     performers="The Velvet Owls (8-pc) + DJ",
                     on_site_contact="Andrea (planner)", on_site_phone="(312) 555-0160",
                     attire="Strictly suit and tie: black suit and tie. No denim, t-shirts, sneakers or hats.",
                     crew_meal="Hot meal at 6:30 PM in the staff dining room (30 min)",
                     run_of_show=WEDDING_RUN_OF_SHOW,
                     crew_notes="Couple asked for no visible cable runs down the chapel aisle. Run under the runner and gaff "
                                "everything.\nMC duties are on the band leader; hand wireless 1 to them at 6:10 PM.\n"
                                "Toasts: father of the bride, then maid of honor. Wireless 2 at the head table.",
                     audio_notes="Ceremony: 2 wireless + small PA in the chapel. Reception: full band.",
                     backline_notes="Drummer brings snare + cymbals. Keys player needs 88-key weighted.")
    _add_gear(wedding, [("Midas M32 console", 1), ("QSC K12.2 powered speaker", 6, "2 go to the chapel"),
                        ("QSC KS118 powered sub", 2), ("QSC K10.2 wedge", 4),
                        ("Shure ULXD2 / Beta 58 handheld", 4, "officiant, reader, MC, toasts"),
                        ("Shure SM58", 6), ("Shure SM57", 4), ("Shure Beta 52A kick mic", 1),
                        ("Sennheiser e604 drum clip mic", 3), ("Radial J48 active DI", 4),
                        ("Fender '65 Twin Reverb", 1), ("Ampeg SVT-CL + SVT-810E", 1),
                        ("DW Collector's 5-pc kit", 1, "shell pack + hardware; no snare/cymbals"),
                        ("Nord Stage 4 88", 1), ("Keyboard stand (double X)", 1), ("XLR cable 25'", 30)])
    _add_crew(wedding, "Dana Kowalski", "Producer", "13:00", confirmed=1)
    _add_crew(wedding, "Maya Ortiz", "A1 / FOH (PA duty)", "13:00", confirmed=1)
    _add_crew(wedding, "Chris Bell", "Ceremony audio, then A2", "13:30")
    _add_crew(wedding, "Jordan Pike", "Backline Tech", "14:00")
    _add_crew(wedding, "Sam Reyes", "Stagehand", "13:00", hours=10)
    _apply_type_checklists(wedding, "Wedding")
    _tick(wedding, 6)
    _message(wedding, "Dana Kowalski", "Riverbend confirmed vendor access from 1:00 PM at the west service door. "
             "Crew parking is the gravel lot behind the maintenance building.", 60 * 26)
    _message(wedding, "Jordan Pike", "I'll bring the spare Twin in the van in case the guitarist's amp acts up.", 60 * 20)
    _message(wedding, "Office", "Reminder: black suit and tie for this one. No sneakers.", 90, crew=False)
    _contract(wedding, "sent", deposit_due=day(-2))
    _invoice(wedding, "draft", today, util.parse_date(wedding_date) - timedelta(days=14))

    # 4. Private party: small PA, DJ and toasts, indoor + roof deck.
    party = _event(title="Jamal's 40th Birthday", event_type="Private Party", status="confirmed",
                   client_id=client["Jamal Wright"], venue_id=venue["Pilsen Rooftop Loft"],
                   honorees="Jamal Wright (guest of honor)\nToasts: his sister Nia, then best friend Andre",
                   performers="DJ Kess", service_type="PA + engineer", setting="Indoor + outdoor", guest_count=120,
                   input_count=6, wireless_count=2,
                   playback_feeds="DJ controller into console ch 5/6. Backup playlist on the FOH laptop.",
                   event_date=day(22), load_in_time="16:00", soundcheck_time="18:00", doors_time="19:00",
                   start_time="19:00", end_time="23:30", load_out_time="00:30",
                   on_site_contact="Jamal Wright", on_site_phone="(773) 555-0146", attire="All black, casual",
                   crew_notes="Building quiet hours start at midnight: deck fills off at 11:30 PM sharp.")
    _add_gear(party, [("QSC K12.2 powered speaker", 2), ("QSC KS118 powered sub", 1),
                      ("Shure ULXD2 / Beta 58 handheld", 2, "toasts"), ("Radial J48 active DI", 1, "DJ"),
                      ("XLR cable 25'", 8)])
    _add_gear(party, [("Deck fill speakers (pair)", 1, "sub-rent; weather covers", "Speakers")])
    _add_crew(party, "Chris Bell", "A1 / PA duty", "16:00", confirmed=1)
    _apply_type_checklists(party, "Private Party")

    # 5 + 6. Festival hold overlapping a concert -> Twin Reverb conflict.
    fest = _event(title="Lakefront Harvest Festival — Stage 2", event_type="Festival / Outdoor", status="hold",
                  client_id=client["Lakefront Harvest Festival"], venue_id=venue["Lakefront Park Bandshell"],
                  producer_id=producer, honorees="Six bands per day; headliners TBA by the festival",
                  service_type="Full production (PA, backline, crew)", setting="Outdoor", guest_count=3000,
                  input_count=32, wireless_count=4, monitor_mixes=8,
                  event_date=day(26), end_date=day(28), load_in_time="08:00", start_time="12:00", end_time="22:00",
                  load_out_time="22:30", backline_notes="Shared backline for 6 bands/day. Per rider: 2x Twin, 1x SVT, 2 kits.")
    _add_gear(fest, [("JBL SRX835P 3-way", 4), ("QSC KS118 powered sub", 2), ("QSC K10.2 wedge", 6),
                     ("Midas M32 console", 1), ("Whirlwind 32x8 snake, 150'", 1), ("Fender '65 Twin Reverb", 2),
                     ("Ampeg SVT-CL + SVT-810E", 1), ("DW Collector's 5-pc kit", 1), ("Ludwig Classic Maple 4-pc kit", 1),
                     ("Drum riser 8x8", 2), ("Motion Labs 100A distro", 1)])
    _add_crew(fest, "Chris Bell", "A2 / Monitors", "08:00")
    _add_crew(fest, "Taylor Nguyen", "Drum Tech", "08:00")
    _apply_type_checklists(fest, "Festival / Outdoor")

    club = _event(title="The Velvet Owls — Blue Door Lounge", event_type="Live Concert", status="confirmed",
                  client_id=client["Ruby Carter"], venue_id=venue["Blue Door Lounge"], event_date=day(27),
                  honorees="The Velvet Owls (headliner)\nOpener: Paper Lanterns (duo)",
                  service_type="Backline + tech", setting="Indoor", guest_count=250, input_count=22, monitor_mixes=5,
                  load_in_time="17:00", soundcheck_time="18:00", doors_time="20:00", start_time="21:00",
                  end_time="23:30", load_out_time="23:45", backline_notes="Two guitarists want Twins. House PA and console.",
                  run_of_show="SET TIMES:\n- 5:00 PM  Load-in, backline set\n- 6:00 PM  Soundcheck: The Velvet Owls\n"
                              "- 7:00 PM  Soundcheck: Paper Lanterns\n- 8:00 PM  Doors\n- 8:30 PM  Paper Lanterns (30 min)\n"
                              "- 9:00 PM  Changeover (15 min)\n- 9:15 PM  The Velvet Owls (75 min)\n- 11:30 PM Curfew, strike")
    _add_gear(club, [("Fender '65 Twin Reverb", 2), ("Ampeg SVT-CL + SVT-810E", 1), ("Snare drum 14x6.5", 1),
                     ("Hammond XK-5 + Leslie 3300", 1)])
    _add_crew(club, "Jordan Pike", "Backline Tech", "17:00", confirmed=1)
    _apply_type_checklists(club, "Live Concert")
    _tick(club, 3)

    # 7. Past corporate show: paid in full; one stagehand still unpaid (overdue).
    launch = _event(title="Northbeam Product Launch", event_type="Corporate / Speaking", status="completed",
                    client_id=client["Priya Shah"], venue_id=venue["Fulton Market Event Loft"], producer_id=producer,
                    honorees="Product lead keynote: lav 1\nDemo team: headsets 2-3", service_type="PA + engineer",
                    setting="Indoor", guest_count=250, input_count=10, wireless_count=4, event_date=day(-24),
                    load_in_time="08:00", start_time="11:00", end_time="14:00", load_out_time="15:00")
    _add_gear(launch, [("Allen & Heath SQ-6 console", 1), ("QSC K12.2 powered speaker", 2),
                       ("Shure ULXD2 / Beta 58 handheld", 2)])
    db.execute("UPDATE event_gear SET pulled = 1, loaded = 1, returned = 1 WHERE event_id = ?", (launch,))
    _add_crew(launch, "Maya Ortiz", "A1 / FOH", "08:00", confirmed=1, paid=(day(-12), "ACH / Bank Transfer", "Payroll run"))
    _add_crew(launch, "Chris Bell", "A2 / mic wrangler", "08:30", confirmed=1, paid=(day(-12), "ACH / Bank Transfer", "Payroll run"))
    _add_crew(launch, "Sam Reyes", "Stagehand", "08:00", confirmed=1, hours=7, actual_hours=8.5)
    launch_contract = _contract(launch, "signed", deposit_due=day(-40), deposit_paid=(day(-41), "Check", "1187"))
    balance = services.create_contract_invoice(
        db.query("SELECT * FROM contracts WHERE id = ?", (launch_contract,), one=True), "balance", status="sent")
    db.insert("payments", {"invoice_id": balance, "paid_on": day(-20), "amount": float(services.invoice_totals(
        db.query("SELECT * FROM invoices WHERE id = ?", (balance,), one=True))["total"]), "method": "ACH / Bank Transfer"})

    # 8. Past show: gear partly not returned, invoice overdue.
    past = _event(title="Blue Door Showcase", event_type="Club / Bar Show", status="completed",
                  client_id=client["Ruby Carter"], venue_id=venue["Blue Door Lounge"], event_date=day(-10),
                  service_type="Backline only", load_in_time="17:00", start_time="20:00", end_time="23:00")
    _add_gear(past, [("Fender Hot Rod Deluxe", 2), ("Aguilar Tone Hammer 500 + DB410", 1), ("Ludwig Classic Maple 4-pc kit", 1),
                     ("Zildjian K cymbal pack", 1)])
    db.execute("UPDATE event_gear SET pulled = 1, loaded = 1, returned = 1 WHERE event_id = ?", (past,))
    db.execute("UPDATE event_gear SET returned = 0, return_notes = 'Cymbal bag missing at load-out; venue is checking.' "
               "WHERE event_id = ? AND item_id = ?", (past, _item("Zildjian K cymbal pack")))
    _add_crew(past, "Jordan Pike", "Backline Tech", "17:00", confirmed=1)
    _add_crew(past, "Taylor Nguyen", "Drum Tech", "17:00", confirmed=1, paid=(day(-8), "Zelle", None))
    _invoice(past, "sent", today - timedelta(days=9), today - timedelta(days=2))

    # 9. Gala inquiry with no details yet.
    _event(title="Lakeview Youth Arts Spring Gala", event_type="Fundraiser / Gala", status="inquiry",
           client_id=client["Lakeview Youth Arts Fund"], event_date=day(45), guest_count=300,
           service_type="Full production (PA, backline, crew)",
           notes="Asked for a quote: podium + 4 wireless for speakers and the auctioneer, jazz trio backline, dance set.")
