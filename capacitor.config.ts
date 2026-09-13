import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.kojaafrica.app',
  appName: 'KOJA AFRICA',
  webDir: 'www',
  server: {
    url: 'https://koja-africa.onrender.com',
    cleartext: false,
    androidScheme: 'https'
  }
};

export default config;
