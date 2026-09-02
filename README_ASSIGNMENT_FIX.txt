KOJA AFRICA - FINAL ASSIGNMENT FIX
Date: 2026-09-03

Fixes:
1. Defines log_activity() before any route can call it.
2. Defines create_notification() before the assignment route can call it.
3. Assignment submission uses profiles.id for student_id/user_id.
4. Assignment status uses submitted.
5. Assignment upload/database failures are handled without a 500 caused by missing helpers.

Deploy app.py and requirements.txt to the Render service.
