KOJA NEXUS — 1,000 LIVE SOURCES (CORRECTED FOR EXISTING SUPABASE TABLE)

1. Open Supabase SQL Editor.
2. Run KOJA_NEXUS_1000_LIVE_SOURCES.sql.
3. The final query should return active_source_count = 1000 (or 1000+ if you already had sources).
4. Then replace app.py in the Render/GitHub project with the included app.py and redeploy.

The registry is rotated in batches; KOJA does NOT request all 1,000 URLs at once.
It stores source URLs in Supabase and fetches a limited window each refresh.

The registry includes 54 African countries x 18 topic queries (972) plus 28 global/high-priority feeds.
Some country/topic entries use Google News RSS search endpoints because many publishers do not expose stable public RSS for every country/topic. Publisher feeds are included separately where available.

AFRICA NOW displays links to original publishers/aggregators and does not copy full articles.
