KOJA AFRICA — DOCUMENT AI HOTFIX

Fixes the production 500 on /documents/ai/<document_id> caused by passing title twice to render_page().

render_page(title, body_template, **context) now receives the page title positionally and the document title as document_title.

Verified with: python -m py_compile app.py

Deploy to existing Render service KOJA-AFRICA. Do not move the service.
