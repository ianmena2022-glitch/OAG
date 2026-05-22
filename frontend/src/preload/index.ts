import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electron', {
  getBackendUrl: (): Promise<string> => ipcRenderer.invoke('get-backend-url'),
})
