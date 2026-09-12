KOJA DELIVERY BUTTONS V2 — 2026-09-12

This is an additive UI/navigation upgrade on top of the deployed KOJA ONE-OTP delivery build.

Added directly to Live Delivery Tracking:
- Find / Select Driver when no driver is assigned.
- Confirm Seller Handover for the seller/business owner.
- Start Driver GPS and Driver Delivery for the assigned driver.
- Confirm Delivery for the buyer after pickup is verified.
- Clear one-OTP flow/status guidance.

No Communications UI changes.
No destructive SQL migration.

IMPORTANT:
Use this app.py as the replacement for the currently deployed ONE-OTP app.py.
The SQL file is included for completeness; if the ONE-OTP migration was already run, do not rerun it unless needed.
Keep Render command: gunicorn app:app
