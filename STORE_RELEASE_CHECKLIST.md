# KOJA AFRICA — Store Release Checklist

## Android
1. Run `npm install`.
2. Run `npx cap add android`.
3. Run `npx cap sync android`.
4. Open Android Studio with `npx cap open android`.
5. Set the release signing key.
6. Verify package ID `com.kojaafrica.app`.
7. Build a signed `.aab`.
8. Upload the AAB to Google Play Console.

## iOS
1. Run `npm install`.
2. Run `npx cap add ios`.
3. Run `npx cap sync ios`.
4. Open Xcode with `npx cap open ios`.
5. Select the Apple Developer team and signing certificate.
6. Verify bundle ID `com.kojaafrica.app`.
7. Archive and upload through Xcode/App Store Connect.

## Windows/macOS/Linux
Run `npm run desktop:build`.
Targets are NSIS, DMG, AppImage and DEB.

## Before publishing
- Privacy policy URL
- Terms URL
- Support URL
- Store screenshots
- App icon set
- App description
- Permission disclosures
- Push notification credentials
- Camera/microphone/location permission descriptions
- Production payment verification
- Deep-link testing
