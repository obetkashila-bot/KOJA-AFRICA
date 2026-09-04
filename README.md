# KOJA AFRICA FINAL PLATFORM V8 — 2026-09-04

Flask + Supabase REST + Supabase Storage platform.

## Included
- Public Facebook-style social feed: posts, images/video, likes, comments, follow/block controls
- Assignments and questions
- Research Engine with web/scholarly/K0JA document sources and citation styles
- Documents and research uploads
- Professional registration, admin approval, public verified directory
- Professional chat, voice/video call foundation, availability and booking calendar
- Live tutoring with multi-user WebRTC classroom, attendance and teacher controls
- KOJA Connect contacts, chat, voice messages and calls
- Driver registration, discovery and live GPS delivery tracking
- Marketplace products, media, orders, reviews and Flutterwave verification webhook
- Notifications, SSE streams and optional Web Push with VAPID
- Admin approvals, moderation/report actions, health checks
- SEO: sitemap/robots, canonical/meta foundations and Google Search Console support
- Security headers, CSRF on new state-changing endpoints, rate limiting foundation

## Required environment
SUPABASE_URL, SUPABASE_SERVICE_KEY, SECRET_KEY, SITE_URL

Optional integrations:
OPENAI_API_KEY, SMTP_HOST/PORT/USERNAME/PASSWORD/FROM, FLW_SECRET_KEY, FLW_WEBHOOK_HASH,
TURN_URL/TURN_USERNAME/TURN_CREDENTIAL, VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY/VAPID_CLAIMS_EMAIL.

## Database
Run `KOJA_FINAL_SCHEMA.sql` in Supabase SQL Editor before first use.

## Important
V8 integrates the application features, but real production readiness still requires deploying it, configuring the external services above, and testing registration, payments, email, WebRTC, GPS, uploads and admin workflows on real devices.
