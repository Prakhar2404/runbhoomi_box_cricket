"""
Database management and operations for Runbhoomi Box Cricket.
Maintains relational SQLite tables locally with schema identical to Supabase PostgreSQL.
"""

import sqlite3
import hashlib
import datetime
import os
from .config import (
    DB_PATH,
    ADMIN_MOBILE,
    ADMIN_EMAIL,
    ADMIN_DEFAULT_PASSWORD,
    SLOT_HOLD_MINUTES,
    CLEANING_LIGHTING_NOTICE
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def init_db():
    """Initializes all 10 relational tables and seeds default master data with strict keys & constraints."""
    conn = get_db()
    cursor = conn.cursor()

    # 1. Users table (Admin, Partners, Customers)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL CHECK (length(phone) >= 10),
        name TEXT NOT NULL,
        email TEXT,
        age INTEGER CHECK (age >= 6 AND age <= 99),
        gender TEXT DEFAULT 'Male' CHECK (gender IN ('Male', 'Female', 'Other')),
        role TEXT DEFAULT 'customer' CHECK (role IN ('customer', 'partner', 'admin')),
        avatar_url TEXT,
        password_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Sports table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        icon_name TEXT DEFAULT 'cricket',
        min_players INTEGER DEFAULT 10 CHECK (min_players > 0),
        max_players INTEGER DEFAULT 16 CHECK (max_players >= min_players),
        is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 3. Dynamic Pricing Rules
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pricing_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sport_id INTEGER NOT NULL,
        day_type TEXT NOT NULL CHECK (day_type IN ('weekday', 'weekend')),
        time_slot_label TEXT NOT NULL,
        start_hour INTEGER NOT NULL CHECK (start_hour >= 0 AND start_hour <= 23),
        end_hour INTEGER NOT NULL CHECK (end_hour >= 1 AND end_hour <= 24),
        hourly_rate REAL NOT NULL CHECK (hourly_rate >= 0),
        floodlight_charge REAL DEFAULT 0 CHECK (floodlight_charge >= 0),
        FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE CASCADE,
        UNIQUE(sport_id, day_type, start_hour, end_hour)
    )
    """)

    # 4. Held Slots table (10-minute hold lock during checkout)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS held_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sport_id INTEGER NOT NULL,
        slot_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        hold_token TEXT UNIQUE NOT NULL,
        customer_phone TEXT,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE CASCADE,
        UNIQUE(sport_id, slot_date, start_time)
    )
    """)

    # 5. Bookings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_ref TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        sport_id INTEGER NOT NULL,
        booking_date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        duration_hours REAL NOT NULL CHECK (duration_hours > 0),
        base_rate REAL NOT NULL CHECK (base_rate >= 0),
        floodlight_charge REAL DEFAULT 0 CHECK (floodlight_charge >= 0),
        discount_amount REAL DEFAULT 0 CHECK (discount_amount >= 0),
        promo_code TEXT,
        total_amount REAL NOT NULL CHECK (total_amount >= 0),
        advance_paid REAL NOT NULL CHECK (advance_paid >= 0),
        balance_due REAL NOT NULL CHECK (balance_due >= 0),
        payment_type TEXT NOT NULL CHECK (payment_type IN ('50_percent_token', '100_percent_full')),
        payment_status TEXT NOT NULL CHECK (payment_status IN ('pending_proof', 'in_process', 'verified', 'cancelled')),
        booking_status TEXT NOT NULL CHECK (booking_status IN ('in_process', 'confirmed', 'cancelled', 'completed')),
        screenshot_url TEXT,
        cancellation_fee REAL DEFAULT 0 CHECK (cancellation_fee >= 0),
        future_credit_code TEXT,
        confirmed_by TEXT,
        confirmed_at TIMESTAMP,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE RESTRICT,
        FOREIGN KEY(sport_id) REFERENCES sports(id) ON DELETE RESTRICT
    )
    """)

    # 6. Canteen Items Catalog
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS canteen_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL CHECK (category IN ('beverages', 'snacks', 'eggs', 'mocktails', 'smokes', 'energy_sports', 'gear_rental', 'drinks', 'electrolytes')),
        price REAL NOT NULL CHECK (price >= 0),
        stock INTEGER DEFAULT 100 CHECK (stock >= 0),
        is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 7. Booking Canteen Orders (Running Tab)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS booking_canteen_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        unit_price REAL NOT NULL CHECK (unit_price >= 0),
        total_price REAL NOT NULL CHECK (total_price >= 0),
        added_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
        FOREIGN KEY(item_id) REFERENCES canteen_items(id) ON DELETE RESTRICT
    )
    """)

    # 8. Promotional Offers Engine
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promo_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        offer_type TEXT NOT NULL CHECK (offer_type IN ('percent', 'flat', 'free_product')),
        discount_value REAL DEFAULT 0 CHECK (discount_value >= 0),
        min_booking_amount REAL DEFAULT 0 CHECK (min_booking_amount >= 0),
        free_item_id INTEGER,
        is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(free_item_id) REFERENCES canteen_items(id) ON DELETE SET NULL
    )
    """)

    # 9. Cancellation Credits (25% Future Credit)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cancellation_credits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER NOT NULL,
        phone TEXT NOT NULL,
        promo_code TEXT UNIQUE NOT NULL,
        discount_percent REAL DEFAULT 25.0 CHECK (discount_percent >= 0 AND discount_percent <= 100),
        retained_fee REAL NOT NULL CHECK (retained_fee >= 0),
        is_redeemed INTEGER DEFAULT 0 CHECK (is_redeemed IN (0, 1)),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE
    )
    """)

    # 10. Partners Table (Max 2 Allowed)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS partners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL CHECK (length(phone) >= 10),
        email TEXT,
        password_hash TEXT NOT NULL,
        is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Performance & Lookup Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sports_slug ON sports(slug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_ref ON bookings(booking_ref)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date, sport_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(booking_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_held_slots_expiry ON held_slots(expires_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_canteen_category ON canteen_items(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_canteen_orders_booking ON booking_canteen_orders(booking_id)")

    conn.commit()
    seed_master_data(conn)
    conn.close()

def seed_master_data(conn):
    cursor = conn.cursor()

    # 1. Ensure Primary Admin Aditya Goyal
    admin_hash = hash_password(ADMIN_DEFAULT_PASSWORD)
    cursor.execute("SELECT id FROM users WHERE phone = ?", (ADMIN_MOBILE,))
    admin = cursor.fetchone()
    if not admin:
        cursor.execute("""
        INSERT INTO users (phone, name, email, age, gender, role, password_hash)
        VALUES (?, 'ADITYA GOYAL', ?, 28, 'Male', 'admin', ?)
        """, (ADMIN_MOBILE, ADMIN_EMAIL, admin_hash))
    else:
        cursor.execute("""
        UPDATE users SET role = 'admin', name = 'ADITYA GOYAL', password_hash = ? WHERE phone = ?
        """, (admin_hash, ADMIN_MOBILE))

    # 2. Seed Default Sports
    sports_data = [
        ("Box Cricket", "box-cricket", "High-intensity turf cricket with synthetic grass and tension boundary netting", "cricket", 10, 16),
        ("5v5 Football", "football-5v5", "Fast-paced mini football with shock-absorbing turf and boundary walls", "football", 10, 14),
        ("Badminton", "badminton", "Tournament-grade synthetic turf badminton court with high-lux LED illumination", "badminton", 2, 4),
        ("Kabaddi", "kabaddi", "Dynamic high-traction mat & turf court with high impact padding", "kabaddi", 14, 18),
        ("Volleyball", "volleyball", "All-weather turf court with adjustable competition net", "volleyball", 10, 14),
    ]

    for name, slug, desc, icon, min_p, max_p in sports_data:
        cursor.execute("SELECT id FROM sports WHERE slug = ?", (slug,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO sports (name, slug, description, icon_name, min_players, max_players)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (name, slug, desc, icon, min_p, max_p))

    # 3. Dynamic Pricing Rules
    cursor.execute("SELECT id, slug FROM sports")
    sports_map = {row["slug"]: row["id"] for row in cursor.fetchall()}

    pricing_presets = {
        "box-cricket": [
            ("weekday", "day", 6, 18, 800.0, 0.0),
            ("weekday", "floodlight_night", 18, 24, 1200.0, 300.0),
            ("weekend", "day", 6, 18, 1000.0, 0.0),
            ("weekend", "floodlight_night", 18, 24, 1400.0, 400.0),
        ],
        "football-5v5": [
            ("weekday", "day", 6, 18, 900.0, 0.0),
            ("weekday", "floodlight_night", 18, 24, 1300.0, 300.0),
            ("weekend", "day", 6, 18, 1100.0, 0.0),
            ("weekend", "floodlight_night", 18, 24, 1500.0, 400.0),
        ],
        "badminton": [
            ("weekday", "day", 6, 18, 400.0, 0.0),
            ("weekday", "floodlight_night", 18, 24, 600.0, 150.0),
            ("weekend", "day", 6, 18, 500.0, 0.0),
            ("weekend", "floodlight_night", 18, 24, 750.0, 200.0),
        ],
        "kabaddi": [
            ("weekday", "day", 6, 18, 500.0, 0.0),
            ("weekday", "floodlight_night", 18, 24, 750.0, 200.0),
            ("weekend", "day", 6, 18, 650.0, 0.0),
            ("weekend", "floodlight_night", 18, 24, 900.0, 250.0),
        ],
        "volleyball": [
            ("weekday", "day", 6, 18, 500.0, 0.0),
            ("weekday", "floodlight_night", 18, 24, 750.0, 200.0),
            ("weekend", "day", 6, 18, 650.0, 0.0),
            ("weekend", "floodlight_night", 18, 24, 900.0, 250.0),
        ],
    }

    for slug, rules in pricing_presets.items():
        s_id = sports_map.get(slug)
        if s_id:
            cursor.execute("SELECT COUNT(*) FROM pricing_rules WHERE sport_id = ?", (s_id,))
            if cursor.fetchone()[0] == 0:
                for day_t, slot_l, sh, eh, rate, flood in rules:
                    cursor.execute("""
                    INSERT INTO pricing_rules (sport_id, day_type, time_slot_label, start_hour, end_hour, hourly_rate, floodlight_charge)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (s_id, day_t, slot_l, sh, eh, rate, flood))

    # 4. Seed In-House Canteen Items (Fresh Food, Beverages, Eggs & Snacks)
    canteen_presets = [
        # Customer Requested Fresh Kitchen & Beverages
        ("Water Bottle (1L Chilled Pure)", "beverages", 10.0, 200),
        ("Cold Drinks (Assorted Chilled)", "beverages", 20.0, 150),
        ("Special Chai", "beverages", 20.0, 100),
        ("Boiled Eggs (2 Eggs)", "eggs", 25.0, 100),
        ("1 Egg Omelette", "eggs", 35.0, 100),
        ("2 Egg Omelette", "eggs", 50.0, 100),
        ("1 Butter Egg Omelette", "eggs", 45.0, 100),
        ("2 Butter Egg Omelette", "eggs", 70.0, 100),
        ("1 Egg Bhurji", "eggs", 35.0, 100),
        ("1 Butter Egg Bhurji", "eggs", 50.0, 100),
        ("2 Egg Bhurji", "eggs", 50.0, 100),
        ("2 Butter Egg Bhurji", "eggs", 70.0, 100),
        ("1 Egg Half Fry", "eggs", 30.0, 100),
        ("1 Butter Egg Half Fry", "eggs", 40.0, 100),
        ("2 Egg Half Fry", "eggs", 50.0, 100),
        ("2 Butter Egg Half Fry", "eggs", 70.0, 100),
        ("Classic Maggie", "snacks", 60.0, 80),
        ("Butter Maggie", "snacks", 75.0, 80),
        ("Classic Pasta", "snacks", 60.0, 60),
        ("Butter Pasta", "snacks", 75.0, 60),
        ("Bun Maska", "snacks", 25.0, 80),
        ("Double Bun Maska", "snacks", 40.0, 80),
        ("Crispy Patties", "snacks", 30.0, 80),
        ("French Fries (Crispy Salted)", "snacks", 40.0, 80),
        ("Virgin Mojito", "mocktails", 50.0, 80),
        ("Blue Lagoon Mocktail", "mocktails", 50.0, 80),
        ("Cigarette (Regular - Rs 20)", "smokes", 20.0, 100),
        ("Cigarette (Gold / Lights - Rs 25)", "smokes", 25.0, 100),
        ("Cigarette (Premium King - Rs 30)", "smokes", 30.0, 100),
        # Sports Energy & Gear Rental
        ("Sting Energy Berry Blast 250ml", "energy_sports", 30.0, 120),
        ("Red Bull Energy Drink 250ml", "energy_sports", 125.0, 60),
        ("Gatorade Blue Bolt Electrolyte 500ml", "energy_sports", 60.0, 80),
        ("Professional Kashmir Willow Bat Rental", "gear_rental", 150.0, 8),
        ("Hard Tennis Match Cricket Ball", "gear_rental", 90.0, 40),
        ("Competition Football Match Ball Rental", "gear_rental", 100.0, 5),
    ]

    for name, cat, price, stock in canteen_presets:
        cursor.execute("SELECT id FROM canteen_items WHERE name = ?", (name,))
        existing_item = cursor.fetchone()
        if not existing_item:
            cursor.execute("""
            INSERT INTO canteen_items (name, category, price, stock)
            VALUES (?, ?, ?, ?)
            """, (name, cat, price, stock))
        else:
            cursor.execute("""
            UPDATE canteen_items SET category = ?, price = ? WHERE id = ?
            """, (cat, price, existing_item[0]))

    # 5. Seed Promotional Offers
    cursor.execute("SELECT id FROM canteen_items WHERE name LIKE 'Sting%' LIMIT 1")
    sting_item = cursor.fetchone()
    sting_id = sting_item[0] if sting_item else None

    promo_presets = [
        ("RUN10", "Flat 10% Off Match Booking", "percent", 10.0, 1000.0, None),
        ("TURF200", "Flat Rs 200 Instant Discount", "flat", 200.0, 1500.0, None),
        ("FREEENERGY", "Free Sting Energy Drink on Match > Rs 1,200", "free_product", 0.0, 1200.0, sting_id),
    ]

    for code, title, o_type, disc, min_amt, f_item in promo_presets:
        cursor.execute("SELECT id FROM promo_offers WHERE code = ?", (code,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO promo_offers (code, title, offer_type, discount_value, min_booking_amount, free_item_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (code, title, o_type, disc, min_amt, f_item))

    # 6. Seed Realistic Verified Customer Accounts (Password min 6 chars)
    sample_customers = [
        ("9876543210", "Rahul Sharma", "rahul.sharma@gmail.com", 24, "Male", "rahul@123"),
        ("9823456781", "Amit Verma", "amit.verma@yahoo.com", 28, "Male", "amit@123"),
        ("9811223344", "Rohit Sen", "rohit.sen@gmail.com", 26, "Male", "rohit@123"),
        ("9833445566", "Priya Patel", "priya.patel@outlook.com", 22, "Female", "priya@123"),
        ("9855544433", "Sameer Khan", "sameer.khan@gmail.com", 23, "Male", "sameer@123"),
        ("9812345678", "Vikram Rathore", "vikram.rathore@gmail.com", 29, "Male", "vikram@123"),
    ]

    for phone, name, email, age, gender, raw_pwd in sample_customers:
        cursor.execute("SELECT id FROM users WHERE phone = ?", (phone,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO users (phone, name, email, age, gender, role, password_hash)
            VALUES (?, ?, ?, ?, ?, 'customer', ?)
            """, (phone, name, email, age, gender, hash_password(raw_pwd)))

    conn.commit()


# Clean up expired slot holds
def cleanup_expired_holds():
    conn = get_db()
    conn.execute("DELETE FROM held_slots WHERE expires_at < CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()

