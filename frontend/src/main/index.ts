import { app, shell, BrowserWindow, ipcMain } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { autoUpdater } from 'electron-updater'

function createWindow(): void {
  const mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    backgroundColor: '#F5F6F8',
    titleBarStyle: 'default',
    autoHideMenuBar: true,
    icon: join(__dirname, '../../resources/icon.ico'),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
    },
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
    mainWindow.setTitle('OGSA — Sistema de Auditorías Comerciales')
  })

  // F12 abre DevTools (útil para debug)
  mainWindow.webContents.on('before-input-event', (_, input) => {
    if (input.key === 'F12') {
      mainWindow.webContents.toggleDevTools()
    }
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// ── Auto-updater ─────────────────────────────────────────────────────────────
function setupAutoUpdater(win: BrowserWindow) {
  // No molestar en desarrollo
  if (is.dev) return

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true

  autoUpdater.on('checking-for-update', () => {
    win.webContents.send('update:checking')
  })

  autoUpdater.on('update-available', (info) => {
    win.webContents.send('update:available', {
      version: info.version,
      releaseDate: info.releaseDate,
    })
  })

  autoUpdater.on('update-not-available', () => {
    win.webContents.send('update:not-available')
  })

  autoUpdater.on('download-progress', (progress) => {
    win.webContents.send('update:progress', {
      percent: Math.round(progress.percent),
      transferred: progress.transferred,
      total: progress.total,
      bytesPerSecond: progress.bytesPerSecond,
    })
  })

  autoUpdater.on('update-downloaded', (info) => {
    win.webContents.send('update:ready', { version: info.version })
  })

  autoUpdater.on('error', (err) => {
    win.webContents.send('update:error', err.message)
  })

  // Verificar al arrancar (5 seg de delay para que cargue la UI)
  setTimeout(() => autoUpdater.checkForUpdates(), 5000)

  // Re-verificar cada 4 horas
  setInterval(() => autoUpdater.checkForUpdates(), 4 * 60 * 60 * 1000)
}

// IPC: el renderer pide instalar la actualización ahora
ipcMain.handle('update:install', () => {
  autoUpdater.quitAndInstall()
})

app.whenReady().then(() => {
  electronApp.setAppUserModelId('com.ogsa.auditoria')

  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  createWindow()
  const win = BrowserWindow.getAllWindows()[0]
  if (win) setupAutoUpdater(win)

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// IPC: obtener URL del backend
ipcMain.handle('get-backend-url', () => {
  return process.env['BACKEND_URL'] || 'https://oag.up.railway.app'
})
