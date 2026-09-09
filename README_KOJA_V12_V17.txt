KOJA AFRICA V12-V17 ENGINE SUITE

V12 Search & Discovery
V13 Ads Network
V14 Pay Infrastructure
V15 Cloud & Developer
V16 Data & Intelligence
V17 Identity & Trust

Built additively on the V11 master. Existing Market, Business/POS, Delivery, AI and other services are preserved. Communications is intentionally untouched.

Deployment:
1. Replace Render app.py with this package app.py.
2. Keep gunicorn app:app.
3. Run KOJA_V12_V17_ENGINE_SUITE.sql in Supabase SQL Editor.
4. Set/retain existing environment variables.

New pages: /v12/search, /v13/ads, /v14/pay, /v15/cloud, /v16/intelligence, /v17/identity.
Admin: /admin/v12-v17.
