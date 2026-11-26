"""
Runbhoomi Admin & Partner Operations Desk Runner
Runs on Port 5001 (ADMIN_PORT)
"""
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from box_cricket_os.app_admin import admin_app
from box_cricket_os.db import init_db
from box_cricket_os.config import ADMIN_PORT

if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print(" RUNBHOOMI ADMIN & PARTNER OPERATIONS DESK")
    print(f" URL: http://127.0.0.1:{ADMIN_PORT}")
    print(" Primary Owner: Aditya Goyal (8858908825)")
    print("=" * 60)
    admin_app.run(host="0.0.0.0", port=ADMIN_PORT, debug=False)
