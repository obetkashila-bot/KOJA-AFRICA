-- KOJA Business Organisation Core V1
-- Additive/update-safe. Does not replace existing business or enterprise tables.

ALTER TABLE IF EXISTS public.koja_businesses
  ADD COLUMN IF NOT EXISTS organization_core_id uuid;

CREATE TABLE IF NOT EXISTS public.koja_business_organizations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL UNIQUE REFERENCES public.koja_businesses(id) ON DELETE CASCADE,
  owner_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  enterprise_organization_id uuid,
  b2b_organization_id uuid,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.koja_business_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES public.koja_businesses(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'employee',
  status text NOT NULL DEFAULT 'active',
  invited_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (business_id,user_id)
);

CREATE TABLE IF NOT EXISTS public.koja_business_departments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES public.koja_businesses(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text,
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.koja_business_workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES public.koja_businesses(id) ON DELETE CASCADE,
  name text NOT NULL,
  owner_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.koja_business_core_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES public.koja_businesses(id) ON DELETE CASCADE,
  actor_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  event_type text NOT NULL,
  entity_type text,
  entity_id uuid,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_koja_business_memberships_business ON public.koja_business_memberships(business_id,status);
CREATE INDEX IF NOT EXISTS idx_koja_business_memberships_user ON public.koja_business_memberships(user_id,status);
CREATE INDEX IF NOT EXISTS idx_koja_business_departments_business ON public.koja_business_departments(business_id);
CREATE INDEX IF NOT EXISTS idx_koja_business_workspaces_business ON public.koja_business_workspaces(business_id);
CREATE INDEX IF NOT EXISTS idx_koja_business_core_events_business ON public.koja_business_core_events(business_id,created_at DESC);

ALTER TABLE public.koja_business_organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.koja_business_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.koja_business_departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.koja_business_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.koja_business_core_events ENABLE ROW LEVEL SECURITY;

-- REST service uses the server-side Supabase key from Flask, so no public policies are required here.
