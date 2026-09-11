KOJA AFRICA — UNIFIED FULFILLMENT V3

Adds one fulfillment model across KOJA Market and KOJA Business Online Store.

PHYSICAL:
- Buyer chooses KOJA Delivery or Self Pickup.
- KOJA Delivery creates a delivery job with pickup code and buyer destination.
- Drivers see only unclaimed jobs at /driver/available-deliveries.
- Driver acceptance is an atomic requested->accepted claim. Once claimed, the job disappears from every other driver's available list while the database history remains.
- Driver enters the pickup code at the seller/business.
- Buyer confirms receipt; existing KOJA payout workflow can then release the driver payout when live Flutterwave payout settings are configured.

DIGITAL:
- Digital products do not offer delivery. They use digital fulfillment.

BUSINESS ONLINE STORE:
- Business products now have physical/digital type, delivery availability and delivery fee.
- Public store products have Buy checkout.
- Flutterwave Zambia mobile-money checkout creates a business order.
- Paid physical delivery orders enter the same deliveries + market delivery job workflow.

SQL is additive/idempotent. Run KOJA_UNIFIED_FULFILLMENT_V3.sql in Supabase SQL Editor before deployment.

Communications/Connect+ is not modified by this package.
