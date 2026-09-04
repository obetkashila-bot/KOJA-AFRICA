# KOJA AFRICA — FINAL PLATFORM V5

Flask + Supabase REST + Supabase Storage application for KOJA AFRICA.

## Included
- Public Facebook-style feed with media, comments, likes and location
- KOJA Connect contacts, direct chat, voice messages and WebRTC calls
- Professional registration with administrator approval before public listing
- Public professional profiles, reviews, service locations and booking
- Professional private chat, voice/video calls and live tutoring entry
- Appointment accept/reject/cancel/reschedule/complete workflow
- Live tutoring class scheduling and classroom room tokens
- Assignments and Research Engine
- Research sources, structured notes and citation styles
- Digital marketplace, checkout integration and seller workflow
- Marketplace moderation/review schema
- Driver registration, approval and live GPS delivery tracking
- Notifications and notification center
- Account email verification and password reset when SMTP is configured
- Reporting/moderation queue
- Google-friendly public routes, robots and sitemap
- TURN configuration endpoint for reliable WebRTC
- Security headers, rate limiting and ownership/admin checks

## Deployment
1. Create/update the Supabase database by running `KOJA_FINAL_SCHEMA.sql` in the Supabase SQL Editor.
2. Deploy this folder to Render as a Python web service.
3. Set all required environment variables in Render.
4. Configure the `koja-files` Storage bucket and service-role access.
5. Configure SMTP for verification/reset/notification email.
6. Configure a TURN service using `TURN_URL`, `TURN_USERNAME`, and `TURN_CREDENTIAL` for reliable voice/video calls.
7. Set `SITE_URL` to the real production domain.
8. Test registration, verification, password reset, professional approval, chat/calls, booking, classroom, marketplace payment, GPS and admin moderation after deployment.

## Important
The application code can expose the integration points, but external services must still be configured. In particular, WebRTC reliability depends on a reachable TURN server, email depends on SMTP, payments depend on Flutterwave configuration/webhooks, and Google indexing depends on Google crawling the public production URLs.
