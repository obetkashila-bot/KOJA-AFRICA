KOJA AFRICA - Notification Settings + Test Button Fix

1. Run KOJA_PRODUCTION_PATCH_20260912.sql in Supabase SQL Editor.
   This is additive/idempotent and includes the notification preferences table and columns.
2. Deploy app.py, requirements.txt and Procfile to the existing KOJA-AFRICA Render Production service.
3. Log in -> Notification Settings.
4. Save settings.
5. Enable phone/browser notifications.
6. Tap Send Test Notification.

Communications module is not modified.
