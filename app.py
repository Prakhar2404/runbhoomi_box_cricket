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
    print(f"[PORTAL: CUSTOMER] Starting on http://127.0.0.1:{CUSTOMER_PORT}")
    customer_app.run(host="0.0.0.0", port=CUSTOMER_PORT, debug=False, use_reloader=False)

def run_admin():
    print(f"[PORTAL: ADMIN & PARTNERS] Starting on http://127.0.0.1:{ADMIN_PORT}")
    admin_app.run(host="0.0.0.0", port=ADMIN_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    print("=" * 70)
    print(" RUNBHOOMI BOX CRICKET ENTERPRISE DUAL PORTAL ARCHITECTURE")
    print("=" * 70)
    init_db()

    # Launch both server instances in daemon threads
    t_customer = threading.Thread(target=run_customer, daemon=True, name="CustomerPortalThread")
    t_admin = threading.Thread(target=run_admin, daemon=True, name="AdminPortalThread")

    t_customer.start()
    t_admin.start()

    time.sleep(1)
    print("=" * 70)
    print(f"  CUSTOMER PORTAL:           http://127.0.0.1:{CUSTOMER_PORT}")
    print(f"  ADMIN & PARTNER DESK:      http://127.0.0.1:{ADMIN_PORT}")
    print("=" * 70)
    print("Press Ctrl+C to terminate both servers.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SUPERVISOR] Shutting down Runbhoomi Dual Portals cleanly.")
