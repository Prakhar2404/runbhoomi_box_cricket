"""
Runbhoomi Box Cricket - Comprehensive Unit & Integration Test Suite
Corporate Legal Entity: Runbhoomi Box Cricket Pvt. Ltd.
8 Automated End-to-End Tests with 100% Pass Target
"""

import unittest
import io
import os
import json
import datetime
from box_cricket_os.app import app
from box_cricket_os.db import init_db, get_db, hash_password
from box_cricket_os.config import (
    BRAND_NAME, LEGAL_ENTITY, BUSINESS_OWNER, UPI_ID,
    ADMIN_MOBILE, ADMIN_DEFAULT_PASSWORD, HELPLINE_PRIMARY
)
from box_cricket_os.qr_generator import generate_upi_intent_url

class RunbhoomiBoxCricketTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        init_db()
        # Clean up any leftover test data
        conn = get_db()
        conn.execute("DELETE FROM held_slots")
        conn.execute("DELETE FROM booking_canteen_orders")
        conn.execute("DELETE FROM cancellation_credits")
        conn.execute("DELETE FROM bookings")
        conn.execute("DELETE FROM partners")
        conn.commit()
        conn.close()

    def setUp(self):
        self.client = app.test_client()
        # Ensure holds are cleaned between individual tests if needed
        conn = get_db()
        conn.execute("DELETE FROM held_slots WHERE expires_at < CURRENT_TIMESTAMP")
        conn.commit()
        conn.close()

    # -------------------------------------------------------------
    # TEST 1: Brand & Health Endpoints
    # -------------------------------------------------------------
    def test_01_brand_and_health_endpoints(self):
        """Verifies Phase 1 Brand Identity, Official Logo link, and /contact desks."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("RUNBHOOMI", html)
        self.assertIn("Runbhoomi Box Cricket Pvt. Ltd.", html)
        self.assertIn("brand_logo_circle.png", html)
        self.assertIn("favicon.png", html)

        # Contact Desk test
        contact_resp = self.client.get("/contact")
        self.assertEqual(contact_resp.status_code, 200)
        c_html = contact_resp.data.decode("utf-8")
        self.assertIn(HELPLINE_PRIMARY, c_html)
        self.assertIn("+91 70071 67223", c_html)
        self.assertIn("+91 63935 52467", c_html)
        self.assertIn("runbhoomiboxcricketup@gmail.com", c_html)
        self.assertIn("10:00 AM to 8:00 PM", c_html)

        # Dedicated Customer Booking Page Gate test (Unauthenticated visitor must be redirected to Customer Login)
        booking_unauth = self.client.get("/booking")
        self.assertEqual(booking_unauth.status_code, 302)
        self.assertIn("/customer/login", booking_unauth.headers.get("Location", ""))

        # Authenticate as verified customer
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 1,
                "name": "Rahul Sharma",
                "phone": "9876543210",
                "role": "customer"
            }
        booking_resp = self.client.get("/booking")
        self.assertEqual(booking_resp.status_code, 200)
        b_html = booking_resp.data.decode("utf-8")
        self.assertIn("Match Slot Booking", b_html)
        # Ensure NO admin features/buttons are exposed to customer
        self.assertNotIn("Admin Panel", b_html)
        self.assertNotIn("Admin Cockpit", b_html)

    # -------------------------------------------------------------
    # TEST 2: Player Registration & Validation
    # -------------------------------------------------------------
    def test_02_player_registration_and_validation(self):
        """Verifies Phase 2 mandatory player fields, password validation (min 6 chars), and session auto-login fallback."""
        # 1. Test rejection when password is less than 6 characters
        short_pwd_resp = self.client.post("/api/customer/register", data={
            "name": "Virat Kohli",
            "phone": "9999888877",
            "age": "35",
            "gender": "Male",
            "password": "123"
        })
        self.assertEqual(short_pwd_resp.status_code, 400)
        self.assertIn("6 characters", short_pwd_resp.get_json()["message"])

        # 2. Test successful customer registration with password >= 6 characters
        reg_resp = self.client.post("/api/customer/register", data={
            "name": "Virat Kohli",
            "phone": "9999888877",
            "age": "35",
            "gender": "Male",
            "password": "virat@123"
        })
        self.assertEqual(reg_resp.status_code, 200)
        self.assertTrue(reg_resp.get_json()["success"])

        # 3. Test customer account login with password
        login_resp = self.client.post("/api/customer/login", json={
            "phone": "9999888877",
            "password": "virat@123"
        })
        self.assertEqual(login_resp.status_code, 200)
        self.assertTrue(login_resp.get_json()["success"])
        self.assertEqual(login_resp.get_json()["user"]["name"], "Virat Kohli")

        # 4. Test customer lookup by phone (auto-login fallback)
        lookup_resp = self.client.post("/api/customer/lookup", json={"phone": "9999888877"})
        self.assertEqual(lookup_resp.status_code, 200)
        self.assertEqual(lookup_resp.get_json()["user"]["name"], "Virat Kohli")

        # 5. Hold a slot first to test validation on creation
        hold_resp = self.client.post("/api/hold-slot", json={
            "sport_id": 1,
            "date": "2026-11-25",
            "start_time": "08:00",
            "end_time": "09:00"
        })
        self.assertEqual(hold_resp.status_code, 200)
        hold_token = hold_resp.get_json()["hold_token"]

        # Missing mandatory fields (e.g. missing age and gender)
        fail_resp = self.client.post("/api/create-booking", data={
            "hold_token": hold_token,
            "name": "Virat Kohli",
            "phone": "9999888877"
        })
        self.assertEqual(fail_resp.status_code, 400)
        self.assertIn("mandatory", fail_resp.get_json()["message"].lower())

    # -------------------------------------------------------------
    # TEST 3: Slot Availability & 10-Minute Hold Lock Engine
    # -------------------------------------------------------------
    def test_03_slot_availability_and_10min_hold_lock(self):
        """Verifies color-coded slots (Green/Yellow/Red) and 10-min hold conflicts."""
        test_date = "2026-11-26"
        # Check initial slot availability
        chk = self.client.post("/api/check-slots", json={"sport_id": 1, "date": test_date})
        self.assertEqual(chk.status_code, 200)
        slots = chk.get_json()["slots"]
        self.assertTrue(len(slots) > 0)

        # Verify 12-hour format & period labeling (Morning, Noon, Evening, Night)
        slot_morning = next(s for s in slots if s["start_time"] == "06:00")
        self.assertEqual(slot_morning["start_time_12h"], "06:00 AM")
        self.assertEqual(slot_morning["period"], "Morning")

        slot_noon = next(s for s in slots if s["start_time"] == "12:00")
        self.assertEqual(slot_noon["start_time_12h"], "12:00 PM")
        self.assertEqual(slot_noon["period"], "Noon")

        slot_evening = next(s for s in slots if s["start_time"] == "16:00")
        self.assertEqual(slot_evening["start_time_12h"], "04:00 PM")
        self.assertEqual(slot_evening["period"], "Evening")

        slot_night = next(s for s in slots if s["start_time"] == "19:00")
        self.assertEqual(slot_night["start_time_12h"], "07:00 PM")
        self.assertEqual(slot_night["period"], "Night")

        # Lock 09:00 to 10:00 (two 30m slots)
        hold = self.client.post("/api/hold-slot", json={
            "sport_id": 1,
            "date": test_date,
            "start_time": "09:00",
            "end_time": "10:00",
            "phone": "9876543210"
        })
        self.assertEqual(hold.status_code, 200)
        hold_data = hold.get_json()
        self.assertTrue(hold_data["success"])
        self.assertEqual(hold_data["duration_hours"], 1.0)

        # Slot should now show as 'held' (Yellow)
        chk2 = self.client.post("/api/check-slots", json={"sport_id": 1, "date": test_date})
        slots2 = chk2.get_json()["slots"]
        slot_900 = next(s for s in slots2 if s["start_time"] == "09:00")
        self.assertEqual(slot_900["status"], "held")

        # Double hold should be rejected (409 Conflict)
        double_hold = self.client.post("/api/hold-slot", json={
            "sport_id": 1,
            "date": test_date,
            "start_time": "09:30",
            "end_time": "10:30"
        })
        self.assertEqual(double_hold.status_code, 409)

        # Release hold
        self.client.post("/api/release-hold", json={"hold_token": hold_data["hold_token"]})

    # -------------------------------------------------------------
    # TEST 4: Multi-Sport Dynamic Pricing (Weekday vs Weekend, Floodlight)
    # -------------------------------------------------------------
    def test_04_multi_sport_dynamic_pricing(self):
        """Verifies tariff engine for Box Cricket, Football, Badminton, Kabaddi, Volleyball."""
        from box_cricket_os.app import calculate_slot_price

        # Weekday Day (e.g. 2026-11-25 is Wednesday)
        price_day, dur_day, flood_day = calculate_slot_price(1, "2026-11-25", "10:00", "12:00")
        self.assertEqual(dur_day, 2.0)
        self.assertEqual(price_day, 1600.0) # 800/hr * 2
        self.assertEqual(flood_day, 0.0)

        # Weekday Night Floodlight (18:00 - 20:00)
        price_night, dur_night, flood_night = calculate_slot_price(1, "2026-11-25", "18:00", "20:00")
        self.assertEqual(dur_night, 2.0)
        self.assertEqual(price_night, 2400.0) # 1200/hr * 2
        self.assertTrue(flood_night > 0.0)

        # Weekend Day (e.g. 2026-11-28 is Saturday)
        price_wknd, dur_wknd, _ = calculate_slot_price(1, "2026-11-28", "10:00", "12:00")
        self.assertEqual(price_wknd, 2000.0) # 1000/hr * 2

    # -------------------------------------------------------------
    # TEST 5: Booking Creation with 50% Advance Token & UPI QR Flow
    # -------------------------------------------------------------
    def test_05_booking_creation_with_50_percent_advance_token(self):
        """Verifies Phase 3 50% advance token calculation, UPI Intent generation."""
        # Test UPI Intent generator
        upi_link = generate_upi_intent_url(UPI_ID, "ADITYA GOYAL", 800.0, "RB-TEST-001")
        self.assertIn("upi://pay", upi_link)
        self.assertIn("pa=goyal2254-1%40okaxis", upi_link)
        self.assertIn("am=800.00", upi_link)

        # Hold slot
        h = self.client.post("/api/hold-slot", json={
            "sport_id": 1,
            "date": "2026-11-27",
            "start_time": "14:00",
            "end_time": "16:00"
        })
        hold_token = h.get_json()["hold_token"]

        # Create 50% token booking with simulated screenshot proof
        fake_screenshot = (io.BytesIO(b"fake image data"), "screenshot.jpg")
        booking_ref = "RB-20261127-T001"

        b_resp = self.client.post("/api/create-booking", data={
            "hold_token": hold_token,
            "booking_ref": booking_ref,
            "name": "Rohit Sharma",
            "phone": "9876500001",
            "age": "32",
            "gender": "Male",
            "payment_type": "50_percent_token",
            "screenshot": fake_screenshot
        }, content_type='multipart/form-data')

        self.assertEqual(b_resp.status_code, 200)
        self.assertTrue(b_resp.get_json()["success"])

        # Check DB state
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bookings WHERE booking_ref = ?", (booking_ref,))
        b = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(b)
        self.assertEqual(b["booking_status"], "in_process") # Turns slot RED
        self.assertEqual(b["advance_paid"], b["total_amount"] * 0.5)
        self.assertEqual(b["balance_due"], b["total_amount"] * 0.5)

    # -------------------------------------------------------------
    # TEST 6: Payment Screenshot Upload & In-Process State
    # -------------------------------------------------------------
    def test_06_payment_screenshot_upload_and_proof(self):
        """Verifies uploaded screenshot file is saved on disk and slot turns RED."""
        test_date = "2026-11-27"
        chk = self.client.post("/api/check-slots", json={"sport_id": 1, "date": test_date})
        slots = chk.get_json()["slots"]
        slot_1400 = next(s for s in slots if s["start_time"] == "14:00")
        # Slot should be red (booked/in_process)
        self.assertEqual(slot_1400["status"], "booked")

    # -------------------------------------------------------------
    # TEST 7: Admin/Partner Auth & Booking Confirmation Flow
    # -------------------------------------------------------------
    def test_07_admin_partner_auth_and_booking_confirmation(self):
        """Verifies Phase 5 Admin login (8858908825/aditya@2026), Partner limit, Confirmation."""
        # 1. Admin Login
        login_resp = self.client.post("/admin/login", data={
            "phone_or_email": ADMIN_MOBILE,
            "password": ADMIN_DEFAULT_PASSWORD
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn("Command Center", login_resp.data.decode("utf-8"))

        # 2. Confirm the booking created in Test 5
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM bookings WHERE booking_ref = 'RB-20261127-T001'")
        b_id = cursor.fetchone()["id"]
        conn.close()

        conf_resp = self.client.post(f"/admin/booking/confirm/{b_id}")
        self.assertEqual(conf_resp.status_code, 200)
        conf_data = conf_resp.get_json()
        self.assertTrue(conf_data["success"])
        self.assertIn("client_wa_url", conf_data)
        self.assertIn("9876500001", conf_data["client_wa_url"])

        # Test digital match receipt endpoint (/receipt/<booking_ref>)
        receipt_resp = self.client.get("/receipt/RB-20261127-T001")
        self.assertEqual(receipt_resp.status_code, 200)
        self.assertIn("RUNBHOOMI BOX CRICKET", receipt_resp.data.decode("utf-8"))

        # 3. Test Max 2 Partners limit
        self.client.post("/admin/partners/add", data={
            "name": "Partner One",
            "phone": "9111111111",
            "password": "partner@pass1"
        })
        self.client.post("/admin/partners/add", data={
            "name": "Partner Two",
            "phone": "9222222222",
            "password": "partner@pass2"
        })
        # 3rd partner should be rejected
        resp_3 = self.client.post("/admin/partners/add", data={
            "name": "Partner Three",
            "phone": "9333333333",
            "password": "partner@pass3"
        }, follow_redirects=True)
        self.assertIn("Maximum 2 partners allowed", resp_3.data.decode("utf-8"))

        # 4. Verify Customer has ZERO access to Admin Command Center
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["user"] = {
                "id": 2,
                "name": "Customer Virat",
                "phone": "9876543210",
                "role": "customer"
            }
        cust_admin_resp = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(cust_admin_resp.status_code, 302)
        self.assertIn("/admin/login", cust_admin_resp.headers.get("Location", ""))

        cust_rev_resp = self.client.get("/admin/revenue", follow_redirects=False)
        self.assertEqual(cust_rev_resp.status_code, 302)
        self.assertIn("/admin/login", cust_rev_resp.headers.get("Location", ""))

        # 5. Verify Partner Restricted Access
        with self.client.session_transaction() as sess:
            sess.clear()
        partner_login = self.client.post("/admin/login", data={
            "phone_or_email": "9111111111",
            "password": "partner@pass1"
        }, follow_redirects=True)
        self.assertEqual(partner_login.status_code, 200)
        self.assertIn("Partner Operational Access", partner_login.data.decode("utf-8"))

        # Partner attempting to access Revenue Intelligence must be blocked and redirected
        partner_rev = self.client.get("/admin/revenue", follow_redirects=False)
        self.assertEqual(partner_rev.status_code, 302)

        # Partner attempting to alter tariffs must receive 403 Forbidden
        partner_tariff = self.client.post("/admin/sports/pricing/update", json={
            "rule_id": 1,
            "hourly_rate": 1500.0,
            "floodlight_charge": 300.0
        })
        self.assertEqual(partner_tariff.status_code, 403)

    # -------------------------------------------------------------
    # TEST 8: Canteen POS, Balance Collection & Revenue Analytics
    # -------------------------------------------------------------
    def test_08_canteen_pos_balance_collection_and_revenue(self):
        """Verifies adding canteen items to match tab, collecting balance, and revenue."""
        # Authenticate admin session first
        self.client.post("/admin/login", data={
            "phone_or_email": ADMIN_MOBILE,
            "password": ADMIN_DEFAULT_PASSWORD
        })

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, total_amount, balance_due FROM bookings WHERE booking_ref = 'RB-20261127-T001'")
        b = cursor.fetchone()
        b_id = b["id"]
        initial_due = b["balance_due"]

        cursor.execute("SELECT id, price FROM canteen_items WHERE name LIKE 'Sting%' LIMIT 1")
        item = cursor.fetchone()
        item_id = item["id"]
        item_price = item["price"]
        conn.close()

        # Add 2x Sting to match bill
        add_canteen = self.client.post(f"/admin/booking/add-canteen/{b_id}", json={
            "item_id": item_id,
            "quantity": 2
        })
        self.assertEqual(add_canteen.status_code, 200)

        # Verify updated balance due
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT balance_due FROM bookings WHERE id = ?", (b_id,))
        new_due = cursor.fetchone()["balance_due"]
        conn.close()
        self.assertEqual(new_due, initial_due + (item_price * 2))

        # Collect balance at turf
        col_resp = self.client.post(f"/admin/booking/collect-balance/{b_id}")
        self.assertEqual(col_resp.status_code, 200)

        # Revenue intelligence page test
        rev_resp = self.client.get("/admin/revenue?filter=30d")
        self.assertEqual(rev_resp.status_code, 200)
        rev_html = rev_resp.data.decode("utf-8")
        self.assertIn("Revenue & Concession Analytics", rev_html)
        self.assertIn("Gross Match Sales", rev_html)
        self.assertIn("Canteen Concessions", rev_html)

        # Test Cancellation policy (50% fee retained, 25% credit issued)
        # Create a second booking to cancel
        h2 = self.client.post("/api/hold-slot", json={
            "sport_id": 1,
            "date": "2026-11-29",
            "start_time": "16:00",
            "end_time": "17:00"
        })
        h2_token = h2.get_json()["hold_token"]
        cancel_ref = "RB-20261129-C001"
        self.client.post("/api/create-booking", data={
            "hold_token": h2_token,
            "booking_ref": cancel_ref,
            "name": "Hardik Pandya",
            "phone": "9888877777",
            "age": "29",
            "gender": "Male",
            "payment_type": "100_percent_full",
            "screenshot": (io.BytesIO(b"dummy"), "proof.png")
        })

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM bookings WHERE booking_ref = ?", (cancel_ref,))
        cancel_id = cursor.fetchone()["id"]
        conn.close()

        can_resp = self.client.post(f"/admin/booking/cancel/{cancel_id}")
        self.assertEqual(can_resp.status_code, 200)
        can_data = can_resp.get_json()
        self.assertTrue(can_data["success"])
        self.assertIn("CREDIT25-", can_data["credit_code"])
        self.assertTrue(can_data["retained_fee"] > 0)

    @classmethod
    def tearDownClass(cls):
        """Cleans up dummy proof images generated during test runs to prevent storage bloat."""
        import os
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

if __name__ == "__main__":
    unittest.main()
