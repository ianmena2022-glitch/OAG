import React, { useState, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Play, Square, Star, StarOff, CheckCircle, XCircle,
  AlertTriangle, Loader, ChevronDown, ChevronRight,
  RefreshCw, Minus, TrendingUp, TrendingDown, BarChart2,
  Eye,
} from 'lucide-react'
import { expedientesAPI, pasosAPI } from '../../lib/api'
import { cn } from '../../lib/utils'

// ─── Tipos ────────────────────────────────────────────────────────────────────

type MetricValue = number | string | null | undefined

interface Metric {
  key:      string
  label:    string
  value:    MetricValue
  fmt?:     'usd' | 'pct' | 'count' | 'ratio'  // cómo formatear
  primary?: boolean   // se muestra inline en la fila
  group?:   string    // agrupación en el detalle expandido
}

interface PasoMetrics {
  paso: number
  metrics: Metric[]
  alertas_errores:  number
  alertas_warnings: number
  alertas_detalle:  { nivel: string; titulo: string }[]
}

interface PasoResult {
  paso:    number
  status:  'idle' | 'running' | 'ok' | 'error'
  error?:  string
  data?:   PasoMetrics
  elapsed?: number
}

interface ExpResult {
  expId:  number
  nombre: string
  pasos:  Record<number, PasoResult>
}

type RunMode  = 'ejecutar' | 'analizar'
type RunState = 'idle' | 'running' | 'done'

// ─── Extracción de métricas ───────────────────────────────────────────────────
// Combina el response de /ejecutar (o /resultado directamente en modo analizar)
// con el response completo de /resultado para sacar métricas derivadas.

function m(key: string, label: string, value: MetricValue,
           fmt: Metric['fmt'] = 'count', primary = false,
           group?: string): Metric {
  return { key, label, value, fmt, primary, group }
}

function extractMetrics(paso: number, ejec: any, res: any): PasoMetrics {
  // ejec = response de /ejecutar (limitado)
  // res  = response de /resultado (completo, puede ser igual si modo analizar)
  const alertas: any[] = ejec?.validacion?.alertas ?? res?.validacion?.alertas ?? []
  const base = {
    alertas_errores:  alertas.filter(a => a.nivel === 'error').length,
    alertas_warnings: alertas.filter(a => a.nivel === 'warning').length,
    alertas_detalle:  alertas.slice(0, 8).map(a => ({ nivel: a.nivel, titulo: a.titulo })),
  }

  const metrics: Metric[] = []

  // ── Paso 1 ────────────────────────────────────────────────────────────────
  if (paso === 1) {
    const r   = ejec?.resumen ?? res?.resumen ?? {}
    const con = res?.conciliacion ?? ejec?.conciliacion ?? []

    // Counts primarios
    const totalArca  = r.total_arca  ?? 0
    const totalGest  = r.total_gestion ?? 0
    const ok         = r.ok          ?? 0
    const soloArca   = r.solo_arca   ?? 0
    const soloGest   = r.solo_gestion ?? 0
    const internos   = r.internos    ?? 0
    const conDif     = r.con_diferencia ?? 0

    metrics.push(
      m('total_arca',     'ARCA total',     totalArca,  'count', true,  'Conteos'),
      m('total_gestion',  'Gestión total',  totalGest,  'count', true,  'Conteos'),
      m('ok',             'Matcheados OK',  ok,         'count', true,  'Conteos'),
      m('solo_arca',      'Solo ARCA',      soloArca,   'count', true,  'Conteos'),
      m('solo_gestion',   'Solo Gestión',   soloGest,   'count', true,  'Conteos'),
      m('internos',       'Internos',       internos,   'count', false, 'Conteos'),
      m('con_diferencia', 'Con diferencia', conDif,     'count', false, 'Conteos'),
    )

    // Porcentajes derivados
    const matchPct = totalArca > 0 ? +(ok / totalArca * 100).toFixed(1) : null
    const sgPct    = totalGest > 0 ? +(soloGest / totalGest * 100).toFixed(1) : null
    metrics.push(
      m('match_rate_pct',    '% matcheado',     matchPct, 'pct', true, 'Ratios'),
      m('solo_gestion_pct',  '% solo gestión',  sgPct,    'pct', false,'Ratios'),
    )

    // Montos
    const montoArca = Math.round(r.monto_total_arca_usd ?? 0)
    const montoGest = Math.round(r.monto_total_gestion_usd ?? 0)
    const difMontos = montoArca > 0 ? +(Math.abs(montoArca - montoGest) / montoArca * 100).toFixed(2) : null
    metrics.push(
      m('monto_arca_usd',    'Monto ARCA',      montoArca, 'usd', false,'Montos'),
      m('monto_gestion_usd', 'Monto Gestión',   montoGest, 'usd', false,'Montos'),
      m('monto_diff_pct',    '% diff montos',   difMontos, 'pct', false,'Montos'),
    )

    // Breakdown por tipo desde conciliación completa
    if (con.length > 0) {
      const fc = con.filter((c: any) => (c.tipo || '').toUpperCase() === 'FC').length
      const nc = con.filter((c: any) => (c.tipo || '').toUpperCase() === 'NC').length
      const nd = con.filter((c: any) => (c.tipo || '').toUpperCase() === 'ND').length
      const difUsd = con
        .filter((c: any) => c.estado === 'DIFERENCIA' || c.estado === 'CON_DIFERENCIA')
        .reduce((s: number, c: any) => s + Math.abs(c.diferencia_usd ?? 0), 0)
      metrics.push(
        m('fc_count', 'FC',              fc,               'count', false, 'Tipos'),
        m('nc_count', 'NC',              nc,               'count', false, 'Tipos'),
        m('nd_count', 'ND',              nd,               'count', false, 'Tipos'),
        m('dif_abs_usd', 'Dif. absol.',  Math.round(difUsd), 'usd', false, 'Tipos'),
      )
    }
  }

  // ── Paso 2 ────────────────────────────────────────────────────────────────
  else if (paso === 2) {
    const tot  = ejec?.totales  ?? res?.totales  ?? {}
    const clas = res?.clasificacion ?? ejec?.clasificacion ?? []
    const tabla = res?.tabla_apertura ?? ejec?.tabla_apertura ?? []

    const facturado  = Math.round(tot.total_facturado_usd  ?? 0)
    const syngenta   = Math.round(tot.total_syngenta_usd   ?? 0)
    const agro       = Math.round(tot.total_agroquimicos_usd ?? 0)
    const synPct     = facturado > 0 ? +(syngenta / facturado * 100).toFixed(1)  : null
    const agroPct    = facturado > 0 ? +(agro     / facturado * 100).toFixed(1)  : null

    metrics.push(
      m('total_facturado_usd', 'Total facturado', facturado, 'usd', true,  'Montos'),
      m('total_syngenta_usd',  'Syngenta',        syngenta,  'usd', true,  'Montos'),
      m('total_agro_usd',      'Agroquímicos',    agro,      'usd', false, 'Montos'),
      m('syngenta_pct',        '% Syngenta',      synPct,    'pct', true,  'Ratios'),
      m('agro_pct',            '% Agro',          agroPct,   'pct', false, 'Ratios'),
    )

    // Desde clasificación completa (solo en modo resultado)
    if (clas.length > 0) {
      const synProds   = clas.filter((c: any) => c.syngenta   === 'SI').length
      const noAgro     = clas.filter((c: any) => c.agroquimico === 'NO').length
      const revisar    = clas.filter((c: any) => c.agroquimico === 'REVISAR' || c.syngenta === 'REVISAR').length
      metrics.push(
        m('clas_total',       'Prods clasificados', clas.length, 'count', false, 'Clasificación'),
        m('syngenta_prods',   'Prods Syngenta',     synProds,    'count', true,  'Clasificación'),
        m('no_agro_prods',    'No agroquímicos',    noAgro,      'count', false, 'Clasificación'),
        m('revisar_prods',    'REVISAR',            revisar,     'count', false, 'Clasificación'),
      )
    }

    // Clientes y tabla apertura
    const topClients = (ejec?.ranking_clientes_top10 ?? res?.ranking_clientes ?? []).length
    const topProds   = (ejec?.ranking_productos_top10 ?? res?.ranking_productos ?? []).length
    metrics.push(
      m('top_clientes', 'Top clientes', topClients, 'count', false, 'Ranking'),
      m('top_productos','Top productos',topProds,   'count', false, 'Ranking'),
      m('tabla_filas',  'Tabla apertura', tabla.length, 'count', false, 'Ranking'),
    )
  }

  // ── Paso 3 ────────────────────────────────────────────────────────────────
  else if (paso === 3) {
    const r   = ejec?.resumen ?? res?.resumen ?? {}
    const con = res?.conciliacion ?? ejec?.conciliacion ?? []

    const total    = r.total      ?? 0
    const okCruz   = r.ok         ?? 0
    const soloCrm  = r.solo_crm   ?? 0
    const soloGest = r.solo_gestion ?? 0
    const montoG   = Math.round(r.monto_gestion_total_usd ?? 0)
    const montoCrm = Math.round(r.monto_crm_total_usd    ?? 0)

    const matchPct  = total > 0 ? +(okCruz  / total * 100).toFixed(1) : null
    const sCrmPct   = total > 0 ? +(soloCrm / total * 100).toFixed(1) : null
    const sGestPct  = total > 0 ? +(soloGest / total * 100).toFixed(1) : null
    const montoDiff = montoCrm > 0
      ? +((montoG - montoCrm) / montoCrm * 100).toFixed(2)
      : null

    metrics.push(
      m('total',         'Total filas',   total,    'count', true,  'Conteos'),
      m('ok_cruzado',    'OK cruzados',   okCruz,   'count', true,  'Conteos'),
      m('solo_crm',      'Solo CRM',      soloCrm,  'count', true,  'Conteos'),
      m('solo_gestion',  'Solo Gestión',  soloGest, 'count', true,  'Conteos'),
      m('match_rate_pct','% match',       matchPct, 'pct',   true,  'Ratios'),
      m('solo_crm_pct',  '% solo CRM',   sCrmPct,  'pct',   false, 'Ratios'),
      m('solo_gestion_pct','% solo Gest.',sGestPct, 'pct',   false, 'Ratios'),
      m('monto_g_usd',   'Monto gestión',montoG,   'usd',   false, 'Montos'),
      m('monto_crm_usd', 'Monto CRM',    montoCrm, 'usd',   false, 'Montos'),
      m('monto_diff_pct','% diff montos',montoDiff,'pct',   false, 'Montos'),
    )

    // Marcas con problemas (desde conciliación)
    if (con.length > 0) {
      const marcasProb = new Map<string, number>()
      for (const row of con) {
        const est = row.estado ?? ''
        if (est === 'SOLO_CRM' || est === 'SOLO_GESTION') {
          const marca = (row.marca_crm ?? row.marca ?? row.producto_crm ?? 'Sin marca').toString().slice(0, 30)
          marcasProb.set(marca, (marcasProb.get(marca) ?? 0) + 1)
        }
      }
      const topMarca = [...marcasProb.entries()].sort((a, b) => b[1] - a[1])[0]
      if (topMarca) {
        metrics.push(m('top_marca_problema', 'Marca c/ más diff', topMarca[0], 'count', false, 'Detalle'))
      }

      // Distribución de estados completa
      const estadoCounts = new Map<string, number>()
      for (const row of con) {
        const e = row.estado ?? 'SIN_ESTADO'
        estadoCounts.set(e, (estadoCounts.get(e) ?? 0) + 1)
      }
      for (const [est, cnt] of estadoCounts.entries()) {
        if (!['OK', 'SOLO_CRM', 'SOLO_GESTION'].includes(est)) {
          metrics.push(m(`estado_${est}`, est, cnt, 'count', false, 'Estados extra'))
        }
      }
    }
  }

  // ── Paso 4 ────────────────────────────────────────────────────────────────
  else if (paso === 4) {
    const tot    = ejec?.totales    ?? res?.totales    ?? {}
    const resumen = ejec?.resumen_top20 ?? res?.resumen ?? []

    const totalCompras = Math.round(tot.total_compras_usd ?? 0)
    const provCount    = resumen.length

    metrics.push(
      m('total_compras_usd',  'Total compras',   totalCompras, 'usd',   true,  'Montos'),
      m('proveedores_count',  'Proveedores',     provCount,    'count', true,  'Conteos'),
    )

    // Top proveedor
    if (resumen.length > 0) {
      const top = resumen[0]
      const topUsd = Math.round(top.total_usd ?? top.monto_usd ?? 0)
      const topPct = totalCompras > 0 ? +(topUsd / totalCompras * 100).toFixed(1) : null
      metrics.push(
        m('top_proveedor_usd', `Top: ${(top.proveedor ?? top.nombre_proveedor ?? 'Proveedor 1').toString().slice(0, 25)}`,
          topUsd, 'usd', true, 'Top'),
        m('top_proveedor_pct', '% top proveedor', topPct, 'pct', false, 'Top'),
      )
    }

    // Concentración: top3 / total
    if (resumen.length >= 3) {
      const top3 = resumen.slice(0, 3).reduce((s: number, r: any) =>
        s + Math.round(r.total_usd ?? r.monto_usd ?? 0), 0)
      const top3Pct = totalCompras > 0 ? +(top3 / totalCompras * 100).toFixed(1) : null
      metrics.push(m('top3_pct', '% top 3 proveedores', top3Pct, 'pct', false, 'Concentración'))
    }

    // Proveedores con NC/ND
    const conNc = resumen.filter((r: any) =>
      (r.nc_count ?? 0) > 0 || (r.nd_count ?? 0) > 0 ||
      ((r.tipos ?? {}).__NC ?? 0) > 0 || ((r.tipos ?? {}).__ND ?? 0) > 0
    ).length
    if (conNc > 0) {
      metrics.push(m('prov_con_nc_nd', 'Proveedores c/ NC/ND', conNc, 'count', false, 'Tipos'))
    }
  }

  // ── Paso 5 ────────────────────────────────────────────────────────────────
  else if (paso === 5) {
    const tot = ejec?.totales ?? res?.totales ?? {}
    const ventas  = Math.round(tot.total_ventas_usd  ?? 0)
    const compras = Math.round(tot.total_compras_usd ?? 0)
    const ratio   = ventas > 0 ? +(compras / ventas * 100).toFixed(1) : null

    metrics.push(
      m('total_ventas_usd',      'Total ventas',    ventas,  'usd',   true, 'Montos'),
      m('total_compras_usd',     'Total compras',   compras, 'usd',   true, 'Montos'),
      m('compras_ventas_ratio',  'Ratio C/V',       ratio,   'pct',   true, 'Ratios'),
    )
  }

  return { paso, metrics, ...base }
}

// ─── Tolerancias ──────────────────────────────────────────────────────────────
// Clave: `{paso}_{key}` → tolerancia porcentual (0.01 = 1%).
// Las métricas de conteo exacto llevan 0.00.
// Las de IA o TC llevan más margen.

const TOL: Record<string, number> = {
  // Paso 1 — conteos exactos (deterministas)
  '1_total_arca':         0.00,
  '1_ok':                 0.00,
  '1_solo_arca':          0.00,
  '1_solo_gestion':       0.00,
  '1_internos':           0.00,
  '1_total_gestion':      0.01,   // TC muy pequeña variación
  '1_con_diferencia':     0.05,
  // Paso 1 — montos (dependen de TC maestro)
  '1_monto_arca_usd':     0.01,
  '1_monto_gestion_usd':  0.02,
  // Paso 1 — derivados
  '1_match_rate_pct':     0.003,  // 0.3%
  '1_solo_gestion_pct':   0.00,
  '1_monto_diff_pct':     0.005,
  '1_fc_count':           0.00,
  '1_nc_count':           0.00,
  '1_nd_count':           0.00,
  '1_dif_abs_usd':        0.10,

  // Paso 2 — IA puede variar ≤5%
  '2_total_facturado_usd':  0.02,
  '2_total_syngenta_usd':   0.05,
  '2_total_agro_usd':       0.05,
  '2_syngenta_pct':         0.02,
  '2_agro_pct':             0.02,
  '2_syngenta_prods':       0.05,  // IA puede mover algún producto
  '2_revisar_prods':        0.20,  // puede variar bastante
  '2_no_agro_prods':        0.05,
  '2_clas_total':           0.02,

  // Paso 3 — conteos exactos
  '3_total':              0.00,
  '3_ok_cruzado':         0.00,
  '3_solo_crm':           0.00,
  '3_solo_gestion':       0.00,
  '3_match_rate_pct':     0.00,
  '3_solo_crm_pct':       0.00,
  '3_solo_gestion_pct':   0.00,
  '3_monto_g_usd':        0.03,
  '3_monto_crm_usd':      0.03,
  '3_monto_diff_pct':     0.02,

  // Paso 4
  '4_total_compras_usd':  0.03,
  '4_proveedores_count':  0.00,
  '4_top_proveedor_usd':  0.05,
  '4_top_proveedor_pct':  0.02,
  '4_top3_pct':           0.02,

  // Paso 5
  '5_total_ventas_usd':   0.03,
  '5_total_compras_usd':  0.03,
  '5_compras_ventas_ratio': 0.03,
}
const DEFAULT_TOL = 0.10

type DiffLevel = 'ok' | 'warning' | 'error' | 'na'

function diffLevel(paso: number, key: string, cur: number, gld: number): DiffLevel {
  const tol = TOL[`${paso}_${key}`] ?? DEFAULT_TOL
  if (gld === 0) return cur === 0 ? 'ok' : 'error'
  const ratio = Math.abs(cur - gld) / Math.abs(gld)
  if (ratio <= tol) return 'ok'
  return ratio > tol * 3 ? 'error' : 'warning'
}

// ─── Formato de valores ───────────────────────────────────────────────────────

function fmtMetric(v: MetricValue, fmt: Metric['fmt']): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') return v
  if (fmt === 'usd') {
    return `US$ ${Math.round(v as number).toLocaleString('es-AR')}`
  }
  if (fmt === 'pct') {
    return `${(v as number).toFixed(1)}%`
  }
  return String(v)
}

// ─── Golden ───────────────────────────────────────────────────────────────────

const GOLDEN_PREFIX = 'ogsa_golden_v2_'

interface GoldenData {
  savedAt: string
  pasos: Record<string, Metric[]>
}

function loadGolden(expId: number): GoldenData | null {
  try {
    const raw = localStorage.getItem(`${GOLDEN_PREFIX}${expId}`)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function saveGolden(expId: number, nombre: string, results: Record<number, PasoResult>) {
  const pasos: Record<string, Metric[]> = {}
  for (const [paso, r] of Object.entries(results)) {
    if (r.data) pasos[paso] = r.data.metrics
  }
  const data: GoldenData = { savedAt: new Date().toISOString(), pasos }
  localStorage.setItem(`${GOLDEN_PREFIX}${expId}`, JSON.stringify(data))
}

function clearGolden(expId: number) {
  localStorage.removeItem(`${GOLDEN_PREFIX}${expId}`)
}

function getGoldenMetric(golden: GoldenData | null, paso: number, key: string): Metric | null {
  if (!golden) return null
  const arr = golden.pasos[String(paso)] ?? []
  return arr.find(m => m.key === key) ?? null
}

// ─── Chip de métrica individual ───────────────────────────────────────────────

function MetricChip({
  metric, golden, paso,
}: {
  metric: Metric
  golden: GoldenData | null
  paso:   number
}) {
  const gm    = getGoldenMetric(golden, paso, metric.key)
  const curN  = typeof metric.value === 'number' ? metric.value : null
  const gldN  = gm && typeof gm.value === 'number' ? gm.value : null
  const level: DiffLevel = (curN !== null && gldN !== null)
    ? diffLevel(paso, metric.key, curN, gldN)
    : 'na'

  const pct = (curN !== null && gldN !== null && gldN !== 0)
    ? `${((curN - gldN) / Math.abs(gldN) * 100).toFixed(1)}%`
    : null

  const chipCls = cn(
    'flex flex-col items-start px-2.5 py-1.5 rounded border text-xs min-w-[110px] max-w-[160px]',
    level === 'ok'      ? 'border-green-200  bg-green-50'   : '',
    level === 'warning' ? 'border-yellow-300 bg-yellow-50'  : '',
    level === 'error'   ? 'border-red-300    bg-red-50'     : '',
    level === 'na'      ? 'border-gray-200   bg-white'      : '',
  )
  const valCls = cn(
    'font-semibold',
    level === 'ok'      ? 'text-green-800'   : '',
    level === 'warning' ? 'text-yellow-800'  : '',
    level === 'error'   ? 'text-red-700'     : '',
    level === 'na'      ? 'text-gray-800'    : '',
  )

  return (
    <div className={chipCls}
         title={gldN !== null ? `Golden: ${fmtMetric(gldN, metric.fmt)}${pct ? ` (${pct})` : ''}` : ''}>
      <span className="text-[10px] text-gray-500 leading-tight truncate w-full">{metric.label}</span>
      <span className={valCls}>{fmtMetric(metric.value, metric.fmt)}</span>
      {gldN !== null && level !== 'ok' && pct && (
        <span className="flex items-center gap-0.5 text-[10px] text-gray-500 mt-0.5">
          {(curN! > gldN!) ? <TrendingUp size={9} className={level === 'error' ? 'text-red-500' : 'text-yellow-500'} />
                           : <TrendingDown size={9} className={level === 'error' ? 'text-red-500' : 'text-yellow-500'} />}
          era {fmtMetric(gldN, metric.fmt)} ({pct})
        </span>
      )}
    </div>
  )
}

// ─── Fila de un paso ──────────────────────────────────────────────────────────

function PasoRow({ result, golden }: { result: PasoResult; golden: GoldenData | null }) {
  const [open, setOpen] = useState(false)
  const { paso, status, data, error, elapsed } = result
  const primary   = data?.metrics.filter(m => m.primary) ?? []
  const secondary = data?.metrics.filter(m => !m.primary) ?? []

  // Calcular diff vs golden
  const diffs = (data?.metrics ?? []).reduce((acc, met) => {
    if (typeof met.value !== 'number') return acc
    const gm = getGoldenMetric(golden, paso, met.key)
    if (!gm || typeof gm.value !== 'number') return acc
    const lvl = diffLevel(paso, met.key, met.value, gm.value as number)
    if (lvl === 'error')   acc.errors++
    if (lvl === 'warning') acc.warnings++
    return acc
  }, { errors: 0, warnings: 0 })

  const hasErr  = diffs.errors > 0 || (data?.alertas_errores ?? 0) > 0
  const hasWarn = !hasErr && (diffs.warnings > 0 || (data?.alertas_warnings ?? 0) > 0)

  // Agrupar secundarias por grupo
  const groups: Record<string, Metric[]> = {}
  for (const met of secondary) {
    const g = met.group ?? 'Más'
    ;(groups[g] = groups[g] ?? []).push(met)
  }

  return (
    <div className={cn(
      'rounded border overflow-hidden',
      status === 'running' ? 'border-blue-300 bg-blue-50/30'   : '',
      status === 'error'   ? 'border-red-300  bg-red-50/20'    : '',
      status === 'ok' && hasErr   ? 'border-red-200    bg-red-50/10'    : '',
      status === 'ok' && hasWarn  ? 'border-yellow-200 bg-yellow-50/10' : '',
      status === 'ok' && !hasErr && !hasWarn ? 'border-green-200 bg-green-50/10' : '',
      status === 'idle'    ? 'border-gray-200 bg-gray-50/50'   : '',
    )}>
      {/* Cabecera clickeable */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer select-none"
        onClick={() => status === 'ok' && setOpen(o => !o)}
      >
        <div className="w-5 flex-shrink-0 flex justify-center">
          {status === 'idle'    && <Minus size={13} className="text-gray-400" />}
          {status === 'running' && <Loader size={13} className="text-blue-500 animate-spin" />}
          {status === 'ok' && !hasErr && !hasWarn && <CheckCircle size={13} className="text-green-600" />}
          {status === 'ok' && hasWarn && <AlertTriangle size={13} className="text-yellow-500" />}
          {status === 'ok' && hasErr  && <XCircle size={13} className="text-red-500" />}
          {status === 'error'         && <XCircle size={13} className="text-red-500" />}
        </div>

        <span className="text-xs font-semibold text-gray-600 w-12 flex-shrink-0">Paso {paso}</span>

        {/* Métricas primarias inline */}
        {primary.length > 0 && status === 'ok' && (
          <div className="flex flex-wrap gap-3 flex-1 min-w-0">
            {primary.map(met => {
              const gm   = getGoldenMetric(golden, paso, met.key)
              const curN = typeof met.value === 'number' ? met.value : null
              const gldN = gm && typeof gm.value === 'number' ? gm.value as number : null
              const lvl  = (curN !== null && gldN !== null) ? diffLevel(paso, met.key, curN, gldN) : 'na'
              return (
                <span key={met.key} className={cn(
                  'text-xs',
                  lvl === 'error'   ? 'text-red-700 font-semibold'    : '',
                  lvl === 'warning' ? 'text-yellow-700 font-semibold' : '',
                  lvl === 'ok'      ? 'text-gray-600'                 : '',
                  lvl === 'na'      ? 'text-gray-600'                 : '',
                )}>
                  <span className="text-gray-400">{met.label}: </span>
                  <span className="font-medium">{fmtMetric(met.value, met.fmt)}</span>
                  {gldN !== null && lvl !== 'ok' && (
                    <span className="text-[10px] opacity-60 ml-0.5">
                      (era {fmtMetric(gldN, met.fmt)})
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

        {/* Badges y toggle */}
        <div className="flex items-center gap-1.5 ml-auto flex-shrink-0">
          {elapsed !== undefined && (
            <span className="text-[10px] text-gray-400">{elapsed.toFixed(1)}s</span>
          )}
          {diffs.errors  > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700">
              {diffs.errors} regr.
            </span>
          )}
          {diffs.warnings > 0 && diffs.errors === 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700">
              {diffs.warnings} warn
            </span>
          )}
          {(data?.alertas_errores ?? 0) > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-100 text-orange-700">
              {data!.alertas_errores} val.err
            </span>
          )}
          {status === 'ok' && (
            open
              ? <ChevronDown  size={11} className="text-gray-400" />
              : <ChevronRight size={11} className="text-gray-400" />
          )}
        </div>
      </div>

      {/* Detalle expandido */}
      {open && data && (
        <div className="px-3 pb-3 pt-1 border-t border-gray-100 space-y-3">
          {/* Grupos de métricas */}
          {Object.entries(groups).map(([grp, mets]) => (
            <div key={grp}>
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">{grp}</p>
              <div className="flex flex-wrap gap-2">
                {mets.map(met => (
                  <MetricChip key={met.key} metric={met} golden={golden} paso={paso} />
                ))}
              </div>
            </div>
          ))}

          {/* Primarias también en detalle */}
          {primary.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Primarias</p>
              <div className="flex flex-wrap gap-2">
                {primary.map(met => (
                  <MetricChip key={met.key} metric={met} golden={golden} paso={paso} />
                ))}
              </div>
            </div>
          )}

          {/* Alertas de validación */}
          {data.alertas_detalle.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Alertas del sistema</p>
              <div className="space-y-1">
                {data.alertas_detalle.map((a, i) => (
                  <div key={i} className={cn(
                    'flex items-start gap-1.5 text-xs px-2 py-1 rounded',
                    a.nivel === 'error'   ? 'bg-red-50 text-red-700'      : '',
                    a.nivel === 'warning' ? 'bg-yellow-50 text-yellow-700' : '',
                    a.nivel === 'info'    ? 'bg-blue-50 text-blue-700'    : '',
                  )}>
                    {a.nivel === 'error'   && <XCircle size={10} className="mt-0.5 flex-shrink-0" />}
                    {a.nivel === 'warning' && <AlertTriangle size={10} className="mt-0.5 flex-shrink-0" />}
                    <span>{a.titulo}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Tarjeta por expediente ───────────────────────────────────────────────────

function ExpCard({
  result, onSaveGolden, onClearGolden,
}: {
  result: ExpResult
  onSaveGolden: () => void
  onClearGolden: () => void
}) {
  const [open, setOpen] = useState(true)
  const golden      = loadGolden(result.expId)
  const goldenDate  = golden?.savedAt?.slice(0, 10) ?? null

  const pasos    = Object.values(result.pasos)
  const running  = pasos.some(p => p.status === 'running')
  const allDone  = pasos.every(p => p.status === 'ok' || p.status === 'error')
  const anyOk    = pasos.some(p => p.status === 'ok')
  const anyErr   = pasos.some(p => p.status === 'error')

  // Contar regresiones vs golden
  let totalDiffErr = 0, totalDiffWarn = 0
  if (golden) {
    for (const pr of pasos) {
      if (!pr.data) continue
      for (const met of pr.data.metrics) {
        if (typeof met.value !== 'number') continue
        const gm = getGoldenMetric(golden, pr.paso, met.key)
        if (!gm || typeof gm.value !== 'number') continue
        const lvl = diffLevel(pr.paso, met.key, met.value, gm.value as number)
        if (lvl === 'error')   totalDiffErr++
        if (lvl === 'warning') totalDiffWarn++
      }
    }
  }

  const statusIcon = running
    ? <Loader size={14} className="text-blue-500 animate-spin" />
    : anyErr || totalDiffErr > 0
    ? <XCircle size={14} className="text-red-500" />
    : totalDiffWarn > 0
    ? <AlertTriangle size={14} className="text-yellow-500" />
    : allDone && anyOk
    ? <CheckCircle size={14} className="text-green-600" />
    : <Minus size={14} className="text-gray-400" />

  return (
    <div className={cn(
      'rounded-lg border shadow-sm overflow-hidden bg-white',
      running                  ? 'border-blue-300'   : '',
      anyErr || totalDiffErr > 0 ? 'border-red-300'   : '',
      !anyErr && totalDiffWarn > 0 && totalDiffErr === 0 ? 'border-yellow-300' : '',
      allDone && !anyErr && totalDiffErr === 0 && totalDiffWarn === 0 ? 'border-green-300' : '',
      !running && !anyErr && !allDone ? 'border-gray-200' : '',
    )}>
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-3 cursor-pointer select-none bg-white hover:bg-gray-50/50 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        {open ? <ChevronDown size={13} className="text-gray-400" /> : <ChevronRight size={13} className="text-gray-400" />}
        {statusIcon}

        <div className="flex-1 min-w-0">
          <span className="font-semibold text-sm text-gray-800">{result.nombre}</span>
          <span className="text-xs text-gray-400 ml-2">#{result.expId}</span>
        </div>

        {/* Badges de diff */}
        {totalDiffErr > 0 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-medium">
            {totalDiffErr} regresión{totalDiffErr !== 1 ? 'es' : ''}
          </span>
        )}
        {totalDiffWarn > 0 && totalDiffErr === 0 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700 font-medium">
            {totalDiffWarn} warning{totalDiffWarn !== 1 ? 's' : ''}
          </span>
        )}
        {allDone && anyOk && totalDiffErr === 0 && totalDiffWarn === 0 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">✓ OK</span>
        )}

        {/* Botones golden */}
        <div className="flex items-center gap-1 ml-2" onClick={e => e.stopPropagation()}>
          {goldenDate && <span className="text-[10px] text-gray-400">⭐ {goldenDate}</span>}
          {allDone && anyOk && (
            <button title="Guardar como golden" onClick={onSaveGolden}
              className="p-1 rounded hover:bg-yellow-100 text-gray-400 hover:text-yellow-600 transition-colors">
              <Star size={13} />
            </button>
          )}
          {golden && (
            <button title="Borrar golden" onClick={onClearGolden}
              className="p-1 rounded hover:bg-red-50 text-gray-300 hover:text-red-400 transition-colors">
              <StarOff size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Filas de pasos */}
      {open && (
        <div className="px-3 pb-3 pt-1.5 bg-gray-50/60 space-y-1.5">
          {Object.values(result.pasos).sort((a, b) => a.paso - b.paso).map(pr => (
            <PasoRow key={pr.paso} result={pr} golden={golden} />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

const PASOS = [1, 2, 3, 4, 5]
const PASO_LABELS: Record<number, string> = {
  1: 'Conciliación', 2: 'Clasificación', 3: 'Cruce CRM', 4: 'Compras', 5: 'Informe',
}

export default function TestingPage() {
  const { data: expedientes = [], isLoading } = useQuery<any[]>({
    queryKey: ['expedientes'],
    queryFn: () => expedientesAPI.listar().then(r => r.data),
  })

  const [selectedExps,   setSelectedExps]   = useState<Set<number>>(new Set())
  const [selectedPasos,  setSelectedPasos]  = useState<Set<number>>(new Set([1, 2, 3, 4, 5]))
  const [runState,       setRunState]       = useState<RunState>('idle')
  const [results,        setResults]        = useState<Record<number, ExpResult>>({})
  const [goldenVersion,  setGoldenVersion]  = useState(0)
  const abortRef = useRef(false)

  // Selección por defecto al cargar
  React.useEffect(() => {
    if (expedientes.length > 0 && selectedExps.size === 0)
      setSelectedExps(new Set(expedientes.map((e: any) => e.id)))
  }, [expedientes])

  const toggleExp = (id: number) =>
    setSelectedExps(p => { const s = new Set(p); s.has(id) ? s.delete(id) : s.add(id); return s })

  const toggleAllExps = () =>
    setSelectedExps(selectedExps.size === expedientes.length
      ? new Set() : new Set(expedientes.map((e: any) => e.id)))

  const togglePaso = (p: number) =>
    setSelectedPasos(prev => { const s = new Set(prev); s.has(p) ? s.delete(p) : s.add(p); return s })

  const initResults = useCallback((expIds: number[], modo: RunMode) => {
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

  const setPasoResult = (expId: number, paso: number, update: Partial<PasoResult>) =>
    setResults(prev => ({
      ...prev,
      [expId]: {
        ...prev[expId],
        pasos: { ...prev[expId].pasos, [paso]: { ...prev[expId].pasos[paso], ...update } },
      },
    }))

  // Ejecutar: re-ejecuta el paso, luego lee /resultado para tener datos completos
  const runSingle = async (expId: number, paso: number): Promise<boolean> => {
    setPasoResult(expId, paso, { status: 'running' })
    const t0 = performance.now()
    try {
      const ejec = await pasosAPI.ejecutarPaso(expId, paso)
      // Tras ejecutar, pedimos /resultado que tiene conciliación completa + clasificación
      let resData = ejec.data
      try {
        const res = await pasosAPI.resultadoPaso(expId, paso)
        resData = res.data
      } catch { /* si falla usamos lo que trajo ejecutar */ }
      const data = extractMetrics(paso, ejec.data, resData)
      setPasoResult(expId, paso, { status: 'ok', data, elapsed: (performance.now() - t0) / 1000 })
      return true
    } catch (err: any) {
      const msg = err.response?.data?.detail ?? err.message ?? 'Error'
      setPasoResult(expId, paso, { status: 'error', error: msg, elapsed: (performance.now() - t0) / 1000 })
      return false
    }
  }

  // Analizar: solo lee el resultado actual sin re-ejecutar
  const analyzeSingle = async (expId: number, paso: number): Promise<boolean> => {
    setPasoResult(expId, paso, { status: 'running' })
    const t0 = performance.now()
    try {
      const res = await pasosAPI.resultadoPaso(expId, paso)
      const data = extractMetrics(paso, res.data, res.data)
      setPasoResult(expId, paso, { status: 'ok', data, elapsed: (performance.now() - t0) / 1000 })
      return true
    } catch (err: any) {
      const msg = err.response?.data?.detail ?? err.message ?? 'Sin datos'
      setPasoResult(expId, paso, { status: 'error', error: msg, elapsed: (performance.now() - t0) / 1000 })
      return false
    }
  }

  const handleRun = async (modo: RunMode) => {
    if (selectedExps.size === 0) return
    abortRef.current = false
    setRunState('running')
    const expIds = [...selectedExps]
    const pasos  = [...selectedPasos].sort()
    setResults(initResults(expIds, modo))

    await Promise.all(expIds.map(async expId => {
      for (const paso of pasos) {
        if (abortRef.current) break
        const ok = modo === 'ejecutar'
          ? await runSingle(expId, paso)
          : await analyzeSingle(expId, paso)
        if (!ok && modo === 'ejecutar') break  // pasos dependientes — parar al primer error
      }
    }))

    setRunState('done')
  }

  const totalCount   = selectedExps.size * selectedPasos.size
  const doneCount    = Object.values(results).reduce((n, r) =>
    n + Object.values(r.pasos).filter(p => p.status === 'ok' || p.status === 'error').length, 0)

  // Resumen global
  const summary = React.useMemo(() => {
    let ok = 0, err = 0, regr = 0, warn = 0
    for (const r of Object.values(results)) {
      const golden = loadGolden(r.expId)
      for (const pr of Object.values(r.pasos)) {
        if (pr.status === 'ok')    ok++
        if (pr.status === 'error') err++
        if (!pr.data) continue
        for (const met of pr.data.metrics) {
          if (typeof met.value !== 'number') continue
          const gm = getGoldenMetric(golden, pr.paso, met.key)
          if (!gm || typeof gm.value !== 'number') continue
          const lvl = diffLevel(pr.paso, met.key, met.value, gm.value as number)
          if (lvl === 'error')   regr++
          if (lvl === 'warning') warn++
        }
      }
    }
    return { ok, err, regr, warn }
  }, [results, goldenVersion])

  return (
    <div className="flex flex-col h-full bg-oag-bg">

      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-oag-border flex-shrink-0">
        <div>
          <h1 className="text-lg font-bold text-oag-text flex items-center gap-2">
            <BarChart2 size={18} className="text-oag-blue" />
            Suite de Testing
          </h1>
          <p className="text-xs text-oag-muted mt-0.5">
            Ejecutá y comparás pasos en lote · Golden guardado localmente
          </p>
        </div>

        <div className="flex items-center gap-2">
          {runState === 'running' && (
            <span className="text-xs text-blue-600 font-medium tabular-nums">
              {doneCount}/{totalCount}
            </span>
          )}
          {runState === 'done' && (
            <button onClick={() => { setResults({}); setRunState('idle') }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded border border-gray-200 transition-colors">
              <RefreshCw size={11} /> Limpiar
            </button>
          )}

          {runState === 'running' ? (
            <button onClick={() => { abortRef.current = true; setRunState('done') }}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-md transition-colors">
              <Square size={13} /> Detener
            </button>
          ) : (
            <>
              {/* Modo analizar (sin ejecutar) */}
              <button
                onClick={() => handleRun('analizar')}
                disabled={selectedExps.size === 0 || selectedPasos.size === 0 || isLoading}
                title="Lee los resultados actuales sin re-ejecutar los pasos"
                className={cn(
                  'flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-md border transition-colors',
                  selectedExps.size > 0
                    ? 'border-gray-300 text-gray-700 hover:bg-gray-100'
                    : 'border-gray-200 text-gray-400 cursor-not-allowed',
                )}>
                <Eye size={14} /> Analizar
              </button>

              {/* Modo ejecutar (re-corre los pasos) */}
              <button
                onClick={() => handleRun('ejecutar')}
                disabled={selectedExps.size === 0 || selectedPasos.size === 0 || isLoading}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors',
                  selectedExps.size > 0 && selectedPasos.size > 0
                    ? 'bg-oag-blue hover:bg-blue-700 text-white'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed',
                )}>
                <Play size={14} />
                Ejecutar
                {selectedExps.size > 0 && (
                  <span className="text-blue-200 text-xs">
                    {selectedExps.size}DS · P{[...selectedPasos].sort().join(',')}
                  </span>
                )}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">

        {/* ── Panel izquierdo ───────────────────────────────────────────── */}
        <div className="w-52 flex-shrink-0 bg-white border-r border-oag-border flex flex-col overflow-y-auto">
          {/* Pasos */}
          <div className="px-4 pt-4 pb-3">
            <p className="text-[10px] font-semibold text-oag-muted uppercase tracking-widest mb-2">Pasos</p>
            {PASOS.map(p => (
              <label key={p} className="flex items-center gap-2 py-0.5 cursor-pointer">
                <input type="checkbox" checked={selectedPasos.has(p)} onChange={() => togglePaso(p)}
                  disabled={runState === 'running'}
                  className="w-3.5 h-3.5 rounded accent-oag-blue" />
                <span className="text-xs text-gray-700">
                  <span className="font-bold text-oag-blue mr-1">{p}</span>{PASO_LABELS[p]}
                </span>
              </label>
            ))}
          </div>

          <div className="border-t border-oag-border" />

          {/* Expedientes */}
          <div className="px-4 pt-3 pb-4 flex-1">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-semibold text-oag-muted uppercase tracking-widest">DS</p>
              <button onClick={toggleAllExps} disabled={runState === 'running'}
                className="text-[10px] text-oag-blue hover:underline">
                {selectedExps.size === expedientes.length ? 'Ninguno' : 'Todos'}
              </button>
            </div>
            {isLoading
              ? <Loader size={14} className="animate-spin text-gray-400 mx-auto mt-4" />
              : expedientes.map((exp: any) => (
                <label key={exp.id} className="flex items-start gap-2 py-1 cursor-pointer">
                  <input type="checkbox" checked={selectedExps.has(exp.id)} onChange={() => toggleExp(exp.id)}
                    disabled={runState === 'running'}
                    className="w-3.5 h-3.5 rounded accent-oag-blue mt-0.5 flex-shrink-0" />
                  <span className="text-xs text-gray-700 leading-tight">
                    {exp.nombre_distribuidor}
                    {loadGolden(exp.id) && <span className="ml-1 text-yellow-500 text-[10px]">⭐</span>}
                    <br />
                    <span className="text-[10px] text-gray-400">
                      {exp.anio_analisis} · P{(exp.pasos_completados || []).join(',')}
                    </span>
                  </span>
                </label>
              ))
            }
          </div>
        </div>

        {/* ── Panel derecho: resultados ─────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">

          {/* Progress bar global */}
          {runState === 'running' && totalCount > 0 && (
            <div className="bg-white rounded-lg border border-blue-200 px-4 py-2.5 flex items-center gap-3">
              <Loader size={13} className="animate-spin text-blue-500 flex-shrink-0" />
              <div className="flex-1">
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>Procesando…</span>
                  <span className="tabular-nums">{doneCount}/{totalCount}</span>
                </div>
                <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full transition-all duration-300"
                    style={{ width: `${(doneCount / totalCount) * 100}%` }} />
                </div>
              </div>
            </div>
          )}

          {/* Empty state */}
          {Object.keys(results).length === 0 && runState === 'idle' && (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <BarChart2 size={40} className="text-gray-200 mb-3" />
              <p className="text-sm font-medium text-gray-400">Seleccioná DS y pasos</p>
              <p className="text-xs text-gray-400 mt-1 max-w-xs">
                <b>Ejecutar</b>: re-corre los pasos (más lento, testea el pipeline completo)<br />
                <b>Analizar</b>: lee los resultados actuales sin re-ejecutar (rápido)
              </p>
            </div>
          )}

          {/* Cards */}
          {expedientes
            .filter((e: any) => results[e.id])
            .map((e: any) => (
              <ExpCard
                key={`${e.id}-${goldenVersion}`}
                result={results[e.id]}
                onSaveGolden={() => { saveGolden(e.id, e.nombre_distribuidor, results[e.id].pasos); setGoldenVersion(v => v + 1) }}
                onClearGolden={() => { clearGolden(e.id); setGoldenVersion(v => v + 1) }}
              />
            ))}

          {/* Resumen global */}
          {runState === 'done' && Object.keys(results).length > 0 && (
            <div className="bg-white rounded-lg border border-oag-border px-4 py-3">
              <p className="text-xs font-semibold text-gray-500 mb-2">Resumen global</p>
              <div className="flex flex-wrap gap-5 text-xs">
                <span className={summary.ok > 0 ? 'text-green-700' : 'text-gray-400'}>
                  <CheckCircle size={11} className="inline mr-1" />{summary.ok} pasos OK
                </span>
                {summary.err > 0 && (
                  <span className="text-red-700">
                    <XCircle size={11} className="inline mr-1" />{summary.err} con error
                  </span>
                )}
                {summary.regr > 0
                  ? <span className="text-red-700 font-semibold">
                      <TrendingDown size={11} className="inline mr-1" />
                      {summary.regr} regresión{summary.regr !== 1 ? 'es' : ''} vs golden
                    </span>
                  : summary.ok > 0
                  ? <span className="text-green-700">✓ Sin regresiones vs golden</span>
                  : null
                }
                {summary.warn > 0 && summary.regr === 0 && (
                  <span className="text-yellow-700">
                    <AlertTriangle size={11} className="inline mr-1" />{summary.warn} warnings
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
