-- Backline Ops schema (SQLite)

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    company TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS venues (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    contact_name TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    load_in_notes TEXT,
    power_notes TEXT,
    parking_notes TEXT,
    stage_notes TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crew (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT,
    email TEXT,
    phone TEXT,
    day_rate REAL,
    hourly_rate REAL,
    notes TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    make TEXT,
    model TEXT,
    serial_number TEXT,
    asset_tag TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    condition TEXT NOT NULL DEFAULT 'Good',
    status TEXT NOT NULL DEFAULT 'active',      -- active | maintenance | retired
    location TEXT,
    purchase_date TEXT,
    purchase_price REAL,
    replacement_value REAL,
    rental_rate REAL,                            -- per day
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    reference_number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    event_type TEXT,
    status TEXT NOT NULL DEFAULT 'inquiry',      -- inquiry | hold | confirmed | completed | cancelled
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    venue_id INTEGER REFERENCES venues(id) ON DELETE SET NULL,
    event_date TEXT NOT NULL,                    -- YYYY-MM-DD
    end_date TEXT,                               -- YYYY-MM-DD, multi-day events
    load_in_time TEXT,
    soundcheck_time TEXT,
    doors_time TEXT,
    start_time TEXT,
    end_time TEXT,
    load_out_time TEXT,
    performers TEXT,
    on_site_contact TEXT,
    on_site_phone TEXT,
    attire TEXT,
    parking TEXT,
    audio_notes TEXT,
    backline_notes TEXT,
    power_notes TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);

CREATE TABLE IF NOT EXISTS event_crew (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    crew_id INTEGER NOT NULL REFERENCES crew(id) ON DELETE CASCADE,
    role TEXT,
    call_time TEXT,
    pay_type TEXT NOT NULL DEFAULT 'flat',       -- flat | hourly
    pay_rate REAL,
    hours REAL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    worksheet_key TEXT NOT NULL UNIQUE
);

-- Audio / backline needs for an event. item_id is NULL for sub-rentals or
-- anything not tracked in inventory. pulled/loaded/returned drive the
-- warehouse checklist.
CREATE TABLE IF NOT EXISTS event_gear (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    item_id INTEGER REFERENCES inventory_items(id) ON DELETE SET NULL,
    description TEXT,
    category TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    rate REAL,
    notes TEXT,
    pulled INTEGER NOT NULL DEFAULT 0,
    loaded INTEGER NOT NULL DEFAULT 0,
    returned INTEGER NOT NULL DEFAULT 0,
    return_notes TEXT,
    sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS checklist_templates (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS checklist_template_items (
    id INTEGER PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES checklist_templates(id) ON DELETE CASCADE,
    section TEXT,
    text TEXT NOT NULL,
    sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_checklist_items (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    section TEXT,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    done_by TEXT,
    done_at TEXT,
    sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',        -- draft | sent | signed | void
    body TEXT NOT NULL,
    total_amount REAL NOT NULL DEFAULT 0,
    deposit_amount REAL NOT NULL DEFAULT 0,
    deposit_due_date TEXT,
    balance_due_date TEXT,
    public_key TEXT NOT NULL UNIQUE,
    sent_at TEXT,
    signed_at TEXT,
    signed_name TEXT,
    signed_ip TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'draft',        -- draft | sent | void (paid/partial/overdue are derived)
    issue_date TEXT NOT NULL,
    due_date TEXT,
    tax_rate REAL NOT NULL DEFAULT 0,            -- percent
    discount REAL NOT NULL DEFAULT 0,            -- flat amount
    notes TEXT,
    terms TEXT,
    public_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 1,
    unit_price REAL NOT NULL DEFAULT 0,
    taxable INTEGER NOT NULL DEFAULT 1,
    sort INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    paid_on TEXT NOT NULL,
    amount REAL NOT NULL,
    method TEXT,
    reference TEXT,
    notes TEXT
);
