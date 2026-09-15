-- KOJA GLOBAL COMMERCE V2
-- Additive/update-safe. No DROP, TRUNCATE or destructive recreation.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.koja_global_countries (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text NOT NULL,
 default_currency text, active boolean NOT NULL DEFAULT true, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_currencies (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text NOT NULL, symbol text,
 decimals integer NOT NULL DEFAULT 2, active boolean NOT NULL DEFAULT true, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_fx_rates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, base_currency text NOT NULL, quote_currency text NOT NULL,
 rate numeric(24,10) NOT NULL DEFAULT 1, effective_at timestamptz DEFAULT now(), source text DEFAULT 'manual', created_by uuid, created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_tax_profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, country_code text NOT NULL,
 tax_name text NOT NULL, tax_type text DEFAULT 'sales', rate numeric(12,4) DEFAULT 0, registration_number text,
 active boolean NOT NULL DEFAULT true, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_entities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL, name text NOT NULL,
 country_code text, entity_type text DEFAULT 'operating_entity', registration_number text, tax_number text,
 base_currency text DEFAULT 'ZMW', status text DEFAULT 'active', created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_trade_lanes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL, name text NOT NULL,
 origin_country text NOT NULL, destination_country text NOT NULL, mode text DEFAULT 'road',
 carrier text, transit_days integer DEFAULT 0, status text DEFAULT 'active', created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_orders (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, owner_id uuid, order_number text UNIQUE NOT NULL,
 origin_country text NOT NULL, destination_country text NOT NULL, currency text NOT NULL DEFAULT 'ZMW', total_amount numeric(20,2) NOT NULL DEFAULT 0,
 customer_reference text, trade_lane_id uuid, entity_id uuid, status text NOT NULL DEFAULT 'draft',
 fx_rate numeric(24,10), base_amount numeric(20,2), tax_amount numeric(20,2) DEFAULT 0, duty_amount numeric(20,2) DEFAULT 0,
 compliance_status text DEFAULT 'pending', created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_settlements (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, order_id uuid, amount numeric(20,2) NOT NULL DEFAULT 0,
 currency text NOT NULL DEFAULT 'ZMW', status text DEFAULT 'pending', payment_reference text, finance_transaction_id uuid,
 settled_at timestamptz, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_compliance_docs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, order_id uuid, document_type text NOT NULL,
 document_number text, country_code text, status text DEFAULT 'pending', document_url text, expires_at timestamptz,
 reviewed_by uuid, reviewed_at timestamptz, notes text, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_global_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, actor_id uuid, event_type text NOT NULL,
 entity_type text, entity_id uuid, payload jsonb DEFAULT '{}'::jsonb, created_at timestamptz DEFAULT now()
);

ALTER TABLE public.koja_global_countries ADD COLUMN IF NOT EXISTS default_currency text;
ALTER TABLE public.koja_global_currencies ADD COLUMN IF NOT EXISTS decimals integer NOT NULL DEFAULT 2;
ALTER TABLE public.koja_global_fx_rates ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_global_tax_profiles ADD COLUMN IF NOT EXISTS registration_number text;
ALTER TABLE public.koja_global_entities ADD COLUMN IF NOT EXISTS tax_number text;
ALTER TABLE public.koja_global_trade_lanes ADD COLUMN IF NOT EXISTS carrier text;
ALTER TABLE public.koja_global_orders ADD COLUMN IF NOT EXISTS fx_rate numeric(24,10);
ALTER TABLE public.koja_global_orders ADD COLUMN IF NOT EXISTS base_amount numeric(20,2);
ALTER TABLE public.koja_global_orders ADD COLUMN IF NOT EXISTS tax_amount numeric(20,2) DEFAULT 0;
ALTER TABLE public.koja_global_orders ADD COLUMN IF NOT EXISTS duty_amount numeric(20,2) DEFAULT 0;
ALTER TABLE public.koja_global_orders ADD COLUMN IF NOT EXISTS compliance_status text DEFAULT 'pending';
ALTER TABLE public.koja_global_settlements ADD COLUMN IF NOT EXISTS finance_transaction_id uuid;
ALTER TABLE public.koja_global_compliance_docs ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_global_fx_pair ON public.koja_global_fx_rates(base_currency,quote_currency,effective_at DESC);
CREATE INDEX IF NOT EXISTS idx_global_tax_country ON public.koja_global_tax_profiles(country_code,active);
CREATE INDEX IF NOT EXISTS idx_global_entities_org ON public.koja_global_entities(organization_id,status);
CREATE INDEX IF NOT EXISTS idx_global_lanes_org ON public.koja_global_trade_lanes(organization_id,status);
CREATE INDEX IF NOT EXISTS idx_global_orders_org ON public.koja_global_orders(organization_id,status);
CREATE INDEX IF NOT EXISTS idx_global_orders_route ON public.koja_global_orders(origin_country,destination_country);
CREATE INDEX IF NOT EXISTS idx_global_settlements_order ON public.koja_global_settlements(order_id,status);
CREATE INDEX IF NOT EXISTS idx_global_compliance_order ON public.koja_global_compliance_docs(order_id,status);
CREATE INDEX IF NOT EXISTS idx_global_events_entity ON public.koja_global_events(entity_type,entity_id);

INSERT INTO public.koja_global_currencies(code,name,symbol,decimals,active) VALUES
('ZMW','Zambian Kwacha','ZK',2,true),('USD','US Dollar','$',2,true),('EUR','Euro','€',2,true),('GBP','Pound Sterling','£',2,true),('ZAR','South African Rand','R',2,true),('KES','Kenyan Shilling','KSh',2,true),('NGN','Nigerian Naira','₦',2,true)
ON CONFLICT (code) DO NOTHING;

INSERT INTO public.koja_global_countries(code,name,default_currency,active) VALUES
('ZM','Zambia','ZMW',true),('ZA','South Africa','ZAR',true),('KE','Kenya','KES',true),('NG','Nigeria','NGN',true),('GB','United Kingdom','GBP',true),('US','United States','USD',true),('DE','Germany','EUR',true)
ON CONFLICT (code) DO NOTHING;
