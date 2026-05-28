import React, { useState } from 'react'
import { AlertTriangle, Sparkles, CheckCircle, ChevronDown, ChevronRight, FileWarning, FileCheck } from 'lucide-react'
import { cn } from '../lib/utils'

interface ValidacionAlerta {
  nivel?: 'info' | 'warning' | 'error'
  titulo?: string
  detalle?: string
  sugerencia?: string
}

interface Validacion {
  ok?: boolean
  severidad?: 'info' | 'warning' | 'error'
  alertas?: ValidacionAlerta[]
}

interface ParserDiagnostico {
  archivo: string
  metodo: 'keywords' | 'ia' | 'ia_thinking' | 'cache'
  confianza: number
  mapping: Record<string, string | null>
  columnas_archivo?: string[]
  columnas_faltantes?: string[]
  columnas_no_mapeadas?: string[]
  warnings?: string[]
  registros_procesados?: number
  filas_en_archivo?: number
}

interface Props {
  validacion?: Validacion | null
  parserDiagnostico?: ParserDiagnostico[] | { items?: ParserDiagnostico[] } | null
  /** Versión vieja (lista de strings). Si se pasa parserDiagnostico, se ignora. */
  parserWarnings?: string[] | { warnings?: string[] } | null
}

const METODO_LABELS: Record<string, string> = {
  keywords: 'Detección automática (keywords)',
  ia: 'IA (Claude)',
  ia_thinking: 'IA con razonamiento profundo',
  cache: 'Cache (archivo ya procesado)',
}

function ParserDiagnosticoCard({ item }: { item: ParserDiagnostico }) {
  const [expanded, setExpanded] = useState(false)
  const tieneFaltantes = (item.columnas_faltantes?.length || 0) > 0
  const bajaConfianza = item.confianza < 0.85
  const tieneWarnings = (item.warnings?.length || 0) > 0
  const hayProblema = tieneFaltantes || bajaConfianza || tieneWarnings

  return (
    <div
      className={cn(
        'card border',
        hayProblema ? 'border-yellow-300 bg-yellow-50/60' : 'border-green-200 bg-green-50/40'
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-start gap-2 text-left"
      >
        {hayProblema ? (
          <FileWarning size={14} className="text-yellow-700 mt-0.5 flex-shrink-0" />
        ) : (
          <FileCheck size={14} className="text-green-700 mt-0.5 flex-shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-oag-text flex items-center gap-2">
            {item.archivo}
            <span className="text-oag-muted font-normal">
              · {METODO_LABELS[item.metodo] || item.metodo} · confianza {Math.round(item.confianza * 100)}%
            </span>
          </p>
          {tieneFaltantes && (
            <p className="text-xs text-red-700 mt-1 font-medium">
              ⚠ No se detectaron las columnas: {item.columnas_faltantes!.join(', ')}
            </p>
          )}
          {!tieneFaltantes && hayProblema && (
            <p className="text-xs text-yellow-800 mt-1">
              {bajaConfianza ? 'Detección con baja confianza — revisar el mapeo' : 'Hay advertencias'}
            </p>
          )}
          {!hayProblema && (
            <p className="text-xs text-green-800 mt-1">
              Todas las columnas detectadas correctamente
            </p>
          )}
          {item.registros_procesados !== undefined && (
            <p className={cn(
              'text-xs mt-1 font-medium',
              item.registros_procesados === 0 ? 'text-red-700' : 'text-oag-muted'
            )}>
              {item.registros_procesados === 0
                ? `⚠ 0 registros procesados de ${item.filas_en_archivo ?? '?'} filas`
                : `${item.registros_procesados} registros procesados de ${item.filas_en_archivo ?? '?'} filas`}
            </p>
          )}
        </div>
        {expanded ? (
          <ChevronDown size={14} className="text-oag-muted flex-shrink-0 mt-0.5" />
        ) : (
          <ChevronRight size={14} className="text-oag-muted flex-shrink-0 mt-0.5" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-1 border-t border-yellow-200/60 space-y-3">
          {/* Mapeo de columnas */}
          <div>
            <p className="text-xs font-medium text-oag-text mb-1.5">Mapeo de columnas detectado:</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs bg-white rounded border border-oag-border p-2.5">
              {Object.entries(item.mapping).map(([std, orig]) => (
                <div key={std} className="flex gap-2">
                  <span className="text-oag-muted min-w-[140px]">{std}:</span>
                  {orig ? (
                    <span className="font-medium text-oag-text truncate" title={orig}>
                      {orig}
                    </span>
                  ) : (
                    <span className="italic text-red-700">(no detectada)</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Columnas del archivo (para ayudar a corregir) */}
          {item.columnas_archivo && item.columnas_archivo.length > 0 && (
            <div>
              <p className="text-xs font-medium text-oag-text mb-1.5">
                Columnas reales del archivo ({item.columnas_archivo.length}):
              </p>
              <div className="text-xs bg-white rounded border border-oag-border p-2.5 max-h-32 overflow-y-auto">
                {item.columnas_archivo.map((c, i) => (
                  <span
                    key={i}
                    className={cn(
                      'inline-block mr-2 mb-1 px-1.5 py-0.5 rounded text-xs',
                      Object.values(item.mapping).includes(c)
                        ? 'bg-green-100 text-green-900 border border-green-300'
                        : 'bg-oag-light text-oag-muted border border-oag-border'
                    )}
                  >
                    {c}
                  </span>
                ))}
              </div>
              <p className="text-xs text-oag-muted mt-1 italic">
                Verde = usada en el mapeo · Gris = no se usó
              </p>
            </div>
          )}

          {/* Warnings textuales */}
          {tieneWarnings && (
            <div>
              <p className="text-xs font-medium text-oag-text mb-1.5">Advertencias:</p>
              <ul className="text-xs text-yellow-800 space-y-0.5 bg-white rounded border border-yellow-200 p-2.5">
                {item.warnings!.map((w, i) => (
                  <li key={i}>• {w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Sugerencias contextuales */}
          {tieneFaltantes && (
            <div className="text-xs text-oag-muted bg-blue-50/50 border border-blue-200 rounded p-2.5">
              <strong className="text-oag-text">¿Qué hacer?</strong> Renombrá las columnas del archivo
              fuente a nombres más claros (ej: "Número Desde" → para número de comprobante) y volvé a subir el archivo,
              o pedile a IT que estandarice el formato del export.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Muestra el diagnóstico estructurado de parseo (por archivo) + alertas IA post-paso.
 */
export default function PasoFeedback({ validacion, parserDiagnostico, parserWarnings }: Props) {
  // Compatibilidad con la versión vieja (strings)
  const legacyWarnings: string[] =
    Array.isArray(parserWarnings)
      ? parserWarnings
      : (parserWarnings as any)?.warnings || []

  const diagItems: ParserDiagnostico[] = Array.isArray(parserDiagnostico)
    ? parserDiagnostico
    : (parserDiagnostico as any)?.items || []

  const alertas = validacion?.alertas || []

  if (diagItems.length === 0 && legacyWarnings.length === 0 && alertas.length === 0) {
    return null
  }

  return (
    <div className="space-y-3">
      {/* Diagnóstico estructurado por archivo */}
      {diagItems.map((item, i) => (
        <ParserDiagnosticoCard key={i} item={item} />
      ))}

      {/* Warnings sueltos (formato viejo, si todavía vienen) */}
      {legacyWarnings.length > 0 && (
        <div className="card p-4 border-yellow-200 bg-yellow-50/50">
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className="text-yellow-700 mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-xs font-semibold text-yellow-900 mb-1">Advertencias de parseo</p>
              <ul className="text-xs text-yellow-800 space-y-0.5">
                {legacyWarnings.map((w, i) => (
                  <li key={i}>• {w}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Validación IA del resultado */}
      {alertas.length > 0 && (
        <div
          className={cn(
            'card p-4 border',
            validacion?.severidad === 'error'
              ? 'border-red-300 bg-red-50/60'
              : validacion?.severidad === 'warning'
              ? 'border-orange-300 bg-orange-50/60'
              : 'border-blue-200 bg-blue-50/40'
          )}
        >
          <div className="flex items-center gap-2 mb-2">
            <Sparkles
              size={14}
              className={cn(
                validacion?.severidad === 'error'
                  ? 'text-red-700'
                  : validacion?.severidad === 'warning'
                  ? 'text-orange-700'
                  : 'text-blue-700'
              )}
            />
            <p className="text-xs font-semibold text-oag-text">Revisión del resultado</p>
          </div>
          <div className="space-y-2">
            {alertas.map((a, i) => (
              <div
                key={i}
                className="text-xs border-l-2 pl-3 py-0.5"
                style={{
                  borderColor:
                    a.nivel === 'error'
                      ? '#b91c1c'
                      : a.nivel === 'warning'
                      ? '#c2410c'
                      : '#1d4ed8',
                }}
              >
                {a.titulo && <p className="font-semibold text-oag-text">{a.titulo}</p>}
                {a.detalle && <p className="text-oag-muted mt-0.5">{a.detalle}</p>}
                {a.sugerencia && (
                  <p className="text-oag-muted italic mt-0.5">→ {a.sugerencia}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
