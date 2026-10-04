KOJA AFRICA — TERMS GATE REMOVED / EMAIL LOGIN

Changes in this build:
- Removed the mandatory Terms acceptance redirect loop from authenticated navigation.
- /terms remains available as a normal legal page.
- Existing account registration still requires agreement to the Terms & Conditions.
- Existing email/password login remains the primary login flow.
- Removed Google/Facebook/GitHub social-login buttons and obsolete OAuth routes.
- Terms version updated to 2026-10-04-v2.
- Existing KOJA services and routes are otherwise preserved.

Render:
- Build command: pip install -r requirements.txt
- Start command: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --graceful-timeout 30 --keep-alive 5
- Keep existing environment variables, including SECRET_KEY/FLASK_SECRET_KEY and Supabase settings.

Deployment:
1. Replace app.py in the Render-connected KOJA-AFRICA repository.
2. Commit and push to the connected branch.
3. Deploy on Render.
4. Test /health, /login, /terms, /research, /services and /media-next.
