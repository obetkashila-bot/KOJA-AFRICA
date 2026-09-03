-- KOJA AFRICA DATABASE - Supabase/PostgreSQL
-- Safe setup: does not drop or delete existing application data.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), full_name text, email text, phone text,
 role text DEFAULT 'student', is_admin boolean DEFAULT false, is_active boolean DEFAULT true,
 password_hash text, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
-- KOJA uses its own profiles/password_hash authentication. Remove a legacy
-- profiles -> public.users foreign key if an older installation created it.
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_id_fkey;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS full_name text;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS phone text;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS role text DEFAULT 'student';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_admin boolean DEFAULT false;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles (lower(email));
CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles (role);
UPDATE public.profiles SET role='admin', is_admin=true, is_active=true, updated_at=now() WHERE lower(email)=lower('obetkashila@gmail.com');

CREATE TABLE IF NOT EXISTS public.questions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, question text, question_text text,
 subject text, answer text, status text DEFAULT 'submitted', answered_by uuid, answered_at timestamptz,
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS question text;
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS question_text text;
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS subject text;
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS answer text;
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS status text DEFAULT 'submitted';
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS answered_by uuid;
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS answered_at timestamptz;
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE public.questions ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_questions_user_id ON public.questions(user_id);
CREATE INDEX IF NOT EXISTS idx_questions_status ON public.questions(status);

CREATE TABLE IF NOT EXISTS public.assignments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), student_id uuid, user_id uuid, title text, description text,
 status text DEFAULT 'submitted', file_name text, file_path text, file_url text, file_size bigint, mime_type text,
 answer text, answer_file_name text, answer_file_path text, answer_file_url text,
 answered_file_name text, answered_file_path text, answered_file_url text, answered_by uuid, answered_at timestamptz,
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS student_id uuid;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS title text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS status text DEFAULT 'submitted';
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS file_name text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS file_path text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS file_url text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS file_size bigint;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS mime_type text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answer text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answer_file_name text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answer_file_path text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answer_file_url text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answered_file_name text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answered_file_path text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answered_file_url text;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answered_by uuid;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS answered_at timestamptz;
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE public.assignments ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_assignments_student ON public.assignments(student_id);
CREATE INDEX IF NOT EXISTS idx_assignments_user ON public.assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_assignments_status ON public.assignments(status);
CREATE INDEX IF NOT EXISTS idx_assignments_created ON public.assignments(created_at DESC);

CREATE TABLE IF NOT EXISTS public.assignment_answers (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), assignment_id uuid, admin_id uuid, answer_text text,
 file_name text, file_path text, file_url text, mime_type text, status text DEFAULT 'answered',
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assignment_answers_assignment ON public.assignment_answers(assignment_id);

CREATE TABLE IF NOT EXISTS public.documents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text, description text, category text, document_type text,
 author text, year text, tags text, file_name text, file_path text, file_url text, file_size bigint, mime_type text,
 uploaded_by uuid, is_public boolean DEFAULT true, status text DEFAULT 'published',
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_documents_category ON public.documents(category);
CREATE INDEX IF NOT EXISTS idx_documents_created ON public.documents(created_at DESC);

CREATE TABLE IF NOT EXISTS public.document_records (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), document_id uuid, user_id uuid, action text, created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.service_providers (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, provider_type text, full_name text, name text,
 phone text, email text, verification_status text DEFAULT 'pending', is_available boolean DEFAULT false,
 is_active boolean DEFAULT true, latitude double precision, longitude double precision, address text, bio text,
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_service_providers_user ON public.service_providers(user_id);
CREATE INDEX IF NOT EXISTS idx_service_providers_type ON public.service_providers(provider_type);

CREATE TABLE IF NOT EXISTS public.doctor_profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), provider_id uuid, user_id uuid, full_name text, doctor_name text,
 specialty text, hospital_clinic text, qualification text, consultation_fee numeric DEFAULT 0, currency text DEFAULT 'ZMW',
 phone text, email text, address text, latitude double precision, longitude double precision,
 verification_status text DEFAULT 'pending', is_active boolean DEFAULT true, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_doctor_profiles_provider ON public.doctor_profiles(provider_id);

CREATE TABLE IF NOT EXISTS public.teacher_profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), provider_id uuid, user_id uuid, full_name text, teacher_name text,
 subjects text, grade_levels text, qualification text, hourly_rate numeric DEFAULT 0, currency text DEFAULT 'ZMW',
 phone text, email text, address text, latitude double precision, longitude double precision,
 verification_status text DEFAULT 'pending', is_active boolean DEFAULT true, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_teacher_profiles_provider ON public.teacher_profiles(provider_id);

CREATE TABLE IF NOT EXISTS public.appointments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), client_id uuid, provider_id uuid, appointment_type text,
 appointment_date date, start_time time, end_time time, location text, status text DEFAULT 'requested', notes text,
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_appointments_client ON public.appointments(client_id);
CREATE INDEX IF NOT EXISTS idx_appointments_provider ON public.appointments(provider_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON public.appointments(appointment_date);

CREATE TABLE IF NOT EXISTS public.driver_profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), provider_id uuid, vehicle_type text, vehicle_make text,
 vehicle_model text, vehicle_registration text, vehicle_number text, driving_license_number text, service_area text,
 verification_status text DEFAULT 'pending', created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_driver_profiles_provider ON public.driver_profiles(provider_id);
CREATE INDEX IF NOT EXISTS idx_driver_profiles_status ON public.driver_profiles(verification_status);

CREATE TABLE IF NOT EXISTS public.driver_locations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), driver_id uuid, user_id uuid, latitude double precision,
 longitude double precision, accuracy double precision, speed double precision, heading double precision,
 altitude double precision, is_online boolean DEFAULT false, created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_driver_locations_driver_created ON public.driver_locations(driver_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_driver_locations_online ON public.driver_locations(is_online, created_at DESC);

CREATE TABLE IF NOT EXISTS public.deliveries (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), customer_id uuid, driver_id uuid,
 pickup_address text, delivery_address text, pickup_latitude double precision, pickup_longitude double precision,
 delivery_latitude double precision, delivery_longitude double precision, status text DEFAULT 'requested', tracking_code text,
 accepted_at timestamptz, picked_up_at timestamptz, delivered_at timestamptz, created_at timestamptz DEFAULT now(),
 updated_at timestamptz DEFAULT now(), currency text DEFAULT 'ZMW', user_id uuid, pickup_location text, destination text,
 destination_latitude double precision, destination_longitude double precision, recipient_name text, recipient_phone text,
 package_description text, package_weight numeric, delivery_fee numeric DEFAULT 0, requested_date date, requested_time time, notes text
);
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS customer_id uuid;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS driver_id uuid;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS pickup_address text;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS delivery_address text;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS pickup_latitude double precision;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS pickup_longitude double precision;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS delivery_latitude double precision;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS delivery_longitude double precision;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS status text DEFAULT 'requested';
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS tracking_code text;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS accepted_at timestamptz;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS picked_up_at timestamptz;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS delivered_at timestamptz;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS currency text DEFAULT 'ZMW';
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS user_id uuid;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS pickup_location text;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS destination text;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS destination_latitude double precision;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS destination_longitude double precision;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS recipient_name text;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS recipient_phone text;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS package_description text;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS package_weight numeric;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS delivery_fee numeric DEFAULT 0;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS requested_date date;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS requested_time time;
ALTER TABLE public.deliveries ADD COLUMN IF NOT EXISTS notes text;
CREATE UNIQUE INDEX IF NOT EXISTS idx_deliveries_tracking_code ON public.deliveries(tracking_code) WHERE tracking_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_deliveries_customer ON public.deliveries(customer_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_driver ON public.deliveries(driver_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_status ON public.deliveries(status);
CREATE INDEX IF NOT EXISTS idx_deliveries_created ON public.deliveries(created_at DESC);

CREATE TABLE IF NOT EXISTS public.activity_logs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, action text, description text, created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON public.activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created ON public.activity_logs(created_at DESC);

CREATE TABLE IF NOT EXISTS public.cv_records (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid, full_name text, phone text, email text, address text,
 profile text, education text, experience text, skills text, references text, file_name text, file_path text, file_url text,
 created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cv_records_user ON public.cv_records(user_id);

-- Storage bucket used by the Flask app.
INSERT INTO storage.buckets(id,name,public) VALUES('koja-files','koja-files',true) ON CONFLICT(id) DO NOTHING;

-- Keep updated_at current.
CREATE OR REPLACE FUNCTION public.koja_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at=now(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_questions_updated_at ON public.questions;
CREATE TRIGGER trg_questions_updated_at BEFORE UPDATE ON public.questions FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_assignments_updated_at ON public.assignments;
CREATE TRIGGER trg_assignments_updated_at BEFORE UPDATE ON public.assignments FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_documents_updated_at ON public.documents;
CREATE TRIGGER trg_documents_updated_at BEFORE UPDATE ON public.documents FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_service_providers_updated_at ON public.service_providers;
CREATE TRIGGER trg_service_providers_updated_at BEFORE UPDATE ON public.service_providers FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_doctor_profiles_updated_at ON public.doctor_profiles;
CREATE TRIGGER trg_doctor_profiles_updated_at BEFORE UPDATE ON public.doctor_profiles FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_teacher_profiles_updated_at ON public.teacher_profiles;
CREATE TRIGGER trg_teacher_profiles_updated_at BEFORE UPDATE ON public.teacher_profiles FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_appointments_updated_at ON public.appointments;
CREATE TRIGGER trg_appointments_updated_at BEFORE UPDATE ON public.appointments FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_driver_profiles_updated_at ON public.driver_profiles;
CREATE TRIGGER trg_driver_profiles_updated_at BEFORE UPDATE ON public.driver_profiles FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_deliveries_updated_at ON public.deliveries;
CREATE TRIGGER trg_deliveries_updated_at BEFORE UPDATE ON public.deliveries FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();
DROP TRIGGER IF EXISTS trg_cv_records_updated_at ON public.cv_records;
CREATE TRIGGER trg_cv_records_updated_at BEFORE UPDATE ON public.cv_records FOR EACH ROW EXECUTE FUNCTION public.koja_set_updated_at();

-- Final checks.
SELECT id,full_name,email,role,is_admin,is_active FROM public.profiles WHERE lower(email)=lower('obetkashila@gmail.com');
SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN
('profiles','questions','assignments','assignment_answers','documents','document_records','service_providers','doctor_profiles','teacher_profiles','appointments','driver_profiles','driver_locations','deliveries','activity_logs','cv_records') ORDER BY table_name;
