KOJA IDENTITY & TRUST V2

Adds an additive Identity & Trust layer without replacing KOJA authentication.

Routes:
- /identity/v2
- /api/identity/v2/summary
- POST /api/identity/v2/verify
- POST /api/identity/v2/devices
- POST /api/identity/v2/audit

Security design:
- Raw identity document numbers are never stored; only SHA-256 hashes are stored.
- Verification remains pending until an authorized workflow verifies it.
- Trust score is a product signal, not legal KYC and not an identity decision.
- Existing KOJA services, Communications, authentication and payments are preserved.
