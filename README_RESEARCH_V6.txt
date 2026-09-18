KOJA AFRICA Research V6 — Native Source UI

Google/search results are no longer presented as a button that simply sends the user to Google. KOJA remains the research UI.

- Google CSE results, when configured, are rendered as KOJA result cards.
- Without Google CSE credentials, KOJA uses its internal Web/Wikipedia research lanes instead of an outbound Google search link.
- Result pages can be read inside KOJA through /research/view.
- Public PDFs are streamed inline by KOJA.
- Public HTML is fetched and text-extracted into the KOJA Research Reader.
- Interactive-source fallback is provided only where a site requires its own browser, JavaScript, login, or blocks embedding.
- SSRF protections block localhost/private/link-local/reserved destinations.
- No SQL migration.
- No DRM/paywall/access-control bypass.
- Based directly on the current production app.py.
