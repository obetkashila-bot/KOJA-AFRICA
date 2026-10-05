KOJA MUSIC — WhatsApp Artist Recruitment Automation

BASELINE
The build starts from app(20261004-204639).py, the 1,111,014-byte production baseline, and adds the Artist Outreach automation layer without deleting the existing KOJA AFRICA / KOJA MUSIC services.

FILES
- app.py — complete replacement application file
- KOJA_MUSIC_WHATSAPP_AUTOMATION.sql — additive Supabase migration
- requirements.txt — production Python dependencies

NEW AUTOMATION
- Meta WhatsApp Cloud API configuration
- WhatsApp template sending
- Incoming webhook verification and message handling
- Delivery/read/status event recording
- Reply detection and follow-up cancellation
- YES/interested response detection
- Automatic onboarding-link response
- Artist onboarding form
- Rights review queue
- Campaign creation and admin approval
- Approved outreach queue
- Daily send limit
- Day 3 and Day 7 follow-up processing
- Protected worker endpoint for external cron
- Best-effort background worker with persisted Supabase state
- Outreach analytics/status endpoint

SUPABASE
Run KOJA_MUSIC_WHATSAPP_AUTOMATION.sql after the existing KOJA_MUSIC.sql / recruitment schema. The migration is additive and uses CREATE TABLE IF NOT EXISTS / ALTER TABLE ADD COLUMN IF NOT EXISTS.

RENDER ENVIRONMENT VARIABLES
Required for live WhatsApp sending:
WHATSAPP_PHONE_NUMBER_ID=Meta WhatsApp phone number ID
WHATSAPP_ACCESS_TOKEN=Meta permanent/system-user access token
WHATSAPP_VERIFY_TOKEN=your private webhook verification token

Recommended:
WHATSAPP_BUSINESS_ACCOUNT_ID=Meta WhatsApp Business Account ID
WHATSAPP_GRAPH_VERSION=v23.0 (change to the Graph API version supported by your Meta app)
KOJA_MUSIC_WHATSAPP_TEMPLATE=approved Meta template name
KOJA_MUSIC_WHATSAPP_TEMPLATE_LANG=en_US
KOJA_MUSIC_ONBOARDING_BASE=https://koja-africa.onrender.com
KOJA_MUSIC_OUTREACH_DAILY_LIMIT=50
KOJA_MUSIC_FOLLOWUP_BATCH=25
KOJA_MUSIC_WORKER_ENABLED=true
KOJA_MUSIC_WORKER_INTERVAL=300
KOJA_MUSIC_WORKER_SECRET=a-long-random-secret

If the approved template uses more than one body parameter, set:
KOJA_MUSIC_TEMPLATE_BODY_PARAMS_JSON=["{{artist_name}}","KOJA MUSIC"]
Use the exact parameter order defined by the approved Meta template.

WEBHOOK
Meta webhook callback URL:
https://koja-africa.onrender.com/webhooks/whatsapp
Use the same WHATSAPP_VERIFY_TOKEN in Meta and Render. Subscribe the WhatsApp webhook to messages.

EXTERNAL CRON OPTION
POST or GET:
https://koja-africa.onrender.com/api/music/outreach/worker?secret=YOUR_WORKER_SECRET
The endpoint processes the approved send queue and due follow-ups. Use the X-KOJA-MUSIC-WORKER-SECRET header when possible.

ADMIN
- /admin/music/outreach
- /admin/music/outreach/campaign/new
- /admin/music/onboarding
- /admin/music/rights

PUBLIC ONBOARDING
/music/onboarding/<token>

IMPORTANT RIGHTS RULE
Recruitment is not licensing. Artist onboarding and a YES response do not grant KOJA permission to reproduce, stream, distribute, monetize or publish recordings. Rights review must be completed before publication.

BUILD CHECK
python -m py_compile app.py
