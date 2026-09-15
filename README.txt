KOJA AFRICA — UI / PLATFORM SHELL REDESIGN

This package rearranges and redesigns the existing Flask interface without intentionally changing the service/database logic.

UI changes:
- New KOJA AFRICA master visual shell
- Navy/black professional navigation with blue/red accents
- Cleaner mobile navigation drawer
- Reorganised navigation: Home, Dashboard, KOJA AI, Services, Research, Notifications, Explore
- Explore menu groups the existing secondary services
- Redesigned public home page
- Redesigned authenticated dashboard
- Responsive service cards and quick actions
- Existing routes, APIs and service handlers are preserved

Important:
- No Communications feature code was intentionally changed.
- No database tables or SQL schema were changed by the UI redesign.
- app.py syntax was checked with Python compile validation.
- Deploy this app.py only when it matches the cumulative production source you intend to use.

Run command: gunicorn app:app
