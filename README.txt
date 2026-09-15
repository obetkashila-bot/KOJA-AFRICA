KOJA AFRICA — Workforce / HR V2

This package upgrades the existing Workforce V1 module in the cumulative production app.

Added:
- Workforce V2 dashboard and KPIs
- Candidate pipeline and stage updates
- Job status workflow
- Employee lifecycle status workflow
- Attendance tracking
- Leave approval/rejection workflow
- Payroll creation and mark-paid workflow
- Payroll -> Finance V2 transaction bridge when Finance V2 is installed
- Training cost -> Finance V2 bridge when available
- Performance reviews
- Workforce summary API V2
- Additive SQL migration only

Deploy:
1. Run KOJA_WORKFORCE_V2.sql in the Supabase SQL Editor.
2. Deploy app.py to the existing KOJA-AFRICA Render production service.

Existing KOJA services are preserved. Communications is untouched.
