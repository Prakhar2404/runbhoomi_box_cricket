"""
Runbhoomi Dual Portal Supervisor
Starts both Customer Portal (Port 5000) and Admin & Partner Operations Desk (Port 5001) concurrently.
"""
import sys
import os
import threading
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from box_cricket_os.db import init_db
from box_cricket_os.config import CUSTOMER_PORT, ADMIN_PORT
from box_cricket_os.app_customer import customer_app
from box_cricket_os.app_admin import admin_app

def run_customer():
    print(f"[PORTAL: CUSTOMER] Starting on http://127.0.0.1:{CUSTOMER_PORT}", flush=True)
    try:
        customer_app.run(host="0.0.0.0", port=CUSTOMER_PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"[PORTAL: CUSTOMER] Encountered error: {e}", flush=True)

def run_admin():
    print(f"[PORTAL: ADMIN & PARTNERS] Starting on http://127.0.0.1:{ADMIN_PORT}", flush=True)
    try:
        admin_app.run(host="0.0.0.0", port=ADMIN_PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"[PORTAL: ADMIN & PARTNERS] Encountered error: {e}", flush=True)

if __name__ == "__main__":
    print("=" * 70, flush=True)
    print(" RUNBHOOMI BOX CRICKET ENTERPRISE DUAL PORTAL ARCHITECTURE", flush=True)
    print("=" * 70, flush=True)
    init_db()

    # Launch both server instances in non-daemon threads
    t_customer = threading.Thread(target=run_customer, daemon=False, name="CustomerPortalThread")
    t_admin = threading.Thread(target=run_admin, daemon=False, name="AdminPortalThread")

    t_customer.start()
    t_admin.start()

    time.sleep(1)
    print("=" * 70, flush=True)
    print(f"  CUSTOMER PORTAL:           http://127.0.0.1:{CUSTOMER_PORT}", flush=True)
    print(f"  ADMIN & PARTNER DESK:      http://127.0.0.1:{ADMIN_PORT}", flush=True)
    print("=" * 70, flush=True)
    print("Press Ctrl+C to terminate both servers.", flush=True)

    try:
        t_customer.join()
        t_admin.join()
    except KeyboardInterrupt:
        print("\n[SUPERVISOR] Shutting down Runbhoomi Dual Portals cleanly.", flush=True)
