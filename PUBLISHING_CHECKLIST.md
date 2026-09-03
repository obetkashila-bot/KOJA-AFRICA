# KOJA AFRICA — Publishing Checklist

## Render
- Runtime: Python 3
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
- Set `SECRET_KEY` to a long random value.
- Set the Supabase and site environment variables from `.env.example`.
- Redeploy after changing environment variables.

## Supabase
- Confirm required KOJA tables exist.
- Confirm `koja-files` Storage bucket exists (or change `SUPABASE_STORAGE_BUCKET`).
- Confirm the service-role key is used only as a Render secret and is never exposed to browser JavaScript.
- Confirm database/storage policies match the application's authorization model.

## Security fixes included in this release
- Global CSRF protection for POST/PUT/PATCH/DELETE requests.
- Browser forms automatically receive the CSRF token.
- Browser fetch requests automatically send `X-CSRF-Token` for state-changing requests.
- Secure, HttpOnly, SameSite=Lax session cookies.
- Production secret is read from `SECRET_KEY` / `FLASK_SECRET_KEY`.

## Google / SEO fixes included
- Google Search Console verification meta tag retained.
- Public sitemap restricted to `/` and `/research`.
- Private/account/GPS/API paths excluded from robots crawling.
- Canonical URLs retained.
- Google Search Console API dependency `google-auth` included.

## Product cleanup included
- University and Farmer public pages/routes removed.
- University/Farmer links removed from home, dashboard, and services.
- Admin counts no longer depend on the retired University/Farmer modules.
- Documents & Research is promoted in the services area through the Research Engine.

## Final live tests after deployment
1. Open `/health` and confirm HTTP 200.
2. Open `/robots.txt` and `/sitemap.xml`.
3. Register a test account.
4. Log in and log out.
5. Save Settings and reset Settings.
6. Submit a question.
7. Upload an assignment.
8. Test professional-service booking.
9. Register a driver.
10. Start driver GPS sharing and verify the live map.
11. Create a delivery and test customer tracking.
12. Test admin access and live GPS monitoring.
13. Test file uploads against the Supabase Storage bucket.
14. In Google Search Console, inspect `/` and submit the sitemap.
15. Check Render logs after each major test for 4xx/5xx errors.
