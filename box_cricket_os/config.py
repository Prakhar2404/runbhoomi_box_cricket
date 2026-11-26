"""
Runbhoomi Box Cricket - System Configuration
Registered Corporate Entity: Runbhoomi Box Cricket Pvt. Ltd.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "runbhoomi.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Brand Identity
BRAND_NAME = "RUNBHOOMI BOX CRICKET"
LEGAL_ENTITY = "Runbhoomi Box Cricket Pvt. Ltd."
BUSINESS_OWNER = "ADITYA GOYAL"
TURF_ADDRESS = "Rajdhani Marg, Shuklaganj, Unnao, Uttar Pradesh, India - 209681"

# Payment & UPI Details
UPI_ID = "goyal2254-1@okaxis"
UPI_PAYEE_NAME = "ADITYA GOYAL"

# Admin & Partner Defaults
ADMIN_MOBILE = "8858908825"
ADMIN_EMAIL = "runbhoomiboxcricketup@gmail.com"
ADMIN_DEFAULT_PASSWORD = "aditya@2026"

# Helplines & Support
HELPLINE_PRIMARY = "+91 88589 08825"  # Primary WhatsApp & Call
HELPLINE_OPERATIONS = "+91 70071 67223"  # Ground & Operations
HELPLINE_TOURNAMENTS = "+91 63935 52467"  # Tournaments & Leagues
SUPPORT_EMAIL = "runbhoomiboxcricketup@gmail.com"
AVAILABILITY_TIMING = "10:00 AM to 8:00 PM (Daily)"

# Community Hubs
WHATSAPP_COMMUNITY_URL = "https://chat.whatsapp.com/KUmMMIC5tvrEdGrLEe6Oc3"
INSTAGRAM_URL = "https://www.instagram.com/runbhoomi_box_cricket?cnvx=MWNwaHB3cWl5NnN4bA%3D%3D&utm_source=qr"

# Policy & Notices
CLEANING_LIGHTING_NOTICE = "Price variations in the slots are due to electricity used to light up the turf and cleaning it."
CANCELLATION_POLICY_NOTICE = "In the case of cancellation of booking, 50% of the booking amount will be deducted, and while booking sometime in the future, a 25% discount offer will be applied."
CANTEEN_HYGIENE_NOTICE = "Note: Only fresh and genuine products with full hygiene is been taken care of in the canteen."

# Slot hold timeout (minutes)
SLOT_HOLD_MINUTES = 10

# Supabase Production Deployment Credentials
SUPABASE_PROJECT_ID = "bdgtamrrrnroeampolpi"
SUPABASE_URL = "https://bdgtamrrrnroeampolpi.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJkZ3RhbXJycm5yb2VhbXBvbHBpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTUyMjg4MzksImV4cCI6MjExMDgwNDgzOX0.KnpRymxFsoC5KfuCwTHSUXrzlbhf2UA1cDRvbWFXdYo"
SUPABASE_DB_HOST = "db.bdgtamrrrnroeampolpi.supabase.co"

# Dual-Portal Pipeline Configuration
CUSTOMER_PORT = 5000
ADMIN_PORT = 5001


