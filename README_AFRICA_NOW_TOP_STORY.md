# KOJA NEXUS — AFRICA NOW TOP STORY

This build keeps AFRICA NOW as a single media screen at the top of KOJA NEXUS.

## Behaviour
- One top story is shown at a time.
- The displayed story rotates automatically through the ranked story pool.
- The collector refreshes sources every 5 minutes.
- New stories automatically replace older stories when ranking changes.
- Images are shown when supplied by the source.
- Authorized/direct video media is shown when supplied by the feed; otherwise the source story opens in its original publisher page.
- No manual admin posting is required.
- There are no LIVE/BREAKING/TRENDING labels on the AFRICA NOW screen.
- NEXUS public services remain below the screen.
- If feeds temporarily fail, the existing cached stories remain available.

## Sources
- Africanews RSS: official Africanews RSS service.
- BBC Africa RSS.
- BBC Afrique RSS.
- AllAfrica Africa RDF feed.
- AllAfrica Business RDF feed.

AllAfrica attribution requirements remain applicable; the source link is preserved on each story.

## Deployment
Replace the existing `app.py` with this file. Keep the existing Render build/start commands.

The Python source passes `py_compile` syntax validation.
