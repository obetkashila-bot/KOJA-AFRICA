/* KOJA AFRICA - Remaining Production Engines
   SAFE ADDITIVE MIGRATION
   No DROP/DELETE/TRUNCATE. Safe to rerun.
*/
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.koja_business_staff (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), business_id uuid NOT NULL, user_id uuid NOT NULL,
 role text NOT NULL DEFAULT 'staff', permissions jsonb NOT NULL DEFAULT '{}'::jsonb,
 status text NOT NULL DEFAULT 'active', invited_by uuid, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kbs_business_user ON public.koja_business_staff(business_id,user_id);
CREATE INDEX IF NOT EXISTS idx_kbs_business ON public.koja_business_staff(business_id);

CREATE TABLE IF NOT EXISTS public.koja_live_sessions_v2 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), business_id uuid NOT NULL, host_user_id uuid NOT NULL,
 title text NOT NULL, description text, room_name text UNIQUE NOT NULL, status text NOT NULL DEFAULT 'scheduled',
 starts_at timestamptz, ends_at timestamptz, max_participants integer NOT NULL DEFAULT 100,
 livekit_room text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_klv2_business ON public.koja_live_sessions_v2(business_id);
CREATE INDEX IF NOT EXISTS idx_klv2_status ON public.koja_live_sessions_v2(status,starts_at);

CREATE TABLE IF NOT EXISTS public.koja_live_participants_v2 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), session_id uuid NOT NULL, user_id uuid,
 display_name text, role text DEFAULT 'participant', joined_at timestamptz NOT NULL DEFAULT now(), left_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_klp2_session ON public.koja_live_participants_v2(session_id);

CREATE TABLE IF NOT EXISTS public.koja_market_payout_ledger (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), payout_id uuid, seller_id uuid, user_id uuid,
 amount numeric(18,2) NOT NULL DEFAULT 0, currency text NOT NULL DEFAULT 'ZMW',
 direction text NOT NULL DEFAULT 'seller_payout', status text NOT NULL DEFAULT 'pending',
 reference text, created_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_kmpl_seller ON public.koja_market_payout_ledger(seller_id,created_at);
CREATE INDEX IF NOT EXISTS idx_kmpl_status ON public.koja_market_payout_ledger(status);

CREATE TABLE IF NOT EXISTS public.koja_delivery_security (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), delivery_id uuid, tracking_code text NOT NULL,
 otp_hash text, otp_expires_at timestamptz, otp_attempts integer NOT NULL DEFAULT 0,
 proof_url text, proof_note text, delivered_at timestamptz, status text NOT NULL DEFAULT 'pending',
 reassignment_count integer NOT NULL DEFAULT 0, last_driver_id uuid, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kds_tracking ON public.koja_delivery_security(tracking_code);
CREATE INDEX IF NOT EXISTS idx_kds_delivery ON public.koja_delivery_security(delivery_id);

CREATE TABLE IF NOT EXISTS public.koja_business_verifications_v2 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), business_id uuid UNIQUE NOT NULL, status text NOT NULL DEFAULT 'pending',
 licence_number text, licence_expires_at date, tax_number text, tax_expires_at date,
 document_url text, reviewer_id uuid, reviewed_at timestamptz, rejection_reason text,
 verified_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kbv2_status ON public.koja_business_verifications_v2(status);
CREATE INDEX IF NOT EXISTS idx_kbv2_expiry ON public.koja_business_verifications_v2(licence_expires_at,tax_expires_at);

CREATE TABLE IF NOT EXISTS public.koja_business_directory (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), business_id uuid UNIQUE NOT NULL, public_name text,
 description text, category text, phone text, location text, latitude numeric(10,7), longitude numeric(10,7),
 verified boolean NOT NULL DEFAULT false, active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kbd_category ON public.koja_business_directory(category);
CREATE INDEX IF NOT EXISTS idx_kbd_verified ON public.koja_business_directory(verified,active);
CREATE INDEX IF NOT EXISTS idx_kbd_geo ON public.koja_business_directory(latitude,longitude);

CREATE TABLE IF NOT EXISTS public.koja_market_promotions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), seller_id uuid NOT NULL, name text NOT NULL,
 promo_type text NOT NULL DEFAULT 'discount', code text, discount_percent numeric(8,2), discount_amount numeric(18,2),
 starts_at timestamptz, ends_at timestamptz, usage_limit integer DEFAULT 0, used_count integer NOT NULL DEFAULT 0,
 active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kmprom_seller ON public.koja_market_promotions(seller_id,active);
CREATE INDEX IF NOT EXISTS idx_kmprom_dates ON public.koja_market_promotions(starts_at,ends_at);

CREATE TABLE IF NOT EXISTS public.koja_market_referrals_v2 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), referrer_id uuid NOT NULL, referred_id uuid,
 referral_code text NOT NULL, status text NOT NULL DEFAULT 'pending', reward_amount numeric(18,2) NOT NULL DEFAULT 0,
 currency text NOT NULL DEFAULT 'ZMW', qualified_at timestamptz, rewarded_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kmr2_referrer ON public.koja_market_referrals_v2(referrer_id,created_at);
CREATE INDEX IF NOT EXISTS idx_kmr2_code ON public.koja_market_referrals_v2(referral_code);

CREATE TABLE IF NOT EXISTS public.koja_audit_log_v2 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, action text NOT NULL, resource_type text,
 resource_id text, ip_address text, user_agent text, metadata jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kal2_user ON public.koja_audit_log_v2(user_id,created_at);
CREATE INDEX IF NOT EXISTS idx_kal2_resource ON public.koja_audit_log_v2(resource_type,resource_id);

CREATE TABLE IF NOT EXISTS public.koja_idempotency_keys_v2 (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, idem_key text NOT NULL,
 request_hash text, response_status integer, response_body jsonb, created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kik2_user_key ON public.koja_idempotency_keys_v2(user_id,idem_key);

/* Compatibility additions for existing payout and delivery tables. */
ALTER TABLE IF EXISTS public.koja_market_payouts ADD COLUMN IF NOT EXISTS processed_at timestamptz;
ALTER TABLE IF EXISTS public.koja_market_payouts ADD COLUMN IF NOT EXISTS failure_reason text;
ALTER TABLE IF EXISTS public.deliveries ADD COLUMN IF NOT EXISTS delivery_security_id uuid;
ALTER TABLE IF EXISTS public.deliveries ADD COLUMN IF NOT EXISTS rejection_count integer DEFAULT 0;
ALTER TABLE IF EXISTS public.deliveries ADD COLUMN IF NOT EXISTS last_reassigned_at timestamptz;

COMMIT;

SELECT table_name, installed FROM (
 SELECT 'koja_business_staff' table_name, to_regclass('public.koja_business_staff') IS NOT NULL installed
 UNION ALL SELECT 'koja_live_sessions_v2', to_regclass('public.koja_live_sessions_v2') IS NOT NULL
 UNION ALL SELECT 'koja_live_participants_v2', to_regclass('public.koja_live_participants_v2') IS NOT NULL
 UNION ALL SELECT 'koja_market_payout_ledger', to_regclass('public.koja_market_payout_ledger') IS NOT NULL
 UNION ALL SELECT 'koja_delivery_security', to_regclass('public.koja_delivery_security') IS NOT NULL
 UNION ALL SELECT 'koja_business_verifications_v2', to_regclass('public.koja_business_verifications_v2') IS NOT NULL
 UNION ALL SELECT 'koja_business_directory', to_regclass('public.koja_business_directory') IS NOT NULL
 UNION ALL SELECT 'koja_market_promotions', to_regclass('public.koja_market_promotions') IS NOT NULL
 UNION ALL SELECT 'koja_market_referrals_v2', to_regclass('public.koja_market_referrals_v2') IS NOT NULL
 UNION ALL SELECT 'koja_audit_log_v2', to_regclass('public.koja_audit_log_v2') IS NOT NULL
 UNION ALL SELECT 'koja_idempotency_keys_v2', to_regclass('public.koja_idempotency_keys_v2') IS NOT NULL
) q ORDER BY table_name;
