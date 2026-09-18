KOJA AFRICA RESEARCH V9 — GOOGLE-LIKE SEARCH LAYER

Base: supplied KOJA production app(20260918-140633).py

Adds:
- Official YouTube Data API search when YOUTUBE_API_KEY or GOOGLE_YOUTUBE_API_KEY is configured.
- YouTube results rendered inside KOJA with permitted YouTube embed playback.
- Public web-source reader at /research/source so eligible HTML/text pages can be read inside KOJA.
- SSRF protections for the source reader: blocks localhost, private, loopback, link-local, multicast and reserved IP destinations.
- Videos filter in Research.
- Read in KOJA + Original source actions for web results.
- Existing research ranking, AI, academic, Wikipedia, KOJA documents and other modules preserved.
- No SQL migration required.

Render environment:
YOUTUBE_API_KEY=your YouTube Data API key

Important:
The public YouTube Data API search endpoint does not grant arbitrary third-party transcript downloads. KOJA does not bypass YouTube permissions or access controls. Video playback is embedded using YouTube's permitted embed URL.
