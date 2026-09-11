KOJA MARKET LIVE SHOPPING V1

Added to KOJA Market:
- Live Shopping discovery page: /market/live
- Approved sellers can start a live: /market/live/start
- Live room with camera/microphone publishing for seller
- Buyers can watch the seller live
- Seller can pin products in the live room
- Buyers can Buy Now or Add to Cart without leaving the live room
- LiveKit SFU token endpoint: /api/market/live-token/<room_id>
- Seller Center shortcut: Go Live Shopping

Production requirements:
Set these Render environment variables:
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET

The live-video client is loaded from the LiveKit browser SDK CDN. No LiveKit secret is exposed to the browser.

Supabase:
Run KOJA_MARKET_LIVE_SHOPPING.sql in Supabase SQL Editor.

Important:
This package changes KOJA Market only. KOJA Communications / Connect+ is not modified.
