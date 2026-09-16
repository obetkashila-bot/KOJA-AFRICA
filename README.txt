KOJA SERVICES GLOBAL V1

This upgrade replaces the /services screen in the current KOJA AFRICA app with a unified global service center.

Added service groups:
- Learning and Research
- AI and Workspace
- Professional Services
- Market, Business and Global Trade
- KOJA Business / Global Business
- Business Connect entry point
- Import & Export
- Customs & Clearance
- International Trade
- Finance, Payments and Payouts
- Delivery, Freight and Logistics
- Connect+
- KOJA Platform Engines

Important:
- Existing backend routes and services are preserved.
- No Supabase migration is required for this UI-only services-center upgrade.
- Import/export/customs cards are connected to existing KOJA Business/Global Business entry points until the dedicated trade route is deployed.
- Communications/Connect+ backend is not modified.

Deploy by replacing the production app.py with this file and keeping the existing requirements.txt and environment variables.
