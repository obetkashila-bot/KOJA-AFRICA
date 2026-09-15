-- KOJA SUPPLY CHAIN V2 — ADDITIVE / UPDATE-SAFE
-- Run after KOJA_SUPPLY_CHAIN_V1.sql and KOJA_FINANCE_V2.sql.

CREATE TABLE IF NOT EXISTS public.koja_supply_reorder_requests (
  id uuid PRIMARY KEY,
  organization_id uuid,
  owner_id uuid,
  inventory_item_id uuid,
  quantity numeric DEFAULT 0,
  status text DEFAULT 'requested',
  source text DEFAULT 'supply_chain',
  notes text,
  requested_by uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS owner_id uuid;
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS inventory_item_id uuid;
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS quantity numeric DEFAULT 0;
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS status text DEFAULT 'requested';
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS source text DEFAULT 'supply_chain';
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS notes text;
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS requested_by uuid;
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE public.koja_supply_reorder_requests ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_koja_supply_reorder_org ON public.koja_supply_reorder_requests(organization_id);
CREATE INDEX IF NOT EXISTS idx_koja_supply_reorder_item ON public.koja_supply_reorder_requests(inventory_item_id);
CREATE INDEX IF NOT EXISTS idx_koja_supply_reorder_status ON public.koja_supply_reorder_requests(status);

ALTER TABLE public.koja_supply_reorder_requests ENABLE ROW LEVEL SECURITY;

-- Keep policy creation safe if a deployment already has policies with these names.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='koja_supply_reorder_requests' AND policyname='koja_supply_reorder_select_own') THEN
    CREATE POLICY koja_supply_reorder_select_own ON public.koja_supply_reorder_requests FOR SELECT USING (owner_id = auth.uid());
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='koja_supply_reorder_requests' AND policyname='koja_supply_reorder_insert_own') THEN
    CREATE POLICY koja_supply_reorder_insert_own ON public.koja_supply_reorder_requests FOR INSERT WITH CHECK (owner_id = auth.uid());
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='koja_supply_reorder_requests' AND policyname='koja_supply_reorder_update_own') THEN
    CREATE POLICY koja_supply_reorder_update_own ON public.koja_supply_reorder_requests FOR UPDATE USING (owner_id = auth.uid()) WITH CHECK (owner_id = auth.uid());
  END IF;
END $$;
