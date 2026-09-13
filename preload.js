const {contextBridge}=require('electron');
contextBridge.exposeInMainWorld('kojaDesktop',{platform:process.platform});
