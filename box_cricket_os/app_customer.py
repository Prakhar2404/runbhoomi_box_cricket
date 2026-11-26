"""
Runbhoomi Box Cricket - Dedicated Customer & Player Portal
Corporate Legal Entity: Runbhoomi Box Cricket Pvt. Ltd.
Runs on Port 5000 (e.g. runbhoomi.com / play.runbhoomi.com)
Zero administrative endpoints or partner controls exposed.
"""

import os
import uuid
import datetime
from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, session, send_from_directory, flash
)
from .config import (
    BRAND_NAME, LEGAL_ENTITY, BUSINESS_OWNER, TURF_ADDRESS,
    UPI_ID, UPI_PAYEE_NAME, ADMIN_MOBILE, ADMIN_EMAIL,
    HELPLINE_PRIMARY, HELPLINE_OPERATIONS, HELPLINE_TOURNAMENTS,
    SUPPORT_EMAIL, AVAILABILITY_TIMING, WHATSAPP_COMMUNITY_URL,
    INSTAGRAM_URL, CLEANING_LIGHTING_NOTICE, CANCELLATION_POLICY_NOTICE,
    CANTEEN_HYGIENE_NOTICE, SLOT_HOLD_MINUTES, UPLOAD_FOLDER,
    CUSTOMER_PORT
)
from .db import (
    get_db, init_db, hash_password, cleanup_expired_holds
)
from .qr_generator import (
    generate_upi_intent_url, generate_qr_svg
)
from .supabase_sync import (
    sync_user_async, sync_booking_async
)
from .app import (
    format_time_12hr, get_slot_period, format_slot_range_12hr,
    allowed_file, calculate_slot_price
)

customer_app = Flask(__name__)
customer_app.secret_key = "runbhoomi_customer_portal_key_2026"
customer_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
customer_app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

@customer_app.context_processor
def inject_brand_context():
    return {
        "portal_type": "customer",
        "BRAND_NAME": BRAND_NAME,
        "LEGAL_ENTITY": LEGAL_ENTITY,
        "BUSINESS_OWNER": BUSINESS_OWNER,
        "TURF_ADDRESS": TURF_ADDRESS,
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
        "current_user": session.get("user"),
        "format_time_12hr": format_time_12hr,
        "get_slot_period": get_slot_period,
        "format_slot_range_12hr": format_slot_range_12hr
    }

customer_app.template_filter("time_12hr")(format_time_12hr)
customer_app.template_filter("slot_period")(get_slot_period)
customer_app.template_filter("slot_range_12hr")(format_slot_range_12hr)

# -------------------------------------------------------------
# CUSTOMER / PLAYER AUTHENTICATION
# -------------------------------------------------------------

@customer_app.route("/customer/auth", methods=["GET", "POST"])
@customer_app.route("/customer/login", methods=["GET", "POST"])
def customer_login_page():
    next_url = request.args.get("next") or request.form.get("next") or url_for("booking_page")
    if session.get("user"):
        return redirect(next_url)

    if request.method == "POST":
        action = request.form.get("action", "login")
        if action == "register":
            name = (request.form.get("name") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            age = request.form.get("age")
            gender = request.form.get("gender")
            email = (request.form.get("email") or "").strip()
            password = (request.form.get("password") or "").strip()

            if not name or not phone or not age or not gender or not password:
                flash("All mandatory fields (*Name, Contact, Age, Gender, Password) are required.")
                return render_template("customer_auth.html", next_url=next_url, active_tab="register")

            if len(password) < 6:
                flash("Password must be at least 6 characters long.")
                return render_template("customer_auth.html", next_url=next_url, active_tab="register")

            avatar_filename = None
            if 'avatar' in request.files:
                avatar_file = request.files['avatar']
                if avatar_file and avatar_file.filename != '' and allowed_file(avatar_file.filename):
                    ext = avatar_file.filename.rsplit('.', 1)[1].lower()
                    avatar_filename = f"avatar_{phone}_{uuid.uuid4().hex[:6]}.{ext}"
                    avatar_file.save(os.path.join(customer_app.config['UPLOAD_FOLDER'], avatar_filename))

            pwd_hash = hash_password(password)
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id, avatar_url FROM users WHERE phone = ?", (phone,))
            existing = cursor.fetchone()

            if existing:
                user_id = existing["id"]
                final_avatar = avatar_filename or existing["avatar_url"]
                cursor.execute("""
                    UPDATE users SET name = ?, age = ?, gender = ?, email = ?, password_hash = ?, avatar_url = ?
                    WHERE id = ?
                """, (name, int(age), gender, email, pwd_hash, final_avatar, user_id))
            else:
                cursor.execute("""
                    INSERT INTO users (phone, name, email, age, gender, role, password_hash, avatar_url)
                    VALUES (?, ?, ?, ?, ?, 'customer', ?, ?)
                """, (phone, name, email, int(age), gender, pwd_hash, avatar_filename))
                user_id = cursor.lastrowid
                final_avatar = avatar_filename

            conn.commit()
            conn.close()

            user_data = {
                "id": user_id, "name": name, "phone": phone, "email": email,
                "age": int(age), "gender": gender, "avatar_url": final_avatar, "role": "customer"
            }
            session["user"] = user_data
            sync_user_async(name, phone, age, gender, email, pwd_hash, "customer", final_avatar)
            flash(f"Welcome {name}! Your player account has been created successfully.")
            return redirect(next_url)
        else:
            login_input = (request.form.get("phone_or_email") or "").strip()
            password = (request.form.get("password") or "").strip()
            if not login_input or not password or len(password) < 6:
                flash("Valid Contact/Email and Password (min 6 chars) are required.")
                return render_template("customer_auth.html", next_url=next_url, active_tab="login")

            pwd_hash = hash_password(password)
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, phone, email, age, gender, avatar_url, role
                FROM users
                WHERE (phone = ? OR email = ?) AND password_hash = ? AND role = 'customer'
            """, (login_input, login_input, pwd_hash))
            user = cursor.fetchone()
            conn.close()

            if not user:
                flash("Invalid mobile number/email or password.")
                return render_template("customer_auth.html", next_url=next_url, active_tab="login")

            session["user"] = dict(user)
            return redirect(next_url)

    return render_template("customer_auth.html", next_url=next_url, active_tab="login")

@customer_app.route("/customer/logout")
def customer_logout_get():
    session.pop("user", None)
    flash("You have been signed out.")
    return redirect(url_for("index"))

@customer_app.route("/api/customer/register", methods=["POST"])
def customer_register():
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    age = request.form.get("age")
    gender = request.form.get("gender")
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip() or f"rb@{phone[-4:]}2026"

    if not name or not phone or not age or not gender:
        return jsonify({"success": False, "message": "All mandatory fields are required."}), 400

    pwd_hash = hash_password(password)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE phone = ?", (phone,))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("UPDATE users SET name = ?, age = ?, gender = ?, email = ?, password_hash = ? WHERE id = ?",
                       (name, int(age), gender, email, pwd_hash, existing["id"]))
        user_id = existing["id"]
    else:
        cursor.execute("INSERT INTO users (phone, name, email, age, gender, role, password_hash) VALUES (?, ?, ?, ?, ?, 'customer', ?)",
                       (phone, name, email, int(age), gender, pwd_hash))
        user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    session["user"] = {"id": user_id, "name": name, "phone": phone, "role": "customer"}
    sync_user_async(name, phone, age, gender, email, pwd_hash, "customer", None)
    return jsonify({"success": True, "message": "Registered successfully", "user": session["user"]})

@customer_app.route("/api/customer/login", methods=["POST"])
def customer_login():
    data = request.get_json() or {}
    phone = data.get("phone") or request.form.get("phone")
    password = data.get("password") or request.form.get("password")
    if not phone or not password:
        return jsonify({"success": False, "message": "Phone and password required"}), 400

    pwd_hash = hash_password(password)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phone, role FROM users WHERE (phone = ? OR email = ?) AND password_hash = ?", (phone, phone, pwd_hash))
    user = cursor.fetchone()
    conn.close()
    if user:
        session["user"] = dict(user)
        return jsonify({"success": True, "user": session["user"]})
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@customer_app.route("/api/customer/logout", methods=["POST"])
def customer_logout():
    session.pop("user", None)
    return jsonify({"success": True})

@customer_app.route("/api/customer/lookup", methods=["POST"])
def customer_lookup():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"found": False})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, age, gender, email FROM users WHERE phone = ?", (phone,))
    u = cursor.fetchone()
    conn.close()
    if u:
        return jsonify({"found": True, "customer": dict(u)})
    return jsonify({"found": False})

# -------------------------------------------------------------
# PLAYER BOOKING & SCHEDULING FLOW
# -------------------------------------------------------------

@customer_app.route("/")
def index():
    cleanup_expired_holds()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sports WHERE is_active = 1 ORDER BY id ASC")
    sports = cursor.fetchall()
    cursor.execute("SELECT * FROM promo_offers WHERE is_active = 1")
    promos = cursor.fetchall()
    conn.close()
    return render_template("index.html", sports=sports, promos=promos)

@customer_app.route("/booking")
def booking_page():
    if not session.get("user"):
        return redirect(url_for("customer_login_page", next=request.path))

    cleanup_expired_holds()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sports WHERE is_active = 1 ORDER BY id ASC")
    sports = cursor.fetchall()
    cursor.execute("SELECT * FROM promo_offers WHERE is_active = 1")
    promos = cursor.fetchall()
    conn.close()

    today = datetime.date.today()
    date_pills = []
    for i in range(14):
        d = today + datetime.timedelta(days=i)
        date_pills.append({
            "date_str": d.strftime("%Y-%m-%d"),
            "day_name": d.strftime("%a"),
            "day_num": d.strftime("%d"),
            "month_name": d.strftime("%b"),
            "is_weekend": d.weekday() >= 5
        })

    return render_template("booking.html", sports=sports, date_pills=date_pills, promos=promos)

@customer_app.route("/api/check-slots", methods=["POST"])
def check_slots():
    cleanup_expired_holds()
    data = request.get_json() or {}
    sport_id = data.get("sport_id", 1)
    slot_date = data.get("date", datetime.date.today().strftime("%Y-%m-%d"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT start_time, end_time, booking_status, payment_status, booking_ref
        FROM bookings
        WHERE sport_id = ? AND booking_date = ? AND booking_status IN ('confirmed', 'in_process')
    """, (sport_id, slot_date))
    active_bookings = cursor.fetchall()

    cursor.execute("""
        SELECT start_time, end_time, hold_token
        FROM held_slots
        WHERE sport_id = ? AND slot_date = ? AND expires_at > CURRENT_TIMESTAMP
    """, (sport_id, slot_date))
    active_holds = cursor.fetchall()
    conn.close()

    slots = []
    for h in range(6, 24):
        for m in (0, 30):
            start_t = f"{h:02d}:{m:02d}"
            end_m = m + 30
            end_h = h
            if end_m == 60:
                end_m = 0
                end_h = h + 1
            end_t = "24:00" if end_h == 24 else f"{end_h:02d}:{end_m:02d}"

            status = "available"
            hold_token = None
            booking_ref = None

            for b in active_bookings:
                if not (end_t <= b["start_time"] or start_t >= b["end_time"]):
                    status = "booked"
                    booking_ref = b["booking_ref"]
                    break

            if status == "available":
                for hd in active_holds:
                    if not (end_t <= hd["start_time"] or start_t >= hd["end_time"]):
                        status = "held"
                        hold_token = hd["hold_token"]
                        break

            price, dur, floodlight = calculate_slot_price(sport_id, slot_date, start_t, end_t)
            period = get_slot_period(start_t)

            slots.append({
                "start_time": start_t,
                "end_time": end_t,
                "start_time_12h": format_time_12hr(start_t),
                "end_time_12h": format_time_12hr(end_t),
                "period": period,
                "price": price,
                "has_floodlight": (floodlight > 0),
                "status": status,
                "hold_token": hold_token,
                "booking_ref": booking_ref
            })

    return jsonify({"success": True, "date": slot_date, "sport_id": sport_id, "slots": slots})

@customer_app.route("/api/hold-slot", methods=["POST"])
def hold_slot():
    cleanup_expired_holds()
    data = request.get_json() or {}
    sport_id = data.get("sport_id")
    slot_date = data.get("date")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    customer_phone = data.get("phone", "")

    if not all([sport_id, slot_date, start_time, end_time]):
        return jsonify({"success": False, "message": "Missing slot details."}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM bookings
        WHERE sport_id = ? AND booking_date = ?
          AND booking_status IN ('confirmed', 'in_process')
          AND NOT (? <= start_time OR ? >= end_time)
    """, (sport_id, slot_date, end_time, start_time))
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Selected slot has already been booked."}), 409

    cursor.execute("""
        SELECT id FROM held_slots
        WHERE sport_id = ? AND slot_date = ?
          AND expires_at > CURRENT_TIMESTAMP
          AND NOT (? <= start_time OR ? >= end_time)
    """, (sport_id, slot_date, end_time, start_time))
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Slot is temporarily held in checkout by another player."}), 409

    hold_token = f"HOLD-{uuid.uuid4().hex[:10].upper()}"
    expires_at = datetime.datetime.now() + datetime.timedelta(minutes=SLOT_HOLD_MINUTES)
    cursor.execute("""
        INSERT INTO held_slots (sport_id, slot_date, start_time, end_time, hold_token, customer_phone, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sport_id, slot_date, start_time, end_time, hold_token, customer_phone, expires_at.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    total_price, duration, floodlight = calculate_slot_price(sport_id, slot_date, start_time, end_time)
    return jsonify({
        "success": True,
        "hold_token": hold_token,
        "expires_at": expires_at.strftime("%H:%M:%S"),
        "total_price": total_price,
        "duration_hours": duration,
        "floodlight_charge": floodlight,
        "redirect_url": url_for("checkout_page", hold_token=hold_token)
    })

@customer_app.route("/api/release-hold", methods=["POST"])
def release_hold():
    data = request.get_json() or {}
    hold_token = data.get("hold_token")
    if hold_token:
        conn = get_db()
        conn.execute("DELETE FROM held_slots WHERE hold_token = ?", (hold_token,))
        conn.commit()
        conn.close()
    return jsonify({"success": True})

@customer_app.route("/book")
def checkout_page():
    cleanup_expired_holds()
    hold_token = request.args.get("hold_token")
    if not hold_token:
        flash("Please select a slot from the timetable to book.")
        return redirect(url_for("index"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT h.*, s.name as sport_name, s.slug as sport_slug
        FROM held_slots h
        JOIN sports s ON h.sport_id = s.id
        WHERE h.hold_token = ? AND h.expires_at > CURRENT_TIMESTAMP
    """, (hold_token,))
    hold = cursor.fetchone()

    if not hold:
        conn.close()
        flash("Your slot hold has expired or is invalid. Please select your slot again.")
        return redirect(url_for("index"))

    total_price, duration, floodlight = calculate_slot_price(
        hold["sport_id"], hold["slot_date"], hold["start_time"], hold["end_time"]
    )
    advance_50 = round(total_price * 0.5, 2)
    temp_ref = f"RB-{datetime.date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    upi_url_50 = generate_upi_intent_url(UPI_ID, UPI_PAYEE_NAME, advance_50, temp_ref, f"Advance 50% {temp_ref}")
    upi_url_100 = generate_upi_intent_url(UPI_ID, UPI_PAYEE_NAME, total_price, temp_ref, f"Full 100% {temp_ref}")

    qr_svg_50 = generate_qr_svg(upi_url_50)
    qr_svg_100 = generate_qr_svg(upi_url_100)
    saved_user = session.get("user") or {}
    conn.close()

    return render_template(
        "checkout.html",
        hold=hold, temp_ref=temp_ref, total_price=total_price, duration=duration,
        floodlight=floodlight, advance_50=advance_50, upi_url_50=upi_url_50,
        upi_url_100=upi_url_100, qr_svg_50=qr_svg_50, qr_svg_100=qr_svg_100, saved_user=saved_user
    )

@customer_app.route("/api/apply-promo", methods=["POST"])
def apply_promo():
    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    total_amount = float(data.get("total_amount", 0))

    if not code:
        return jsonify({"success": False, "message": "Promo code cannot be empty."})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promo_offers WHERE code = ? AND is_active = 1", (code,))
    offer = cursor.fetchone()

    if offer:
        if total_amount < offer["min_booking_amount"]:
            conn.close()
            return jsonify({
                "success": False,
                "message": f"This code requires minimum booking amount of ₹{offer['min_booking_amount']}."
            })
        discount = 0.0
        if offer["offer_type"] == "percent":
            discount = round(total_amount * (offer["discount_value"] / 100.0), 2)
        elif offer["offer_type"] == "flat":
            discount = min(total_amount, float(offer["discount_value"]))
        conn.close()
        return jsonify({
            "success": True, "discount_amount": discount,
            "final_amount": max(0.0, total_amount - discount), "title": offer["title"]
        })

    cursor.execute("SELECT * FROM cancellation_credits WHERE promo_code = ? AND is_redeemed = 0", (code,))
    credit = cursor.fetchone()
    conn.close()
    if credit:
        discount = round(total_amount * (credit["discount_percent"] / 100.0), 2)
        return jsonify({
            "success": True, "discount_amount": discount,
            "final_amount": max(0.0, total_amount - discount), "title": "25% Future Booking Credit applied!"
        })

    return jsonify({"success": False, "message": "Invalid or expired promo/credit code."})

@customer_app.route("/api/create-booking", methods=["POST"])
def create_booking():
    cleanup_expired_holds()
    hold_token = request.form.get("hold_token")
    booking_ref = request.form.get("booking_ref") or f"RB-{datetime.date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    payment_type = request.form.get("payment_type", "50_percent_token")
    promo_code = request.form.get("promo_code", "").strip().upper()
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    age = request.form.get("age")
    gender = request.form.get("gender")
    notes = request.form.get("notes", "")

    if not name or not phone or not age or not gender:
        return jsonify({"success": False, "message": "Full Name, Contact Number, Age, and Gender are mandatory."}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM held_slots WHERE hold_token = ?", (hold_token,))
    hold = cursor.fetchone()

    if not hold:
        conn.close()
        return jsonify({"success": False, "message": "Slot hold has expired. Please choose a slot again."}), 400

    sport_id = hold["sport_id"]
    slot_date = hold["slot_date"]
    start_time = hold["start_time"]
    end_time = hold["end_time"]

    gross_amount, duration, floodlight = calculate_slot_price(sport_id, slot_date, start_time, end_time)

    discount_amount = 0.0
    if promo_code:
        cursor.execute("SELECT * FROM promo_offers WHERE code = ? AND is_active = 1", (promo_code,))
        p = cursor.fetchone()
        if p and gross_amount >= p["min_booking_amount"]:
            if p["offer_type"] == "percent":
                discount_amount = round(gross_amount * (p["discount_value"] / 100.0), 2)
            elif p["offer_type"] == "flat":
                discount_amount = min(gross_amount, p["discount_value"])
        else:
            cursor.execute("SELECT * FROM cancellation_credits WHERE promo_code = ? AND is_redeemed = 0", (promo_code,))
            cc = cursor.fetchone()
            if cc:
                discount_amount = round(gross_amount * (cc["discount_percent"] / 100.0), 2)
                cursor.execute("UPDATE cancellation_credits SET is_redeemed = 1 WHERE id = ?", (cc["id"],))

    net_total = max(0.0, gross_amount - discount_amount)
    if payment_type == "50_percent_token":
        advance_paid = round(net_total * 0.5, 2)
        balance_due = round(net_total - advance_paid, 2)
    else:
        advance_paid = net_total
        balance_due = 0.0

    screenshot_filename = None
    if 'screenshot' in request.files:
        file = request.files['screenshot']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            screenshot_filename = f"proof_{booking_ref}_{uuid.uuid4().hex[:6]}.{ext}"
            file.save(os.path.join(customer_app.config['UPLOAD_FOLDER'], screenshot_filename))

    raw_password = (request.form.get("password") or "").strip()
    pwd_hash = hash_password(raw_password) if (raw_password and len(raw_password) >= 6) else hash_password(f"rb@{phone[-4:]}2026")

    cursor.execute("SELECT id FROM users WHERE phone = ?", (phone,))
    existing_user = cursor.fetchone()
    if existing_user:
        user_id = existing_user["id"]
        cursor.execute("UPDATE users SET name = ?, age = ?, gender = ? WHERE id = ?", (name, int(age), gender, user_id))
    else:
        cursor.execute("INSERT INTO users (phone, name, age, gender, role, password_hash) VALUES (?, ?, ?, ?, 'customer', ?)",
                       (phone, name, int(age), gender, pwd_hash))
        user_id = cursor.lastrowid

    session["user"] = {"id": user_id, "name": name, "phone": phone, "age": age, "gender": gender}

    cursor.execute("""
        INSERT INTO bookings (
            booking_ref, user_id, sport_id, booking_date, start_time, end_time,
            duration_hours, base_rate, floodlight_charge, discount_amount, promo_code,
            total_amount, advance_paid, balance_due, payment_type, payment_status,
            booking_status, screenshot_url, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_process', 'in_process', ?, ?)
    """, (
        booking_ref, user_id, sport_id, slot_date, start_time, end_time,
        duration, gross_amount, floodlight, discount_amount, promo_code,
        net_total, advance_paid, balance_due, payment_type, screenshot_filename, notes
    ))
    cursor.execute("DELETE FROM held_slots WHERE hold_token = ?", (hold_token,))
    conn.commit()
    conn.close()

    sync_user_async(name, phone, age, gender, None, pwd_hash, "customer", None)
    sync_booking_async({
        "booking_ref": booking_ref, "customer_phone": phone, "sport_id": sport_id,
        "booking_date": slot_date, "start_time": start_time, "end_time": end_time,
        "duration_hours": duration, "base_rate": gross_amount, "floodlight_charge": floodlight,
        "discount_amount": discount_amount, "promo_code": promo_code, "total_amount": net_total,
        "advance_paid": advance_paid, "balance_due": balance_due, "payment_type": payment_type,
        "payment_status": "in_process", "booking_status": "in_process",
        "screenshot_url": screenshot_filename, "notes": notes
    })

    return jsonify({
        "success": True, "booking_ref": booking_ref,
        "redirect_url": url_for("booking_confirmation", booking_ref=booking_ref)
    })

@customer_app.route("/confirmation/<booking_ref>")
def booking_confirmation(booking_ref):
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
    conn.close()

    if not booking:
        flash("Booking record not found.")
        return redirect(url_for("index"))

    return render_template("confirmation.html", booking=booking)

@customer_app.route("/voucher/<booking_ref>")
@customer_app.route("/receipt/<booking_ref>")
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
        return redirect(url_for("index"))

    return render_template("voucher.html", booking=booking, canteen_orders=canteen_orders)

@customer_app.route("/contact")
def contact_page():
    return render_template("contact.html")

@customer_app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(customer_app.config['UPLOAD_FOLDER'], filename)

# Administrative lock on customer portal
@customer_app.errorhandler(404)
def not_found(e):
    return render_template("index.html"), 404
