KOJA V8 MARKET DELIVERY GPS V1

Adds the physical Shop -> Road -> Home delivery flow to the existing V8 Market.

Included:
- shop/seller GPS pickup coordinates
- customer GPS delivery coordinates
- physical address, landmark and phone fallback
- distance-based configurable delivery fee
- nearest online approved driver matching
- driver acceptance, pickup, road delivery and delivery confirmation
- live driver GPS updates on market delivery jobs
- customer/seller/driver delivery tracking
- ETA estimate from live GPS
- delivery OTP proof of delivery
- waiting-driver fallback when GPS/driver matching is unavailable

Render environment defaults:
KOJA_DELIVERY_BASE_FEE=15
KOJA_DELIVERY_PER_KM=3
KOJA_DELIVERY_MAX_RADIUS_KM=50

Important: runtime import was not tested in this container because Flask is not installed here. Python syntax compilation passed. Communications/WebRTC/FCM/LiveKit were not intentionally modified.
