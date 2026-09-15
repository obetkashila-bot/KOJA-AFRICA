KOJA AFRICA — SUPPLY CHAIN V2

This package contains the cumulative production app.py with Supply Chain V2 completion.

Key additions:
- Supply Chain V2 dashboard KPIs
- inventory search
- replenishment/reorder requests
- transfer approval and completion workflow
- stock movement to Finance V2 transaction bridge
- expanded supply-chain summary API
- additive SQL for reorder requests

Preserved: existing KOJA services and modules.

Deployment:
1. Replace production app.py with this app.py.
2. Run KOJA_SUPPLY_CHAIN_V2.sql in Supabase SQL Editor after the existing Supply Chain V1 and Finance V2 SQL.
3. Deploy normally with gunicorn app:app.
