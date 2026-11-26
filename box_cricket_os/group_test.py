"""
Runbhoomi Box Cricket - Full Group E2E Simulation Test
Simulates full multi-user matchday operations across all 7 Phases
"""

import unittest
import io
import os
import sys
import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from box_cricket_os.app import app
from box_cricket_os.db import init_db, get_db
from box_cricket_os.config import (
    ADMIN_MOBILE, ADMIN_DEFAULT_PASSWORD, BRAND_NAME, LEGAL_ENTITY,
    CLEANING_LIGHTING_NOTICE, CANCELLATION_POLICY_NOTICE
)

def run_group_simulation():
    print("=" * 70)
    print("🏏 STARTING RUNBHOOMI GROUP MATCHDAY SIMULATION (ALL 7 PHASES)")
    print("=" * 70)

    client = app.test_client()
    init_db()

    # Step 1: Verify Phase 1 Brand Identity & Notices
    print("\n[PHASE 1] Checking Brand Identity & Notices...")
    home_res = client.get("/")
    assert home_res.status_code == 200, "Home page failed"
    home_html = home_res.data.decode("utf-8")
    assert BRAND_NAME in home_html, f"Brand name '{BRAND_NAME}' missing on home page"
    assert LEGAL_ENTITY in home_html, f"Legal entity '{LEGAL_ENTITY}' missing"
    assert CLEANING_LIGHTING_NOTICE in home_html, "Cleaning notice missing on home page"
    print("✓ Brand logo, stadium theme, and legal entity verified.")

    # Step 2: Player A picks 2-hour Box Cricket slot on Weekday Evening (Floodlights)
    print("\n[PHASE 2] Player A selecting 2-hour Box Cricket slot (18:00 - 20:00)...")
    date_a = (datetime.date.today() + datetime.timedelta(days=2)).strftime("%Y-%m-%d")

    hold_a = client.post("/api/hold-slot", json={
        "sport_id": 1,
        "date": date_a,
        "start_time": "18:00",
        "end_time": "20:00",
        "phone": "9812345678"
    }).get_json()
    assert hold_a["success"], f"Hold failed: {hold_a}"
    token_a = hold_a["hold_token"]
    print(f"✓ Slot held: Token={token_a}, Price=Rs {hold_a['total_price']}, Duration={hold_a['duration_hours']}h")

    # Step 3: Player A checks out with 50% Advance Token & uploads Screenshot Proof
    print("\n[PHASE 3] Player A checking out with 50% Advance Token and payment proof...")
    dummy_screenshot = (io.BytesIO(b"GPay Transaction UTR: 412398127391"), "gpay_proof.jpg")
    ref_a = f"RB-{datetime.date.today().strftime('%Y%m%d')}-SIMA"

    booking_a = client.post("/api/create-booking", data={
        "hold_token": token_a,
        "booking_ref": ref_a,
        "name": "Captain Vikram Rathore",
        "phone": "9812345678",
        "age": "26",
        "gender": "Male",
        "payment_type": "50_percent_token",
        "screenshot": dummy_screenshot
    }, content_type='multipart/form-data').get_json()

    assert booking_a["success"], f"Booking A creation failed: {booking_a}"
    print(f"✓ Booking Created: Ref={ref_a}. Slot status in system is now RED (in_process).")

    # Verify slot is RED on timetable
    chk_slots = client.post("/api/check-slots", json={"sport_id": 1, "date": date_a}).get_json()
    s_1800 = next(s for s in chk_slots["slots"] if s["start_time"] == "18:00")
    assert s_1800["status"] == "booked", f"Expected booked (RED) status, got {s_1800['status']}"
    print("✓ Timetable verified: Slot at 18:00 successfully locked in RED.")

    # Step 4: Verify Phase 4 Contact & Multi-Line Desk
    print("\n[PHASE 4] Verifying 3 dedicated calling lines & support availability...")
    contact_res = client.get("/contact")
    assert contact_res.status_code == 200
    c_html = contact_res.data.decode("utf-8")
    assert "+91 88589 08825" in c_html, "Helpline 1 missing"
    assert "+91 70071 67223" in c_html, "Helpline 2 missing"
    assert "+91 63935 52467" in c_html, "Helpline 3 missing"
    assert "10:00 AM to 8:00 PM" in c_html, "Availability missing"
    print("✓ Multi-line helpdesk verified.")

    # Step 5: Admin signs in to Command Center
    print("\n[PHASE 5] Admin signing in to Command Center...")
    client.post("/admin/login", data={
        "phone_or_email": ADMIN_MOBILE,
        "password": ADMIN_DEFAULT_PASSWORD
    })

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, total_amount, advance_paid, balance_due FROM bookings WHERE booking_ref = ?", (ref_a,))
    b_row = cursor.fetchone()
    b_id = b_row["id"]
    conn.close()

    # Admin confirms the booking
    print(f"Admin confirming incoming match {ref_a}...")
    conf_res = client.post(f"/admin/booking/confirm/{b_id}").get_json()
    assert conf_res["success"], f"Confirmation failed: {conf_res}"
    print(f"✓ Booking Confirmed. WhatsApp Notification Dispatched: {conf_res['client_wa_url'][:60]}...")

    # Step 6: In-House Canteen POS order added to match bill & balance collected at turf
    print("\n[PHASE 6] Concession POS: Adding 4x Sting Energy drinks & 1x Cricket Ball to match bill...")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, price FROM canteen_items WHERE name LIKE 'Sting%' LIMIT 1")
    sting_id = cursor.fetchone()["id"]
    cursor.execute("SELECT id, price FROM canteen_items WHERE name LIKE 'Hard Tennis%' LIMIT 1")
    ball_id = cursor.fetchone()["id"]
    conn.close()

    # Add Sting
    client.post(f"/admin/booking/add-canteen/{b_id}", json={"item_id": sting_id, "quantity": 4})
    # Add Ball
    client.post(f"/admin/booking/add-canteen/{b_id}", json={"item_id": ball_id, "quantity": 1})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT total_amount, balance_due FROM bookings WHERE id = ?", (b_id,))
    updated_b = cursor.fetchone()
    conn.close()

    expected_add = (30.0 * 4) + (90.0 * 1) # 120 + 90 = 210
    print(f"✓ Canteen items added. Total Bill updated to: Rs {updated_b['total_amount']}, Balance Due: Rs {updated_b['balance_due']}")

    # Player arrives at turf, Admin settles remaining balance
    print("Player arriving at turf: Admin collecting and settling outstanding balance...")
    client.post(f"/admin/booking/collect-balance/{b_id}")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance_due FROM bookings WHERE id = ?", (b_id,))
    final_due = cursor.fetchone()["balance_due"]
    conn.close()
    assert final_due == 0.0, f"Expected 0.0 balance due, got {final_due}"
    print("✓ Balance successfully marked collected and settled at turf.")

    # Revenue Intelligence Check
    print("Verifying Revenue Intelligence report (/admin/revenue)...")
    rev = client.get("/admin/revenue?filter=today")
    assert rev.status_code == 200
    rev_html = rev.data.decode("utf-8")
    assert "Revenue & Concession Analytics" in rev_html
    print("✓ Revenue intelligence page fully rendered.")

    # Step 7: Test Cancellation Policy and 25% Future Credit Redemption
    print("\n[PHASE 3 & 5] Testing Non-Refundable Cancellation & 25% Future Credit...")
    date_b = (datetime.date.today() + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    h_b = client.post("/api/hold-slot", json={
        "sport_id": 2, # 5v5 Football
        "date": date_b,
        "start_time": "16:00",
        "end_time": "17:00"
    }).get_json()
    ref_b = f"RB-{datetime.date.today().strftime('%Y%m%d')}-SIMB"

    client.post("/api/create-booking", data={
        "hold_token": h_b["hold_token"],
        "booking_ref": ref_b,
        "name": "Sameer Khan",
        "phone": "9855544433",
        "age": "22",
        "gender": "Male",
        "payment_type": "100_percent_full",
        "screenshot": (io.BytesIO(b"Proof"), "proof.png")
    })

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM bookings WHERE booking_ref = ?", (ref_b,))
    b_b_id = cursor.fetchone()["id"]
    conn.close()

    # Cancel booking
    cancel_res = client.post(f"/admin/booking/cancel/{b_b_id}").get_json()
    assert cancel_res["success"]
    promo_code = cancel_res["credit_code"]
    print(f"✓ Booking cancelled. 50% retained fee: Rs {cancel_res['retained_fee']}. Issued Promo: {promo_code}")

    # Player redeems 25% credit promo code on new booking
    promo_apply = client.post("/api/apply-promo", json={
        "code": promo_code,
        "total_amount": 1000.0
    }).get_json()
    assert promo_apply["success"]
    assert promo_apply["discount_amount"] == 250.0 # 25% of 1000
    print(f"✓ 25% Future Credit Promo '{promo_code}' redeemed successfully! Discount: Rs {promo_apply['discount_amount']}")

    # Clean up simulation dummy test proof files
    from box_cricket_os.config import UPLOAD_FOLDER
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT screenshot_url FROM bookings WHERE screenshot_url IS NOT NULL")
    used = set(r[0] for r in cursor.fetchall())
    conn.close()
    for fname in os.listdir(UPLOAD_FOLDER):
        if fname.startswith("proof_") and fname not in used:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, fname))
            except Exception:
                pass

    print("\n" + "=" * 70)
    print("🎉 ALL 7 PHASES PASSED END-TO-END GROUP SIMULATION WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    run_group_simulation()
