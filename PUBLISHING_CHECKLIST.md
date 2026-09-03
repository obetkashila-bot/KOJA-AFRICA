# KOJA AFRICA Publishing Checklist

## Render
- Repository entrypoint: `app.py`
- Start command: `gunicorn app:app`
- Deploy after committing the updated `app.py` and `static/favicon.png`.

## Public Google pages
- `/`
- `/research`
- `/research/topics/education`
- `/research/topics/zambia`
- `/research/topics/technology`
- `/research/topics/health`
- `/research/topics/agriculture`
- `/research/topics/climate`
- `/research/topics/business`
- `/research/topics/social-sciences`

## Search-result policy
- `/research?q=...` remains noindex because it is a query/filter result page.
- Permanent topic pages are indexable and are included in the sitemap.

## Search Console
1. Confirm `https://koja-africa.onrender.com/` returns HTTP 200.
2. Open `/robots.txt` and confirm it references `/sitemap.xml`.
3. Open `/sitemap.xml` and confirm the topic URLs are listed.
4. Submit `/sitemap.xml` in Google Search Console.
5. Use URL Inspection for the home page, `/research`, and selected topic pages.
6. Request indexing for the most important public URLs after deployment.

Google may take time to crawl, evaluate and index pages; a sitemap and indexing request do not guarantee immediate inclusion.
