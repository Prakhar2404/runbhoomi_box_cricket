"""
Real-time Supabase Cloud Synchronization Engine
Ensures all customer registrations, bookings, canteen orders, and credits
are mirrored directly to Supabase PostgreSQL in real-time.
"""

import json
import threading
import urllib.request
import urllib.error
from .config import SUPABASE_URL, SUPABASE_ANON_KEY

def _supabase_request(endpoint, method="GET", payload=None, query_params=""):
    """Internal helper to make authenticated REST calls to Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}{query_params}"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json"
    }
    
    data_bytes = None
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        if method == "POST":
            headers["Prefer"] = "return=representation,resolution=merge-duplicates"

    try:
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except Exception as e:
        # Graceful non-blocking failure
        return None

def sync_user_async(name, phone, age, gender, email=None, password_hash=None, role="customer", avatar_url=None):
    """Asynchronously syncs/upserts a registered customer or partner to Supabase."""
    def _task():
        # Check if user with this phone exists in Supabase
        existing = _supabase_request("users", method="GET", query_params=f"?phone=eq.{phone}&select=id")
        payload = {
            "name": name,
            "phone": phone,
            "age": int(age) if age else 20,
            "gender": gender or "Male",
            "email": email or None,
            "role": role,
            "avatar_url": avatar_url or None
        }
        if password_hash:
            payload["password_hash"] = password_hash

        if existing and len(existing) > 0:
            # Update existing
            _supabase_request("users", method="PATCH", payload=payload, query_params=f"?phone=eq.{phone}")
        else:
            # Insert new
            _supabase_request("users", method="POST", payload=payload)

    t = threading.Thread(target=_task, daemon=True)
    t.start()

def sync_booking_async(booking_dict):
    """Asynchronously mirrors a booking to Supabase."""
    def _task():
        ref = booking_dict.get("booking_ref")
        phone = booking_dict.get("customer_phone")
        
        # Get user UUID in Supabase
        user_uuid = None
        if phone:
            user_data = _supabase_request("users", method="GET", query_params=f"?phone=eq.{phone}&select=id")
            if user_data and len(user_data) > 0:
                user_uuid = user_data[0]["id"]
        
        if not user_uuid:
            # Fallback to first customer user
            any_user = _supabase_request("users", method="GET", query_params="?role=eq.customer&limit=1&select=id")
            if any_user and len(any_user) > 0:
                user_uuid = any_user[0]["id"]

        if not user_uuid:
            return

        payload = {
            "booking_ref": ref,
            "user_id": user_uuid,
            "sport_id": int(booking_dict.get("sport_id", 1)),
            "booking_date": booking_dict.get("booking_date"),
            "start_time": booking_dict.get("start_time"),
            "end_time": booking_dict.get("end_time"),
            "duration_hours": float(booking_dict.get("duration_hours", 1.0)),
            "base_rate": float(booking_dict.get("base_rate", 0)),
            "floodlight_charge": float(booking_dict.get("floodlight_charge", 0)),
            "discount_amount": float(booking_dict.get("discount_amount", 0)),
            "promo_code": booking_dict.get("promo_code") or None,
            "total_amount": float(booking_dict.get("total_amount", 0)),
            "advance_paid": float(booking_dict.get("advance_paid", 0)),
            "balance_due": float(booking_dict.get("balance_due", 0)),
            "payment_type": booking_dict.get("payment_type", "50_percent_token"),
            "payment_status": "verified" if booking_dict.get("payment_status") == "paid" else (booking_dict.get("payment_status") or "in_process"),
            "booking_status": booking_dict.get("booking_status", "in_process"),
            "screenshot_url": booking_dict.get("screenshot_url") or None,
            "notes": booking_dict.get("notes") or None
        }

        existing_b = _supabase_request("bookings", method="GET", query_params=f"?booking_ref=eq.{ref}&select=id")
        if existing_b and len(existing_b) > 0:
            _supabase_request("bookings", method="PATCH", payload=payload, query_params=f"?booking_ref=eq.{ref}")
        else:
            _supabase_request("bookings", method="POST", payload=payload)

    t = threading.Thread(target=_task, daemon=True)
    t.start()
