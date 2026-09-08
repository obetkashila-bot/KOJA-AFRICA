KOJA AFRICA — KOJA MARKET V3 + KOJA BUSINESS
Version: 2026.09.08-MARKET-V3-BUSINESS
Foundation: V52 / KOJA Market V2

ADDED COMMERCIAL ENGINE
- Commission on marketplace sales (existing 10% foundation retained)
- Seller subscription plans: Free / Pro / Business
- Featured product requests
- Marketplace advertising campaigns
- KOJA platform/service fee ledger
- Payment-fee ledger
- Seller earnings ledger
- Product reviews and ratings
- Multi-seller cart checkout foundation
- Delivery-job handoff table

ADDED KOJA BUSINESS
- Business accounts/workspaces
- POS/sales records
- Inventory and stock movements
- Accounting: sales, expenses, profit/loss
- Invoices and invoice items
- Customers / CRM
- Suppliers
- Employees and payroll
- Online-store settings connected to KOJA Market
- Business subscriptions
- Business AI usage/plans
- Business payment records
- Business delivery records

DEPLOYMENT
1. Keep the existing V52/Market V2 app.py as the application base.
2. Deploy the supplied app.py.
3. Run KOJA_MARKET_V3.sql in Supabase SQL Editor after the existing Market SQL.
4. Keep existing Render environment variables, including payment credentials.
5. KOJA Communications is not modified by this package.

IMPORTANT
The payment and subscription screens create commercial records, but a production billing flow must verify provider webhooks/transactions before marking paid or active. KOJA should use licensed payment providers and must not hold regulated customer funds without the required licensing/partners.
