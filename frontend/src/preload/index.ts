import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electron', {
  getBackendUrl: (): Promise<string> => ipcRenderer.invoke('get-backend-url'),

  // Auto-update
  onUpdateChecking:     (cb: () => void) =>              ipcRenderer.on('update:checking',     () => cb()),
  onUpdateAvailable:    (cb: (info: any) => void) =>     ipcRenderer.on('update:available',    (_, i) => cb(i)),
  onUpdateNotAvailable: (cb: () => void) =>              ipcRenderer.on('update:not-available', () => cb()),
  onUpdateProgress:     (cb: (p: any) => void) =>        ipcRenderer.on('update:progress',     (_, p) => cb(p)),
  onUpdateReady:        (cb: (info: any) => void) =>     ipcRenderer.on('update:ready',        (_, i) => cb(i)),
  onUpdateError:        (cb: (msg: string) => void) =>   ipcRenderer.on('update:error',        (_, m) => cb(m)),
  installUpdate:        (): Promise<void> =>             ipcRenderer.invoke('update:install'),
  checkUpdate:          (): Promise<void> =>             ipcRenderer.invoke('update:check'),
})
