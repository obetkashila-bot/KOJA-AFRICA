KOJA AFRICA — MARKET INTELLIGENCE BUILD

This build preserves the existing Flask application and repairs the Market Intelligence engine.
Provider order:
1. Alpha Vantage
2. Twelve Data
3. Public market fallback
4. KOJA reference/cache fallback

Important market fixes:
- Alpha Vantage HTTP 429 and quota messages activate a temporary Alpha cooldown.
- Twelve Data is attempted immediately after Alpha fails.
- Market quotes are fetched concurrently so one slow provider does not block all symbols sequentially.
- Public and KOJA reference fallbacks prevent indefinite loading.
- Chart endpoint also has a final KOJA reference fallback.
- Market API returns diagnostic error/provider information instead of hanging.

Render:
Build command: pip install -r requirements.txt
Start command: gunicorn app:app
Environment variables:
ALPHAVANTAGE_API_KEY=your_key
TWELVEDATA_API_KEY=your_key
