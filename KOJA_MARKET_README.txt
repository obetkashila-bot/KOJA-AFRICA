KOJA MARKET V1 — built on V52 foundation

Features
- Physical + digital marketplace
- Seller registration and admin approval
- Product listings with images, stock, SKU and location
- Buyer orders with recipient/delivery details
- Flutterwave checkout when FLW_SECRET_KEY is configured
- Server-side payment verification
- 10% marketplace commission calculation
- Seller sales and buyer purchase dashboard
- Admin seller/product approval and order management
- Existing V52 KOJA AI, Communications, Assignments, Research, Delivery and other services are preserved.

Deployment
1. Deploy app.py from this package.
2. Run KOJA_MARKET.sql in the same Supabase project.
3. Keep existing V52 environment variables.
4. If online checkout is desired, configure the existing FLW_SECRET_KEY.
5. Open /market.

Important
- Commission is an accounting calculation; actual seller settlement/payout and regulated payment activity should use a compliant payment arrangement.
- Do not delete the existing V52 database tables.
