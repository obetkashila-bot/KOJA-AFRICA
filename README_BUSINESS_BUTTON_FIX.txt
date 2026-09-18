KOJA AFRICA — BUSINESS BUTTON / MODULE FIX

This patch stabilizes the Business dashboard module links with a dedicated module dispatcher.

FIXED MODULES
- Inventory / POS
- Accounting
- Subscription
- Customers
- Suppliers
- Invoices
- Employees / Payroll
- Online Store
- AI Assistant
- Business Intelligence
- Platform Engines
- Payments
- Delivery

The existing Business routes remain intact. The dispatcher only redirects to the existing route.
Communications / Connect+ is untouched.
No SQL migration is required for this button-routing fix.

DEPLOY
Replace the deployed app.py on the existing KOJA-AFRICA Render service with this app.py.
Keep the existing requirements.txt and environment variables.
Then deploy/restart the service.
