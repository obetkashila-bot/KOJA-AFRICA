KOJA AFRICA — REGISTERED ASSIGNMENT ANSWERS + PAID UNLOCKS

1. Replace the existing app.py with this app.py.
2. Run KOJA_ASSIGNMENT_ANSWER_PAYMENTS.sql in Supabase SQL Editor.
3. In Render Environment Variables, optionally set:
   KOJA_ASSIGNMENT_UNLOCK_PRICE=10
   The default is 10 ZMW.
4. FLW_SECRET_KEY and FLW_SECRET_HASH must already be configured for Flutterwave payments.
5. Supported Zambia mobile-money methods in this flow: MTN, AIRTEL and ZAMTEL.

Workflow:
- Registered users see unanswered assignments in Assignments.
- The first successful registered-user submission wins; the unique assignment_id constraint prevents a second answer.
- The answered assignment disappears from the answering pool for other registered users.
- The assignment owner sees "Unlock Registered Answer".
- Owner pays the configured unlock price through Flutterwave mobile money.
- KOJA verifies the payment server-side before revealing the answer.
- Admin can monitor all registered-user answers at /admin/assignments/community-answers.
