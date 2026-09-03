-- KOJA AFRICA APPROVAL CENTRE — SAFE UPDATE-ONLY MIGRATION
-- Adds approval workflow columns only. Does NOT DROP, DELETE, TRUNCATE or recreate tables.
BEGIN;

ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS approval_status text DEFAULT 'pending';
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS approval_note text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answer_approval_status text DEFAULT 'pending';

ALTER TABLE public.doctor_profiles ADD COLUMN IF NOT EXISTS approval_status text DEFAULT 'pending';
ALTER TABLE public.doctor_profiles ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE public.doctor_profiles ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.doctor_profiles ADD COLUMN IF NOT EXISTS approval_note text;

ALTER TABLE public.teacher_profiles ADD COLUMN IF NOT EXISTS approval_status text DEFAULT 'pending';
ALTER TABLE public.teacher_profiles ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE public.teacher_profiles ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.teacher_profiles ADD COLUMN IF NOT EXISTS approval_note text;

ALTER TABLE public.driver_profiles ADD COLUMN IF NOT EXISTS approval_status text DEFAULT 'pending';
ALTER TABLE public.driver_profiles ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE public.driver_profiles ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.driver_profiles ADD COLUMN IF NOT EXISTS approval_note text;

ALTER TABLE public.service_providers ADD COLUMN IF NOT EXISTS approval_status text DEFAULT 'pending';
ALTER TABLE public.service_providers ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE public.service_providers ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.service_providers ADD COLUMN IF NOT EXISTS approval_note text;

ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS approval_status text DEFAULT 'pending';
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS approval_note text;

ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS approval_status text DEFAULT 'pending';
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS approval_note text;

ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS approval_status text DEFAULT 'pending';
ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS approved_by uuid;
ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS approval_note text;

CREATE INDEX IF NOT EXISTS idx_assignments_approval_status ON public.assignments(approval_status);
CREATE INDEX IF NOT EXISTS idx_assignments_answer_approval_status ON public.assignments(answer_approval_status);
CREATE INDEX IF NOT EXISTS idx_doctor_profiles_approval_status ON public.doctor_profiles(approval_status);
CREATE INDEX IF NOT EXISTS idx_teacher_profiles_approval_status ON public.teacher_profiles(approval_status);
CREATE INDEX IF NOT EXISTS idx_driver_profiles_approval_status ON public.driver_profiles(approval_status);
CREATE INDEX IF NOT EXISTS idx_service_providers_approval_status ON public.service_providers(approval_status);
CREATE INDEX IF NOT EXISTS idx_documents_approval_status ON public.documents(approval_status);
CREATE INDEX IF NOT EXISTS idx_deliveries_approval_status ON public.deliveries(approval_status);
CREATE INDEX IF NOT EXISTS idx_appointments_approval_status ON public.appointments(approval_status);

COMMIT;
