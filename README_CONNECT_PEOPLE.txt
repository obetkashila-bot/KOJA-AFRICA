KOJA AFRICA - Connect People Upgrade
=====================================

Adds to the existing KOJA Connect / Find KOJA People page:
- Add from Contacts
- Add from Facebook (Facebook sharing/invitation flow; no private friend scraping)
- Invite Friends using the device share menu, WhatsApp or SMS fallback
- Phone-number matching against existing KOJA profiles
- Existing search, Connect, Message and Incoming Requests are preserved

No new Supabase table or SQL migration is required.

Deploy normally:
    gunicorn app:app

The contact matcher accepts up to 300 numbers per request and returns only
matched KOJA profile IDs/names. Phone numbers are not returned to the browser.
