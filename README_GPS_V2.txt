KOJA AFRICA — PUBLIC PRO MEDIA + REAL GPS V2 + MENU
Version: 2026.09.05-PRO-PUBLIC-MEDIA-REAL-GPS-V2-MENU

This package preserves the authoritative REAL GPS V2 implementation and now exposes GPS directly in the signed-in KOJA navigation menu.

Visible Delivery menu:
- Request Delivery
- Find Drivers
- Live GPS Tracking
- Driver Dashboard (driver/admin)
- Admin Live GPS (admin)

Authoritative REAL GPS V2 routes preserved:
- /tracking
- /api/driver/location
- /api/driver/offline
- /track/<tracking_code>
- /api/delivery/route
- /api/delivery/<tracking_code>/location
- /admin/live-tracking
- /api/admin/live-drivers

Deploy notes:
1. Replace the deployed app.py with this package's app.py in the Git branch connected to Render.
2. Commit/push the change.
3. In Render, deploy the latest commit if auto-deploy is off.
4. Sign in to KOJA AFRICA and open ☰ Menu → 🚚 Delivery → 📍 Live GPS Tracking.
