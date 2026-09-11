KOJA AFRICA Unified Fulfillment V6

Includes V5 Complete plus AI nearby-driver selection and secure pickup-number verification.

Pickup verification:
- Driver enters the pickup number supplied by the seller/shop.
- KOJA checks the delivery, assigned driver, completion/cancellation state, and exact pickup code.
- Results: VALID, INVALID PICKUP NUMBER, WRONG DRIVER, NOT ASSIGNED, or ALREADY COMPLETED.
- Valid verification changes delivery status to in_transit and records pickup_verified_at.
- Buyer receives a pickup verification notification.

AI driver matching:
- Uses delivery GPS when available.
- Falls back to physical pickup address/area matching when GPS is unavailable.
- Only approved/active/verified online drivers with recent locations are considered.
- AI ranks candidates, but the server performs the final assignment.
- Driver assignment is conditional so a delivery cannot be claimed twice.

Communications/Connect+ remains untouched.
