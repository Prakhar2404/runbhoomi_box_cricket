"""
Runbhoomi Box Cricket - Dedicated Admin & Partner Operations Desk
Corporate Legal Entity: Runbhoomi Box Cricket Pvt. Ltd.
Runs on Port 5001 (e.g. admin.runbhoomi.com / partner.runbhoomi.com)
Strictly for Primary Owner Aditya Goyal and Authorized Arena Partners.
Zero customer registration or public booking marketing exposed.
"""

import os
import uuid
import datetime
import urllib.parse
from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, session, send_from_directory, flash
)
from .config import (
    BRAND_NAME, LEGAL_ENTITY, BUSINESS_OWNER, TURF_ADDRESS, GOOGLE_MAPS_URL,
    UPI_ID, UPI_PAYEE_NAME, ADMIN_MOBILE, ADMIN_EMAIL, ADMIN_DEFAULT_PASSWORD,
    HELPLINE_PRIMARY, HELPLINE_OPERATIONS, HELPLINE_TOURNAMENTS,
    SUPPORT_EMAIL, AVAILABILITY_TIMING, WHATSAPP_COMMUNITY_URL,
    INSTAGRAM_URL, CLEANING_LIGHTING_NOTICE, CANCELLATION_POLICY_NOTICE,
    CANTEEN_HYGIENE_NOTICE, UPLOAD_FOLDER, ADMIN_PORT
)
from .db import (
    get_db, hash_password
)
from .supabase_sync import (
    sync_booking_async
)
from .app import (
    format_time_12hr, get_slot_period, format_slot_range_12hr,
    allowed_file
)

admin_app = Flask(__name__)
admin_app.secret_key = "runbhoomi_admin_partner_operations_key_2026"
admin_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
admin_app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

@admin_app.context_processor
def inject_brand_context():
    return {
        "portal_type": "admin",
        "BRAND_NAME": BRAND_NAME,
        "LEGAL_ENTITY": LEGAL_ENTITY,
        "BUSINESS_OWNER": BUSINESS_OWNER,
        "TURF_ADDRESS": TURF_ADDRESS,
        "GOOGLE_MAPS_URL": GOOGLE_MAPS_URL,
        "UPI_ID": UPI_ID,
        "UPI_PAYEE_NAME": UPI_PAYEE_NAME,
        "HELPLINE_PRIMARY": HELPLINE_PRIMARY,
        "HELPLINE_OPERATIONS": HELPLINE_OPERATIONS,
        "HELPLINE_TOURNAMENTS": HELPLINE_TOURNAMENTS,
        "SUPPORT_EMAIL": SUPPORT_EMAIL,
        "AVAILABILITY_TIMING": AVAILABILITY_TIMING,
        "WHATSAPP_COMMUNITY_URL": WHATSAPP_COMMUNITY_URL,
        "INSTAGRAM_URL": INSTAGRAM_URL,
        "CLEANING_LIGHTING_NOTICE": CLEANING_LIGHTING_NOTICE,
        "CANCELLATION_POLICY_NOTICE": CANCELLATION_POLICY_NOTICE,
        "CANTEEN_HYGIENE_NOTICE": CANTEEN_HYGIENE_NOTICE,
        "current_user": session.get("admin_user"),
        "admin_user": session.get("admin_user"),
        "format_time_12hr": format_time_12hr,
        "get_slot_period": get_slot_period,
        "format_slot_range_12hr": format_slot_range_12hr
    }

admin_app.template_filter("time_12hr")(format_time_12hr)
admin_app.template_filter("slot_period")(get_slot_period)
admin_app.template_filter("slot_range_12hr")(format_slot_range_12hr)

def is_admin_or_partner():
    user = session.get("admin_user")
    return user is not None and user.get("role") in ["admin", "partner"]

def is_super_admin():
    user = session.get("admin_user")
    return user is not None and user.get("role") == "admin"

# -------------------------------------------------------------
# ROOT ROUTING & AUTHENTICATION GATEWAY
# -------------------------------------------------------------

@admin_app.route("/")
def index():
    if is_admin_or_partner():
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("admin_login"))

@admin_app.route("/admin/login", methods=["GET", "POST"])
@admin_app.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        login_input = (request.form.get("phone_or_email") or "").strip()
        password = request.form.get("password") or ""
        pwd_hash = hash_password(password)

        conn = get_db()
        cursor = conn.cursor()

        # Check super admin (Aditya Goyal)
        cursor.execute("""
            SELECT * FROM users
            WHERE (phone = ? OR email = ?) AND role = 'admin' AND password_hash = ?
        """, (login_input, login_input, pwd_hash))
        admin = cursor.fetchone()

        if admin:
            session["admin_user"] = {
                "id": admin["id"],
                "name": admin["name"],
                "phone": admin["phone"],
                "role": "admin"
            }
            conn.close()
            return redirect(url_for("admin_dashboard"))

        # Check partner credentials
        cursor.execute("""
            SELECT * FROM partners
            WHERE (phone = ? OR email = ?) AND password_hash = ? AND is_active = 1
        """, (login_input, login_input, pwd_hash))
        partner = cursor.fetchone()

        if partner:
            session["admin_user"] = {
                "id": partner["id"],
                "name": partner["name"],
                "phone": partner["phone"],
                "role": "partner"
            }
            conn.close()
            return redirect(url_for("admin_dashboard"))

        conn.close()
        flash("Invalid mobile/email or password for staff portal.")
        return render_template("admin_login.html")

    return render_template("admin_login.html")

@admin_app.route("/admin/logout")
@admin_app.route("/logout")
def admin_logout():
    session.pop("admin_user", None)
    flash("Staff session ended successfully.")
    return redirect(url_for("admin_login"))

# -------------------------------------------------------------
# OPERATIONS COMMAND CENTER (MATCH COCKPIT)
# -------------------------------------------------------------

@admin_app.route("/admin")
@admin_app.route("/admin/dashboard")
@admin_app.route("/dashboard")
def admin_dashboard():
    if not is_admin_or_partner():
        return redirect(url_for("admin_login"))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone, u.age, u.gender,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_status = 'in_process'
        ORDER BY b.created_at DESC
    """)
    in_process_bookings = cursor.fetchall()

    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone, u.age, u.gender,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_status IN ('confirmed', 'completed')
        ORDER BY b.booking_date DESC, b.start_time DESC
        LIMIT 50
    """)
    confirmed_bookings = cursor.fetchall()

    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone, u.age, u.gender,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_status = 'cancelled'
        ORDER BY b.booking_date DESC, b.start_time DESC
        LIMIT 50
    """)
    cancelled_bookings = cursor.fetchall()

    cursor.execute("""
        SELECT u.id, u.name, u.phone, u.email, u.age, u.gender, u.role, u.avatar_url, u.created_at,
               COUNT(b.id) as booking_count,
               COALESCE(SUM(CASE WHEN b.booking_status IN ('confirmed', 'completed') THEN b.total_amount ELSE 0 END), 0) as total_spent
        FROM users u
        LEFT JOIN bookings b ON u.id = b.user_id
        WHERE u.role = 'customer'
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """)
    registered_customers = cursor.fetchall()

    cursor.execute("SELECT * FROM partners ORDER BY created_at DESC")
    partners = cursor.fetchall()

    cursor.execute("SELECT * FROM sports ORDER BY id ASC")
    sports = cursor.fetchall()

    cursor.execute("""
        SELECT r.*, s.name as sport_name
        FROM pricing_rules r
        JOIN sports s ON r.sport_id = s.id
        ORDER BY r.sport_id, r.day_type, r.start_hour
    """)
    pricing_rules = cursor.fetchall()

    cursor.execute("SELECT * FROM canteen_items WHERE is_active = 1 ORDER BY category, name ASC")
    canteen_items = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        in_process_bookings=in_process_bookings,
        confirmed_bookings=confirmed_bookings,
        cancelled_bookings=cancelled_bookings,
        registered_customers=registered_customers,
        partners=partners,
        sports=sports,
        pricing_rules=pricing_rules,
        canteen_items=canteen_items,
        is_super_admin=is_super_admin()
    )

# -------------------------------------------------------------
# REVENUE INTELLIGENCE & MATCHDAY LEDGER
# -------------------------------------------------------------

@admin_app.route("/admin/revenue")
@admin_app.route("/revenue")
def revenue_analytics():
    if not is_admin_or_partner():
        return redirect(url_for("admin_login"))
    if not is_super_admin():
        flash("Access Denied: Revenue Intelligence is strictly restricted to Primary Turf Owner Aditya Goyal.")
        return redirect(url_for("admin_dashboard"))

    time_filter = request.args.get("filter", "30d")
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    today_formatted = now.strftime("%d %b %Y")

    if time_filter == "today":
        start_date = now.strftime("%Y-%m-%d")
    elif time_filter == "7d":
        start_date = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    elif time_filter == "30d":
        start_date = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    elif time_filter == "6m":
        start_date = (now - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
    elif time_filter == "1y":
        start_date = (now - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    else:
        start_date = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%d")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(total_amount - balance_due), 0)
        FROM bookings
        WHERE booking_status = 'confirmed'
    """)
    total_booking_earned = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(total_price), 0) FROM booking_canteen_orders")
    total_canteen_orders = cursor.fetchone()[0]
    total_amount_earned = total_booking_earned + total_canteen_orders

    cursor.execute("""
        SELECT COALESCE(SUM(balance_due), 0), COUNT(*)
        FROM bookings
        WHERE booking_status = 'confirmed' AND balance_due > 0
    """)
    pend_summary = cursor.fetchone()
    total_pending_amount = pend_summary[0]
    total_pending_count = pend_summary[1]

    cursor.execute("""
        SELECT COALESCE(SUM(balance_due), 0), COUNT(*), COALESCE(SUM(total_amount - balance_due), 0), COALESCE(SUM(total_amount), 0)
        FROM bookings
        WHERE booking_status = 'confirmed' AND booking_date = ?
    """, (today_str,))
    today_summary = cursor.fetchone()
    today_amount_to_collect = today_summary[0]
    today_matches_count = today_summary[1]
    today_earned = today_summary[2]
    today_gross_sales = today_summary[3]

    cursor.execute("""
        SELECT b.id, b.booking_ref, b.booking_date, b.start_time, b.end_time,
               b.total_amount, b.advance_paid, b.balance_due,
               u.name as customer_name, u.phone as customer_phone,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_status = 'confirmed' AND b.booking_date = ?
        ORDER BY b.start_time ASC
    """, (today_str,))
    today_bookings = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(total_amount), 0), COALESCE(SUM(advance_paid), 0)
        FROM bookings
        WHERE booking_status = 'confirmed' AND booking_date >= ?
    """, (start_date,))
    row = cursor.fetchone()
    total_matches = row[0]
    gross_booking_sales = row[1]
    amount_collected = row[2]

    cursor.execute("""
        SELECT COALESCE(SUM(o.total_price), 0)
        FROM booking_canteen_orders o
        JOIN bookings b ON o.booking_id = b.id
        WHERE b.booking_status = 'confirmed' AND b.booking_date >= ?
    """, (start_date,))
    canteen_revenue = cursor.fetchone()[0]
    total_collected_revenue = amount_collected + canteen_revenue

    cursor.execute("""
        SELECT b.id, b.booking_ref, b.booking_date, b.start_time, b.end_time,
               b.total_amount, b.advance_paid, b.balance_due,
               u.name as customer_name, u.phone as customer_phone,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_status = 'confirmed' AND b.balance_due > 0
        ORDER BY b.booking_date ASC, b.start_time ASC
    """)
    pending_balances = cursor.fetchall()

    cursor.execute("""
        SELECT s.name, COUNT(b.id) as match_count, COALESCE(SUM(b.total_amount), 0) as total_rev
        FROM sports s
        LEFT JOIN bookings b ON s.id = b.sport_id AND b.booking_status = 'confirmed' AND b.booking_date >= ?
        GROUP BY s.id
    """, (start_date,))
    sports_breakdown = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_revenue.html",
        time_filter=time_filter, today_date_str=today_str, today_date_formatted=today_formatted,
        total_amount_earned=total_amount_earned, total_booking_earned=total_booking_earned,
        total_canteen_orders=total_canteen_orders, total_pending_amount=total_pending_amount,
        total_pending_count=total_pending_count, today_amount_to_collect=today_amount_to_collect,
        today_matches_count=today_matches_count, today_earned=today_earned,
        today_gross_sales=today_gross_sales, today_bookings=today_bookings,
        total_matches=total_matches, gross_booking_sales=gross_booking_sales,
        amount_collected=amount_collected, canteen_revenue=canteen_revenue,
        total_collected_revenue=total_collected_revenue, pending_balances=pending_balances,
        sports_breakdown=sports_breakdown
    )

# -------------------------------------------------------------
# GROUND CANTEEN CONCESSION POS
# -------------------------------------------------------------

@admin_app.route("/canteen")
@admin_app.route("/admin/canteen")
def canteen_page():
    if not is_admin_or_partner():
        return redirect(url_for("admin_login"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM canteen_items WHERE is_active = 1 ORDER BY category, price ASC")
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()

    category_order = ["eggs", "snacks", "beverages", "mocktails", "smokes", "energy_sports", "gear_rental"]
    category_labels = {
        "eggs": "Fresh Eggs & Kitchen",
        "snacks": "Hot Snacks, Maggie & Pasta",
        "beverages": "Chilled Beverages, Water & Chai",
        "mocktails": "Mocktails & Coolers",
        "smokes": "Smokes & Lounge",
        "energy_sports": "Sports Hydration & Energy",
        "gear_rental": "Sports Gear & Rentals"
    }
    grouped = {}
    for cat in category_order:
        cat_items = [i for i in items if i.get("category") == cat]
        if cat_items:
            grouped[cat] = {"title": category_labels.get(cat, cat.title()), "products": cat_items}

    return render_template("canteen.html", grouped_menu=grouped, all_items=items, total_count=len(items))

@admin_app.route("/api/canteen/menu")
def api_canteen_menu():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, category, price, stock FROM canteen_items WHERE is_active = 1 ORDER BY category, price ASC")
    items = [dict(row) for row in cursor.fetchall()]
    return jsonify({"success": True, "items": items, "hygiene_notice": CANTEEN_HYGIENE_NOTICE})

# -------------------------------------------------------------
# MATCH OPERATIONS (CONFIRM, CANCEL, COLLECT, CANTEEN POS)
# -------------------------------------------------------------

@admin_app.route("/admin/booking/confirm/<int:booking_id>", methods=["POST"])
@admin_app.route("/booking/confirm/<int:booking_id>", methods=["POST"])
def confirm_booking(booking_id):
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    admin_name = session.get("admin_user", {}).get("name", "Staff")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bookings
        SET booking_status = 'confirmed', payment_status = 'verified',
            confirmed_by = ?, confirmed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (admin_name, booking_id))

    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone, s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.id = ?
    """, (booking_id,))
    booking = cursor.fetchone()
    conn.commit()
    conn.close()

    if not booking:
        return jsonify({"success": False, "message": "Booking not found"}), 404

    ref = booking["booking_ref"]
    phone = booking["customer_phone"]
    date_str = booking["booking_date"]
    time_slot = f"{booking['start_time']} to {booking['end_time']}"
    sport_name = booking["sport_name"]
    bal = booking["balance_due"]

    sync_booking_async({
        "booking_ref": ref, "booking_status": "confirmed", "payment_status": "verified",
        "confirmed_by": admin_name, "confirmed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    wa_msg = (
        f"🎉 *BOOKING CONFIRMED - RUNBHOOMI BOX CRICKET*\n\n"
        f"Dear {booking['customer_name']},\n"
        f"Your slot for *{sport_name}* on *{date_str}* ({time_slot}) is officially confirmed!\n\n"
        f"📋 *Receipt Ref:* {ref}\n"
        f"💰 *Remaining Balance Due:* Rs {bal} (Payable at turf ground before start)\n"
        f"📍 *Venue:* Rajdhani Marg, Shuklaganj, Unnao\n"
        f"📞 *Helpline:* {HELPLINE_PRIMARY}\n\n"
        f"Please arrive 15 minutes prior to match time with non-marking turf shoes."
    )
    wa_link = f"https://wa.me/91{phone}?text={urllib.parse.quote(wa_msg)}"
    return jsonify({"success": True, "message": "Booking confirmed successfully", "whatsapp_link": wa_link})

@admin_app.route("/admin/booking/cancel/<int:booking_id>", methods=["POST"])
@admin_app.route("/booking/cancel/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, u.phone as customer_phone
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        WHERE b.id = ?
    """, (booking_id,))
    booking = cursor.fetchone()

    if not booking:
        conn.close()
        return jsonify({"success": False, "message": "Booking not found"}), 404

    paid = booking["advance_paid"]
    retained_fee = round(paid * 0.50, 2)
    credit_code = f"CREDIT25-{uuid.uuid4().hex[:6].upper()}"

    cursor.execute("""
        UPDATE bookings
        SET booking_status = 'cancelled', payment_status = 'cancelled',
            cancellation_fee = ?, future_credit_code = ?
        WHERE id = ?
    """, (retained_fee, credit_code, booking_id))

    cursor.execute("""
        INSERT INTO cancellation_credits (booking_id, phone, promo_code, discount_percent, retained_fee)
        VALUES (?, ?, ?, 25.0, ?)
    """, (booking_id, booking["customer_phone"], credit_code, retained_fee))
    conn.commit()
    conn.close()

    sync_booking_async({
        "booking_ref": booking["booking_ref"], "booking_status": "cancelled",
        "payment_status": "cancelled", "cancellation_fee": retained_fee, "future_credit_code": credit_code
    })

    return jsonify({
        "success": True, "message": f"Booking cancelled. 50% non-refundable retained: ₹{retained_fee}.",
        "credit_code": credit_code, "retained_fee": retained_fee
    })

@admin_app.route("/admin/booking/collect-balance/<int:booking_id>", methods=["POST"])
@admin_app.route("/booking/collect-balance/<int:booking_id>", methods=["POST"])
def collect_balance(booking_id):
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET balance_due = 0 WHERE id = ?", (booking_id,))
    cursor.execute("SELECT booking_ref FROM bookings WHERE id = ?", (booking_id,))
    b = cursor.fetchone()
    conn.commit()
    conn.close()

    if b:
        sync_booking_async({"booking_ref": b["booking_ref"], "balance_due": 0.0})
    return jsonify({"success": True, "message": "Outstanding balance collected and settled at ground."})

@admin_app.route("/admin/booking/add-canteen/<int:booking_id>", methods=["POST"])
@admin_app.route("/booking/add-canteen/<int:booking_id>", methods=["POST"])
def add_canteen_to_bill(booking_id):
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    admin_name = session.get("admin_user", {}).get("name", "Staff")
    items_to_add = []
    if request.is_json:
        data = request.get_json() or {}
        raw_items = data.get("items")
        if raw_items and isinstance(raw_items, list):
            items_to_add = raw_items
        elif "item_id" in data:
            items_to_add = [{"item_id": data.get("item_id"), "quantity": data.get("quantity", 1)}]
    else:
        item_id = request.form.get("item_id")
        qty = int(request.form.get("quantity", 1))
        if item_id:
            items_to_add = [{"item_id": int(item_id), "quantity": qty}]

    if not items_to_add:
        return jsonify({"success": False, "message": "No menu items selected"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
    booking = cursor.fetchone()
    if not booking:
        conn.close()
        return jsonify({"success": False, "message": "Booking not found"}), 404

    batch_total = 0.0
    for entry in items_to_add:
        it_id = int(entry.get("item_id") or 0)
        q = int(entry.get("quantity") or 1)
        if it_id <= 0 or q <= 0:
            continue
        cursor.execute("SELECT * FROM canteen_items WHERE id = ?", (it_id,))
        item = cursor.fetchone()
        if not item:
            continue
        price = item["price"]
        item_tot = price * q
        batch_total += item_tot

        cursor.execute("""
            INSERT INTO booking_canteen_orders (booking_id, item_id, quantity, unit_price, total_price, added_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (booking_id, it_id, q, price, item_tot, admin_name))

    new_total = booking["total_amount"] + batch_total
    new_bal = booking["balance_due"] + batch_total
    cursor.execute("UPDATE bookings SET total_amount = ?, balance_due = ? WHERE id = ?", (new_total, new_bal, booking_id))
    conn.commit()
    conn.close()

    sync_booking_async({"booking_ref": booking["booking_ref"], "total_amount": new_total, "balance_due": new_bal})
    return jsonify({
        "success": True, "message": f"Concessions added to bill. Total: ₹{new_total}, Due: ₹{new_bal}",
        "new_total": new_total, "new_balance": new_bal
    })

# -------------------------------------------------------------
# CUSTOMER DIRECTORY & PLAYER LOOKUP API
# -------------------------------------------------------------

@admin_app.route("/admin/api/customer-lookup")
@admin_app.route("/api/admin/customer-lookup")
def api_customer_lookup():
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    q = (request.args.get("q") or "").strip()
    conn = get_db()
    cursor = conn.cursor()
    if q:
        cursor.execute("""
            SELECT u.id, u.name, u.phone, u.email, u.age, u.gender, u.created_at,
                   COUNT(b.id) as booking_count,
                   COALESCE(SUM(CASE WHEN b.booking_status IN ('confirmed', 'completed') THEN b.total_amount ELSE 0 END), 0) as total_spent
            FROM users u
            LEFT JOIN bookings b ON u.id = b.user_id
            WHERE u.role = 'customer' AND (u.phone LIKE ? OR u.name LIKE ? OR u.email LIKE ?)
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    else:
        cursor.execute("""
            SELECT u.id, u.name, u.phone, u.email, u.age, u.gender, u.created_at,
                   COUNT(b.id) as booking_count,
                   COALESCE(SUM(CASE WHEN b.booking_status IN ('confirmed', 'completed') THEN b.total_amount ELSE 0 END), 0) as total_spent
            FROM users u
            LEFT JOIN bookings b ON u.id = b.user_id
            WHERE u.role = 'customer'
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """)
    results = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "customers": results, "count": len(results)})

# -------------------------------------------------------------
# PARTNER MANAGEMENT & PRICING
# -------------------------------------------------------------

@admin_app.route("/admin/partners/add", methods=["POST"])
@admin_app.route("/partners/add", methods=["POST"])
def add_partner():
    if not is_super_admin():
        return jsonify({"success": False, "message": "Only Primary Turf Owner can add partners."}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM partners WHERE is_active = 1")
    count = cursor.fetchone()[0]
    if count >= 2:
        conn.close()
        return jsonify({"success": False, "message": "Maximum 2 partners allowed in system."}), 400

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    if not name or not phone or not password:
        conn.close()
        return jsonify({"success": False, "message": "Name, phone, and password required."}), 400

    pwd_hash = hash_password(password)
    try:
        cursor.execute("INSERT INTO partners (name, phone, email, password_hash) VALUES (?, ?, ?, ?)",
                       (name, phone, email, pwd_hash))
        conn.commit()
        conn.close()
        flash(f"Partner {name} created successfully.")
        return redirect(url_for("admin_dashboard"))
    except Exception as e:
        conn.close()
        flash(f"Error adding partner: {str(e)}")
        return redirect(url_for("admin_dashboard"))

@admin_app.route("/admin/partners/delete/<int:partner_id>", methods=["POST"])
@admin_app.route("/partners/delete/<int:partner_id>", methods=["POST"])
def delete_partner(partner_id):
    if not is_super_admin():
        return jsonify({"success": False, "message": "Only Primary Owner can remove partners."}), 403

    conn = get_db()
    conn.execute("DELETE FROM partners WHERE id = ?", (partner_id,))
    conn.commit()
    conn.close()
    flash("Partner removed successfully.")
    return redirect(url_for("admin_dashboard"))

@admin_app.route("/admin/sports/pricing/update", methods=["POST"])
@admin_app.route("/sports/pricing/update", methods=["POST"])
def update_sport_pricing():
    if not is_super_admin():
        return jsonify({"success": False, "message": "Only Owner can modify pricing rules."}), 403

    rule_id = request.form.get("rule_id")
    rate = request.form.get("hourly_rate")
    flood = request.form.get("floodlight_charge", 0)

    conn = get_db()
    conn.execute("UPDATE pricing_rules SET hourly_rate = ?, floodlight_charge = ? WHERE id = ?", (rate, flood, rule_id))
    conn.commit()
    conn.close()
    flash("Pricing rule updated successfully.")
    return redirect(url_for("admin_dashboard"))

@admin_app.route("/voucher/<booking_ref>")
@admin_app.route("/receipt/<booking_ref>")
def match_voucher(booking_ref):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone, u.age, u.gender,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_ref = ?
    """, (booking_ref,))
    booking = cursor.fetchone()

    canteen_orders = []
    if booking:
        cursor.execute("""
            SELECT o.*, i.name as item_name
            FROM booking_canteen_orders o
            JOIN canteen_items i ON o.item_id = i.id
            WHERE o.booking_id = ?
        """, (booking["id"],))
        canteen_orders = cursor.fetchall()

    conn.close()
    if not booking:
        flash("Pass or match voucher not found.")
        return redirect(url_for("admin_dashboard"))

    return render_template("voucher.html", booking=booking, canteen_orders=canteen_orders)

@admin_app.route("/contact")
def contact_page():
    return render_template("contact.html")

@admin_app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(admin_app.config['UPLOAD_FOLDER'], filename)
