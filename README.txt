KOJA AFRICA — RESEARCH ALL-IN-ONE ADDITIVE UPGRADE

Base: app(20260918-140633).py (pre-free-sources rollback base)

Added:
- Unified Research search
- Web, Google, Wikipedia, KOJA Documents
- OpenAlex, Crossref, arXiv
- YouTube search when YOUTUBE_API_KEY is configured
- News discovery
- Wikimedia Commons image discovery
- Open Library, Internet Archive, Project Gutenberg book discovery
- Source filtering
- In-KOJA research result workspace
- Research history
- Related research questions
- Comparison workspace
- DOCX export when python-docx is available
- PDF export when reportlab is installed
- Unified Research JSON API
- Short-lived in-process research caching

Existing Research routes/providers remain in place. No SQL migration is included.

Important:
- External sources are used through their public/API interfaces.
- KOJA does not bypass DRM, paywalls, authentication, robots/access controls, or private content.
- YouTube search requires YOUTUBE_API_KEY for live YouTube results.
- PDF export requires reportlab; it is optional and does not prevent KOJA from starting.
