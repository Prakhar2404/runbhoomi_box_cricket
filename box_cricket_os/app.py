"""
Runbhoomi Box Cricket - Core Application Engine
Corporate Legal Entity: Runbhoomi Box Cricket Pvt. Ltd.
"""

import os
import uuid
import datetime
import urllib.parse
from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, session, send_from_directory, flash
)
from werkzeug.utils import secure_filename
from .config import (
    BRAND_NAME, LEGAL_ENTITY, BUSINESS_OWNER, TURF_ADDRESS,
    UPI_ID, UPI_PAYEE_NAME, ADMIN_MOBILE, ADMIN_EMAIL, ADMIN_DEFAULT_PASSWORD,
    HELPLINE_PRIMARY, HELPLINE_OPERATIONS, HELPLINE_TOURNAMENTS,
    SUPPORT_EMAIL, AVAILABILITY_TIMING, WHATSAPP_COMMUNITY_URL,
    INSTAGRAM_URL, CLEANING_LIGHTING_NOTICE, CANCELLATION_POLICY_NOTICE,
    CANTEEN_HYGIENE_NOTICE, SLOT_HOLD_MINUTES, UPLOAD_FOLDER
)
from .db import (
    get_db, init_db, hash_password, cleanup_expired_holds
)
from .qr_generator import (
    generate_upi_intent_url, generate_qr_svg, generate_qr_base64_png
)
from .supabase_sync import (
    sync_user_async, sync_booking_async
)

app = Flask(__name__)
app.secret_key = "runbhoomi_box_cricket_secure_turf_key_2026"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB max

# -------------------------------------------------------------
# 12-HOUR FORMAT & PERIOD CLASSIFICATION HELPERS
# -------------------------------------------------------------
def format_time_12hr(time_str):
    """
    Converts 24-hr time ('06:00', '13:30', '24:00', '00:00') into 12-hr time string ('06:00 AM', '01:30 PM', '12:00 AM').
    """
    if not time_str:
        return ""
    try:
        parts = time_str.strip().split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        if h == 24 or h == 0:
            return f"12:{m:02d} AM"
        elif h < 12:
            return f"{h:02d}:{m:02d} AM"
        elif h == 12:
            return f"12:{m:02d} PM"
        else:
            return f"{(h - 12):02d}:{m:02d} PM"
    except Exception:
        return time_str

def get_slot_period(time_str):
    """
    Returns time period tag: 'Morning', 'Noon', 'Evening', or 'Night'.
    - Morning: 06:00 AM to 11:59 AM
    - Noon:    12:00 PM to 03:59 PM
    - Evening: 04:00 PM to 06:59 PM
    - Night:   07:00 PM to 12:00 AM Midnight
    """
    try:
        h = int(time_str.strip().split(":")[0])
        if 5 <= h < 12:
            return "Morning"
        elif 12 <= h < 16:
            return "Noon"
        elif 16 <= h < 19:
            return "Evening"
        else:
            return "Night"
    except Exception:
        return "Morning"

def format_slot_range_12hr(start_time_str, end_time_str):
    """
    Returns 12-hour continuous range with period label.
    e.g. '06:00 PM to 08:00 PM (Night)'
    """
    period = get_slot_period(start_time_str)
    start_12 = format_time_12hr(start_time_str)
    end_12 = format_time_12hr(end_time_str)
    return f"{start_12} to {end_12} ({period})"

# Context processor for templates to always have brand assets
@app.context_processor
def inject_brand_context():
    return {
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

# Template filters for 12-hour formatting & periods
@app.template_filter("time_12hr")
def filter_time_12hr(val):
    return format_time_12hr(val)

@app.template_filter("slot_period")
def filter_slot_period(val):
    return get_slot_period(val)

@app.template_filter("slot_range_12hr")
def filter_slot_range_12hr(start_val, end_val):
    return format_slot_range_12hr(start_val, end_val)

# Ensure database is initialized at startup
init_db()

# Allowed image extensions for proofs and avatars
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'svg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------------------------------------------
# HELPER FUNCTIONS: Slot Times & Dynamic Pricing
# -------------------------------------------------------------
SLOT_TIMINGS_30MIN = [
    ("06:00", "06:30"), ("06:30", "07:00"), ("07:00", "07:30"), ("07:30", "08:00"),
    ("08:00", "08:30"), ("08:30", "09:00"), ("09:00", "09:30"), ("09:30", "10:00"),
    ("10:00", "10:30"), ("10:30", "11:00"), ("11:00", "11:30"), ("11:30", "12:00"),
    ("12:00", "12:30"), ("12:30", "13:00"), ("13:00", "13:30"), ("13:30", "14:00"),
    ("14:00", "14:30"), ("14:30", "15:00"), ("15:00", "15:30"), ("15:30", "16:00"),
    ("16:00", "16:30"), ("16:30", "17:00"), ("17:00", "17:30"), ("17:30", "18:00"),
    ("18:00", "18:30"), ("18:30", "19:00"), ("19:00", "19:30"), ("19:30", "20:00"),
    ("20:00", "20:30"), ("20:30", "21:00"), ("21:00", "21:30"), ("21:30", "22:00"),
    ("22:00", "22:30"), ("22:30", "23:00"), ("23:00", "23:30"), ("23:30", "24:00"),
]

def calculate_slot_price(sport_id, target_date_str, start_time_str, end_time_str):
    """
    Computes dynamic price taking into account:
    - Sport rates
    - Weekday (Mon-Fri) vs Weekend (Sat-Sun)
    - Day (06:00 - 18:00) vs Night Floodlight (18:00 - 24:00)
    """
    try:
        dt = datetime.datetime.strptime(target_date_str, "%Y-%m-%d")
        day_type = "weekend" if dt.weekday() >= 5 else "weekday"
    except Exception:
        day_type = "weekday"

    # parse hours
    s_h, s_m = map(int, start_time_str.split(":"))
    e_h, e_m = map(int, end_time_str.split(":"))
    s_val = s_h + s_m / 60.0
    e_val = e_h + e_m / 60.0
    if e_val <= s_val:
        e_val = 24.0 # midnight wrap
    duration = e_val - s_val

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM pricing_rules
        WHERE sport_id = ? AND day_type = ?
    """, (sport_id, day_type))
    rules = cursor.fetchall()
    conn.close()

    total_price = 0.0
    floodlight_charge = 0.0

    # Calculate hourly by slices
    curr = s_val
    while curr < e_val:
        step = min(0.5, e_val - curr)
        hour_int = int(curr)
        matched_rule = None
        for r in rules:
            if r["start_hour"] <= hour_int < r["end_hour"]:
                matched_rule = r
                break
        if not matched_rule and rules:
            matched_rule = rules[0]

        if matched_rule:
            hourly_rate = matched_rule["hourly_rate"]
            flood = matched_rule["floodlight_charge"]
            total_price += (hourly_rate * step)
            if flood > 0:
                floodlight_charge += (flood * step)
        else:
            total_price += 800.0 * step
        curr += step

    return round(total_price, 2), round(duration, 2), round(floodlight_charge, 2)

# -------------------------------------------------------------
# PHASE 1 & 2: PUBLIC ROUTES & LIVE SCHEDULING ENGINE
# -------------------------------------------------------------

@app.route("/api/customer/register", methods=["POST"])
def customer_register():
    """First-time customer registration with password (min 6 chars) and session preservation."""
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    age = request.form.get("age")
    gender = request.form.get("gender")
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()

    if not name or not phone or not age or not gender:
        return jsonify({"success": False, "message": "Full Name, Contact Number, Age, and Gender are mandatory."}), 400

    if password:
        if len(password) < 6:
            return jsonify({"success": False, "message": "Password must be at least 6 characters long."}), 400
    else:
        # Default secure password of minimum 6 characters for quick registration
        password = f"rb@{phone[-4:]}2026"

    avatar_filename = None
    if 'avatar' in request.files:
        avatar_file = request.files['avatar']
        if avatar_file and avatar_file.filename != '' and allowed_file(avatar_file.filename):
            ext = avatar_file.filename.rsplit('.', 1)[1].lower()
            avatar_filename = f"avatar_{phone}_{uuid.uuid4().hex[:6]}.{ext}"
            avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))

    pwd_hash = hash_password(password)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, avatar_url, password_hash FROM users WHERE phone = ?", (phone,))
    existing_user = cursor.fetchone()

    if existing_user:
        user_id = existing_user["id"]
        final_avatar = avatar_filename or existing_user["avatar_url"]
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

    # Save to session for auto-login fallback
    user_data = {
        "id": user_id,
        "name": name,
        "phone": phone,
        "email": email,
        "age": int(age),
        "gender": gender,
        "avatar_url": final_avatar,
        "role": "customer"
    }
    session.pop("admin_user", None) # Ensure customer has strictly zero admin access
    session["user"] = user_data

    # Synchronize to Supabase Cloud Database in real time
    sync_user_async(name, phone, age, gender, email, pwd_hash, "customer", final_avatar)

    return jsonify({
        "success": True,
        "message": f"Welcome {name}! Your player account has been created successfully.",
        "user": user_data
    })

@app.route("/api/customer/login", methods=["POST"])
def customer_login():
    """Customer account sign in with phone/email and password (min 6 characters)."""
    data = request.get_json() if request.is_json else request.form
    login_input = (data.get("phone") or data.get("phone_or_email") or "").strip()
    password = (data.get("password") or "").strip()

    if not login_input or not password:
        return jsonify({"success": False, "message": "Contact Number and Password are required."}), 400

    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters long."}), 400

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
        return jsonify({"success": False, "message": "Invalid mobile number or password."}), 401

    user_data = dict(user)
    session.pop("admin_user", None) # Ensure customer has strictly zero admin access
    session["user"] = user_data

    return jsonify({
        "success": True,
        "message": f"Welcome back {user['name']}!",
        "user": user_data
    })

@app.route("/api/customer/logout", methods=["POST"])
def customer_logout():
    session.pop("user", None)
    return jsonify({"success": True, "message": "Logged out successfully."})

@app.route("/customer/auth", methods=["GET", "POST"])
@app.route("/customer/login", methods=["GET", "POST"])
def customer_login_page():
    """Dedicated Customer Authentication Webpage (Login & Register Gate for Booking)."""
    next_url = request.args.get("next") or request.form.get("next") or url_for("booking_page")

    # If already logged in as customer, proceed directly to booking
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
                    avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))

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
                "id": user_id,
                "name": name,
                "phone": phone,
                "email": email,
                "age": int(age),
                "gender": gender,
                "avatar_url": final_avatar,
                "role": "customer"
            }
            session.pop("admin_user", None)
            session["user"] = user_data
            
            # Real-time mirror to Supabase Cloud Database
            sync_user_async(name, phone, age, gender, email, pwd_hash, "customer", final_avatar)
            
            flash(f"Welcome {name}! Your player account has been created successfully.")
            return redirect(next_url)

        else: # Login
            login_input = (request.form.get("phone_or_email") or "").strip()
            password = (request.form.get("password") or "").strip()

            if not login_input or not password:
                flash("Contact Number and Password are required.")
                return render_template("customer_auth.html", next_url=next_url, active_tab="login")

            if len(password) < 6:
                flash("Password must be at least 6 characters long.")
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

            user_data = dict(user)
            session.pop("admin_user", None)
            session["user"] = user_data
            return redirect(next_url)

    return render_template("customer_auth.html", next_url=next_url, active_tab="login")

@app.route("/customer/logout")
def customer_logout_get():
    session.pop("user", None)
    return redirect(url_for("index"))

@app.route("/api/customer/lookup", methods=["POST"])
def customer_lookup():
    """Auto-login fallback using contact number."""
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"success": False, "message": "Phone number required"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phone, age, gender, avatar_url FROM users WHERE phone = ?", (phone,))
    u = cursor.fetchone()
    conn.close()

    if u:
        user_data = dict(u)
        session["user"] = user_data
        return jsonify({"success": True, "user": user_data})
    return jsonify({"success": False, "message": "Player not found. Please register."}), 404

@app.route("/")
def index():
    cleanup_expired_holds()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sports WHERE is_active = 1 ORDER BY id ASC")
    sports = cursor.fetchall()
    cursor.execute("SELECT * FROM promo_offers WHERE is_active = 1")
    promos = cursor.fetchall()
    conn.close()

    # Generate next 14 days
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

    return render_template(
        "index.html",
        sports=sports,
        date_pills=date_pills,
        promos=promos
    )

@app.route("/booking")
def booking_page():
    """Dedicated Customer Booking Webpage with Interactive Timetable & Scheduling."""
    # Enforce customer (or admin/partner) login before entering the booking section
    if not session.get("user") and not session.get("admin_user"):
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

    return render_template(
        "booking.html",
        sports=sports,
        date_pills=date_pills,
        promos=promos
    )

@app.route("/api/check-slots", methods=["POST"])
def check_slots():
    cleanup_expired_holds()
    data = request.get_json() or {}
    sport_id = data.get("sport_id", 1)
    slot_date = data.get("date", datetime.date.today().strftime("%Y-%m-%d"))

    conn = get_db()
    cursor = conn.cursor()

    # Fetch active/in_process bookings for this day and sport
    cursor.execute("""
        SELECT start_time, end_time, booking_status, payment_status, booking_ref
        FROM bookings
        WHERE sport_id = ? AND booking_date = ? AND booking_status != 'cancelled'
    """, (sport_id, slot_date))
    bookings = cursor.fetchall()

    # Fetch active held slots (yellow - 10 min hold lock)
    cursor.execute("""
        SELECT start_time, end_time, hold_token, expires_at
        FROM held_slots
        WHERE sport_id = ? AND slot_date = ? AND expires_at > CURRENT_TIMESTAMP
    """, (sport_id, slot_date))
    held = cursor.fetchall()
    conn.close()

    result_slots = []
    for start_t, end_t in SLOT_TIMINGS_30MIN:
        # Check if overlaps with any booked/in-process
        is_booked = False
        is_in_process = False
        for b in bookings:
            if not (end_t <= b["start_time"] or start_t >= b["end_time"]):
                if b["booking_status"] == "in_process" or b["payment_status"] == "in_process":
                    is_in_process = True
                else:
                    is_booked = True
                break

        # Check if held
        is_held = False
        held_token = None
        if not is_booked and not is_in_process:
            for h in held:
                if not (end_t <= h["start_time"] or start_t >= h["end_time"]):
                    is_held = True
                    held_token = h["hold_token"]
                    break

        price, _, floodlight = calculate_slot_price(sport_id, slot_date, start_t, end_t)

        status = "available"
        if is_booked or is_in_process:
            status = "booked" # Red
        elif is_held:
            status = "held"   # Yellow

        period = get_slot_period(start_t)
        start_12 = format_time_12hr(start_t)
        end_12 = format_time_12hr(end_t)

        result_slots.append({
            "start_time": start_t,
            "end_time": end_t,
            "start_time_12h": start_12,
            "end_time_12h": end_12,
            "period": period,
            "label_12h": f"{start_12} - {end_12}",
            "period_label": f"{period} ({start_12} - {end_12})",
            "status": status,
            "price": price,
            "has_floodlight": floodlight > 0,
            "held_token": held_token
        })

    return jsonify({
        "success": True,
        "date": slot_date,
        "sport_id": sport_id,
        "slots": result_slots
    })

@app.route("/api/hold-slot", methods=["POST"])
def hold_slot():
    """
    Locks chosen continuous slot range for 10 minutes.
    Turns slots YELLOW in system timetable.
    """
    cleanup_expired_holds()
    data = request.get_json() or {}
    sport_id = data.get("sport_id")
    slot_date = data.get("date")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    customer_phone = data.get("phone", "")

    if not all([sport_id, slot_date, start_time, end_time]):
        return jsonify({"success": False, "message": "Missing required slot parameters"}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Check for conflict with existing confirmed or in-process bookings
    cursor.execute("""
        SELECT id FROM bookings
        WHERE sport_id = ? AND booking_date = ? AND booking_status != 'cancelled'
        AND NOT (end_time <= ? OR start_time >= ?)
    """, (sport_id, slot_date, start_time, end_time))
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Selected time range has already been booked or is in-process."}), 409

    # Check for conflict with other held slots
    cursor.execute("""
        SELECT id FROM held_slots
        WHERE sport_id = ? AND slot_date = ? AND expires_at > CURRENT_TIMESTAMP
        AND NOT (end_time <= ? OR start_time >= ?)
    """, (sport_id, slot_date, start_time, end_time))
    if cursor.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Slot is currently on hold by another customer. Please wait or choose another slot."}), 409

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
        "expires_at": expires_at.isoformat(),
        "hold_minutes": SLOT_HOLD_MINUTES,
        "total_price": total_price,
        "duration_hours": duration,
        "floodlight_charge": floodlight
    })

@app.route("/api/release-hold", methods=["POST"])
def release_hold():
    data = request.get_json() or {}
    hold_token = data.get("hold_token")
    if hold_token:
        conn = get_db()
        conn.execute("DELETE FROM held_slots WHERE hold_token = ?", (hold_token,))
        conn.commit()
        conn.close()
    return jsonify({"success": True})

# -------------------------------------------------------------
# PHASE 3: ZERO-GATEWAY UPI CHECKOUT & PROOF VERIFICATION
# -------------------------------------------------------------

@app.route("/book")
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

    # Pre-generate a booking reference
    temp_ref = f"RB-{datetime.date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    # Generate UPI Intent URLs and dynamic QR codes for 50% and 100%
    upi_url_50 = generate_upi_intent_url(UPI_ID, UPI_PAYEE_NAME, advance_50, temp_ref, f"Advance 50% {temp_ref}")
    upi_url_100 = generate_upi_intent_url(UPI_ID, UPI_PAYEE_NAME, total_price, temp_ref, f"Full 100% {temp_ref}")

    qr_svg_50 = generate_qr_svg(upi_url_50)
    qr_svg_100 = generate_qr_svg(upi_url_100)

    # Check remembered customer in session
    saved_user = session.get("user") or {}

    conn.close()

    return render_template(
        "checkout.html",
        hold=hold,
        temp_ref=temp_ref,
        total_price=total_price,
        duration=duration,
        floodlight=floodlight,
        advance_50=advance_50,
        upi_url_50=upi_url_50,
        upi_url_100=upi_url_100,
        qr_svg_50=qr_svg_50,
        qr_svg_100=qr_svg_100,
        saved_user=saved_user
    )

@app.route("/api/apply-promo", methods=["POST"])
def apply_promo():
    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    total_amount = float(data.get("total_amount", 0))

    if not code:
        return jsonify({"success": False, "message": "Please enter a promo code"}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Check standard promo offers
    cursor.execute("SELECT * FROM promo_offers WHERE code = ? AND is_active = 1", (code,))
    promo = cursor.fetchone()

    # Check cancellation 25% credit promo codes
    cursor.execute("SELECT * FROM cancellation_credits WHERE promo_code = ? AND is_redeemed = 0", (code,))
    credit = cursor.fetchone()
    conn.close()

    if credit:
        discount = round(total_amount * (credit["discount_percent"] / 100.0), 2)
        return jsonify({
            "success": True,
            "code": code,
            "type": "cancellation_credit",
            "discount_amount": discount,
            "message": f"25% Future Booking Credit applied! (Saved Rs {discount})"
        })

    if not promo:
        return jsonify({"success": False, "message": "Invalid or expired promo code."}), 404

    if total_amount < promo["min_booking_amount"]:
        return jsonify({
            "success": False,
            "message": f"Code valid on bookings above Rs {promo['min_booking_amount']:.0f}."
        }), 400

    discount = 0.0
    free_product = None
    if promo["offer_type"] == "percent":
        discount = round(total_amount * (promo["discount_value"] / 100.0), 2)
    elif promo["offer_type"] == "flat":
        discount = min(total_amount, promo["discount_value"])
    elif promo["offer_type"] == "free_product":
        discount = 0.0
        free_product = promo["title"]

    return jsonify({
        "success": True,
        "code": code,
        "type": promo["offer_type"],
        "discount_amount": discount,
        "free_product": free_product,
        "message": f"Promo '{code}' applied successfully!"
    })

@app.route("/api/create-booking", methods=["POST"])
def create_booking():
    """
    Processes customer onboarding & creates booking with status 'in_process'.
    Uploads transaction screenshot proof.
    Automatically turns slot RED in system.
    """
    cleanup_expired_holds()

    hold_token = request.form.get("hold_token")
    booking_ref = request.form.get("booking_ref") or f"RB-{datetime.date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    payment_type = request.form.get("payment_type", "50_percent_token") # or '100_percent_full'
    promo_code = request.form.get("promo_code", "").strip().upper()

    # Customer fields (Mandatory: Full Name, Contact Number, Age, Gender)
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    age = request.form.get("age")
    gender = request.form.get("gender")
    notes = request.form.get("notes", "")

    if not name or not phone or not age or not gender:
        return jsonify({"success": False, "message": "Full Name, Contact Number, Age, and Gender are mandatory."}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Validate held slot
    cursor.execute("""
        SELECT * FROM held_slots WHERE hold_token = ?
    """, (hold_token,))
    hold = cursor.fetchone()

    if not hold:
        conn.close()
        return jsonify({"success": False, "message": "Slot hold has expired. Please choose a slot again."}), 400

    sport_id = hold["sport_id"]
    slot_date = hold["slot_date"]
    start_time = hold["start_time"]
    end_time = hold["end_time"]

    # Calculate base price
    gross_amount, duration, floodlight = calculate_slot_price(sport_id, slot_date, start_time, end_time)

    # Check promo discount
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
            # Check cancellation credits
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

    # Handle Payment Screenshot Proof Upload
    screenshot_filename = None
    if 'screenshot' in request.files:
        file = request.files['screenshot']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            screenshot_filename = f"proof_{booking_ref}_{uuid.uuid4().hex[:6]}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], screenshot_filename))

    # Optional avatar upload
    avatar_filename = None
    if 'avatar' in request.files:
        avatar_file = request.files['avatar']
        if avatar_file and avatar_file.filename != '' and allowed_file(avatar_file.filename):
            ext = avatar_file.filename.rsplit('.', 1)[1].lower()
            avatar_filename = f"avatar_{phone}_{uuid.uuid4().hex[:6]}.{ext}"
            avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))

    # Customer User Registration / Auto-login
    raw_password = (request.form.get("password") or "").strip()
    if raw_password and len(raw_password) >= 6:
        pwd_hash = hash_password(raw_password)
    else:
        pwd_hash = hash_password(f"rb@{phone[-4:]}2026")

    cursor.execute("SELECT id, password_hash FROM users WHERE phone = ?", (phone,))
    existing_user = cursor.fetchone()
    if existing_user:
        user_id = existing_user["id"]
        cursor.execute("""
            UPDATE users SET name = ?, age = ?, gender = ?
            WHERE id = ?
        """, (name, int(age), gender, user_id))
        if raw_password and len(raw_password) >= 6:
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))
        if avatar_filename:
            cursor.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_filename, user_id))
    else:
        cursor.execute("""
            INSERT INTO users (phone, name, age, gender, role, avatar_url, password_hash)
            VALUES (?, ?, ?, ?, 'customer', ?, ?)
        """, (phone, name, int(age), gender, avatar_filename, pwd_hash))
        user_id = cursor.lastrowid

    # Store user in session for auto-login / remembered profile
    session["user"] = {
        "id": user_id,
        "name": name,
        "phone": phone,
        "age": age,
        "gender": gender,
        "avatar_url": avatar_filename
    }

    # Create Booking under 'in_process' status (turns slot 🔴 RED in system)
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

    # Delete the hold token now that booking is created
    cursor.execute("DELETE FROM held_slots WHERE hold_token = ?", (hold_token,))

    conn.commit()
    conn.close()

    # Real-time mirror of user & booking to Supabase Cloud Database
    sync_user_async(name, phone, age, gender, None, pwd_hash, "customer", avatar_filename)
    sync_booking_async({
        "booking_ref": booking_ref,
        "customer_phone": phone,
        "sport_id": sport_id,
        "booking_date": slot_date,
        "start_time": start_time,
        "end_time": end_time,
        "duration_hours": duration,
        "base_rate": gross_amount,
        "floodlight_charge": floodlight,
        "discount_amount": discount_amount,
        "promo_code": promo_code,
        "total_amount": net_total,
        "advance_paid": advance_paid,
        "balance_due": balance_due,
        "payment_type": payment_type,
        "payment_status": "in_process",
        "booking_status": "in_process",
        "screenshot_url": screenshot_filename,
        "notes": notes
    })

    return jsonify({
        "success": True,
        "booking_ref": booking_ref,
        "redirect_url": url_for("booking_confirmation", booking_ref=booking_ref)
    })

@app.route("/confirmation/<booking_ref>")
def booking_confirmation(booking_ref):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone, u.age, u.gender,
               s.name as sport_name, s.slug as sport_slug
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_ref = ?
    """, (booking_ref,))
    booking = cursor.fetchone()
    conn.close()

    if not booking:
        flash("Booking reference not found.")
        return redirect(url_for("index"))

    # Construct Direct Admin WhatsApp Alert pre-filled message
    wa_msg = (
        f"🏏 *RUNBHOOMI BOX CRICKET - NEW MATCH BOOKING*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Ref ID:* {booking['booking_ref']}\n"
        f"👤 *Player:* {booking['customer_name']} ({booking['customer_phone']})\n"
        f"🏟️ *Sport:* {booking['sport_name']}\n"
        f"📅 *Date:* {booking['booking_date']}\n"
        f"⏰ *Time:* {format_slot_range_12hr(booking['start_time'], booking['end_time'])} ({booking['duration_hours']} hrs)\n"
        f"💰 *Total Match Amount:* ₹{booking['total_amount']:.0f}\n"
        f"🟢 *Advance Paid (Token):* ₹{booking['advance_paid']:.0f}\n"
        f"⚠️ *Balance Due at Turf:* ₹{booking['balance_due']:.0f}\n"
        f"📌 *Status:* {booking['booking_status'].upper()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Payment screenshot proof attached on portal."
    )
    admin_wa_url = f"https://wa.me/918858908825?text={urllib.parse.quote(wa_msg)}"

    # Generate Digital Pass QR Code
    pass_data = f"RUNBHOOMI-PASS|{booking['booking_ref']}|{booking['customer_name']}|{booking['booking_date']}|{booking['start_time']}"
    pass_qr_base64 = generate_qr_base64_png(pass_data)

    return render_template(
        "confirmation.html",
        booking=booking,
        admin_wa_url=admin_wa_url,
        pass_qr_base64=pass_qr_base64
    )

@app.route("/voucher/<booking_ref>")
@app.route("/receipt/<booking_ref>")
def match_voucher(booking_ref):
    """Printable / Downloadable Digital Match Voucher & Receipt"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_ref = ?
    """, (booking_ref,))
    booking = cursor.fetchone()
    
    # Fetch any canteen items attached to this booking
    cursor.execute("""
        SELECT o.*, c.name as item_name
        FROM booking_canteen_orders o
        JOIN canteen_items c ON o.item_id = c.id
        WHERE o.booking_id = ?
    """, (booking["id"] if booking else 0,))
    canteen_orders = cursor.fetchall()
    conn.close()

    if not booking:
        return "Booking not found", 404

    pass_data = f"RUNBHOOMI-PASS|{booking['booking_ref']}|{booking['customer_name']}|{booking['booking_date']}|{booking['start_time']}"
    pass_qr_base64 = generate_qr_base64_png(pass_data)

    return render_template(
        "voucher.html",
        booking=booking,
        canteen_orders=canteen_orders,
        pass_qr_base64=pass_qr_base64
    )

# -------------------------------------------------------------
# PHASE 4: MULTI-LINE HELP & COMMUNITY DESK (/contact)
# -------------------------------------------------------------

@app.route("/contact")
def contact_page():
    return render_template("contact.html")

@app.route("/canteen")
def canteen_page():
    """In-House Sports Canteen POS Catalog - Admin & Authorized Partners Only."""
    if not is_admin_or_partner():
        flash("Canteen ordering and POS is managed strictly by ground staff and admin.")
        return redirect(url_for("admin_login"))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM canteen_items WHERE is_active = 1 ORDER BY price ASC")
    items = [dict(row) for row in cursor.fetchall()]

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
            grouped[cat] = {
                "title": category_labels.get(cat, cat.title()),
                "products": cat_items
            }
    # Catch any remaining items
    for i in items:
        cat = i.get("category")
        if cat not in grouped:
            cat_items = [it for it in items if it.get("category") == cat]
            if cat_items:
                grouped[cat] = {
                    "title": category_labels.get(cat, (cat or "Other").replace('_', ' ').title()),
                    "products": cat_items
                }

    return render_template("canteen.html", grouped_menu=grouped, all_items=items, total_count=len(items))

@app.route("/api/canteen/menu")
def api_canteen_menu():
    """JSON API for canteen items."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, name, category, price, stock FROM canteen_items WHERE is_active = 1 ORDER BY category, price ASC")
    items = [dict(row) for row in cursor.fetchall()]
    return jsonify({
        "success": True,
        "items": items,
        "hygiene_notice": CANTEEN_HYGIENE_NOTICE
    })

# -------------------------------------------------------------
# PHASE 5 & 6: ADMIN & PARTNER COMMAND CENTER & REVENUE
# -------------------------------------------------------------

def is_admin_or_partner():
    # If customer is active and not explicitly an admin_user, deny admin access
    if session.get("user") and not session.get("admin_user"):
        return False
    user = session.get("admin_user")
    return user is not None and user.get("role") in ["admin", "partner"]

def is_super_admin():
    # If customer is active and not explicitly an admin_user, deny admin access
    if session.get("user") and not session.get("admin_user"):
        return False
    user = session.get("admin_user")
    return user is not None and user.get("role") == "admin"

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        login_input = (request.form.get("phone_or_email") or "").strip()
        password = request.form.get("password") or ""
        pwd_hash = hash_password(password)

        conn = get_db()
        cursor = conn.cursor()

        # Check super admin (phone: 8858908825 or email)
        cursor.execute("""
            SELECT * FROM users
            WHERE (phone = ? OR email = ?) AND role = 'admin' AND password_hash = ?
        """, (login_input, login_input, pwd_hash))
        admin = cursor.fetchone()

        if admin:
            session.pop("user", None) # Clear any customer session
            session["admin_user"] = {
                "id": admin["id"],
                "name": admin["name"],
                "phone": admin["phone"],
                "role": "admin"
            }
            conn.close()
            return redirect(url_for("admin_dashboard"))

        # Check partner table
        cursor.execute("""
            SELECT * FROM partners
            WHERE (phone = ? OR email = ?) AND password_hash = ? AND is_active = 1
        """, (login_input, login_input, pwd_hash))
        partner = cursor.fetchone()

        if partner:
            session.pop("user", None) # Clear any customer session
            session["admin_user"] = {
                "id": partner["id"],
                "name": partner["name"],
                "phone": partner["phone"],
                "role": "partner"
            }
            conn.close()
            return redirect(url_for("admin_dashboard"))

        conn.close()
        flash("Invalid mobile/email or password.")
        return render_template("admin_login.html")

    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_user", None)
    return redirect(url_for("admin_login"))

@app.route("/admin")
@app.route("/admin/dashboard")
def admin_dashboard():
    if not is_admin_or_partner():
        if session.get("user"):
            flash("Access Denied: Customer accounts do not have access to Admin Command Center.")
        return redirect(url_for("admin_login"))

    conn = get_db()
    cursor = conn.cursor()

    # 1. In-Process Bookings Window
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

    # 2. Confirmed Booked Window
    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone, u.age, u.gender,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_status = 'confirmed'
        ORDER BY b.booking_date DESC, b.start_time DESC
    """)
    confirmed_bookings = cursor.fetchall()

    # 3. Cancelled Bookings Window
    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone,
               s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.booking_status = 'cancelled'
        ORDER BY b.created_at DESC
    """)
    cancelled_bookings = cursor.fetchall()

    # Partners list (max 2)
    cursor.execute("SELECT * FROM partners WHERE is_active = 1")
    partners = cursor.fetchall()

    # Canteen items for POS
    cursor.execute("SELECT * FROM canteen_items WHERE is_active = 1 ORDER BY category, name")
    canteen_items = cursor.fetchall()

    # Sports list
    cursor.execute("SELECT * FROM sports WHERE is_active = 1")
    sports = cursor.fetchall()

    # Registered Customer Accounts Directory
    cursor.execute("""
        SELECT u.id, u.name, u.phone, u.email, u.age, u.gender, u.created_at,
               COUNT(b.id) as booking_count,
               COALESCE(SUM(b.total_amount), 0) as total_spent
        FROM users u
        LEFT JOIN bookings b ON u.id = b.user_id AND b.booking_status = 'confirmed'
        WHERE u.role = 'customer'
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """)
    registered_customers = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        in_process_bookings=in_process_bookings,
        confirmed_bookings=confirmed_bookings,
        cancelled_bookings=cancelled_bookings,
        partners=partners,
        canteen_items=canteen_items,
        sports=sports,
        registered_customers=registered_customers,
        admin_user=session.get("admin_user")
    )

@app.route("/admin/booking/confirm/<int:booking_id>", methods=["POST"])
def confirm_booking(booking_id):
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    user = session.get("admin_user")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bookings
        SET booking_status = 'confirmed',
            payment_status = 'verified',
            confirmed_by = ?,
            confirmed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (user.get("name", "Staff"), booking_id))
    conn.commit()

    # Fetch details for automated client WhatsApp confirmation notification
    cursor.execute("""
        SELECT b.*, u.name as customer_name, u.phone as customer_phone, s.name as sport_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sports s ON b.sport_id = s.id
        WHERE b.id = ?
    """, (booking_id,))
    b = cursor.fetchone()
    conn.close()

    # Format Automated Client Confirmation WhatsApp notification
    wa_msg = (
        f"🎉 *BOOKING CONFIRMED - RUNBHOOMI BOX CRICKET*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Dear {b['customer_name']},\n"
        f"Your turf match slot is *CONFIRMED*!\n\n"
        f"📋 *Booking ID:* {b['booking_ref']}\n"
        f"🏟️ *Sport:* {b['sport_name']}\n"
        f"📅 *Date:* {b['booking_date']}\n"
        f"⏰ *Slot Timing:* {format_slot_range_12hr(b['start_time'], b['end_time'])}\n"
        f"🟢 *Advance Token Received:* ₹{b['advance_paid']:.0f}\n"
        f"⚠️ *Remaining Balance Due at Turf:* ₹{b['balance_due']:.0f}\n\n"
        f"📍 *Turf Address:*\n{TURF_ADDRESS}\n\n"
        f"👥 *Join Player Community Group:*\n{WHATSAPP_COMMUNITY_URL}\n"
        f"📸 *Follow on Instagram:*\n{INSTAGRAM_URL}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"See you at the turf! Please arrive 10 minutes prior to kickoff."
    )
    client_wa_url = f"https://wa.me/91{b['customer_phone']}?text={urllib.parse.quote(wa_msg)}"

    return jsonify({
        "success": True,
        "message": f"Booking {b['booking_ref']} confirmed successfully!",
        "client_wa_url": client_wa_url
    })

@app.route("/admin/booking/cancel/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):
    """
    Enforces strict non-refundable cancellation policy:
    50% of the booking amount is deducted/retained as cancellation fee.
    Automatically generates a 25% discount promo code for future booking!
    """
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, u.phone as customer_phone
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        WHERE b.id = ?
    """, (booking_id,))
    b = cursor.fetchone()

    if not b:
        conn.close()
        return jsonify({"success": False, "message": "Booking not found"}), 404

    # Calculate 50% retained fee
    retained_fee = round(b["total_amount"] * 0.5, 2)
    credit_code = f"CREDIT25-{uuid.uuid4().hex[:6].upper()}"

    # Log retained fee and update status
    cursor.execute("""
        UPDATE bookings
        SET booking_status = 'cancelled',
            payment_status = 'cancelled',
            cancellation_fee = ?,
            future_credit_code = ?
        WHERE id = ?
    """, (retained_fee, credit_code, booking_id))

    # Issue 25% future credit promo code
    cursor.execute("""
        INSERT INTO cancellation_credits (booking_id, phone, promo_code, discount_percent, retained_fee)
        VALUES (?, ?, ?, 25.0, ?)
    """, (booking_id, b["customer_phone"], credit_code, retained_fee))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": f"Booking cancelled. Retained 50% fee: ₹{retained_fee}. Generated 25% Credit Promo: {credit_code}",
        "credit_code": credit_code,
        "retained_fee": retained_fee
    })

@app.route("/admin/booking/collect-balance/<int:booking_id>", methods=["POST"])
def collect_balance(booking_id):
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bookings
        SET advance_paid = total_amount,
            balance_due = 0.0
        WHERE id = ?
    """, (booking_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Balance marked as collected at turf."})

@app.route("/admin/booking/add-canteen/<int:booking_id>", methods=["POST"])
def add_canteen_to_bill(booking_id):
    """Adds single or multiple canteen items to active running match bill."""
    if not is_admin_or_partner():
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.get_json() or {}
    items_to_add = data.get("items", [])
    if not items_to_add and data.get("item_id"):
        items_to_add = [{"item_id": data.get("item_id"), "quantity": int(data.get("quantity", 1))}]

    if not items_to_add:
        return jsonify({"success": False, "message": "No items selected to add."}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Verify booking exists
    cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
    booking = cursor.fetchone()
    if not booking:
        conn.close()
        return jsonify({"success": False, "message": "Booking not found."}), 404

    user = session.get("admin_user", {})
    added_by = user.get("name", "Staff")

    total_added_price = 0.0
    added_summary = []

    for entry in items_to_add:
        item_id = entry.get("item_id")
        qty = int(entry.get("quantity", 1))
        if qty <= 0:
            continue

        cursor.execute("SELECT * FROM canteen_items WHERE id = ?", (item_id,))
        item = cursor.fetchone()
        if not item:
            continue

        unit_price = item["price"]
        line_total = unit_price * qty
        total_added_price += line_total
        added_summary.append(f"{qty}x {item['name']}")

        cursor.execute("""
            INSERT INTO booking_canteen_orders (booking_id, item_id, quantity, unit_price, total_price, added_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (booking_id, item_id, qty, unit_price, line_total, added_by))

        # Reduce stock
        cursor.execute("""
            UPDATE canteen_items SET stock = MAX(0, stock - ?) WHERE id = ?
        """, (qty, item_id))

    if total_added_price == 0:
        conn.close()
        return jsonify({"success": False, "message": "No valid items were processed."}), 400

    # Update booking balance due and total amount
    cursor.execute("""
        UPDATE bookings
        SET total_amount = total_amount + ?,
            balance_due = balance_due + ?
        WHERE id = ?
    """, (total_added_price, total_added_price, booking_id))

    conn.commit()
    conn.close()

    summary_str = ", ".join(added_summary)
    return jsonify({
        "success": True,
        "message": f"Added {summary_str} (₹{int(total_added_price)}) to match tab.",
        "total_added": total_added_price,
        "items_count": len(added_summary)
    })

# Partner Management (Owner/Super Admin Only, Max 2)
@app.route("/admin/partners/add", methods=["POST"])
def add_partner():
    if not is_super_admin():
        flash("Only Primary Business Owner (Aditya Goyal) can add partners.")
        return redirect(url_for("admin_dashboard"))

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    if not name or not phone or not password:
        flash("Partner Name, Phone, and Password are required.")
        return redirect(url_for("admin_dashboard"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM partners WHERE is_active = 1")
    count = cursor.fetchone()[0]

    if count >= 2:
        conn.close()
        flash("Maximum 2 partners allowed in system.")
        return redirect(url_for("admin_dashboard"))

    pwd_hash = hash_password(password)
    cursor.execute("""
        INSERT INTO partners (name, phone, email, password_hash)
        VALUES (?, ?, ?, ?)
    """, (name, phone, email, pwd_hash))
    conn.commit()
    conn.close()

    flash(f"Partner {name} added successfully.")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/partners/delete/<int:partner_id>", methods=["POST"])
def delete_partner(partner_id):
    if not is_super_admin():
        flash("Only Primary Business Owner can remove partners.")
        return redirect(url_for("admin_dashboard"))

    conn = get_db()
    conn.execute("DELETE FROM partners WHERE id = ?", (partner_id,))
    conn.commit()
    conn.close()

    flash("Partner removed successfully.")
    return redirect(url_for("admin_dashboard"))

# Dynamic Tariff Control (Owner / Super Admin Only)
@app.route("/admin/sports/pricing/update", methods=["POST"])
def update_sport_pricing():
    if not is_super_admin():
        return jsonify({"success": False, "message": "Access Denied: Altering tariffs requires Primary Owner permissions."}), 403

    data = request.get_json() or {}
    rule_id = data.get("rule_id")
    hourly_rate = float(data.get("hourly_rate", 0))
    floodlight_charge = float(data.get("floodlight_charge", 0))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE pricing_rules
        SET hourly_rate = ?, floodlight_charge = ?
        WHERE id = ?
    """, (hourly_rate, floodlight_charge, rule_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Pricing rule updated successfully!"})

# Revenue Intelligence & Analytics (Owner / Super Admin Only - Strictly Restricted for Partners)
@app.route("/admin/revenue")
def revenue_analytics():
    if not is_admin_or_partner():
        return redirect(url_for("admin_login"))
    if not is_super_admin():
        flash("Access Denied: Revenue Intelligence is strictly restricted to Primary Turf Owner Aditya Goyal.")
        return redirect(url_for("admin_dashboard"))

    time_filter = request.args.get("filter", "30d") # 'today', '7d', '30d', '6m', '1y'

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

    # --- 1. MANDATORY METRIC: TOTAL AMOUNT EARNED ---
    # Overall cleared revenue: Confirmed Match tokens & settled balances + All Canteen Concessions
    cursor.execute("""
        SELECT COALESCE(SUM(total_amount - balance_due), 0)
        FROM bookings
        WHERE booking_status = 'confirmed'
    """)
    total_booking_earned = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(total_price), 0) FROM booking_canteen_orders")
    total_canteen_orders = cursor.fetchone()[0]

    total_amount_earned = total_booking_earned + total_canteen_orders

    # --- 2. MANDATORY METRIC: TOTAL PENDING AMOUNT ---
    # Outstanding balance due across all active confirmed matches
    cursor.execute("""
        SELECT COALESCE(SUM(balance_due), 0), COUNT(*)
        FROM bookings
        WHERE booking_status = 'confirmed' AND balance_due > 0
    """)
    pend_summary = cursor.fetchone()
    total_pending_amount = pend_summary[0]
    total_pending_count = pend_summary[1]

    # --- 3. MANDATORY METRIC: TOTAL AMOUNT TO COLLECT AT THAT DAY (TODAY) ---
    # Remaining balance due scheduled to be collected at the ground specifically today
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

    # Today's Specific Matches with Balances
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

    # Filtered window matches played (confirmed)
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(total_amount), 0), COALESCE(SUM(advance_paid), 0)
        FROM bookings
        WHERE booking_status = 'confirmed' AND booking_date >= ?
    """, (start_date,))
    row = cursor.fetchone()
    total_matches = row[0]
    gross_booking_sales = row[1]
    amount_collected = row[2]

    # Filtered canteen concession revenue
    cursor.execute("""
        SELECT COALESCE(SUM(o.total_price), 0)
        FROM booking_canteen_orders o
        JOIN bookings b ON o.booking_id = b.id
        WHERE b.booking_status = 'confirmed' AND b.booking_date >= ?
    """, (start_date,))
    canteen_revenue = cursor.fetchone()[0]

    total_collected_revenue = amount_collected + canteen_revenue

    # All Pending Balance Tracker Table
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

    # Sports breakdown
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
        time_filter=time_filter,
        today_date_str=today_str,
        today_date_formatted=today_formatted,
        total_amount_earned=total_amount_earned,
        total_booking_earned=total_booking_earned,
        total_canteen_orders=total_canteen_orders,
        total_pending_amount=total_pending_amount,
        total_pending_count=total_pending_count,
        today_amount_to_collect=today_amount_to_collect,
        today_matches_count=today_matches_count,
        today_earned=today_earned,
        today_gross_sales=today_gross_sales,
        today_bookings=today_bookings,
        total_matches=total_matches,
        gross_booking_sales=gross_booking_sales,
        amount_collected=amount_collected,
        canteen_revenue=canteen_revenue,
        total_collected_revenue=total_collected_revenue,
        pending_balances=pending_balances,
        sports_breakdown=sports_breakdown
    )

# Serve uploaded screenshots / avatars
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)

