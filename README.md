# KOJA AFRICA FINAL PLATFORM V6 — 2026-09-04

Built from the approved KOJA AFRICA V5 package.

## V6 completion layer
- Server-side SSE chat and notification streams (no browser Supabase service key required)
- Follow/unfollow and block/unblock APIs
- Appointment rescheduling with conflict protection
- Professional recurring availability slots
- Live-class enrollment, attendance and end-session lifecycle
- Admin report moderation actions: resolve, dismiss, hide and delete
- Web Push subscription storage endpoint
- TURN/STUN runtime configuration
- Full integration health endpoint: `/api/health/full`
- Existing KOJA Research, Assignments, Professionals, Social, Marketplace, Connect, Booking and Live GPS Delivery features retained

## Required production services
Set Supabase, SMTP, OpenAI, Flutterwave and TURN credentials in Render. The health endpoint reports which integrations are configured.

## Deployment
1. Run `KOJA_FINAL_SCHEMA.sql` in Supabase SQL Editor.
2. Upload the project to GitHub.
3. Deploy the repository on Render.
4. Add environment variables from `.env.example`.
5. Open `/api/health/full` and verify integrations.
6. Test registration, approval, public professional profile, chat, calls, tutoring, booking, marketplace, research and live delivery.
