KOJA FINANCE V2 -> PLATFORM FOUNDATIONS V2

This package connects the existing KOJA Finance V2 operating layer to the shared Platform Foundations V2 without replacing Finance workflows.

Connected Finance actions:
- Journal posting -> platform event + unified transaction context
- Payment recording -> platform event + unified transaction context
- Completed inbound payments -> revenue ledger context
- Bank reconciliation -> platform event
- Finance transaction register -> platform event + unified transaction context
- User and organization context are carried into foundation records
- Foundation transaction keys are deterministic for idempotent retry protection

Existing Finance V2 routes and records remain the source of truth.
Communications is intentionally untouched.
No table is dropped, truncated, or recreated.

Deployment order:
1. Apply KOJA_PLATFORM_FOUNDATIONS_V2.sql if it has not already been applied.
2. Apply KOJA_FINANCE_PLATFORM_FOUNDATION_V2.sql.
3. Deploy the included cumulative app.py to the existing KOJA-AFRICA Render Production service.
4. Test /health.
5. Log in and test /finance/v2.
6. Record a test Finance transaction or payment.
7. Confirm the Finance record remains present and the platform foundation receives the corresponding event/transaction.

The bridge is fail-soft: if the foundation tables are unavailable, the existing Finance operation is not intentionally blocked by the integration layer.
