KOJA AFRICA — Connect+ / People Upgrade

This build upgrades the existing Find KOJA People page without replacing the existing Connect+ messaging, calls, groups or status system.

Included:
- Personal KOJA profiles with View Profile and Share Profile.
- Search by name, username or email.
- People You May Know suggestions.
- My Connections section.
- Incoming connection requests with profile preview.
- Add from Contacts using the browser/device Contacts Picker when supported.
- Server-side phone matching without importing an entire contact list.
- Facebook invite/share without importing a private Facebook friend list.
- Invite Friends through device share, with WhatsApp fallback.
- Direct Message, Voice Call and Video Call from connected personal profiles.

No separate database migration is required for the core upgrade because it uses the existing profiles and koja_contacts tables. Optional profile fields are read only when already present.

Deploy this app.py in the existing KOJA AFRICA Render service. Keep the existing environment variables and existing Supabase configuration.
