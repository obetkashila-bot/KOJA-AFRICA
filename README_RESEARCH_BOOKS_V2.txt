KOJA AFRICA — RESEARCH BOOKS ENGINE V2

Based on production app(20260918-113649).py.

WHAT THIS ADDS
- /research/books — dedicated Books research workspace.
- Search Open Library, Google Books, DOAB and Project Gutenberg.
- Book metadata: title, authors, year, publisher, ISBN, language, cover and description where supplied.
- Availability classification: metadata, preview, read/borrow, open access or download available.
- Source landing/preview links.
- Direct source-provided download links when a source exposes an appropriate public/open file URL (especially DOAB bitstreams).
- Project Gutenberg uses its canonical ebook landing page for downloads rather than hard-coding direct file URLs, following Gutenberg's linking guidance.
- Save books to /research/books/library.
- Additive Supabase table: public.koja_research_books.
- Research page gets a Books tab.

SOURCES
1. Open Library Search API
2. Google Books Volumes API
3. Directory of Open Access Books (DOAB) REST API
4. Project Gutenberg OPDS discovery

LEGAL/ACCESS BEHAVIOR
KOJA only exposes access that the source itself provides. It does not bypass DRM, paywalls, authentication, access controls, or copyright restrictions. For Project Gutenberg, users are sent to the canonical ebook page where available formats can be selected.

CONFIGURATION
GOOGLE_BOOKS_API_KEY is optional. Public Google Books search can work without a key but quota/rate limits may apply.

DATABASE
Run KOJA_RESEARCH_BOOKS_V2_MIGRATION.sql in Supabase SQL Editor. The migration is additive/update-safe and does not recreate existing tables.

DEPLOY
Replace the production app.py with this app.py, commit to the existing KOJA-AFRICA repository, and deploy on the existing Render Production service. Do not replace the Render service.

ANDROID
The existing KOJA Android WebView download layer can download source-provided PDF/EPUB links. Gutenberg links intentionally open the canonical book page so the user can choose the permitted format there.

VALIDATION
Python syntax compilation passed. Production Supabase/external-source runtime was not executed from this build environment.
