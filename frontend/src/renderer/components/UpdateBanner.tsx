import React, { useEffect, useState } from 'react'
import { Download, RefreshCw, CheckCircle, X } from 'lucide-react'
import { cn } from '../lib/utils'

type UpdateState =
  | { status: 'idle' }
  | { status: 'available'; version: string }
  | { status: 'downloading'; percent: number; bytesPerSecond: number }
  | { status: 'ready'; version: string }
  | { status: 'error'; message: string }

export default function UpdateBanner() {
  const [state, setState] = useState<UpdateState>({ status: 'idle' })
  const [dismissed, setDismissed] = useState(false)
  const [installing, setInstalling] = useState(false)

  useEffect(() => {
    const el = (window as any).electron
    if (!el) return

    el.onUpdateAvailable?.((info: any) => {
      setState({ status: 'available', version: info.version })
      setDismissed(false)
    })

    el.onUpdateProgress?.((p: any) => {
      setState({ status: 'downloading', percent: p.percent, bytesPerSecond: p.bytesPerSecond })
      setDismissed(false)
    })

    el.onUpdateReady?.((info: any) => {
      setState({ status: 'ready', version: info.version })
      setDismissed(false)
    })

    el.onUpdateError?.((msg: string) => {
      setState({ status: 'error', message: msg })
    })
  }, [])

  const handleInstall = async () => {
    setInstalling(true)
    await (window as any).electron?.installUpdate?.()
  }

  if (state.status === 'idle' || dismissed) return null

  return (
    <div className={cn(
      'fixed bottom-4 right-4 z-50 w-80 rounded-lg shadow-xl border text-sm',
      state.status === 'ready'    && 'bg-white border-oag-blue',
      state.status === 'available'&& 'bg-white border-oag-border',
      state.status === 'downloading' && 'bg-white border-oag-border',
      state.status === 'error'    && 'bg-red-50 border-red-200',
    )}>
      {/* Header */}
      <div className={cn(
        'flex items-center justify-between px-4 py-2.5 rounded-t-lg',
        state.status === 'ready'       && 'bg-oag-blue text-white',
        state.status === 'available'   && 'bg-oag-dark text-white',
        state.status === 'downloading' && 'bg-oag-dark text-white',
        state.status === 'error'       && 'bg-red-600 text-white',
      )}>
        <div className="flex items-center gap-2 font-semibold">
          {state.status === 'ready'       && <CheckCircle size={14} />}
          {state.status === 'available'   && <Download size={14} />}
          {state.status === 'downloading' && <Download size={14} />}
          {state.status === 'error'       && <X size={14} />}
          <span>
            {state.status === 'ready'       && 'Actualización lista'}
            {state.status === 'available'   && 'Actualización disponible'}
            {state.status === 'downloading' && 'Descargando actualización…'}
            {state.status === 'error'       && 'Error de actualización'}
          </span>
        </div>
        {state.status !== 'downloading' && (
          <button onClick={() => setDismissed(true)} className="opacity-70 hover:opacity-100">
            <X size={13} />
          </button>
        )}
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-3">
        {state.status === 'available' && (
          <>
            <p className="text-oag-muted text-xs">
              La versión <span className="font-semibold text-oag-text">{state.version}</span> está
              disponible. Se descargará en segundo plano automáticamente.
            </p>
          </>
        )}

        {state.status === 'downloading' && (
          <>
            <p className="text-oag-muted text-xs">
              {state.percent}% — {(state.bytesPerSecond / 1024 / 1024).toFixed(1)} MB/s
            </p>
            <div className="w-full bg-oag-border rounded-full h-1.5">
              <div
                className="bg-oag-blue h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${state.percent}%` }}
              />
            </div>
          </>
        )}

        {state.status === 'ready' && (
          <>
            <p className="text-oag-muted text-xs">
              La versión <span className="font-semibold text-oag-text">{state.version}</span> está
              descargada. Cerrá y reabrí la app para aplicar la actualización.
            </p>
            <button
              onClick={handleInstall}
              disabled={installing}
              className="w-full flex items-center justify-center gap-2 bg-oag-blue text-white
                         text-xs font-semibold py-2 rounded-md hover:bg-blue-800 transition-colors
                         disabled:opacity-60"
            >
              <RefreshCw size={13} className={installing ? 'animate-spin' : ''} />
              {installing ? 'Reiniciando…' : 'Reiniciar e instalar ahora'}
            </button>
          </>
        )}

        {state.status === 'error' && (
          <div className="space-y-2">
            <p className="text-red-700 text-xs">
              No se pudo verificar la actualización.
            </p>
            {state.message && (
              <p className="text-red-900 text-[10px] font-mono break-all bg-red-100 rounded px-2 py-1">
                {state.message}
              </p>
            )}
            <button
              onClick={async () => {
                setState({ status: 'idle' })
                await (window as any).electron?.checkUpdate?.()
              }}
              className="w-full flex items-center justify-center gap-2 bg-red-600 text-white
                         text-xs font-semibold py-1.5 rounded-md hover:bg-red-700 transition-colors"
            >
              <RefreshCw size={12} />
              Reintentar
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
