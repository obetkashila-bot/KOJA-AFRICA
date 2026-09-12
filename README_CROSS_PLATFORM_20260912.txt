KOJA AFRICA — CROSS-PLATFORM APP PACKAGE

This package adds the platform packaging foundation to the KOJA PWA.

ANDROID / IOS
Uses Capacitor with the existing production KOJA web application.
App ID: com.kojaafrica.app
Production URL: https://koja-africa.onrender.com

Commands after installing Node.js:
npm install
npx cap add android
npx cap add ios
npx cap sync
npx cap open android
npx cap open ios

Android release requires Android signing and Google Play Console submission.
iOS release requires Apple Developer signing and App Store Connect submission.

WINDOWS / MACOS / LINUX
Uses Electron + electron-builder.

npm install
npm run desktop
npm run desktop:build

The build configuration targets:
Windows: NSIS installer
macOS: DMG
Linux: AppImage and DEB

IMPORTANT
The desktop and mobile shells load the existing production KOJA service. They do not replace Render, Supabase, Flutterwave, LiveKit, or the existing KOJA backend.

Before store submission, configure production signing certificates, privacy policy URLs, support URLs, store screenshots, icons, permissions disclosures, and platform-specific push notification credentials.
