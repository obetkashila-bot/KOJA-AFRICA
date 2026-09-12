const { app, BrowserWindow, shell, session } = require('electron');

const KOJA_URL = 'https://koja-africa.onrender.com';

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 390,
    minHeight: 700,
    title: 'KOJA AFRICA',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(KOJA_URL)) return { action: 'allow' };
    shell.openExternal(url);
    return { action: 'deny' };
  });

  win.loadURL(KOJA_URL);
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    const allowed = ['notifications', 'media', 'geolocation'];
    callback(allowed.includes(permission));
  });
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
