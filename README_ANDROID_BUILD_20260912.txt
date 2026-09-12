KOJA AFRICA ANDROID BUILD

This package adds a GitHub Actions pipeline for the existing KOJA AFRICA Capacitor app.

Repository setup:
1. Upload the package contents to the existing KOJA-AFRICA GitHub repository.
2. Commit and push to main or master.
3. Open GitHub Actions.
4. Run "KOJA AFRICA Android Build".
5. Download the generated "koja-africa-debug-apk" artifact for direct Android installation.

Google Play release:
Configure these GitHub Actions repository secrets before expecting a signed AAB:
KOJA_KEYSTORE_BASE64
KOJA_KEYSTORE_PASSWORD
KOJA_KEY_ALIAS
KOJA_KEY_PASSWORD

Never commit the keystore or passwords into the repository.

The app ID remains com.kojaafrica.app and the production backend remains:
https://koja-africa.onrender.com

This workflow does not move, replace, or modify the existing Render Production service.
