# KOJA AFRICA Teacher Profit Centre

## Included
- Teacher dashboard
- Standard hourly pricing update
- Paid live, online and in-person class creation
- Scheduled class marketplace and class booking
- Multi-lesson teaching packages
- Teacher availability calendar
- Earnings estimate from completed teacher appointments
- Configurable KOJA teacher commission via `KOJA_TEACHER_COMMISSION` (default 10%)

## Supabase setup
Run `teacher_profit_upgrade.sql` in the Supabase SQL Editor once. The existing app can then use the new class/package/availability features.

## Important payment note
The upgrade calculates class prices and estimated teacher earnings, but it does not claim that money has been transferred. A real payout requires a payment gateway/mobile-money integration and a verified payout workflow.
