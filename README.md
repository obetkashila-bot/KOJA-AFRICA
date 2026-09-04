# KOJA AFRICA — Final Flask Package (2026-09-04)

This package is the final integrated KOJA AFRICA Flask application based on the latest KOJA build.

## Included
- Academic questions and complete assignment workflow
- Multi-source Research Engine + AI research summaries/notes + citation styles
- Documents and research resources
- Universal professional registration for all listed professions
- Administrator approval workflow before a professional becomes publicly discoverable
- Public approved professional directory
- Professional private chat/messages
- Voice and video calling using browser WebRTC signaling
- Live tutoring entry point using video sessions
- Professional bookings/appointments, advice and counselling requests
- Facebook-style KOJA Public feed with posts, images, likes and comments
- Optional GPS location attached to public posts
- KOJA Connect contacts, private chat, voice messages, voice/video calls and status
- Digital Marketplace with product listings, media, orders and Flutterwave integration when configured
- Driver registration, discovery, delivery requests and live GPS tracking
- Live delivery map, route, ETA, speed, heading and GPS freshness
- Google Search Console tools, robots.txt and sitemap.xml
- Mobile-friendly UI, themes and animations

## Deployment
1. Create/update the Supabase database by running `KOJA_FINAL_SCHEMA.sql` in Supabase SQL Editor.
2. Confirm the `koja-files` Storage bucket exists.
3. Push `app.py`, `requirements.txt`, `Procfile`, `render.yaml` and `.env.example` to GitHub.
4. In Render, set the production environment variables from `.env.example` (never commit secrets).
5. Deploy.

## Important external requirements
- Browser voice/video requires HTTPS and user microphone/camera permission.
- Live GPS requires HTTPS and user location permission.
- Real road routing uses OSRM through the KOJA server route endpoint.
- Flutterwave payments require `FLW_SECRET_KEY`.
- AI research summaries require `OPENAI_API_KEY` (or the supported AI key configuration already present in the app).
- Google Search Console API reporting requires the service-account setup described in the Admin area.

## Security
Do not put Supabase service-role keys, SMTP passwords, Flutterwave secrets, OpenAI keys or Google service-account JSON into browser JavaScript or public repositories.
