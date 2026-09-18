KOJA AFRICA END-TO-END V6 — EVERYTHING PURCHASABLE

V6 adds a customer-facing purchasing layer on top of the existing KOJA modules.

Customer paths:
  /buy
  /buy/business-product/<product_id>
  /buy/professional/<provider_id>
  /buy/service/<service_id>

What V6 makes directly purchasable:
  1. Business POS products — customers can buy active business products even when the owner has not separately configured a public store.
  2. Professional services — approved professionals can publish a paid hourly/service rate; customers choose service type/date/time/location, then pay by mobile money.
  3. Published E2E services — any published KOJA E2E service can be purchased through the common checkout.
  4. KOJA Market remains available through its existing production checkout and is surfaced in the Buy Center.

Payment:
  - Flutterwave Mobile Money: MTN, AIRTEL, ZAMTEL.
  - V6 creates an idempotent checkout session with a unique tx_ref.
  - Payment is verified server-side before the E2E order becomes paid.
  - Earnings are created for the provider/business using the existing E2E fee configuration.

Lifecycle:
  Discover -> Buy/Book -> Payment -> Verified -> Provider fulfilment -> Complete -> Settlement -> Review.

Source-of-truth rule:
  Existing business orders, appointments and Market orders remain the source records.
  E2E is the universal transaction layer and does not replace those modules.

V6 migration order:
  1. KOJA_E2E_V1_MIGRATION.sql
  2. KOJA_E2E_V2_MIGRATION.sql
  3. KOJA_E2E_V4_MIGRATION.sql
  4. KOJA_E2E_V5_MIGRATION.sql
  5. KOJA_E2E_V6_MIGRATION.sql

Production:
  Keep the existing KOJA AFRICA Render Production deployment.
  Connect+ / Communications was not modified.

Important:
  This package has been syntax-checked, but the production Supabase/Flutterwave environment must be tested with a real sandbox/live payment before claiming live payment success.
