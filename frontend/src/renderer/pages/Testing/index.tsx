import React, { useState, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Play, Square, Star, StarOff, CheckCircle, XCircle,
  AlertTriangle, Loader, ChevronDown, ChevronRight,
  RefreshCw, Minus, TrendingUp, TrendingDown,
} from 'lucide-react'
import { expedientesAPI, pasosAPI } from '../../lib/api'
import { cn } from '../../lib/utils'

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface PasoMetrics {
  paso: number
  [key: string]: number | string | any[] | null
}

interface PasoResult {
  paso: number
  status: 'idle' | 'running' | 'ok' | 'error'
  error?: string
  metrics?: PasoMetrics
  elapsed?: number
}

interface ExpResult {
  expId: number
  nombre: string
  pasos: Record<number, PasoResult>
}

type RunState = 'idle' | 'running' | 'done'

// ─── Extracción de métricas ───────────────────────────────────────────────────
// Espeja la lógica de tests/ogsa_test.py::extract_metrics()

function extractMetrics(paso: number, data: any): PasoMetrics {
  const m: PasoMetrics = { paso }

  if (paso === 1) {
    const r = data.resumen || {}
    m.total_arca        = r.total_arca ?? 0
    m.total_gestion     = r.total_gestion ?? 0
    m.solo_arca         = r.solo_arca ?? 0
    m.solo_gestion      = r.solo_gestion ?? 0
    m.internos          = r.internos ?? 0
    m.con_diferencia    = r.con_diferencia ?? 0
    m.monto_arca_usd    = Math.round(r.monto_total_arca_usd ?? 0)
    m.monto_gestion_usd = Math.round(r.monto_total_gestion_usd ?? 0)
  } else if (paso === 2) {
    const t = data.totales || {}
    m.total_facturado_usd = Math.round(t.total_facturado_usd ?? 0)
    m.total_syngenta_usd  = Math.round(t.total_syngenta_usd ?? 0)
    m.total_agro_usd      = Math.round(t.total_agroquimicos_usd ?? 0)
  } else if (paso === 3) {
    const r = data.resumen || {}
    m.total        = r.total ?? 0
    m.ok_cruzado   = r.ok ?? 0
    m.solo_crm     = r.solo_crm ?? 0
    m.solo_gestion = r.solo_gestion ?? 0
    m.monto_g_usd  = Math.round(r.monto_gestion_total_usd ?? 0)
    m.monto_crm_usd= Math.round(r.monto_crm_total_usd ?? 0)
  } else if (paso === 4) {
    const t = data.totales || {}
    m.total_compras_usd  = Math.round(t.total_compras_usd ?? 0)
    m.proveedores_count  = (data.resumen_top20 || []).length
  } else if (paso === 5) {
    const t = data.totales || {}
    m.total_ventas_usd  = Math.round(t.total_ventas_usd ?? 0)
    m.total_compras_usd = Math.round(t.total_compras_usd ?? 0)
  }

  // Alertas de validación
  const alertas: any[] = data.validacion?.alertas ?? []
  m._errores  = alertas.filter((a: any) => a.nivel === 'error').length
  m._warnings = alertas.filter((a: any) => a.nivel === 'warning').length
  m._alertas  = alertas.slice(0, 5)

  return m
}

// ─── Tolerancias para diff ────────────────────────────────────────────────────

const TOLERANCIAS: Record<string, number> = {
  '1_solo_gestion':       0.00,
  '1_solo_arca':          0.00,
  '1_monto_arca_usd':     0.02,
  '1_monto_gestion_usd':  0.02,
  '1_total_arca':         0.00,
  '1_total_gestion':      0.02,
  '2_total_syngenta_usd': 0.05,
  '2_total_facturado_usd':0.05,
  '3_solo_crm':           0.00,
  '3_solo_gestion':       0.00,
  '3_monto_g_usd':        0.05,
  '4_total_compras_usd':  0.05,
}
const DEFAULT_TOL = 0.10

function getDiffLevel(paso: number, key: string, cur: number, gld: number): 'ok' | 'warning' | 'error' {
  const tol = TOLERANCIAS[`${paso}_${key}`] ?? DEFAULT_TOL
  if (gld === 0) return cur === 0 ? 'ok' : 'error'
  const ratio = Math.abs(cur - gld) / Math.abs(gld)
  if (ratio <= tol) return 'ok'
  return ratio > tol * 3 ? 'error' : 'warning'
}

// ─── Golden (localStorage) ────────────────────────────────────────────────────

const GOLDEN_PREFIX = 'ogsa_golden_'

function loadGolden(expId: number): Record<string, PasoMetrics> | null {
  try {
    const raw = localStorage.getItem(`${GOLDEN_PREFIX}${expId}`)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function saveGolden(expId: number, pasoMetrics: Record<number, PasoResult>) {
  const data: Record<string, PasoMetrics> = {}
  for (const [paso, r] of Object.entries(pasoMetrics)) {
    if (r.metrics) data[paso] = r.metrics
  }
  localStorage.setItem(`${GOLDEN_PREFIX}${expId}`, JSON.stringify({
    savedAt: new Date().toISOString(),
    pasos: data,
  }))
}

function clearGolden(expId: number) {
  localStorage.removeItem(`${GOLDEN_PREFIX}${expId}`)
}

function hasGolden(expId: number): boolean {
  return !!localStorage.getItem(`${GOLDEN_PREFIX}${expId}`)
}

// ─── Helpers de formato ───────────────────────────────────────────────────────

function fmtVal(key: string, val: number): string {
  if (key.endsWith('_usd') && Math.abs(val) > 999) {
    return `US$ ${val.toLocaleString('es-AR', { maximumFractionDigits: 0 })}`
  }
  return String(val)
}

// ─── Sub-componentes ──────────────────────────────────────────────────────────

const METRICAS_POR_PASO: Record<number, string[]> = {
  1: ['total_arca', 'total_gestion', 'solo_arca', 'solo_gestion', 'internos', 'con_diferencia', 'monto_arca_usd', 'monto_gestion_usd'],
  2: ['total_facturado_usd', 'total_syngenta_usd', 'total_agro_usd'],
  3: ['total', 'ok_cruzado', 'solo_crm', 'solo_gestion', 'monto_g_usd', 'monto_crm_usd'],
  4: ['total_compras_usd', 'proveedores_count'],
  5: ['total_ventas_usd', 'total_compras_usd'],
}

const KEY_LABELS: Record<string, string> = {
  total_arca: 'ARCA',
  total_gestion: 'Gestión',
  solo_arca: 'Solo ARCA',
  solo_gestion: 'Solo Gestión',
  internos: 'Internos',
  con_diferencia: 'Con diferencia',
  monto_arca_usd: 'Monto ARCA',
  monto_gestion_usd: 'Monto Gestión',
  total_facturado_usd: 'Total facturado',
  total_syngenta_usd: 'Syngenta',
  total_agro_usd: 'Agroquímicos',
  total: 'Total filas',
  ok_cruzado: 'OK cruzado',
  solo_crm: 'Solo CRM',
  monto_g_usd: 'Monto gestión',
  monto_crm_usd: 'Monto CRM',
  total_compras_usd: 'Total compras',
  proveedores_count: 'Proveedores',
  total_ventas_usd: 'Total ventas',
}

function MetricChip({
  label, value, goldenVal, paso, metricKey,
}: {
  label: string
  value: number
  goldenVal?: number
  paso: number
  metricKey: string
}) {
  const hasGld = goldenVal !== undefined && goldenVal !== null
  const level = hasGld ? getDiffLevel(paso, metricKey, value, goldenVal!) : 'ok'

  const chip = cn(
    'flex flex-col items-start px-2.5 py-1.5 rounded border text-xs min-w-[100px]',
    level === 'ok' && hasGld   ? 'border-green-200 bg-green-50'   : '',
    level === 'warning'        ? 'border-yellow-300 bg-yellow-50' : '',
    level === 'error'          ? 'border-red-300 bg-red-50'       : '',
    !hasGld                    ? 'border-gray-200 bg-gray-50'     : '',
  )

  const valColor = cn(
    'font-semibold',
    level === 'ok' && hasGld  ? 'text-green-800'  : '',
    level === 'warning'       ? 'text-yellow-800' : '',
    level === 'error'         ? 'text-red-700'    : '',
    !hasGld                   ? 'text-gray-800'   : '',
  )

  const pctStr = hasGld && goldenVal !== 0
    ? ` (${(((value - goldenVal!) / Math.abs(goldenVal!)) * 100).toFixed(1)}%)`
    : ''

  return (
    <div className={chip} title={hasGld ? `Golden: ${fmtVal(metricKey, goldenVal!)}${pctStr}` : undefined}>
      <span className="text-gray-500 text-[10px] leading-tight">{label}</span>
      <span className={valColor}>{fmtVal(metricKey, value)}</span>
      {hasGld && level !== 'ok' && (
        <span className="text-[10px] text-gray-500 flex items-center gap-0.5 mt-0.5">
          {level === 'error' ? <TrendingDown size={9} className="text-red-600" /> : <TrendingUp size={9} className="text-yellow-600" />}
          era {fmtVal(metricKey, goldenVal!)}{pctStr}
        </span>
      )}
    </div>
  )
}

function PasoRow({
  result, golden,
}: {
  result: PasoResult
  golden: PasoMetrics | null
}) {
  const [open, setOpen] = useState(false)
  const { paso, status, metrics, error, elapsed } = result
  const keys = METRICAS_POR_PASO[paso] ?? []

  const errores  = (metrics as any)?._errores ?? 0
  const warnings = (metrics as any)?._warnings ?? 0
  const alertas: any[] = (metrics as any)?._alertas ?? []

  // Estado visual de la fila
  const rowDiffs = golden && metrics
    ? keys.filter(k => {
        const cur = (metrics as any)[k]
        const gld = (golden as any)[k]
        if (typeof cur !== 'number' || typeof gld !== 'number') return false
        return getDiffLevel(paso, k, cur, gld) !== 'ok'
      })
    : []

  const hasDiffErrors   = rowDiffs.some(k => getDiffLevel(paso, k, (metrics as any)[k], (golden as any)[k]) === 'error')
  const hasDiffWarnings = rowDiffs.some(k => getDiffLevel(paso, k, (metrics as any)[k], (golden as any)[k]) === 'warning')

  return (
    <div className={cn(
      'border rounded-md overflow-hidden',
      status === 'running' ? 'border-blue-300 bg-blue-50/40' : '',
      status === 'error'   ? 'border-red-300 bg-red-50/30'   : '',
      status === 'ok' && hasDiffErrors   ? 'border-red-200 bg-red-50/20'     : '',
      status === 'ok' && hasDiffWarnings ? 'border-yellow-200 bg-yellow-50/20': '',
      status === 'ok' && !hasDiffErrors && !hasDiffWarnings ? 'border-green-200 bg-green-50/20' : '',
      status === 'idle'    ? 'border-gray-200 bg-gray-50/50'  : '',
    )}>
      {/* Header de la fila */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none"
        onClick={() => status !== 'idle' && setOpen(o => !o)}
      >
        {/* Icono de estado */}
        <div className="w-5 flex justify-center">
          {status === 'idle'    && <Minus size={14} className="text-gray-400" />}
          {status === 'running' && <Loader size={14} className="text-blue-500 animate-spin" />}
          {status === 'ok' && !hasDiffErrors && !hasDiffWarnings && !errores && (
            <CheckCircle size={14} className="text-green-600" />
          )}
          {status === 'ok' && (hasDiffWarnings || warnings > 0) && !hasDiffErrors && !errores && (
            <AlertTriangle size={14} className="text-yellow-500" />
          )}
          {status === 'ok' && (hasDiffErrors || errores > 0) && (
            <XCircle size={14} className="text-red-500" />
          )}
          {status === 'error'   && <XCircle size={14} className="text-red-500" />}
        </div>

        <span className="text-xs font-semibold text-gray-700 w-12">Paso {paso}</span>

        {/* Métricas clave inline (las primeras 3) */}
        {metrics && (
          <div className="flex items-center gap-3 flex-1 flex-wrap">
            {keys.slice(0, 4).map(k => {
              const v = (metrics as any)[k]
              if (v === undefined || v === null) return null
              const gv = golden ? (golden as any)[k] : undefined
              const level = gv !== undefined ? getDiffLevel(paso, k, v, gv) : 'ok'
              return (
                <span key={k} className={cn(
                  'text-xs',
                  level === 'error'   ? 'text-red-700 font-semibold' : '',
                  level === 'warning' ? 'text-yellow-700 font-semibold' : '',
                  level === 'ok'      ? 'text-gray-600' : '',
                )}>
                  {KEY_LABELS[k] || k}: <span className="font-medium">{fmtVal(k, v)}</span>
                  {gv !== undefined && level !== 'ok' && (
                    <span className="text-[10px] opacity-70 ml-0.5">
                      (era {fmtVal(k, gv)})
                    </span>
                  )}
                </span>
              )
            })}
          </div>
        )}

        {status === 'error' && (
          <span className="text-xs text-red-600 flex-1 truncate">{error}</span>
        )}

        <div className="flex items-center gap-2 ml-auto flex-shrink-0">
          {elapsed !== undefined && (
            <span className="text-[10px] text-gray-400">{elapsed.toFixed(1)}s</span>
          )}
          {errores > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700">{errores} err</span>
          )}
          {warnings > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700">{warnings} warn</span>
          )}
          {status !== 'idle' && (
            open ? <ChevronDown size={12} className="text-gray-400" /> : <ChevronRight size={12} className="text-gray-400" />
          )}
        </div>
      </div>

      {/* Detalle expandido */}
      {open && metrics && (
        <div className="px-3 pb-3 border-t border-gray-100">
          {/* Chips de métricas */}
          <div className="flex flex-wrap gap-2 mt-2">
            {keys.map(k => {
              const v = (metrics as any)[k]
              if (v === undefined || v === null) return null
              return (
                <MetricChip
                  key={k}
                  label={KEY_LABELS[k] || k}
                  value={v}
                  goldenVal={golden ? (golden as any)[k] : undefined}
                  paso={paso}
                  metricKey={k}
                />
              )
            })}
          </div>

          {/* Alertas de validación */}
          {alertas.length > 0 && (
            <div className="mt-3 space-y-1">
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Alertas de validación</p>
              {alertas.map((a: any, i: number) => (
                <div key={i} className={cn(
                  'flex items-start gap-1.5 text-xs px-2 py-1 rounded',
                  a.nivel === 'error'   ? 'bg-red-50 text-red-700'    : '',
                  a.nivel === 'warning' ? 'bg-yellow-50 text-yellow-700' : '',
                  a.nivel === 'info'    ? 'bg-blue-50 text-blue-700'  : '',
                )}>
                  {a.nivel === 'error'   && <XCircle size={11} className="mt-0.5 flex-shrink-0" />}
                  {a.nivel === 'warning' && <AlertTriangle size={11} className="mt-0.5 flex-shrink-0" />}
                  <span className="font-medium">{a.titulo}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ExpCard({
  result, onSaveGolden, onClearGolden,
}: {
  result: ExpResult
  onSaveGolden: () => void
  onClearGolden: () => void
}) {
  const [open, setOpen] = useState(true)
  const golden = loadGolden(result.expId)
  const goldenDate = golden ? (golden as any).savedAt?.slice(0, 10) : null

  const pasos = Object.values(result.pasos)
  const hasRunning = pasos.some(p => p.status === 'running')
  const hasError   = pasos.some(p => p.status === 'error')
  const hasOk      = pasos.some(p => p.status === 'ok')
  const allDone    = pasos.every(p => p.status === 'ok' || p.status === 'error')

  // Calcular si hay diff errors vs golden
  let diffErrors = 0, diffWarnings = 0
  if (golden) {
    for (const pr of pasos) {
      if (!pr.metrics) continue
      const gPaso = (golden as any).pasos?.[String(pr.paso)]
      if (!gPaso) continue
      const keys = METRICAS_POR_PASO[pr.paso] ?? []
      for (const k of keys) {
        const cur = (pr.metrics as any)[k]
        const gld = (gPaso as any)[k]
        if (typeof cur !== 'number' || typeof gld !== 'number') continue
        const lvl = getDiffLevel(pr.paso, k, cur, gld)
        if (lvl === 'error') diffErrors++
        else if (lvl === 'warning') diffWarnings++
      }
    }
  }

  return (
    <div className={cn(
      'rounded-lg border shadow-sm overflow-hidden',
      hasRunning              ? 'border-blue-300'  : '',
      hasError && !hasRunning ? 'border-red-300'   : '',
      diffErrors > 0          ? 'border-red-300'   : '',
      diffWarnings > 0 && diffErrors === 0 ? 'border-yellow-300' : '',
      allDone && !hasError && diffErrors === 0 && diffWarnings === 0 ? 'border-green-300' : '',
      !hasRunning && !hasError && !allDone ? 'border-gray-200' : '',
    )}>
      {/* Card header */}
      <div
        className="flex items-center gap-2 px-4 py-3 bg-white cursor-pointer select-none"
        onClick={() => setOpen(o => !o)}
      >
        {open ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}

        {/* Estado global */}
        {hasRunning && <Loader size={15} className="text-blue-500 animate-spin" />}
        {!hasRunning && hasError && <XCircle size={15} className="text-red-500" />}
        {!hasRunning && !hasError && diffErrors > 0 && <XCircle size={15} className="text-red-500" />}
        {!hasRunning && !hasError && diffErrors === 0 && diffWarnings > 0 && <AlertTriangle size={15} className="text-yellow-500" />}
        {!hasRunning && !hasError && diffErrors === 0 && diffWarnings === 0 && allDone && <CheckCircle size={15} className="text-green-600" />}
        {!hasRunning && !allDone && diffErrors === 0 && <Minus size={15} className="text-gray-400" />}

        <div className="flex-1">
          <span className="font-semibold text-sm text-gray-800">{result.nombre}</span>
          <span className="text-xs text-gray-400 ml-2">exp #{result.expId}</span>
        </div>

        {/* Badges de diff */}
        {diffErrors > 0 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-medium">
            {diffErrors} regresión{diffErrors !== 1 ? 'es' : ''}
          </span>
        )}
        {diffWarnings > 0 && diffErrors === 0 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700 font-medium">
            {diffWarnings} warning{diffWarnings !== 1 ? 's' : ''}
          </span>
        )}
        {allDone && !hasError && diffErrors === 0 && diffWarnings === 0 && hasOk && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">OK</span>
        )}

        {/* Botones golden */}
        <div className="flex items-center gap-1 ml-2" onClick={e => e.stopPropagation()}>
          {golden && (
            <span className="text-[10px] text-gray-400 mr-1">⭐ {goldenDate}</span>
          )}
          {allDone && hasOk && (
            <button
              title="Guardar como golden (referencia)"
              onClick={onSaveGolden}
              className="p-1 rounded hover:bg-yellow-100 text-gray-400 hover:text-yellow-600 transition-colors"
            >
              <Star size={13} />
            </button>
          )}
          {golden && (
            <button
              title="Borrar golden"
              onClick={onClearGolden}
              className="p-1 rounded hover:bg-red-50 text-gray-300 hover:text-red-400 transition-colors"
            >
              <StarOff size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Filas de pasos */}
      {open && (
        <div className="px-3 pb-3 bg-gray-50/60 space-y-1.5 pt-2">
          {Object.values(result.pasos)
            .sort((a, b) => a.paso - b.paso)
            .map(pr => (
              <PasoRow
                key={pr.paso}
                result={pr}
                golden={(golden as any)?.pasos?.[String(pr.paso)] ?? null}
              />
            ))}
        </div>
      )}
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

const PASOS = [1, 2, 3, 4, 5]
const PASO_LABELS: Record<number, string> = {
  1: 'Conciliación ARCA',
  2: 'Clasificación',
  3: 'Cruce CRM',
  4: 'Compras',
  5: 'Informe',
}

export default function TestingPage() {
  const { data: expedientes = [], isLoading } = useQuery<any[]>({
    queryKey: ['expedientes'],
    queryFn: () => expedientesAPI.listar().then(r => r.data),
  })

  const [selectedExps, setSelectedExps]   = useState<Set<number>>(new Set())
  const [selectedPasos, setSelectedPasos] = useState<Set<number>>(new Set([1, 2, 3, 4, 5]))
  const [runState, setRunState]           = useState<RunState>('idle')
  const [results, setResults]             = useState<Record<number, ExpResult>>({})
  const [goldenVersion, setGoldenVersion] = useState(0) // fuerza re-render al cambiar golden
  const abortRef = useRef(false)

  // Selección de expedientes
  const toggleExp = (id: number) =>
    setSelectedExps(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })

  const toggleAllExps = () => {
    if (selectedExps.size === expedientes.length) {
      setSelectedExps(new Set())
    } else {
      setSelectedExps(new Set(expedientes.map((e: any) => e.id)))
    }
  }

  const togglePaso = (p: number) =>
    setSelectedPasos(prev => {
      const s = new Set(prev)
      s.has(p) ? s.delete(p) : s.add(p)
      return s
    })

  // Inicializa resultados con estado idle
  const initResults = useCallback((expIds: number[]) => {
    const pasos = [...selectedPasos].sort()
    const init: Record<number, ExpResult> = {}
    for (const id of expIds) {
      const exp = expedientes.find((e: any) => e.id === id)
      const pasosMap: Record<number, PasoResult> = {}
      for (const p of pasos) pasosMap[p] = { paso: p, status: 'idle' }
      init[id] = { expId: id, nombre: exp?.nombre_distribuidor ?? `Exp #${id}`, pasos: pasosMap }
    }
    return init
  }, [selectedPasos, expedientes])

  const updatePaso = (expId: number, paso: number, update: Partial<PasoResult>) => {
    setResults(prev => ({
      ...prev,
      [expId]: {
        ...prev[expId],
        pasos: {
          ...prev[expId].pasos,
          [paso]: { ...prev[expId].pasos[paso], ...update },
        },
      },
    }))
  }

  const handleRun = async () => {
    if (selectedExps.size === 0) return
    abortRef.current = false
    setRunState('running')

    const expIds = [...selectedExps]
    const pasos  = [...selectedPasos].sort()
    const init   = initResults(expIds)
    setResults(init)

    // Ejecutar expedientes en paralelo, pasos secuenciales dentro de cada uno
    await Promise.all(expIds.map(async expId => {
      for (const paso of pasos) {
        if (abortRef.current) break
        updatePaso(expId, paso, { status: 'running' })
        const t0 = performance.now()
        try {
          const res = await pasosAPI.ejecutarPaso(expId, paso)
          const metrics = extractMetrics(paso, res.data)
          updatePaso(expId, paso, {
            status: 'ok',
            metrics,
            elapsed: (performance.now() - t0) / 1000,
          })
        } catch (err: any) {
          const msg = err.response?.data?.detail ?? err.message ?? 'Error desconocido'
          updatePaso(expId, paso, {
            status: 'error',
            error: msg,
            elapsed: (performance.now() - t0) / 1000,
          })
          break // parar en este expediente al primer error (los pasos son dependientes)
        }
      }
    }))

    setRunState('done')
  }

  const handleStop = () => {
    abortRef.current = true
    setRunState('done')
  }

  const handleSaveGolden = (expId: number) => {
    const r = results[expId]
    if (!r) return
    saveGolden(expId, r.pasos)
    setGoldenVersion(v => v + 1)
  }

  const handleClearGolden = (expId: number) => {
    clearGolden(expId)
    setGoldenVersion(v => v + 1)
  }

  // Selección por defecto: todos los expedientes al cargar
  React.useEffect(() => {
    if (expedientes.length > 0 && selectedExps.size === 0) {
      setSelectedExps(new Set(expedientes.map((e: any) => e.id)))
    }
  }, [expedientes])

  const runningCount = Object.values(results).reduce((n, r) =>
    n + Object.values(r.pasos).filter(p => p.status === 'running').length, 0)

  const doneCount = Object.values(results).reduce((n, r) =>
    n + Object.values(r.pasos).filter(p => p.status === 'ok' || p.status === 'error').length, 0)

  const totalCount = selectedExps.size * selectedPasos.size

  return (
    <div className="flex flex-col h-full bg-oag-bg">
      {/* ── Top bar ──────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-oag-border flex-shrink-0">
        <div>
          <h1 className="text-lg font-bold text-oag-text">Suite de Testing</h1>
          <p className="text-xs text-oag-muted mt-0.5">
            Ejecutá y comparás pasos en lote · Golden se guarda localmente
          </p>
        </div>

        <div className="flex items-center gap-2">
          {runState === 'running' && (
            <span className="text-xs text-blue-600 font-medium">
              {doneCount}/{totalCount} pasos completados
            </span>
          )}
          {runState === 'done' && (
            <button
              onClick={() => { setResults({}); setRunState('idle') }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded transition-colors border border-gray-200"
            >
              <RefreshCw size={12} />
              Limpiar
            </button>
          )}
          {runState === 'running' ? (
            <button
              onClick={handleStop}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-md transition-colors"
            >
              <Square size={14} />
              Detener
            </button>
          ) : (
            <button
              onClick={handleRun}
              disabled={selectedExps.size === 0 || selectedPasos.size === 0 || isLoading}
              className={cn(
                'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors',
                selectedExps.size > 0 && selectedPasos.size > 0
                  ? 'bg-oag-blue hover:bg-blue-700 text-white'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed',
              )}
            >
              <Play size={14} />
              Ejecutar
              {selectedExps.size > 0 && selectedPasos.size > 0 && (
                <span className="text-blue-200 text-xs">
                  {selectedExps.size} DS · {selectedPasos.size} pasos
                </span>
              )}
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Panel izquierdo: config ──────────────────────────── */}
        <div className="w-56 flex-shrink-0 bg-white border-r border-oag-border flex flex-col overflow-y-auto">
          {/* Pasos */}
          <div className="px-4 pt-4 pb-3">
            <p className="text-[10px] font-semibold text-oag-muted uppercase tracking-widest mb-2">Pasos</p>
            <div className="space-y-1">
              {PASOS.map(p => (
                <label key={p} className="flex items-center gap-2 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={selectedPasos.has(p)}
                    onChange={() => togglePaso(p)}
                    disabled={runState === 'running'}
                    className="w-3.5 h-3.5 rounded accent-oag-blue"
                  />
                  <span className="text-xs text-gray-700">
                    <span className="font-semibold text-oag-blue mr-1">{p}</span>
                    {PASO_LABELS[p]}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="border-t border-oag-border" />

          {/* Expedientes */}
          <div className="px-4 pt-3 pb-4 flex-1">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-semibold text-oag-muted uppercase tracking-widest">DS</p>
              <button
                onClick={toggleAllExps}
                disabled={runState === 'running'}
                className="text-[10px] text-blue-600 hover:text-blue-800"
              >
                {selectedExps.size === expedientes.length ? 'Ninguno' : 'Todos'}
              </button>
            </div>

            {isLoading ? (
              <div className="flex justify-center pt-4">
                <Loader size={16} className="animate-spin text-gray-400" />
              </div>
            ) : (
              <div className="space-y-1">
                {expedientes.map((exp: any) => {
                  const gld = hasGolden(exp.id)
                  return (
                    <label key={exp.id} className="flex items-start gap-2 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={selectedExps.has(exp.id)}
                        onChange={() => toggleExp(exp.id)}
                        disabled={runState === 'running'}
                        className="w-3.5 h-3.5 rounded accent-oag-blue mt-0.5 flex-shrink-0"
                      />
                      <span className="text-xs text-gray-700 leading-tight">
                        {exp.nombre_distribuidor}
                        {gld && <span className="ml-1 text-yellow-500">⭐</span>}
                        <br />
                        <span className="text-[10px] text-gray-400">
                          {exp.anio_analisis} · P{(exp.pasos_completados || []).join(',')}
                        </span>
                      </span>
                    </label>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* ── Panel derecho: resultados ────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {/* Progress bar global */}
          {runState === 'running' && totalCount > 0 && (
            <div className="bg-white rounded-lg border border-blue-200 px-4 py-2.5 flex items-center gap-3">
              <Loader size={14} className="animate-spin text-blue-500 flex-shrink-0" />
              <div className="flex-1">
                <div className="flex justify-between text-xs text-gray-600 mb-1">
                  <span>Ejecutando…</span>
                  <span>{doneCount} / {totalCount}</span>
                </div>
                <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-300"
                    style={{ width: `${totalCount > 0 ? (doneCount / totalCount) * 100 : 0}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Empty state */}
          {Object.keys(results).length === 0 && runState === 'idle' && (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <div className="text-4xl mb-3">🧪</div>
              <p className="text-sm font-medium text-gray-500">Seleccioná DS y pasos, luego ejecutá</p>
              <p className="text-xs text-gray-400 mt-1 max-w-xs">
                Los pasos se re-ejecutan para los expedientes seleccionados y las métricas
                se comparan contra el golden guardado (⭐).
              </p>
            </div>
          )}

          {/* Cards de resultados — en el orden de la lista de expedientes */}
          {expedientes
            .filter((e: any) => results[e.id])
            .map((e: any) => (
              <ExpCard
                key={`${e.id}-${goldenVersion}`}
                result={results[e.id]}
                onSaveGolden={() => handleSaveGolden(e.id)}
                onClearGolden={() => handleClearGolden(e.id)}
              />
            ))}

          {/* Resumen final */}
          {runState === 'done' && Object.keys(results).length > 0 && (
            <div className="bg-white rounded-lg border border-oag-border px-4 py-3">
              <p className="text-xs font-semibold text-gray-600 mb-2">Resumen</p>
              <div className="flex flex-wrap gap-4 text-xs">
                {(() => {
                  let ok = 0, err = 0, warn = 0, regr = 0
                  for (const r of Object.values(results)) {
                    for (const pr of Object.values(r.pasos)) {
                      if (pr.status === 'ok') ok++
                      if (pr.status === 'error') err++
                      const a = (pr.metrics as any)?._warnings ?? 0
                      if (a > 0) warn++
                      // regressions vs golden
                      const g = loadGolden(r.expId)
                      if (g && pr.metrics) {
                        const gp = (g as any).pasos?.[String(pr.paso)]
                        if (gp) {
                          const keys = METRICAS_POR_PASO[pr.paso] ?? []
                          for (const k of keys) {
                            const cur = (pr.metrics as any)[k]
                            const gld = (gp as any)[k]
                            if (typeof cur === 'number' && typeof gld === 'number') {
                              if (getDiffLevel(pr.paso, k, cur, gld) === 'error') { regr++; break }
                            }
                          }
                        }
                      }
                    }
                  }
                  return (
                    <>
                      <span className={ok > 0 ? 'text-green-700' : 'text-gray-400'}>
                        <CheckCircle size={11} className="inline mr-1" />{ok} pasos OK
                      </span>
                      {err > 0 && (
                        <span className="text-red-700">
                          <XCircle size={11} className="inline mr-1" />{err} con error
                        </span>
                      )}
                      {regr > 0 ? (
                        <span className="text-red-700 font-semibold">
                          <TrendingDown size={11} className="inline mr-1" />{regr} regresión{regr !== 1 ? 'es' : ''} vs golden
                        </span>
                      ) : ok > 0 ? (
                        <span className="text-green-700">
                          ✓ Sin regresiones vs golden
                        </span>
                      ) : null}
                    </>
                  )
                })()}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
