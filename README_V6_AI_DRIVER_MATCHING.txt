KOJA AFRICA — V6 AI DRIVER MATCHING

Adds AI-assisted nearby-driver matching to Unified Fulfillment V5.

FLOW
1. Delivery is registered and tracking code is generated.
2. Buyer can capture GPS or provide/use the physical pickup address.
3. KOJA checks trusted, approved, online drivers.
4. If GPS exists, KOJA calculates real distance from pickup to driver.
5. If GPS is unavailable, KOJA uses physical pickup-address/area matching against available driver profile location data.
6. KOJA AI ranks the candidate drivers using the supplied facts only.
7. Buyer sees the recommended driver and can choose one.
8. Assignment is conditional: if another driver was selected first, KOJA rejects the second claim.
9. Selected driver receives a notification.
10. Existing pickup-number verification, delivery tracking, buyer confirmation and payout flow remain in place.

AI DOES NOT INVENT GPS OR DISTANCES.
When no GPS is available, the UI explicitly identifies physical-address matching.

No Supabase schema migration is required for this V6 change; it uses existing delivery pickup coordinates and driver_locations.
Communications/Connect+ is untouched.
