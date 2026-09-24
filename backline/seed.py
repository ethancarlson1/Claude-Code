"""Demo data: a small audio/backline shop with a few weeks of bookings.
Dates are relative to today so the demo always looks current."""

from datetime import timedelta

from . import db, services, util

INVENTORY = [
    # name, category, make, model, qty, rate/day, replacement value, location
    ("Midas M32 console", "Consoles", "Midas", "M32", 1, 250, 4500, "Shop — Console cage"),
    ("Allen & Heath SQ-6 console", "Consoles", "Allen & Heath", "SQ-6", 1, 225, 5000, "Shop — Console cage"),
    ("QSC K12.2 powered speaker", "Speakers", "QSC", "K12.2", 8, 60, 900, "Shop — Bay 1"),
    ("QSC KS118 powered sub", "Speakers", "QSC", "KS118", 4, 85, 1600, "Shop — Bay 1"),
    ("JBL SRX835P 3-way", "Speakers", "JBL", "SRX835P", 4, 150, 3000, "Shop — Bay 1"),
    ("QSC K10.2 wedge", "Monitors", "QSC", "K10.2", 6, 45, 750, "Shop — Bay 2"),
    ("Shure PSM1000 IEM system", "Wireless", "Shure", "PSM1000", 4, 120, 3500, "Shop — Wireless rack"),
    ("Shure ULXD2 / Beta 58 handheld", "Wireless", "Shure", "ULXD2/B58", 8, 65, 1500, "Shop — Wireless rack"),
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
    ("Maya Ortiz", "A1 / FOH Engineer", "maya@example.com", "(555) 201-3344", 450, None),
    ("Chris Bell", "A2 / Monitors", "chris@example.com", "(555) 201-8812", 350, None),
    ("Jordan Pike", "Backline Tech", "jordan@example.com", "(555) 201-4467", 300, None),
    ("Taylor Nguyen", "Drum Tech", "taylor@example.com", "(555) 201-9021", 300, None),
    ("Sam Reyes", "Stagehand", "sam@example.com", "(555) 201-5530", None, 28),
]

CLIENTS = [
    ("Daniel Lange", None, "daniel.lange@example.com", "(555) 310-2210"),
    ("Priya Shah", "Northbeam Corporate Events", "priya@northbeam.example.com", "(555) 310-4418"),
    ("Harbor Lights Festival", "Harbor Lights Music Festival LLC", "production@harborlights.example.com", "(555) 310-7702"),
    ("Ruby Carter", "The Velvet Owls", "ruby@velvetowls.example.com", "(555) 310-9934"),
]

VENUES = [
    dict(name="The Grand Ballroom at Bayview", address="100 Harbor Way", city="Bayview", state="CA", postal_code="94000",
         contact_name="Luis Ramos (banquet captain)", contact_phone="(555) 400-1200",
         load_in_notes="Loading dock B off Pier St. Freight elevator to 2nd floor, 20 min push.",
         power_notes="Two 20A circuits stage left, 60A 1-phase disconnect behind stage right drape.",
         parking_notes="Vendor parking in garage level P2; validate at front desk."),
    dict(name="Riverside Amphitheater", address="4500 River Rd", city="Riverton", state="CA", postal_code="94100",
         contact_name="Dana Wu (production manager)", contact_phone="(555) 400-3300",
         load_in_notes="Truck access via service gate 3. Stage is ground level with ramp.",
         power_notes="400A 3-phase company switch, cam-lok.", stage_notes="40' x 32' stage with roof. House PA not included."),
    dict(name="Blue Door Club", address="22 Market St", city="Bayview", state="CA", postal_code="94001",
         contact_name="Eli (GM)", contact_phone="(555) 400-7788",
         load_in_notes="Front door load-in only, 3 steps. Street loading zone after 4 PM.",
         stage_notes="16' x 12' stage. House console is Midas M32 — backline only unless noted."),
]


def _item(name):
    return db.scalar("SELECT id FROM inventory_items WHERE name = ?", (name,))


def _add_gear(event_id, items):
    for sort, (name, qty, *rest) in enumerate(items):
        item = db.query("SELECT * FROM inventory_items WHERE name = ?", (name,), one=True)
        row = {"event_id": event_id, "quantity": qty, "sort": sort, "notes": rest[0] if rest else None}
        if item:
            row.update(item_id=item["id"], rate=item["rental_rate"])
        else:
            row.update(description=name, category="Keyboards", rate=None)
        db.insert("event_gear", row)


def _add_crew(event_id, name, role, call, **extra):
    member = db.query("SELECT * FROM crew WHERE name = ?", (name,), one=True)
    pay_type = "hourly" if member["hourly_rate"] and not member["day_rate"] else "flat"
    db.insert("event_crew", {
        "event_id": event_id, "crew_id": member["id"], "role": role, "call_time": call,
        "pay_type": pay_type, "pay_rate": member["hourly_rate"] if pay_type == "hourly" else member["day_rate"],
        "hours": extra.get("hours"), "confirmed": extra.get("confirmed", 0), "worksheet_key": util.gen_key(),
    })


def _event(**values):
    client = db.query("SELECT name FROM clients WHERE id = ?", (values.get("client_id"),), one=True)
    values["reference_number"] = util.gen_reference(values["event_date"], client and client["name"], values["title"])
    return db.insert("events", values)


def _tick(event_id, count):
    ids = [r["id"] for r in db.query(
        "SELECT id FROM event_checklist_items WHERE event_id = ? ORDER BY sort LIMIT ?", (event_id, count))]
    for i in ids:
        db.update("event_checklist_items", i, {"done": 1, "done_by": "demo", "done_at": util.now_iso()})


def _contract(event_id, status, deposit_pct=50):
    event = db.query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
    total = services.gear_total(event)
    deposit = util.round_money(total * deposit_pct / 100)
    number = services.next_number("contracts", db.get_setting("contract_prefix"))
    balance_due = (util.parse_date(event["event_date"]) - timedelta(days=7)).isoformat()
    body = services.render_contract(db.get_setting("contract_template"), event, number, total, deposit, None, balance_due)
    row = {"event_id": event_id, "number": number, "title": "Equipment Rental & Production Services Agreement",
           "status": status, "body": body, "total_amount": float(total), "deposit_amount": float(deposit),
           "balance_due_date": balance_due, "public_key": util.gen_key(18)}
    if status in ("sent", "signed"):
        row["sent_at"] = util.now_iso()
    if status == "signed":
        client = db.query("SELECT c.name FROM clients c JOIN events e ON e.client_id = c.id WHERE e.id = ?",
                          (event_id,), one=True)
        row.update(signed_at=util.now_iso(), signed_name=client["name"], signed_ip="203.0.113.10")
    return db.insert("contracts", row)


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


def seed():
    if db.scalar("SELECT COUNT(*) FROM events") or db.scalar("SELECT COUNT(*) FROM inventory_items"):
        raise SystemExit("Database already has data; demo seed skipped.")

    if db.get_setting("company_name") == db.DEFAULT_SETTINGS["company_name"]:
        db.set_setting("company_name", "Coastal Audio & Backline")
    db.set_setting("company_phone", db.get_setting("company_phone") or "(555) 100-2000")
    db.set_setting("company_email", db.get_setting("company_email") or "bookings@coastalaudio.example.com")
    db.set_setting("company_address", db.get_setting("company_address") or "850 Warehouse Row, Unit 4\nBayview, CA 94002")

    for n, (name, category, make, model, qty, rate, value, location) in enumerate(INVENTORY, start=1):
        db.insert("inventory_items", {
            "name": name, "category": category, "make": make, "model": model or None, "quantity": qty,
            "rental_rate": rate, "replacement_value": value, "location": location,
            "asset_tag": f"CA-{n:04d}" if qty == 1 else None, "condition": "Good", "status": "active",
        })
    db.execute("UPDATE inventory_items SET status = 'maintenance', condition = 'Needs Repair', "
               "notes = 'Channel 2 crackle; at amp tech since last week.' WHERE name = 'Vox AC30'")

    for name, role, email, phone, day, hourly in CREW:
        db.insert("crew", {"name": name, "role": role, "email": email, "phone": phone, "day_rate": day, "hourly_rate": hourly})
    for name, company, email, phone in CLIENTS:
        db.insert("clients", {"name": name, "company": company, "email": email, "phone": phone})
    for v in VENUES:
        db.insert("venues", v)

    client = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM clients")}
    venue = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM venues")}
    templates = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM checklist_templates")}
    today = util.today()
    day = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731

    # 1. Corporate event next week: confirmed, contract signed, deposit paid.
    corp = _event(title="Northbeam Q3 All-Hands", event_type="Corporate", status="confirmed",
                  client_id=client["Priya Shah"], venue_id=venue["The Grand Ballroom at Bayview"],
                  event_date=day(5), load_in_time="07:00", soundcheck_time="09:30", doors_time="10:30",
                  start_time="11:00", end_time="15:00", load_out_time="15:30",
                  on_site_contact="Priya Shah", on_site_phone="(555) 310-4418", attire="Business casual, all black",
                  audio_notes="Podium mic + 4 wireless handhelds for Q&A. Playback from laptop via DI.\nPA covers 400 seated.")
    _add_gear(corp, [("Allen & Heath SQ-6 console", 1), ("QSC K12.2 powered speaker", 4), ("QSC KS118 powered sub", 2),
                     ("Shure ULXD2 / Beta 58 handheld", 4), ("Shure SM58", 2, "podium"), ("Radial ProDI passive DI", 2),
                     ("XLR cable 25'", 16), ("K&M boom mic stand", 4)])
    _add_crew(corp, "Maya Ortiz", "A1 / FOH", "07:00", confirmed=1)
    _add_crew(corp, "Sam Reyes", "Stagehand", "07:00", hours=9, confirmed=1)
    for name in ("Advance & Prep", "Show Day"):
        services.apply_checklist_template(corp, templates[name])
    _tick(corp, 11)
    _contract(corp, "signed")
    _invoice(corp, "sent", today - timedelta(days=20), today + timedelta(days=5),
             payments=[(today - timedelta(days=18), 800, "ACH / Bank Transfer")])

    # 2. Wedding (mirrors a typical band worksheet): confirmed, contract out for signature.
    wedding = _event(title="Lange / Daniel Wedding", event_type="Wedding", status="confirmed",
                     client_id=client["Daniel Lange"], venue_id=venue["The Grand Ballroom at Bayview"],
                     event_date=day(12), load_in_time="14:00", soundcheck_time="16:00", doors_time="17:30",
                     start_time="18:00", end_time="23:00", load_out_time="23:15", performers="The Velvet Owls (8-pc)",
                     on_site_contact="Andrea (planner)", on_site_phone="(555) 777-1122", attire="Black suit / black dress",
                     parking="Load in through dock B before 3 PM; ceremony starts 5:00 on the lawn — stay out of sightlines.",
                     audio_notes="Ceremony: 2 wireless + small PA on lawn. Reception: full band, 12 inputs, 4 mixes.",
                     backline_notes="Drummer brings snare + cymbals. Keys player needs 88-key weighted.")
    _add_gear(wedding, [("Midas M32 console", 1), ("QSC K12.2 powered speaker", 4), ("QSC KS118 powered sub", 2),
                        ("QSC K10.2 wedge", 4), ("Shure ULXD2 / Beta 58 handheld", 2, "ceremony officiant + toasts"),
                        ("Shure SM58", 6), ("Shure SM57", 4), ("Shure Beta 52A kick mic", 1),
                        ("Sennheiser e604 drum clip mic", 3), ("Radial J48 active DI", 4),
                        ("Fender '65 Twin Reverb", 1), ("Ampeg SVT-CL + SVT-810E", 1),
                        ("DW Collector's 5-pc kit", 1, "shell pack + hardware; no snare/cymbals"),
                        ("Nord Stage 4 88", 1), ("Keyboard stand (double X)", 1), ("XLR cable 25'", 30)])
    _add_crew(wedding, "Maya Ortiz", "A1 / FOH", "14:00", confirmed=1)
    _add_crew(wedding, "Jordan Pike", "Backline Tech", "14:00")
    _add_crew(wedding, "Sam Reyes", "Stagehand", "14:00", hours=10)
    services.apply_checklist_template(wedding, templates["Advance & Prep"])
    _tick(wedding, 6)
    _contract(wedding, "sent")
    _invoice(wedding, "draft", today, util.parse_date(day(5)))

    # 3 + 4. Festival hold overlapping a club gig -> Twin Reverb conflict.
    fest = _event(title="Harbor Lights Music Festival — Stage 2", event_type="Festival", status="hold",
                  client_id=client["Harbor Lights Festival"], venue_id=venue["Riverside Amphitheater"],
                  event_date=day(26), end_date=day(28), load_in_time="08:00", start_time="12:00", end_time="22:00",
                  load_out_time="22:30", backline_notes="Shared backline for 6 bands/day. Per rider: 2x Twin, 1x SVT, 2 kits.")
    _add_gear(fest, [("JBL SRX835P 3-way", 4), ("QSC KS118 powered sub", 2), ("QSC K10.2 wedge", 6),
                     ("Midas M32 console", 1), ("Whirlwind 32x8 snake, 150'", 1), ("Fender '65 Twin Reverb", 2),
                     ("Ampeg SVT-CL + SVT-810E", 1), ("DW Collector's 5-pc kit", 1), ("Ludwig Classic Maple 4-pc kit", 1),
                     ("Drum riser 8x8", 2), ("Motion Labs 100A distro", 1)])
    _add_crew(fest, "Chris Bell", "A2 / Monitors", "08:00")
    _add_crew(fest, "Taylor Nguyen", "Drum Tech", "08:00")
    services.apply_checklist_template(fest, templates["Advance & Prep"])

    club = _event(title="The Velvet Owls — Blue Door", event_type="Club Night", status="confirmed",
                  client_id=client["Ruby Carter"], venue_id=venue["Blue Door Club"], event_date=day(27),
                  load_in_time="17:00", soundcheck_time="18:00", doors_time="20:00", start_time="21:00",
                  end_time="23:30", load_out_time="23:45", backline_notes="Two guitarists want Twins.")
    _add_gear(club, [("Fender '65 Twin Reverb", 2), ("Ampeg SVT-CL + SVT-810E", 1), ("Snare drum 14x6.5", 1),
                     ("Hammond XK-5 + Leslie 3300", 1)])
    _add_crew(club, "Jordan Pike", "Backline Tech", "17:00", confirmed=1)
    services.apply_checklist_template(club, templates["Advance & Prep"])
    _tick(club, 3)

    # 5. Past show: gear partly not returned, invoice overdue.
    past = _event(title="Blue Door Showcase", event_type="Club Night", status="completed",
                  client_id=client["Ruby Carter"], venue_id=venue["Blue Door Club"], event_date=day(-10),
                  load_in_time="17:00", start_time="20:00", end_time="23:00")
    _add_gear(past, [("Fender Hot Rod Deluxe", 2), ("Aguilar Tone Hammer 500 + DB410", 1), ("Ludwig Classic Maple 4-pc kit", 1),
                     ("Zildjian K cymbal pack", 1)])
    db.execute("UPDATE event_gear SET pulled = 1, loaded = 1, returned = 1 WHERE event_id = ?", (past,))
    db.execute("UPDATE event_gear SET returned = 0, return_notes = 'Cymbal bag missing at load-out — venue checking.' "
               "WHERE event_id = ? AND item_id = ?", (past, _item("Zildjian K cymbal pack")))
    _add_crew(past, "Jordan Pike", "Backline Tech", "17:00", confirmed=1)
    _invoice(past, "sent", today - timedelta(days=9), today - timedelta(days=2))

    # 6. Inquiry with no details yet.
    _event(title="Spring Gala", event_type="Private Party", status="inquiry", client_id=client["Priya Shah"],
           event_date=day(45), notes="Asked for a quote on PA + 3-pc jazz backline.")
