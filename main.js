const {app,BrowserWindow,session,shell} = require('electron');
const path=require('path');
const URL='https://koja-africa.onrender.com/';
function create(){
  const w=new BrowserWindow({width:1440,height:900,minWidth:1024,minHeight:700,backgroundColor:'#0b1220',webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false}});
  w.loadURL(URL);
  w.webContents.setWindowOpenHandler(({url})=>{ if(url.startsWith('https://koja-africa.onrender.com/')) return {action:'allow'}; shell.openExternal(url); return {action:'deny'}; });
}
app.whenReady().then(()=>{session.defaultSession.setPermissionRequestHandler((_webContents,permission,callback)=>{callback(['geolocation','media'].includes(permission));});create();app.on('activate',()=>{if(BrowserWindow.getAllWindows().length===0)create();});});
app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit();});
