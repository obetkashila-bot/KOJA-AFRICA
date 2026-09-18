KOJA AFRICA — V10 BUSINESS BUTTONS FULLY WORKING

Base: KOJA AFRICA Business Button Fix / V9 Business Commerce Hub.

Fixes:
1. The /business landing page now gives every existing business real working actions.
2. Each business can open its own Business Dashboard, POS/Inventory, Commerce Hub and Online Store.
3. Business Dashboard now exposes Commerce Hub directly.
4. Business module dispatcher now includes Commerce Hub and Commerce Orders.
5. Dispatcher verifies the target endpoint exists before redirecting, so a missing module does not produce a silent broken button.
6. Existing module routes remain scoped to the selected business.
7. No database migration required.
8. Connect+ and unrelated KOJA services are untouched.

Deploy this app.py as the production app.py. After deployment, open /business, select the business, then test Open Business -> POS/Inventory -> Commerce Hub -> Online Store.
