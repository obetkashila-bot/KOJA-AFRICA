-- KOJA AFRICA — ROBUST APPROVAL CENTRE MIGRATION
-- UPDATE ONLY. No DROP, DELETE, TRUNCATE, or table recreation.
-- Safe when optional KOJA tables do not exist: missing tables are skipped.

BEGIN;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['assignments','doctor_profiles','teacher_profiles','driver_profiles','service_providers','documents','deliveries','appointments']
  LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS approval_status text DEFAULT ''pending''', t);
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS approved_by uuid', t);
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS approved_at timestamptz', t);
      EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS approval_note text', t);
      EXECUTE format('UPDATE public.%I SET approval_status = ''pending'' WHERE approval_status IS NULL', t);
      EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON public.%I(approval_status)', 'idx_' || t || '_approval_status', t);
    END IF;
  END LOOP;
END $$;

-- Assignment answers use a separate approval status on the assignments row.
DO $$
BEGIN
  IF to_regclass('public.assignments') IS NOT NULL THEN
    ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answer_approval_status text DEFAULT 'pending';
    UPDATE public.assignments SET answer_approval_status = 'pending' WHERE answer_approval_status IS NULL;
    CREATE INDEX IF NOT EXISTS idx_assignments_answer_approval_status
      ON public.assignments(answer_approval_status);
  END IF;
END $$;

COMMIT;

-- Verification: run this separately if desired.
-- SELECT table_name, column_name
-- FROM information_schema.columns
-- WHERE table_schema='public'
--   AND column_name IN ('approval_status','answer_approval_status','approved_by','approved_at','approval_note')
-- ORDER BY table_name, column_name;
