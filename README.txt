KOJA SALES + CRM V2

Cumulative source: KOJA Supply Chain V2 + Finance V2 + Workforce V2 + Sales & CRM V2.

Deploy order:
1. Run KOJA_SALES_CRM_V2.sql in the existing KOJA Supabase SQL Editor.
2. Confirm SQL completes successfully.
3. Deploy app.py to the existing KOJA AFRICA Render production service.

V2 includes:
- Lead qualification and conversion to customer
- Customer 360 with pipeline and realized sales
- Opportunity pipeline with probability-weighted forecasting
- Quotations and sales orders
- Sales activities/follow-ups
- Sales targets
- Sales -> Finance V2 bridge when an order becomes paid/fulfilled/completed
- /api/sales/summary V2

Migration is additive/update-safe. It does not drop, truncate, recreate, or delete existing KOJA business tables.
Communications and other unrelated KOJA services are not intentionally modified.
