-- KOJA AFRICA PRODUCTION READINESS
-- Additive migration. No DROP statements.

create table if not exists public.koja_core_security_policies (
 id uuid primary key default gen_random_uuid(),
 policy_key text not null unique,
 enabled boolean not null default true,
 config jsonb not null default '{}'::jsonb,
 updated_at timestamptz not null default now()
);

create table if not exists public.koja_core_consents (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null,
 consent_type text not null,
 version text not null,
 granted boolean not null default false,
 source text not null default 'web',
 granted_at timestamptz,
 revoked_at timestamptz,
 created_at timestamptz not null default now(),
 unique(user_id,consent_type,version)
);
create index if not exists koja_core_consents_user_idx on public.koja_core_consents(user_id,created_at desc);

create table if not exists public.koja_core_idempotency_keys (
 id uuid primary key default gen_random_uuid(),
 user_id uuid,
 organization_id uuid,
 idempotency_key text not null,
 request_hash text not null,
 response_status integer,
 response_body jsonb,
 expires_at timestamptz not null default (now() + interval '24 hours'),
 created_at timestamptz not null default now(),
 unique(user_id,idempotency_key)
);
create index if not exists koja_core_idempotency_expiry_idx on public.koja_core_idempotency_keys(expires_at);

create table if not exists public.koja_core_rate_limits (
 id uuid primary key default gen_random_uuid(),
 subject_key text not null,
 route_key text not null,
 window_started_at timestamptz not null,
 request_count integer not null default 0,
 limit_count integer not null default 60,
 updated_at timestamptz not null default now(),
 unique(subject_key,route_key,window_started_at)
);

create table if not exists public.koja_core_security_incidents (
 id uuid primary key default gen_random_uuid(),
 incident_type text not null,
 severity text not null default 'medium',
 status text not null default 'open',
 source text not null default 'system',
 affected_service text default '',
 details jsonb not null default '{}'::jsonb,
 detected_at timestamptz not null default now(),
 resolved_at timestamptz
);
create index if not exists koja_core_incidents_status_idx on public.koja_core_security_incidents(status,severity,detected_at desc);

create table if not exists public.koja_core_backup_registry (
 id uuid primary key default gen_random_uuid(),
 backup_type text not null,
 storage_reference text not null,
 status text not null default 'pending',
 checksum text default '',
 size_bytes bigint default 0,
 created_at timestamptz not null default now(),
 verified_at timestamptz
);

create table if not exists public.koja_core_feature_flags (
 flag_key text primary key,
 enabled boolean not null default false,
 rollout_percent integer not null default 0 check (rollout_percent between 0 and 100),
 countries jsonb not null default '[]'::jsonb,
 config jsonb not null default '{}'::jsonb,
 updated_at timestamptz not null default now()
);

create table if not exists public.koja_core_support_tickets (
 id uuid primary key default gen_random_uuid(),
 user_id uuid,
 organization_id uuid,
 category text not null default 'general',
 priority text not null default 'normal',
 status text not null default 'open',
 subject text not null,
 description text not null,
 metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists koja_core_support_status_idx on public.koja_core_support_tickets(status,priority,created_at desc);

create table if not exists public.koja_core_compliance_profiles (
 country_code text primary key,
 privacy_law text default '',
 payment_regulator text default '',
 consumer_protection text default '',
 ecommerce_law text default '',
 cyber_security_law text default '',
 tax_authority text default '',
 registration_required boolean not null default false,
 payment_license_required boolean not null default false,
 config jsonb not null default '{}'::jsonb,
 updated_at timestamptz not null default now()
);

insert into public.koja_core_security_policies(policy_key,enabled,config) values
('csrf_protection',true,'{}'),
('secure_session_cookies',true,'{}'),
('api_rate_limiting',true,'{"window_seconds":60,"default_limit":120}'),
('idempotent_payments',true,'{"ttl_hours":24}'),
('audit_sensitive_actions',true,'{}'),
('security_incident_logging',true,'{}'),
('consent_tracking',true,'{}'),
('backup_verification',true,'{}'),
('feature_flags',true,'{}'),
('support_and_complaints',true,'{}')
on conflict(policy_key) do update set enabled=excluded.enabled,config=excluded.config,updated_at=now();

insert into public.koja_core_feature_flags(flag_key,enabled,rollout_percent) values
('core_production_readiness',true,100),
('cross_border_commerce',true,100),
('multi_currency',true,100),
('developer_platform',true,100),
('cloud_control_plane',true,100)
on conflict(flag_key) do update set enabled=excluded.enabled,rollout_percent=excluded.rollout_percent,updated_at=now();

-- Zambia baseline. Country-specific legal values should be reviewed with local counsel before activation.
insert into public.koja_core_compliance_profiles(country_code,privacy_law,payment_regulator,consumer_protection,ecommerce_law,cyber_security_law,tax_authority,registration_required,payment_license_required)
values ('ZM','Data Protection Act 2021','Bank of Zambia','Consumer protection framework','Electronic Communications and Transactions Act 2021','Cyber Security Act 2025','Zambia Revenue Authority',true,true)
on conflict(country_code) do update set updated_at=now();

create index if not exists koja_core_security_policies_enabled_idx on public.koja_core_security_policies(enabled);
-- KOJA AFRICA: FINAL EXTERNAL GO-LIVE GATES
-- Additive SQL. Run after the existing production-readiness SQL.


-- ============================================================
-- FINAL REACHING PRODUCTION FOUNDATION
-- ============================================================
-- KOJA AFRICA FINAL REACHING / PRODUCTION COMPLETION FOUNDATION
-- Additive only. No DROP statements. Run after the existing CORE/readiness migrations.

create table if not exists public.koja_core_service_credentials (
 id uuid primary key default gen_random_uuid(), service_key text not null unique,
 provider text not null default '', status text not null default 'not_configured',
 secret_ref text default '', last_verified_at timestamptz, config jsonb not null default '{}'::jsonb,
 updated_at timestamptz not null default now()
);

create table if not exists public.koja_core_service_auth (
 id uuid primary key default gen_random_uuid(), caller_service text not null,
 target_service text not null, status text not null default 'active', scopes jsonb not null default '[]'::jsonb,
 last_used_at timestamptz, created_at timestamptz not null default now(),
 unique(caller_service,target_service)
);

create table if not exists public.koja_core_jobs (
 id uuid primary key default gen_random_uuid(), job_type text not null, service_key text not null,
 status text not null default 'queued', attempts integer not null default 0,
 max_attempts integer not null default 5, available_at timestamptz not null default now(),
 locked_at timestamptz, completed_at timestamptz, last_error text default '', payload jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists koja_core_jobs_ready_idx on public.koja_core_jobs(status,available_at);

create table if not exists public.koja_core_job_attempts (
 id uuid primary key default gen_random_uuid(), job_id uuid references public.koja_core_jobs(id) on delete cascade,
 attempt_no integer not null, status text not null, error_message text default '', started_at timestamptz not null default now(),
 finished_at timestamptz
);

create table if not exists public.koja_core_webhook_receipts (
 id uuid primary key default gen_random_uuid(), provider text not null, event_id text not null,
 signature_valid boolean not null default false, status text not null default 'received',
 payload_hash text default '', received_at timestamptz not null default now(), processed_at timestamptz,
 unique(provider,event_id)
);

create table if not exists public.koja_core_payment_reconciliation (
 id uuid primary key default gen_random_uuid(), provider text not null, provider_reference text not null,
 internal_reference text default '', amount numeric(18,2) not null default 0, currency text not null,
 provider_status text default '', internal_status text default '', reconciliation_status text not null default 'pending',
 discrepancy numeric(18,2) not null default 0, details jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(provider,provider_reference)
);

create table if not exists public.koja_core_settlements (
 id uuid primary key default gen_random_uuid(), organization_id uuid, seller_id uuid, driver_id uuid,
 gross_amount numeric(18,2) not null default 0, platform_fee numeric(18,2) not null default 0,
 seller_amount numeric(18,2) not null default 0, driver_amount numeric(18,2) not null default 0,
 currency text not null default 'ZMW', status text not null default 'pending',
 reference text unique, metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), settled_at timestamptz
);

create table if not exists public.koja_core_kyc_cases (
 id uuid primary key default gen_random_uuid(), subject_type text not null, subject_id uuid,
 status text not null default 'pending', risk_level text not null default 'unknown', reviewer_id uuid,
 provider text default '', provider_reference text default '', decision_reason text default '',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(), reviewed_at timestamptz
);
create index if not exists koja_core_kyc_status_idx on public.koja_core_kyc_cases(status,risk_level,created_at desc);

create table if not exists public.koja_core_kyc_documents (
 id uuid primary key default gen_random_uuid(), case_id uuid references public.koja_core_kyc_cases(id) on delete cascade,
 document_type text not null, storage_ref text not null, verification_status text not null default 'pending',
 checksum text default '', created_at timestamptz not null default now(), verified_at timestamptz
);

create table if not exists public.koja_core_notification_deliveries (
 id uuid primary key default gen_random_uuid(), user_id uuid, channel text not null, provider text default '',
 template_key text not null, destination_hash text default '', status text not null default 'queued',
 attempts integer not null default 0, last_error text default '', sent_at timestamptz, created_at timestamptz not null default now()
);
create index if not exists koja_core_notifications_status_idx on public.koja_core_notification_deliveries(status,created_at desc);

create table if not exists public.koja_core_media_jobs (
 id uuid primary key default gen_random_uuid(), asset_id uuid, job_type text not null,
 status text not null default 'queued', source_ref text default '', output_ref text default '',
 attempts integer not null default 0, last_error text default '', metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), completed_at timestamptz
);

create table if not exists public.koja_core_cloud_resources (
 id uuid primary key default gen_random_uuid(), project_id uuid, resource_type text not null,
 resource_name text not null, provider text default 'koja_cloud', external_id text default '',
 status text not null default 'provisioning', region text default '', metadata jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(provider,external_id)
);

create table if not exists public.koja_core_monitoring_alerts (
 id uuid primary key default gen_random_uuid(), service_key text not null, severity text not null default 'warning',
 status text not null default 'open', metric text default '', threshold text default '', details jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), resolved_at timestamptz
);

create table if not exists public.koja_core_test_runs (
 id uuid primary key default gen_random_uuid(), suite text not null, test_name text not null,
 status text not null default 'pending', environment text not null default 'production',
 details jsonb not null default '{}'::jsonb, started_at timestamptz not null default now(), finished_at timestamptz
);
create index if not exists koja_core_test_runs_suite_idx on public.koja_core_test_runs(suite,status,started_at desc);

create table if not exists public.koja_core_legal_controls (
 id uuid primary key default gen_random_uuid(), country_code text not null, control_key text not null,
 status text not null default 'review_required', evidence_ref text default '', owner text default '',
 expires_at timestamptz, metadata jsonb not null default '{}'::jsonb, updated_at timestamptz not null default now(),
 unique(country_code,control_key)
);

insert into public.koja_core_service_credentials(service_key,provider,status) values
('email','production_email','not_configured'),('sms','production_sms','not_configured'),
('push','production_push','not_configured'),('fx','trusted_fx_provider','not_configured'),
('flutterwave','flutterwave','not_configured'),('livekit','livekit','not_configured'),
('koja_cloud','koja_cloud','not_configured')
on conflict(service_key) do nothing;

insert into public.koja_core_service_auth(caller_service,target_service,scopes) values
('market','pay','["payments.write","payments.read"]'),
('pay','delivery','["delivery.create","delivery.read"]'),
('delivery','notifications','["notifications.send"]'),
('media','cloud','["storage.write","media.transcode"]'),
('core','*','["core.events.write","core.audit.write"]'),
('business','pay','["payments.write","settlements.read"]')
on conflict(caller_service,target_service) do update set scopes=excluded.scopes,status='active';

-- Initial test/control matrix. These are controls to execute; they do not claim a test passed.
insert into public.koja_core_test_runs(suite,test_name,status) values
('authentication','login/password/recovery/oauth', 'pending'),
('payments','payment/webhook/refund/reconciliation', 'pending'),
('api','authentication/scopes/rate-limits/idempotency', 'pending'),
('database','migration/constraints/indexes/backup-restore', 'pending'),
('permissions','RBAC/service-to-service', 'pending'),
('cross_service','market-pay-delivery-notifications', 'pending'),
('media','upload/transcode/HLS/publish', 'pending'),
('cloud','storage/compute/database/API', 'pending'),
('mobile','Android/WebView/sessions/uploads/calls', 'pending'),
('production','smoke/load/failover/monitoring', 'pending');

insert into public.koja_core_legal_controls(country_code,control_key,status) values
('ZM','data_controller_processor_registration','review_required'),
('ZM','payment_services_licensing','review_required'),
('ZM','consumer_protection','review_required'),
('ZM','tax_registration','review_required'),
('ZM','cross_border_data_transfer','review_required')
on conflict(country_code,control_key) do nothing;

-- ============================================================
-- FINAL GO-LIVE GATES
-- ============================================================
create table if not exists public.koja_core_go_live_gates (
  id uuid primary key default gen_random_uuid(),
  gate_key text not null unique,
  category text not null,
  title text not null,
  status text not null default 'pending' check (status in ('pending','in_progress','verified','blocked','waived')),
  required boolean not null default true,
  owner text,
  evidence_url text,
  evidence_note text,
  due_date date,
  verified_by text,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists koja_core_go_live_gates_status_idx
  on public.koja_core_go_live_gates(status, category);

insert into public.koja_core_go_live_gates (gate_key,category,title,required)
values
('production_credentials','infrastructure','Production secrets and credentials configured and rotated',true),
('provider_onboarding','providers','All production providers onboarded and accounts verified',true),
('payment_licensing','regulatory','Payment activity reviewed and required licences/approvals obtained',true),
('livekit_production','communications','LiveKit production project and credentials verified',true),
('notification_contracts','communications','Production email/SMS/push providers contracted and delivery-tested',true),
('live_fx','payments','Trusted production FX feed connected and stale-rate controls verified',true),
('backup_restore','reliability','Production backup and restore exercise completed',true),
('security_testing','security','Penetration, vulnerability and load/concurrency testing completed',true),
('disaster_recovery','reliability','Disaster-recovery exercise completed with measured RTO/RPO',true),
('country_legal_regulatory','regulatory','Country-specific legal review and required registrations completed',true),
('production_smoke','operations','Production smoke test completed after all external gates',true),
('go_live_approval','operations','Final accountable owner approves production activation',true)
on conflict (gate_key) do nothing;

-- Zambia is the initial operating country; expansion gates should be added per country.

-- Final external go-live legal gate.
insert into public.koja_core_legal_controls(country_code,control_key,status,owner,metadata)
values ('ZM','GO_LIVE_EXTERNAL_REVIEW','pending','KOJA Compliance','{"note":"Complete payment, data protection, consumer, tax and other applicable regulatory review before activation."}'::jsonb)
on conflict(country_code,control_key) do update set status=excluded.status, owner=excluded.owner, metadata=excluded.metadata, updated_at=now();
