# KOJA AFRICA — Environment Variable Checklist

Start command: `gunicorn app:app --workers 2 --threads 4 --timeout 300`
(Background threads for Africa Now / AI approval run per worker.)

## 1. REQUIRED (app will not boot or core features fail)
| Variable | Purpose |
|---|---|
| SECRET_KEY (or FLASK_SECRET_KEY) | Flask sessions. App raises RuntimeError without it |
| SITE_URL | Public base URL (e.g. https://koja-africa.onrender.com) |
| SUPABASE_URL | Supabase project URL |
| SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_KEY / SUPABASE_KEY) | Server-side DB + Storage |
| SUPABASE_PUBLISHABLE_KEY / SUPABASE_ANON_KEY | Browser-side auth / OAuth bridge |

## 2. PAYMENTS (Market, Business, Profit engine)
FLW_SECRET_KEY, FLW_SECRET_HASH (webhook), KOJA_FLW_ZM_MOMO_BANK_CODE,
KOJA_PLATFORM_FEE_RATE, KOJA_PROFIT_FEE_RATE, KOJA_B2B_COMMISSION_RATE,
KOJA_DRIVER_AUTO_PAYOUT, KOJA_AI_CREDIT_PRICE

## 3. AI
GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL, GEMINI_API_URL
GROQ_API_KEY, GROQ_MODEL
OPENAI_API_KEY, OPENAI_MODEL
KOJA_AI_AUTO_APPROVAL, KOJA_AI_AUTO_APPROVAL_THRESHOLD
(Set at least one provider key.)

## 4. EMAIL (set ONE provider)
EMAIL_PROVIDER + RESEND_API_KEY | SENDGRID_API_KEY | SMTP_HOST, SMTP_PORT,
SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS

## 5. SMS / WHATSAPP
AT_API_KEY, AT_USERNAME, AT_SENDER_ID (Africa's Talking)
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

## 6. LIVE VIDEO / CALLS
LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
TURN_URL (or KOJA_TURN_URL), TURN_USERNAME, TURN_CREDENTIAL
(Without TURN, calls fail behind strict NATs / mobile carriers.)

## 7. PUSH NOTIFICATIONS
VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIMS_EMAIL
FCM_RELAY_URL / FCM_RELAY_ENDPOINT / KOJA_FCM_RELAY_URL / PUSH_RELAY_URL, FCM_RELAY_SECRET

## 8. SOCIAL LOGIN (optional)
GOOGLE_CLIENT_ID/SECRET, FACEBOOK_CLIENT_ID/SECRET, GITHUB_CLIENT_ID/SECRET

## 9. SEARCH / SEO / DATA (optional)
GOOGLE_SEARCH_API_KEY, GOOGLE_CSE_ID, GSC_SERVICE_ACCOUNT_JSON, GSC_SITE_URL,
RESEARCH_EMAIL, ALPHAVANTAGE_API_KEY, TWELVEDATA_API_KEY,
EXCHANGE_RATE_API_KEY, FX_API_URL

## 10. TUNING (all have defaults)
KOJA_MUSIC_MAX_MB (default 100: max size per music video/audio upload),
SESSION_COOKIE_SECURE (default true), PORT, KOJA_APP_VERSION, KOJA_CLOUD_API_URL,
KOJA_HLS_BUCKET, KOJA_HLS_CDN_BASE, KOJA_HLS_PUBLIC_BASE,
KOJA_MARKET_CACHE_TTL, KOJA_MARKET_SYMBOLS, KOJA_MARKET_TIMEOUT,
KOJA_NEXUS_SERVICES_CACHE_TTL, KOJA_NEXUS_AFRICA_NOW_ENABLED / _INTERVAL /
_TIMEOUT / _ROTATE_SECONDS / _REGISTRY_BATCH / _EMERGENCY_TTL

## KOJA NEWS LIVE (Cloudflare Stream)
| Variable | Purpose |
|---|---|
| CF_ACCOUNT_ID | Cloudflare account ID |
| CF_STREAM_API_TOKEN | API token with **Stream: Edit** permission |
| CF_STREAM_CUSTOMER_CODE | The `xxxx` in `customer-xxxx.cloudflarestream.com` (Stream dashboard) |
| KOJA_NEWS_LL_HLS | `true` to use Cloudflare's beta Low-Latency HLS (default false) |
| KOJA_NEWS_RECORD | `true` (default) saves a replay of every broadcast |

Setup: (1) run `koja_news_live_schema.sql`; (2) set the three CF variables;
(3) open `/admin/news/live` and press **Create live input**; (4) copy the RTMPS
URL + key into OBS (Settings > Stream > Custom) or the SRT details into a hardware
or mobile encoder; (5) wait for **Encoder: connected**, then press **Go Live**.
No Cloudflare? Paste any HTTPS HLS URL into the studio's "Manual HLS URL" field.

## Consent policy (all KOJA services)
Terms & Conditions and the Privacy Policy are accepted once, at account creation (registration
checkbox; for Google/Facebook sign-ups, the first sign-in). That acceptance applies to every KOJA
service: services never re-ask and never block access over consent. A newer `TERMS_VERSION` is
recorded on new acceptances for the audit trail but does not force existing users to re-accept.
Accounts with no acceptance on record at all are asked once at sign-in, never inside a service.

## KOJA BUSINESS HUB (no new environment variables)
1. Run `koja_business_hub_schema.sql` in the Supabase SQL editor (safe to re-run; it also
   adds optional columns to `koja_business_sales` / `koja_business_sale_items` if they exist).
2. Open `/admin/production-health-v2` and confirm the new `koja_business_*` and
   `koja_connectplus_*` tables show READY.
3. Logos upload to the public `koja-files` bucket (same bucket as KOJA MUSIC).
4. Moderation: `/admin/business-hub` (approve investors and funding requests, suspend profiles).
5. Approving a business in `/admin/business-verification-v2` is what shows the "Verified" badge
   in the directory, on company pages and in the funding-request review screen.

## KOJA MUSIC setup (3 steps)
1. Run `koja_music_schema.sql` in the Supabase SQL editor (tables + public `koja-files` bucket).
2. Supabase free plan caps a single file at 50 MB. Raise it in Storage settings
   or keep KOJA_MUSIC_MAX_MB at 50 or less.
3. Use gunicorn `--timeout 300` (large uploads) and at least 1 GB RAM:
   uploads are buffered in memory before being sent to Supabase.

## Database (not in app.py)
~150 Supabase tables are referenced; only ~30 have embedded `create table`
SQL. The `koja_core_*`, `koja_business_*`, `koja_global_trade_*` families
need migrations from your Supabase project (export with `supabase db dump`).
