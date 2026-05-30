import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { logsAPI } from '../lib/api'
import { useNotificationStore } from '../store'
import { downloadBlob } from '../lib/utils'
import { Download, RefreshCw, ChevronRight, ChevronDown, Loader, FileText } from 'lucide-react'
import { cn } from '../lib/utils'

interface LogEntry {
  id: number
  created_at: string
  user_id: number | null
  paso: number | null
  nivel: 'info' | 'warning' | 'error'
  evento: string
  mensaje: string
  contexto: any
  duracion_ms: number | null
}

const NIVEL_COLORS: Record<string, string> = {
  info: 'bg-blue-50 text-blue-700 border-blue-200',
  warning: 'bg-orange-50 text-orange-700 border-orange-200',
  error: 'bg-red-50 text-red-700 border-red-200',
}

function fmtTime(s: string) {
  try {
    const d = new Date(s)
    return d.toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'medium' })
  } catch {
    return s
  }
}

function LogRow({ log }: { log: LogEntry }) {
  const [open, setOpen] = React.useState(false)
  const hasContexto = log.contexto && Object.keys(log.contexto).length > 0

  return (
    <div className={cn('border rounded text-xs', NIVEL_COLORS[log.nivel] || 'bg-gray-50 border-gray-200')}>
      <button
        type="button"
        onClick={() => hasContexto && setOpen(!open)}
        className="w-full flex items-start gap-2 px-3 py-2 text-left"
      >
        {hasContexto ? (
          open ? <ChevronDown size={12} className="mt-0.5 flex-shrink-0" />
               : <ChevronRight size={12} className="mt-0.5 flex-shrink-0" />
        ) : <span className="w-3 inline-block flex-shrink-0" />}

        <span className="font-mono text-[10px] text-oag-muted flex-shrink-0">{fmtTime(log.created_at)}</span>
        <span className="font-semibold uppercase text-[10px] flex-shrink-0">{log.nivel}</span>
        {log.paso != null && (
          <span className="px-1 rounded bg-white/60 text-[10px] font-mono flex-shrink-0">P{log.paso}</span>
        )}
        <span className="font-mono text-[10px] flex-shrink-0">{log.evento}</span>
        {log.duracion_ms != null && (
          <span className="text-[10px] text-oag-muted flex-shrink-0">({log.duracion_ms}ms)</span>
        )}
        <span className="flex-1 truncate" title={log.mensaje}>{log.mensaje}</span>
      </button>
      {open && hasContexto && (
        <pre className="px-3 pb-2 text-[10px] font-mono whitespace-pre-wrap break-all bg-white/40 mx-2 mb-2 rounded p-2">
          {JSON.stringify(log.contexto, null, 2)}
        </pre>
      )}
    </div>
  )
}

export default function LogsPanel({ expedienteId }: { expedienteId: number }) {
  const { push } = useNotificationStore()
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['logs', expedienteId],
    queryFn: () => logsAPI.listar(expedienteId).then(r => r.data as LogEntry[]),
    refetchInterval: 10000, // auto-refresh para debugging en vivo
  })

  const handleDownload = async () => {
    try {
      const res = await logsAPI.descargar(expedienteId)
      downloadBlob(res.data, `OAG_log_exp${expedienteId}.txt`)
      push('success', 'Log descargado')
    } catch {
      push('error', 'No se pudo descargar el log')
    }
  }

  const logs = data || []

  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-oag-blue" />
          <h3 className="text-sm font-semibold text-oag-text">Logs de ejecución</h3>
          <span className="text-xs text-oag-muted">({logs.length} eventos)</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs px-2 py-1 rounded border border-oag-border text-oag-muted hover:text-oag-text hover:border-oag-text flex items-center gap-1"
          >
            <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
            Recargar
          </button>
          <button
            type="button"
            onClick={handleDownload}
            disabled={logs.length === 0}
            className="text-xs px-3 py-1 rounded bg-oag-blue text-white hover:bg-blue-800 disabled:opacity-50 flex items-center gap-1"
          >
            <Download size={12} />
            Descargar .txt
          </button>
        </div>
      </div>

      <p className="text-xs text-oag-muted">
        Registro de qué pasó en cada paso (auto-refresh cada 10s). Sirve para
        diagnosticar problemas sin necesitar acceso al servidor.
      </p>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader size={18} className="animate-spin text-oag-muted" />
        </div>
      )}

      {!isLoading && logs.length === 0 && (
        <p className="text-xs text-oag-muted text-center py-8">
          No hay eventos registrados para este expediente todavía.
        </p>
      )}

      {!isLoading && logs.length > 0 && (
        <div className="space-y-1 max-h-[60vh] overflow-y-auto">
          {logs.map(log => <LogRow key={log.id} log={log} />)}
        </div>
      )}
    </div>
  )
}
