KOJA AFRICA — MODERN DASHBOARD UPDATE

This release updates the existing KOJA AFRICA app.py without replacing the existing platform routes.

Changes:
- New unified authenticated Dashboard at /dashboard.
- Dashboard assimilates existing KOJA AI, People, Market, Business, Documents, Research, Services and Media.
- Existing connection, requests, questions, deliveries and appointment activity remains connected.
- Adds dashboard quick-access statistics for connections, requests, documents and notifications.
- Adds KOJA Market/business activity where available.
- Adds KOJA Business to authenticated navigation.
- Removes the old “Knowledge • Questions • Answers” branding/tagline from the application identity/footer.
- Footer is now simply “KOJA AFRICA”.
- Existing Contacts, Facebook invite, device invite, Connect+, OAuth, services, marketplace, documents and other routes are preserved.

No new Supabase SQL migration is required for this UI/dashboard change.

Deploy app.py to the existing KOJA-AFRICA Render service.
