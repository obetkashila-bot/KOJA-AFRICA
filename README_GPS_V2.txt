KOJA AFRICA — PUBLIC PRO MEDIA + REAL GPS V2 + MULTI-MAP
Version: 2026.09.05-PRO-PUBLIC-MEDIA-REAL-GPS-V2-MULTI-MAP

This package preserves the authoritative REAL GPS V2 implementation and exposes GPS directly in the signed-in KOJA navigation menu.

Live GPS / map interface:
- Leaflet street map
- Satellite imagery layer
- Optional Google Maps view via GOOGLE_MAPS_API_KEY
- Live device GPS with high-accuracy browser geolocation
- Live server GPS posting to /api/driver/location
- GPS error/permission/no-signal handling
- Preview/demo driver when no GPS/driver is connected, so the map is still visible and usable
- Zambia default map center
- Location accuracy circle
- Mobile-responsive map controls

Important:
- "Demo/Preview" is clearly labelled and is NOT a real driver location.
- A real live GPS position requires the driver's device GPS and network connection to send updates to KOJA.
- Map tiles themselves require network access unless a separately licensed/self-hosted/offline map provider is configured. Do not prefetch OpenStreetMap tiles.
- OpenStreetMap attribution is included.
- Google Maps is optional. If enabled, set GOOGLE_MAPS_API_KEY in Render and restrict the browser key to the KOJA domain/API usage.

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

Deploy:
1. Replace the deployed app.py with this package's app.py in the Git branch connected to Render.
2. Commit/push the change.
3. In Render, deploy the latest commit if auto-deploy is off.
4. Sign in to KOJA AFRICA and open ☰ Menu → 🚚 Delivery → 📍 Live GPS Tracking.
5. Optional: add GOOGLE_MAPS_API_KEY in Render Environment for the Google Map button.
