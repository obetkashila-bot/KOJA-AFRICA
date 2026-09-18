KOJA AFRICA — RESEARCH BOOKS ENGINE V3

Based on the KOJA Research Books V2 app.py.

ADDED
- Internet Archive book/text discovery.
- Conservative direct PDF/EPUB links only when the Internet Archive record itself declares an open/public-domain/Creative Commons-style right and the corresponding format is present.
- Internet Archive source selector in Research Books.
- My Book Library removal action.
- Library preview links when a source provides one.
- Existing Open Library, Google Books, DOAB and Project Gutenberg connectors preserved.
- Existing legal-access rules preserved: no DRM, paywall, authentication or access-control bypass.

DATABASE
- V3 requires the existing V2 table public.koja_research_books.
- Migration is additive and only creates an optional index.
- If V2 migration has already been run, run V3 migration after it.

IMPORTANT
- A source may expose metadata or a landing page without exposing a downloadable file. KOJA does not manufacture or bypass a download URL.
- Internet Archive direct download is intentionally conservative because availability and rights vary by item.

VALIDATION
- Python syntax compilation passed.
- Production Supabase/external API runtime was not executed from this build environment.
