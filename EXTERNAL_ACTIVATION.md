# KOJA AFRICA — FINAL EXTERNAL GO-LIVE ACTIVATION

This document covers the requirements that application code cannot truthfully complete by itself. A gate becomes `verified` only after real evidence exists.

## 1. Production credentials

Configure production secrets only in the hosting provider's secret/environment-variable store. Do not commit them to GitHub, SQL, screenshots or support messages.

Required groups:
- Supabase production credentials
- strong production Flask `SECRET_KEY`
- Flutterwave live credentials
- LiveKit credentials
- KOJA Cloud service credential
- production email provider
- production SMS provider
- FX provider
- OAuth production credentials

After configuration, rotate any credential that was ever exposed in source code, chat, logs or screenshots.

## 2. Provider onboarding

For every provider, record:
- legal/business account name
- production account ID
- supported countries
- supported currencies
- settlement account
- webhook endpoint
- webhook signing/verification method
- support contact
- service-level limits
- activation date

Do not mark the gate verified merely because an API key exists.

## 3. Payments and licensing

Before live customer payments:
- complete payment-provider merchant onboarding;
- verify the provider's permitted payment rails and countries;
- determine whether KOJA itself is performing a regulated payment activity or only facilitating payments through a licensed provider;
- obtain any licence, approval, registration or contractual authorization that legal counsel/regulators require;
- test authorization, capture, failure, duplicate webhook, refund, reversal, settlement and reconciliation flows.

Do not activate regulated payment features based only on software readiness.

## 4. LiveKit

Create the production LiveKit project and configure:
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

Then test:
1. authorized room creation;
2. user authorization;
3. voice call;
4. video call;
5. reconnect after network loss;
6. participant join/leave;
7. unauthorized-room rejection;
8. call/session record creation;
9. credential rotation.

## 5. Email, SMS and push

Complete production provider onboarding and verify:
- domain/sender identity;
- SPF/DKIM/DMARC where applicable;
- SMS sender configuration;
- OTP delivery;
- password recovery;
- email verification;
- payment notification;
- order notification;
- driver/delivery notification;
- failure and retry handling;
- delivery callbacks.

## 6. Live FX

Use a production FX provider that supports the currencies KOJA actually enables.

Required controls:
- timestamp every rate;
- store provider/source;
- reject stale rates;
- define a maximum rate age;
- retain the rate used for each cross-currency transaction;
- define a fallback/market-closed policy;
- monitor provider failures;
- never silently substitute a hard-coded exchange rate.

## 7. Backup and restore exercise

A backup is not verified until it has been restored.

Exercise:
1. create a production backup;
2. restore it into an isolated environment;
3. verify authentication data and critical records;
4. verify orders/payments/settlements;
5. verify audit logs;
6. verify required file/object metadata;
7. run application smoke tests;
8. measure restore time;
9. document RTO and RPO;
10. record evidence and approver.

## 8. Penetration and load testing

At minimum test:
- authentication/session handling;
- OAuth callback validation;
- authorization/role boundaries;
- IDOR/BOLA;
- CSRF;
- XSS;
- injection;
- file upload abuse;
- webhook replay/signature validation;
- rate limits;
- API key scopes;
- payment idempotency;
- password recovery;
- admin endpoints;
- Supabase/RLS boundaries;
- queue/job abuse;
- concurrent orders and payments;
- sustained API load.

Never perform intrusive testing against third-party provider infrastructure without permission.

## 9. Disaster recovery

Run a controlled failure exercise covering at least:
- application outage;
- database outage;
- queue/worker failure;
- storage failure;
- payment provider outage;
- notification provider outage;
- LiveKit outage.

For each scenario record detection time, mitigation, recovery time, data loss, duplicate-event behavior and follow-up actions.

## 10. Zambia legal/regulatory gate

Before launch, obtain professional review of the services KOJA will actually operate in Zambia. Review at minimum:
- data protection/privacy obligations and applicable registration;
- payment/financial-services requirements;
- consumer protection;
- tax/VAT obligations;
- electronic communications requirements where applicable;
- business verification/KYC/KYB requirements;
- cross-border data transfer;
- contracts/terms for providers and merchants.

The application may store a compliance status, but it cannot create a regulatory approval.

## 11. Africa expansion gate

For every additional country, create a country launch record covering:
- country code;
- currency;
- phone format;
- supported payment providers;
- FX availability;
- tax rules;
- consumer rules;
- data-protection requirements;
- cross-border transfer requirements;
- KYC/KYB requirements;
- delivery/logistics constraints;
- local legal review;
- provider contracts;
- launch approval.

Zambia (`ZM`/`ZMW`) is the initial default, not a restriction on the African architecture.

## 12. Final go-live order

1. Apply SQL migrations.
2. Configure production secrets.
3. Complete provider onboarding.
4. Complete payment/regulatory review.
5. Configure LiveKit.
6. Configure email/SMS/push.
7. Configure FX.
8. Execute backup/restore.
9. Execute security/load tests.
10. Execute disaster-recovery exercise.
11. Complete country legal/regulatory review.
12. Run production smoke tests.
13. Record evidence in `koja_core_go_live_gates`.
14. Obtain accountable-owner approval.
15. Enable live regulated/payment features.

## Gate rule

`verified` means there is evidence, not merely code.

`pending` = not started.
`in_progress` = being completed.
`blocked` = a dependency prevents completion.
`verified` = evidence reviewed and accepted.
`waived` = formally waived by an accountable owner with a recorded reason.

Do not mark a required gate `waived` merely to make the dashboard green.
