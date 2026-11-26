"""
Runbhoomi Customer Portal Runner
Runs on Port 5000 (CUSTOMER_PORT)
"""
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from box_cricket_os.app_customer import customer_app
from box_cricket_os.db import init_db
from box_cricket_os.config import CUSTOMER_PORT

if __name__ == "__main__":
    init_db()
    print("=" * 60)
    print(" RUNBHOOMI CUSTOMER PORTAL")
    print(f" URL: http://127.0.0.1:{CUSTOMER_PORT}")
    print(" Gated: Admin & Partner routes return 404")
    print("=" * 60)
    customer_app.run(host="0.0.0.0", port=CUSTOMER_PORT, debug=False)
