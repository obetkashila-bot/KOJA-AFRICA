-- KOJA Assignments + Documents V2
-- Additive/update-safe migration. No tables are dropped or recreated.

ALTER TABLE IF EXISTS public.assignments
  ADD COLUMN IF NOT EXISTS file_name text,
  ADD COLUMN IF NOT EXISTS file_path text,
  ADD COLUMN IF NOT EXISTS file_url text,
  ADD COLUMN IF NOT EXISTS file_size bigint,
  ADD COLUMN IF NOT EXISTS mime_type text,
  ADD COLUMN IF NOT EXISTS owner_id uuid,
  ADD COLUMN IF NOT EXISTS sender_id uuid,
  ADD COLUMN IF NOT EXISTS tracking_code text,
  ADD COLUMN IF NOT EXISTS answer text,
  ADD COLUMN IF NOT EXISTS answered_by uuid,
  ADD COLUMN IF NOT EXISTS answered_at timestamptz,
  ADD COLUMN IF NOT EXISTS answer_file_name text,
  ADD COLUMN IF NOT EXISTS answer_file_path text,
  ADD COLUMN IF NOT EXISTS answer_file_url text,
  ADD COLUMN IF NOT EXISTS answered_file_name text,
  ADD COLUMN IF NOT EXISTS answered_file_path text,
  ADD COLUMN IF NOT EXISTS answered_file_url text;

CREATE INDEX IF NOT EXISTS idx_assignments_owner_created
  ON public.assignments (owner_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_assignments_tracking_code
  ON public.assignments (tracking_code);

ALTER TABLE IF EXISTS public.documents
  ADD COLUMN IF NOT EXISTS file_name text,
  ADD COLUMN IF NOT EXISTS file_path text,
  ADD COLUMN IF NOT EXISTS file_url text,
  ADD COLUMN IF NOT EXISTS approval_status text,
  ADD COLUMN IF NOT EXISTS is_public boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true,
  ADD COLUMN IF NOT EXISTS category text,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_documents_approval_created
  ON public.documents (approval_status, created_at DESC);
