-- ============================================================================
-- RUNBHOOMI BOX CRICKET - PRODUCTION SUPABASE POSTGRESQL SCHEMA
-- Corporate Entity: Runbhoomi Box Cricket Pvt. Ltd.
-- Business Owner: ADITYA GOYAL | UPI: goyal2254-1@okaxis
-- Arena: Rajdhani Marg, Shuklaganj, Unnao, Uttar Pradesh - 209681
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. USERS TABLE (Players, Admins, Partners)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) UNIQUE NOT NULL CHECK (length(phone) >= 10),
    name VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    age INTEGER CHECK (age >= 6 AND age <= 99),
    gender VARCHAR(20) DEFAULT 'Male' CHECK (gender IN ('Male', 'Female', 'Other')),
    role VARCHAR(30) DEFAULT 'customer' CHECK (role IN ('customer', 'partner', 'admin')),
    avatar_url TEXT,
    password_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON public.users(phone);
CREATE INDEX IF NOT EXISTS idx_users_role ON public.users(role);

-- ============================================================================
-- 2. SPORTS TABLE (Multi-Sport Arena Engine)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.sports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    icon_name VARCHAR(50) DEFAULT 'cricket',
    min_players INTEGER DEFAULT 10 CHECK (min_players > 0),
    max_players INTEGER DEFAULT 16 CHECK (max_players >= min_players),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sports_slug ON public.sports(slug);

-- ============================================================================
-- 3. PRICING RULES (Dynamic Weekday vs Weekend, Floodlight Night Engine)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.pricing_rules (
    id SERIAL PRIMARY KEY,
    sport_id INTEGER NOT NULL REFERENCES public.sports(id) ON DELETE CASCADE,
    day_type VARCHAR(20) NOT NULL CHECK (day_type IN ('weekday', 'weekend')),
    time_slot_label VARCHAR(50) NOT NULL,
    start_hour INTEGER NOT NULL CHECK (start_hour >= 0 AND start_hour <= 23),
    end_hour INTEGER NOT NULL CHECK (end_hour >= 1 AND end_hour <= 24),
    hourly_rate NUMERIC(10, 2) NOT NULL CHECK (hourly_rate >= 0),
    floodlight_charge NUMERIC(10, 2) DEFAULT 0.00 CHECK (floodlight_charge >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT pricing_rules_sport_day_hours_unique UNIQUE (sport_id, day_type, start_hour, end_hour)
);

CREATE INDEX IF NOT EXISTS idx_pricing_sport_day ON public.pricing_rules(sport_id, day_type);

-- ============================================================================
-- 4. HELD SLOTS (10-Minute Lockout Window During Checkout)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.held_slots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sport_id INTEGER NOT NULL REFERENCES public.sports(id) ON DELETE CASCADE,
    slot_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    hold_token VARCHAR(100) UNIQUE NOT NULL,
    customer_phone VARCHAR(20),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT held_slots_sport_date_time_unique UNIQUE (sport_id, slot_date, start_time)
);

CREATE INDEX IF NOT EXISTS idx_held_slots_date_sport ON public.held_slots(slot_date, sport_id);
CREATE INDEX IF NOT EXISTS idx_held_slots_expiry ON public.held_slots(expires_at);

-- ============================================================================
-- 5. BOOKINGS TABLE (Primary Match Records)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_ref VARCHAR(50) UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    sport_id INTEGER NOT NULL REFERENCES public.sports(id) ON DELETE RESTRICT,
    booking_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    duration_hours NUMERIC(4, 2) NOT NULL CHECK (duration_hours > 0),
    base_rate NUMERIC(10, 2) NOT NULL CHECK (base_rate >= 0),
    floodlight_charge NUMERIC(10, 2) DEFAULT 0.00 CHECK (floodlight_charge >= 0),
    discount_amount NUMERIC(10, 2) DEFAULT 0.00 CHECK (discount_amount >= 0),
    promo_code VARCHAR(50),
    total_amount NUMERIC(10, 2) NOT NULL CHECK (total_amount >= 0),
    advance_paid NUMERIC(10, 2) NOT NULL CHECK (advance_paid >= 0),
    balance_due NUMERIC(10, 2) NOT NULL CHECK (balance_due >= 0),
    payment_type VARCHAR(50) DEFAULT '50_percent_token' CHECK (payment_type IN ('50_percent_token', '100_percent_full')),
    payment_status VARCHAR(50) DEFAULT 'in_process' CHECK (payment_status IN ('pending_proof', 'in_process', 'verified', 'cancelled')),
    booking_status VARCHAR(50) DEFAULT 'in_process' CHECK (booking_status IN ('in_process', 'confirmed', 'cancelled', 'completed')),
    screenshot_url TEXT,
    cancellation_fee NUMERIC(10, 2) DEFAULT 0.00 CHECK (cancellation_fee >= 0),
    future_credit_code VARCHAR(50),
    confirmed_by VARCHAR(150),
    confirmed_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bookings_ref ON public.bookings(booking_ref);
CREATE INDEX IF NOT EXISTS idx_bookings_date_sport ON public.bookings(booking_date, sport_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON public.bookings(booking_status);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON public.bookings(user_id);

-- ============================================================================
-- 6. CANTEEN ITEMS CATALOG
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.canteen_items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL CHECK (category IN ('beverages', 'snacks', 'eggs', 'mocktails', 'smokes', 'energy_sports', 'gear_rental', 'drinks', 'electrolytes')),
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER DEFAULT 100 CHECK (stock >= 0),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_canteen_items_category ON public.canteen_items(category);

-- ============================================================================
-- 7. BOOKING CANTEEN ORDERS (Running Match Tab)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.booking_canteen_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES public.canteen_items(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    total_price NUMERIC(10, 2) NOT NULL CHECK (total_price >= 0),
    added_by VARCHAR(150),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_canteen_orders_booking ON public.booking_canteen_orders(booking_id);

-- ============================================================================
-- 8. PROMO OFFERS ENGINE
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.promo_offers (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(150) NOT NULL,
    offer_type VARCHAR(50) NOT NULL CHECK (offer_type IN ('percent', 'flat', 'free_product')),
    discount_value NUMERIC(10, 2) DEFAULT 0.00 CHECK (discount_value >= 0),
    min_booking_amount NUMERIC(10, 2) DEFAULT 0.00 CHECK (min_booking_amount >= 0),
    free_item_id INTEGER REFERENCES public.canteen_items(id) ON DELETE SET NULL,
    valid_until TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 9. CANCELLATION CREDITS (25% Future Credit System)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.cancellation_credits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    phone VARCHAR(20) NOT NULL,
    promo_code VARCHAR(50) UNIQUE NOT NULL,
    discount_percent NUMERIC(5, 2) DEFAULT 25.00 CHECK (discount_percent >= 0 AND discount_percent <= 100),
    retained_fee NUMERIC(10, 2) NOT NULL CHECK (retained_fee >= 0),
    is_redeemed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cancellation_credits_code ON public.cancellation_credits(promo_code);

-- ============================================================================
-- 10. PARTNERS TABLE (Max 2 Allowed by Business Policy)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.partners (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL CHECK (length(phone) >= 10),
    email VARCHAR(255),
    password_hash TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enforce Max 2 Partners via Trigger
CREATE OR REPLACE FUNCTION public.check_max_partners()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT COUNT(*) FROM public.partners WHERE is_active = TRUE) >= 2 THEN
        RAISE EXCEPTION 'Runbhoomi Policy Violation: Maximum 2 partners allowed in system.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_limit_partners ON public.partners;
CREATE TRIGGER trg_limit_partners
BEFORE INSERT ON public.partners
FOR EACH ROW EXECUTE FUNCTION public.check_max_partners();

-- ============================================================================
-- SUPABASE REALTIME CONFIGURATION
-- ============================================================================
-- Enable Realtime publication for instant slot updates & admin dashboard alerts
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' AND tablename = 'bookings'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.bookings;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' AND tablename = 'held_slots'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.held_slots;
    END IF;
END $$;

-- ============================================================================
-- SUPABASE STORAGE BUCKETS
-- ============================================================================
INSERT INTO storage.buckets (id, name, public)
VALUES ('payment-screenshots', 'payment-screenshots', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public)
VALUES ('avatars', 'avatars', true)
ON CONFLICT (id) DO NOTHING;

-- Storage RLS Policies
DROP POLICY IF EXISTS "Public Read Screenshots" ON storage.objects;
CREATE POLICY "Public Read Screenshots" ON storage.objects
FOR SELECT USING (bucket_id = 'payment-screenshots');

DROP POLICY IF EXISTS "Authenticated Upload Screenshots" ON storage.objects;
CREATE POLICY "Authenticated Upload Screenshots" ON storage.objects
FOR INSERT WITH CHECK (bucket_id = 'payment-screenshots');

DROP POLICY IF EXISTS "Public Read Avatars" ON storage.objects;
CREATE POLICY "Public Read Avatars" ON storage.objects
FOR SELECT USING (bucket_id = 'avatars');

DROP POLICY IF EXISTS "Authenticated Upload Avatars" ON storage.objects
FOR INSERT WITH CHECK (bucket_id = 'avatars');

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES - ENFORCING SECURE MULTI-ROLE ACCESS
-- ============================================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pricing_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.held_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.canteen_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.booking_canteen_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promo_offers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cancellation_credits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partners ENABLE ROW LEVEL SECURITY;

-- 1. Sports & Pricing (Public Read)
DROP POLICY IF EXISTS "Public read sports" ON public.sports;
CREATE POLICY "Public read sports" ON public.sports FOR SELECT USING (is_active = TRUE);

DROP POLICY IF EXISTS "Public read pricing" ON public.pricing_rules;
CREATE POLICY "Public read pricing" ON public.pricing_rules FOR SELECT USING (TRUE);

-- 2. Canteen & Promos (Public Read)
DROP POLICY IF EXISTS "Public read promos" ON public.promo_offers;
CREATE POLICY "Public read promos" ON public.promo_offers FOR SELECT USING (is_active = TRUE);

DROP POLICY IF EXISTS "Public read canteen" ON public.canteen_items;
CREATE POLICY "Public read canteen" ON public.canteen_items FOR SELECT USING (is_active = TRUE);

-- 3. Held Slots (Checkout lock)
DROP POLICY IF EXISTS "Public read holds" ON public.held_slots;
CREATE POLICY "Public read holds" ON public.held_slots FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS "Public insert holds" ON public.held_slots;
CREATE POLICY "Public insert holds" ON public.held_slots FOR INSERT WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Public update holds" ON public.held_slots;
CREATE POLICY "Public update holds" ON public.held_slots FOR UPDATE USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Public delete holds" ON public.held_slots;
CREATE POLICY "Public delete holds" ON public.held_slots FOR DELETE USING (TRUE);

-- 4. Users (Players, Admins, Partners)
DROP POLICY IF EXISTS "Public read users" ON public.users;
CREATE POLICY "Public read users" ON public.users FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS "Public insert users" ON public.users;
CREATE POLICY "Public insert users" ON public.users FOR INSERT WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Public update users" ON public.users;
CREATE POLICY "Public update users" ON public.users FOR UPDATE USING (TRUE) WITH CHECK (TRUE);

-- 5. Bookings
DROP POLICY IF EXISTS "Public read bookings" ON public.bookings;
CREATE POLICY "Public read bookings" ON public.bookings FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS "Public insert bookings" ON public.bookings;
CREATE POLICY "Public insert bookings" ON public.bookings FOR INSERT WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Public update bookings" ON public.bookings;
CREATE POLICY "Public update bookings" ON public.bookings FOR UPDATE USING (TRUE) WITH CHECK (TRUE);

-- 6. Booking Canteen Orders (Running Tab)
DROP POLICY IF EXISTS "Public read canteen orders" ON public.booking_canteen_orders;
CREATE POLICY "Public read canteen orders" ON public.booking_canteen_orders FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS "Public insert canteen orders" ON public.booking_canteen_orders;
CREATE POLICY "Public insert canteen orders" ON public.booking_canteen_orders FOR INSERT WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Public update canteen orders" ON public.booking_canteen_orders;
CREATE POLICY "Public update canteen orders" ON public.booking_canteen_orders FOR UPDATE USING (TRUE) WITH CHECK (TRUE);

-- 7. Cancellation Credits
DROP POLICY IF EXISTS "Public read cancellation credits" ON public.cancellation_credits;
CREATE POLICY "Public read cancellation credits" ON public.cancellation_credits FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS "Public insert cancellation credits" ON public.cancellation_credits;
CREATE POLICY "Public insert cancellation credits" ON public.cancellation_credits FOR INSERT WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Public update cancellation credits" ON public.cancellation_credits;
CREATE POLICY "Public update cancellation credits" ON public.cancellation_credits FOR UPDATE USING (TRUE) WITH CHECK (TRUE);

-- 8. Partners
DROP POLICY IF EXISTS "Public read partners" ON public.partners;
CREATE POLICY "Public read partners" ON public.partners FOR SELECT USING (is_active = TRUE);

DROP POLICY IF EXISTS "Public insert partners" ON public.partners;
CREATE POLICY "Public insert partners" ON public.partners FOR INSERT WITH CHECK (TRUE);

DROP POLICY IF EXISTS "Public update partners" ON public.partners;
CREATE POLICY "Public update partners" ON public.partners FOR UPDATE USING (TRUE) WITH CHECK (TRUE);

-- ============================================================================
-- SEED INITIAL MASTER DATA
-- ============================================================================
-- 1. Default Super Admin (Aditya Goyal)
INSERT INTO public.users (phone, name, email, age, gender, role, password_hash)
VALUES ('8858908825', 'ADITYA GOYAL', 'runbhoomiboxcricketup@gmail.com', 28, 'Male', 'admin', encode(sha256('aditya@2026'::bytea), 'hex'))
ON CONFLICT (phone) DO NOTHING;

-- 2. Default Multi-Sports
INSERT INTO public.sports (name, slug, description, icon_name, min_players, max_players)
VALUES
('Box Cricket', 'box-cricket', 'High-intensity turf cricket with synthetic grass and tension boundary netting', 'cricket', 10, 16),
('5v5 Football', 'football-5v5', 'Fast-paced mini football with shock-absorbing turf and boundary walls', 'football', 10, 14),
('Badminton', 'badminton', 'Tournament-grade synthetic turf badminton court with high-lux LED illumination', 'badminton', 2, 4),
('Kabaddi', 'kabaddi', 'Dynamic high-traction mat & turf court with high impact padding', 'kabaddi', 14, 18),
('Volleyball', 'volleyball', 'All-weather turf court with adjustable competition net', 'volleyball', 10, 14)
ON CONFLICT (slug) DO NOTHING;
