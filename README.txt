KOJA AFRICA — PROFESSIONAL SERVICES + KOJA CONNECT

This package combines the production Professional Services module with KOJA Connect.

Professional Services:
- All professional categories
- Search/filter professions
- Professional registration and admin approval
- Book service / ask advice / counselling
- Contact professional
- Professional chat
- Voice calls and video calls

KOJA Connect (separate from Professional Services):
- Find people and contacts
- Private chat
- Voice messages
- General voice/video calls
- Status

Deployment:
1. Run KOJA_CONNECT.sql in Supabase SQL Editor.
2. Replace your Render app.py with this package's app.py.
3. Keep your existing Render environment variables.
4. Deploy/restart Render.

Important: WebRTC calls use browser STUN. TURN may be needed on restrictive mobile/carrier networks.


PROFESSION-SPECIFIC COMMUNICATION
- Every profession in the Professional Services directory has its own public communication room.
- Public profession pages can be viewed without logging in; posting requires a KOJA account.
- Each professional profile keeps private communication separate: private chat, voice call, video call, booking/advice/counselling.
- Public profession posts are also available separately for longer discussions and announcements.
- Run the updated KOJA_CONNECT.sql in Supabase before deployment.

DIGITAL MARKETPLACE (2026-09-03)
-------------------------------
Added KOJA Digital Marketplace at /marketplace.

Features:
- Public marketplace browsing and search by category.
- Digital products: ebooks, courses, research resources, templates, software/code, graphics, audio, video and business resources.
- Users can submit digital products with a cover image, description and price in ZMW.
- New products are unpublished until admin approval.
- Free products can be claimed and downloaded immediately.
- Paid products create a pending purchase order; payment is deliberately not marked paid automatically because a verified payment gateway is not connected in this build.
- Admin Marketplace page: /admin/marketplace for publishing products and managing pending orders.
- Digital files are served through KOJA's server-side Supabase connection, so private storage buckets can still be used.
- Marketplace cover images are also proxied through KOJA.

DATABASE:
Run MARKETPLACE.sql once in Supabase SQL Editor.

IMPORTANT PAYMENT NOTE:
Before taking real money, integrate and verify a payment provider (for example a supported mobile-money/card gateway) and only change an order to paid after a trusted server-side payment confirmation/webhook.
