const { contextBridge, ipcRenderer } = require('electron')
// 每个操作单独声明；不暴露任意 IPC、网络、路径或进程执行能力。
contextBridge.exposeInMainWorld('mycollabDesktop', Object.freeze({
  settings: () => ipcRenderer.invoke('desktop:settings'),
  setServer: (server) => ipcRenderer.invoke('desktop:set-server', server),
  setLocalNetwork: (enabled) => ipcRenderer.invoke('desktop:set-local-network', enabled),
  setAutostart: (enabled) => ipcRenderer.invoke('desktop:set-autostart', enabled),
  openExternal: (url) => ipcRenderer.invoke('desktop:external', url),
  downloadLibrary: (url) => ipcRenderer.invoke('desktop:download-library', url),
}))
