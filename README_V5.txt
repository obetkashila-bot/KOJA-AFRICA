KOJA AFRICA — UNIFIED FULFILLMENT V5 — PRODUCTION COMPLETION

This package consolidates the current Unified Fulfillment V4 + AI Auto-Approval and adds the remaining production hardening requested.

ADDED
1. AI approval hardening and audit page.
2. Assignment-answer AI auto approval detection.
3. Market product auto-publishing requires an approved seller.
4. Secure Business digital-product upload and paid download route.
5. Driver availability restricted to approved/active/verified drivers.
6. First-driver atomic claim remains in place for requested deliveries.
7. Pickup code generation and seller/business pickup notification.
8. Available-driver notifications.
9. Buyer, seller and driver delivery-completion notifications.
10. Market delivery job completion synchronization.
11. Email notification delivery when SMTP is configured.
12. Optional Africa's Talking SMS notifications when credentials are configured.
13. Admin Fulfillment Production Health diagnostics (no secrets exposed).
14. Delivery address/pickup address and payout compatibility fields.
15. Live Shopping foundation preserved.
16. Fulfillment AI preserved.
17. Profit/revenue engine preserved.
18. Existing Market, Business, GPS, Live Shop, Flutterwave and core engines preserved.

IMPORTANT
- AI rejects are never automatically applied; uncertain cases remain for human review.
- Doctors, teachers, drivers, professional providers and seller identity remain manual review.
- Flutterwave driver payout only transfers real money when the LIVE credentials, Zambia Mobile Money bank code and KOJA_DRIVER_AUTO_PAYOUT=true are correctly configured.
- Communications/Connect+ was not modified.

SUPABASE
Run KOJA_AFRICA_FULFILLMENT_V5.sql in Supabase SQL Editor. It is additive and contains no DROP/TRUNCATE/DELETE statements.

RENDER ENVIRONMENT
KOJA_AI_AUTO_APPROVAL=true
KOJA_AI_AUTO_APPROVAL_THRESHOLD=0.90
KOJA_DRIVER_AUTO_PAYOUT=true          # only after LIVE payout testing
KOJA_FLW_ZM_MOMO_BANK_CODE=<your configured Zambia Flutterwave MoMo bank code>

Optional email:
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM

Optional SMS:
AT_USERNAME
AT_API_KEY
AT_SENDER_ID

Existing AI, Flutterwave, LiveKit and other production variables must remain unchanged.

ADMIN
/admin/approvals
/admin/approvals/ai-log
/admin/fulfillment/health

TEST FLOW
Buyer pays → seller/business notified → pickup number generated → approved drivers notified → first driver claims → driver verifies pickup → buyer receives live status → buyer confirms receipt → payout is attempted → seller/buyer/driver notified → delivery job marked completed → revenue remains auditable.

DIGITAL
Business digital products are stored privately. Buyers can download only after their paid order is verified through /business/store/download/<order_id>.
