KOJA ALL-PLATFORM V1 - MOBILE FOUNDATION

App ID: com.kojaafrica.app
App name: KOJA AFRICA
Backend: https://koja-africa.onrender.com

The Capacitor wrapper loads the existing production KOJA web application. It is designed so the same backend and account system are used on Android and iOS.

Included native capability foundations:
- Camera
- Geolocation
- Push notifications
- Filesystem
- External browser/payment return handling

Preparation:
1. Install Node.js/npm on the build machine.
2. Run: npm install
3. Run: npx cap add android
4. Run: npx cap add ios
5. Run: npx cap sync
6. Build/sign Android in Android Studio/Gradle.
7. Build/sign iOS in Xcode on macOS.

Do not add production certificates, keystores, APNs keys or store credentials to source control.
