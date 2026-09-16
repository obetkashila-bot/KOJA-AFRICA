KOJA Global Business — Vertical Round Button UI

This package updates the /services page in the supplied KOJA Flask app.

UI changes:
- Small circular icon launcher arranged vertically on desktop.
- Bottom horizontal scroll launcher on small mobile screens.
- Tooltips on desktop/focus labels.
- Business, Business Connect, CRM, Procurement, Market, Professional Services,
  Projects, Finance, Logistics, KOJA AI, Connect+, Research and Settings.
- Existing backend routes are reused; no database migration is required for this UI change.
- Existing Communications/Connect+ implementation is not replaced.

Deploy:
1. Replace the existing app.py in the KOJA-AFRICA repository with this app.py.
2. Commit/push to the existing production branch.
3. Render deploys the existing KOJA-AFRICA service.
4. Test /health, then /services.
