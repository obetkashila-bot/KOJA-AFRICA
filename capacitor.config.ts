import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.kojaafrica.app',
  appName: 'KOJA AFRICA',
  webDir: 'static',
  server: {
    url: 'https://koja-africa.onrender.com',
    cleartext: false
  }
};

export default config;
