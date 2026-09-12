KOJA AI + AUTOMATIC NEARBY DRIVER REQUESTS — 2026-09-12

WHAT THIS UPDATE DOES
1. Buyer sees "KOJA AI — Find Nearby Drivers" on a waiting delivery.
2. KOJA reads fresh online driver GPS locations and approved driver profiles.
3. KOJA ranks nearby trusted drivers with AI when an AI provider is available.
4. If AI is unavailable, KOJA safely falls back to GPS distance + physical-area matching.
5. KOJA automatically sends the delivery request notification to the best nearby drivers.
6. Up to 8 drivers can receive the request; the first driver to accept wins.
7. Driver acceptance is atomic on the server. Once one driver accepts, the delivery gets a driver_id and status=accepted.
8. The delivery immediately disappears from the Available KOJA Deliveries queue for every other driver because that queue only shows requested/unclaimed jobs.
9. Buyer tracking page polls for acceptance and updates automatically.
10. AI provider router is Gemini -> Groq -> OpenAI with configured-model and fallback-model failover.

IMPORTANT
- No Communications UI redesign.
- No destructive database changes.
- Existing one-OTP seller/buyer delivery flow is preserved.
- Do not make another payment just to test this feature.

DEPLOY
1. Keep the existing KOJA ONE-OTP SQL already deployed. No new SQL is required for the new button/AI logic.
2. Replace production app.py with this package's app.py.
3. Keep the existing requirements.txt and Procfile.
4. Render command remains: gunicorn app:app
5. Deploy the existing KOJA-AFRICA Production service.
6. Ensure AI environment variables are present in Render:
   GEMINI_API_KEY
   GEMINI_MODEL (optional; use the model you have configured)
   GROQ_API_KEY
   GROQ_MODEL (optional)
   OPENAI_API_KEY (optional fallback)
7. Test the buyer delivery tracking page. For an unassigned delivery, press:
   KOJA AI — Find Nearby Drivers
8. On a driver account, open Available KOJA Deliveries. The first driver to press Accept Delivery claims it. Other drivers will no longer see the job.

FLOW
BUYER: Find Nearby Drivers
  -> KOJA AI ranks nearby online drivers
  -> KOJA sends automatic requests
  -> FIRST DRIVER ACCEPTS
  -> delivery becomes assigned/accepted
  -> request disappears for other drivers
  -> seller confirms the shared OTP
  -> driver transports
  -> buyer confirms the same OTP
  -> payout flow runs after buyer confirmation
