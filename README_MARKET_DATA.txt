KOJA AFRICA — GLOBAL MARKET DATA ENGINE

This package adds direct market-data API support to KOJA NEXUS / GLOBAL NOW.

Providers:
1. Alpha Vantage — primary
2. Twelve Data — secondary fallback

Render Environment Variables:
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
TWELVEDATA_API_KEY=your_twelve_data_key

Optional:
KOJA_MARKET_SYMBOLS=AAPL,MSFT,NVDA,AMZN,TSLA,GOOGL,META,ORCL,KO,SONY
KOJA_MARKET_CACHE_TTL=30
KOJA_MARKET_TIMEOUT=8

API routes:
/api/markets/quotes
/api/markets/status

The browser never receives the API keys. Quotes are cached server-side and
freshness is labelled according to provider/exchange entitlement. RSS remains
used for market/news stories; it is not used as the source of stock prices.

Replace the existing app.py with the supplied app.py and deploy normally.
Do not remove the existing NEXUS/Africa Now code.
