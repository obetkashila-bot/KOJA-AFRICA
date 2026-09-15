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
