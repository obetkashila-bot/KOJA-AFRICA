KOJA GLOBAL IMPORT & EXPORT V1

Added on top of the existing KOJA Global Business layer.

Features:
- Import/export trade orders
- Country of origin and destination
- HS/tariff classification field
- Landed-cost calculation
- Freight, insurance, duty, tax and destination fees
- Customs and clearance workflow
- Trade documents
- Customs broker/clearing-agent assignment
- Carrier/tracking/port/customs reference
- Workflow audit trail
- Country-specific customs rules table for future verified rules

Deploy:
1. Run KOJA_GLOBAL_IMPORT_EXPORT_V1.sql in the existing Supabase SQL editor.
2. Replace the existing app.py with the supplied app.py.
3. Keep the current Render service and environment variables.
4. Open a business Global Business page, then Global Import & Export.

This migration is additive: it does not drop or recreate existing KOJA tables.
