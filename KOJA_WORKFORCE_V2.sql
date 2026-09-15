-- KOJA WORKFORCE / HR V1 foundation + V2 completion
-- Additive/update-safe. No DROP/TRUNCATE/RECREATE.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.koja_workforce_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, owner_id uuid, title text, department text, location text,
 employment_type text DEFAULT 'full_time', salary_min numeric DEFAULT 0, salary_max numeric DEFAULT 0, status text DEFAULT 'open',
 description text, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_workforce_candidates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, job_id uuid, first_name text, last_name text, email text, phone text,
 resume_url text, stage text DEFAULT 'applied', notes text, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_workforce_employees (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, owner_id uuid, employee_number text, first_name text, last_name text,
 email text, phone text, department text, job_title text, employment_type text DEFAULT 'full_time', hire_date date, base_salary numeric DEFAULT 0,
 currency text DEFAULT 'ZMW', status text DEFAULT 'active', created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_workforce_attendance (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, employee_id uuid, attendance_date date, status text DEFAULT 'present',
 check_in timestamptz, check_out timestamptz, hours numeric DEFAULT 0, notes text, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_workforce_leave (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, employee_id uuid, leave_type text DEFAULT 'annual', start_date date, end_date date,
 days numeric DEFAULT 0, reason text, status text DEFAULT 'pending', approved_by uuid, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_workforce_payroll (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, employee_id uuid, pay_period text, gross_pay numeric DEFAULT 0,
 deductions numeric DEFAULT 0, net_pay numeric DEFAULT 0, currency text DEFAULT 'ZMW', status text DEFAULT 'draft', paid_at timestamptz,
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_workforce_performance (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, employee_id uuid, period text, score numeric DEFAULT 0, rating text,
 goals text, feedback text, reviewer_id uuid, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_workforce_training (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, employee_id uuid, title text, provider text, training_date date,
 status text DEFAULT 'planned', cost numeric DEFAULT 0, currency text DEFAULT 'ZMW', certificate_ref text, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.koja_workforce_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid, actor_id uuid, event_type text, entity_type text, entity_id uuid,
 metadata jsonb DEFAULT '{}'::jsonb, created_at timestamptz DEFAULT now()
);

ALTER TABLE public.koja_workforce_jobs ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_workforce_candidates ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_workforce_employees ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_workforce_attendance ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_workforce_leave ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_workforce_payroll ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_workforce_performance ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_workforce_training ADD COLUMN IF NOT EXISTS organization_id uuid;
ALTER TABLE public.koja_workforce_events ADD COLUMN IF NOT EXISTS organization_id uuid;

CREATE INDEX IF NOT EXISTS idx_koja_workforce_jobs_org ON public.koja_workforce_jobs(organization_id);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_candidates_org ON public.koja_workforce_candidates(organization_id);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_employees_org ON public.koja_workforce_employees(organization_id);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_attendance_org_date ON public.koja_workforce_attendance(organization_id,attendance_date);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_leave_org_status ON public.koja_workforce_leave(organization_id,status);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_payroll_org_period ON public.koja_workforce_payroll(organization_id,pay_period);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_performance_org ON public.koja_workforce_performance(organization_id);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_training_org ON public.koja_workforce_training(organization_id);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_events_org ON public.koja_workforce_events(organization_id,created_at);

-- KOJA WORKFORCE / HR V2 — additive migration
-- Safe migration: no DROP, TRUNCATE or table recreation.

ALTER TABLE public.koja_workforce_jobs ADD COLUMN IF NOT EXISTS closed_at timestamptz;
ALTER TABLE public.koja_workforce_jobs ADD COLUMN IF NOT EXISTS hiring_manager_id uuid;
ALTER TABLE public.koja_workforce_jobs ADD COLUMN IF NOT EXISTS openings integer DEFAULT 1;

ALTER TABLE public.koja_workforce_candidates ADD COLUMN IF NOT EXISTS source text;
ALTER TABLE public.koja_workforce_candidates ADD COLUMN IF NOT EXISTS interview_at timestamptz;
ALTER TABLE public.koja_workforce_candidates ADD COLUMN IF NOT EXISTS offer_amount numeric DEFAULT 0;
ALTER TABLE public.koja_workforce_candidates ADD COLUMN IF NOT EXISTS hired_at timestamptz;

ALTER TABLE public.koja_workforce_employees ADD COLUMN IF NOT EXISTS tax_number text;
ALTER TABLE public.koja_workforce_employees ADD COLUMN IF NOT EXISTS national_id text;
ALTER TABLE public.koja_workforce_employees ADD COLUMN IF NOT EXISTS emergency_contact text;
ALTER TABLE public.koja_workforce_employees ADD COLUMN IF NOT EXISTS salary_frequency text DEFAULT 'monthly';
ALTER TABLE public.koja_workforce_employees ADD COLUMN IF NOT EXISTS terminated_at timestamptz;

ALTER TABLE public.koja_workforce_attendance ADD COLUMN IF NOT EXISTS source text DEFAULT 'manual';
ALTER TABLE public.koja_workforce_attendance ADD COLUMN IF NOT EXISTS approved_by uuid;

ALTER TABLE public.koja_workforce_leave ADD COLUMN IF NOT EXISTS decision_at timestamptz;
ALTER TABLE public.koja_workforce_leave ADD COLUMN IF NOT EXISTS decision_note text;

ALTER TABLE public.koja_workforce_payroll ADD COLUMN IF NOT EXISTS payment_reference text;
ALTER TABLE public.koja_workforce_payroll ADD COLUMN IF NOT EXISTS finance_transaction_id uuid;
ALTER TABLE public.koja_workforce_payroll ADD COLUMN IF NOT EXISTS payment_method text;

ALTER TABLE public.koja_workforce_performance ADD COLUMN IF NOT EXISTS review_status text DEFAULT 'completed';
ALTER TABLE public.koja_workforce_training ADD COLUMN IF NOT EXISTS completion_date date;
ALTER TABLE public.koja_workforce_training ADD COLUMN IF NOT EXISTS notes text;

CREATE INDEX IF NOT EXISTS idx_koja_workforce_candidates_job_stage ON public.koja_workforce_candidates(job_id,stage);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_employees_status ON public.koja_workforce_employees(organization_id,status);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_attendance_employee_date ON public.koja_workforce_attendance(employee_id,attendance_date);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_payroll_status ON public.koja_workforce_payroll(organization_id,status);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_performance_employee_period ON public.koja_workforce_performance(employee_id,period);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_training_employee_status ON public.koja_workforce_training(employee_id,status);
CREATE INDEX IF NOT EXISTS idx_koja_workforce_events_entity ON public.koja_workforce_events(entity_type,entity_id,created_at);
