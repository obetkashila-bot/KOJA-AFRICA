# KOJA NEXUS — AFRICA NOW v2.0

This package replaces the earlier Google-News-search-feed collector with verified publisher/aggregator RSS/RDF endpoints:

- Africanews: https://www.africanews.com/feed/rss
- BBC Africa: https://feeds.bbci.co.uk/news/world/africa/rss.xml
- BBC Afrique: https://feeds.bbci.co.uk/afrique/rss.xml
- AllAfrica Africa: https://allafrica.com/tools/headlines/rdf/africa/headlines.rdf
- AllAfrica Business: https://allafrica.com/tools/headlines/rdf/business/headlines.rdf

## Automatic updating

- Background collector starts 10 seconds after the Render process is ready, so RSS network calls cannot delay Gunicorn startup or Render health checks.
- Default interval: 5 minutes.
- NEXUS browser screen also refreshes every 5 minutes.
- If the cache is stale, `/api/nexus/africa-now` triggers a non-blocking refresh and immediately returns the cached screen.
- Feed failures do not crash KOJA; the last cached feed is preserved when no new items are collected.
- Per-source status is exposed in the API collector metadata for troubleshooting.

## Deploy

1. Run `KOJA_NEXUS_AFRICA_NOW_VERIFIED.sql` in the KOJA Supabase SQL Editor if the cache table does not already exist.
2. Replace production `app.py` with the included `app.py`.
3. Commit to the connected GitHub branch.
4. Redeploy the existing Render service.

## Optional Render environment variables

- `KOJA_NEXUS_AFRICA_NOW_ENABLED=true`
- `KOJA_NEXUS_AFRICA_NOW_INTERVAL=300`
- `KOJA_NEXUS_AFRICA_NOW_TIMEOUT=8`

The interval is clamped to at least 300 seconds.

## Important hosting limitation

A sleeping Render free instance cannot run a background thread while it is asleep. The first request after wake-up can still trigger a stale-feed refresh, so the feature does not require manual news entry.

## Source-use note

The implementation displays headlines/summaries with links back to the original sources. Follow each publisher's current RSS, attribution, branding, and commercial-use terms before enabling it for a commercial production service. Africanews and AllAfrica explicitly document their RSS/aggregation services; BBC also documents its Africa RSS feed, but commercial syndication permissions should be checked for your use case.
