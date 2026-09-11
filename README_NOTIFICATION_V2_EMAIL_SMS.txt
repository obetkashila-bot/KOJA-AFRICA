KOJA Notification Center V2 - Email + SMS

Channels:
- In-app notification center
- Browser/phone push
- Email
- SMS

Email Render environment variables:
SMTP_HOST
SMTP_PORT=587
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM
SMTP_TLS=true
APP_BASE_URL=https://koja-africa.onrender.com

SMS option A - Africa's Talking:
AT_USERNAME
AT_API_KEY
AT_SENDER_ID (optional, if approved)

SMS option B - Twilio:
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_FROM_NUMBER

The user can enable/disable Email and SMS independently in Notification Settings. The notification is still saved in KOJA if an external email/SMS provider is unavailable or fails.

Run KOJA_NOTIFICATION_EMAIL_SMS.sql in Supabase before deploying the package.
