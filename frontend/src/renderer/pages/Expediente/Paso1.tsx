import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { expedientesAPI, pasosAPI } from '../../lib/api'
import { useNotificationStore } from '../../store'
import { formatUSD } from '../../lib/utils'
import FileUpload from '../../components/FileUpload'
import DataTable, { Column } from '../../components/DataTable'
import { Play, Loader, Info, Plus, Trash2, FileText, AlertTriangle, Pencil } from 'lucide-react'
import { cn } from '../../lib/utils'
import PasoFeedback from '../../components/PasoFeedback'
import EditAnotacionModal from '../../components/EditAnotacionModal'

interface Props { expediente: any }

const ESTADO_COLORS: Record<string, string> = {
  OK: 'text-green-700 bg-green-50',
  DIFERENCIA: 'text-yellow-700 bg-yellow-50',
  SOLO_ARCA: 'text-red-700 bg-red-50',
  SOLO_GESTION: 'text-orange-700 bg-orange-50',
  MANUAL: 'text-blue-700 bg-blue-50',
}

function formatSize(bytes?: number) {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function Paso1({ expediente }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [uploading, setUploading] = useState<Record<string, boolean>>({})
  const [erpUploading, setErpUploading] = useState(0)   // contador de uploads ERP en curso
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [editingRow, setEditingRow] = useState<any | null>(null)

  const archivos = expediente.archivos || []
  const getArchivo = (tipo: string) => archivos.find((a: any) => a.tipo === tipo)
  const archivosGestion: any[] = archivos.filter((a: any) => a.tipo === 'BAJADA_GESTION')

  const handleUploadErp = async (file: File) => {
    setErpUploading((n) => n + 1)
    try {
      await expedientesAPI.subirArchivo(expediente.id, 'BAJADA_GESTION', file)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      push('success', `"${file.name}" cargado`)
    } catch (err: any) {
      push('error', err.response?.data?.detail || `Error al subir "${file.name}"`)
    } finally {
      setErpUploading((n) => n - 1)
    }
  }

  const handleUpload = async (tipo: string, file: File) => {
    setUploading((p) => ({ ...p, [tipo]: true }))
    try {
      await expedientesAPI.subirArchivo(expediente.id, tipo, file)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      push('success', 'Archivo cargado correctamente')
    } catch (err: any) {
      push('error', err.response?.data?.detail || 'Error al subir archivo')
    } finally {
      setUploading((p) => ({ ...p, [tipo]: false }))
    }
  }

  const handleDeleteArchivo = async (archivoId: number, nombre: string) => {
    setDeletingId(archivoId)
    try {
      await expedientesAPI.eliminarArchivo(expediente.id, archivoId)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      push('success', `"${nombre}" eliminado`)
    } catch {
      push('error', 'Error al eliminar archivo')
    } finally {
      setDeletingId(null)
    }
  }

  const handleErpFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    files.forEach((file) => handleUploadErp(file))
    // Resetear el input para que el mismo archivo pueda volver a seleccionarse
    e.target.value = ''
  }

  const { data: resultado, isLoading: loadingResultado } = useQuery({
    queryKey: ['paso1', expediente.id],
    queryFn: () => pasosAPI.resultadoPaso(expediente.id, 1).then((r) => r.data),
    enabled: expediente.pasos_completados?.includes(1),
    retry: false,
  })

  const ejecutarMutation = useMutation({
    mutationFn: () => pasosAPI.ejecutarPaso(expediente.id, 1),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      qc.invalidateQueries({ queryKey: ['paso1', expediente.id] })
      push('success', 'Paso 1 ejecutado correctamente')
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error al ejecutar Paso 1'),
  })

  const conciliacion = resultado?.conciliacion || []
  const resumen = resultado?.resumen || {}

  const canRun =
    archivosGestion.length > 0 &&
    getArchivo('COMPROBANTES_EMITIDOS')

  const columns: Column<any>[] = [
    { key: 'fecha', label: 'Fecha', type: 'date', width: '90px' },
    { key: 'tipo', label: 'Tipo', width: '60px', align: 'center' },
    { key: 'numero', label: 'Comprobante', width: '140px' },
    { key: 'cliente', label: 'Cliente' },
    { key: 'monto_usd_arca', label: 'Monto ARCA USD', type: 'usd', align: 'right', width: '130px' },
    { key: 'monto_usd_gestion', label: 'Monto Gestión USD', type: 'usd', align: 'right', width: '140px' },
    { key: 'diferencia_usd', label: 'Diferencia USD', type: 'usd', align: 'right', width: '120px',
      render: (v) => v != null ? (
        <span className={cn('font-mono', Math.abs(v) > 1 ? 'text-red-700 font-semibold' : 'text-green-700')}>
          {formatUSD(v)}
        </span>
      ) : '—'
    },
    {
      key: 'estado', label: 'Estado', width: '130px', align: 'center',
      render: (v, row: any) => {
        // Para MANUAL: marcar si está incompleta (sin clasificación agroquímico/Syngenta)
        // — no aporta al Paso 3 hasta que se complete.
        const incompleta =
          v === 'MANUAL' &&
          (row?.anotacion?.es_agroquimico == null ||
            (row?.anotacion?.es_agroquimico === true && !row?.anotacion?.producto))
        return (
          <div className="flex flex-col items-center gap-0.5">
            <span className={cn('text-xs px-2 py-0.5 rounded font-medium', ESTADO_COLORS[v] || '')}>
              {v}
            </span>
            {incompleta && (
              <span
                className="text-[10px] text-orange-700 font-medium"
                title="Falta clasificar como agroquímico Syngenta. No se incluye en Paso 3."
              >
                ⚠ sin clasificar
              </span>
            )}
          </div>
        )
      },
    },
    {
      key: '_edit', label: '', width: '40px', align: 'center',
      render: (_v: any, row: any) => (
        <button
          type="button"
          onClick={() => setEditingRow(row)}
          title="Editar anotación"
          className="w-7 h-7 flex items-center justify-center rounded bg-oag-blue text-white hover:bg-oag-blue/80 transition-colors flex-shrink-0"
        >
          <Pencil size={12} />
        </button>
      ),
    },
  ]

  return (
    <div className="space-y-5">
      {editingRow && (
        <EditAnotacionModal
          expedienteId={expediente.id}
          row={editingRow}
          onClose={() => setEditingRow(null)}
        />
      )}
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-oag-text">Paso 1 — Cruce de Base de Datos</h2>
        <p className="text-xs text-oag-muted mt-0.5">
          Comparación de bajada de gestión vs comprobantes emitidos (ARCA). Universo de referencia: ARCA.
        </p>
      </div>

      {/* Carga de archivos */}
      <div className="card p-5">
        <h3 className="section-title">Archivos Requeridos</h3>

        {/* Bajada de Gestión — multi-archivo */}
        <div className="mb-4">
          {/* Input de archivo — siempre presente, activado por el label */}
          <input
            id="erp-file-input"
            type="file"
            multiple
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={handleErpFileSelect}
          />

          <div className="flex items-center justify-between mb-2">
            <div>
              <p className="text-xs font-semibold text-oag-text">Bajada de Gestión (ERP)</p>
              <p className="text-xs text-oag-muted">
                Reportes de ventas del ERP — podés subir varios archivos (uno por tipo de comprobante o todo junto)
              </p>
            </div>
            <label
              htmlFor="erp-file-input"
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-colors cursor-pointer',
                archivosGestion.length === 0
                  ? 'border-oag-blue text-oag-blue hover:bg-oag-blue/5'
                  : 'border-oag-border text-oag-muted hover:text-oag-text hover:border-oag-text'
              )}
            >
              {erpUploading > 0 ? (
                <Loader size={12} className="animate-spin" />
              ) : (
                <Plus size={12} />
              )}
              {archivosGestion.length === 0 ? 'Agregar archivo ERP' : 'Agregar otro'}
              {erpUploading > 0 && ` (${erpUploading} subiendo...)`}
            </label>
          </div>

          {archivosGestion.length === 0 && erpUploading === 0 ? (
            <label
              htmlFor="erp-file-input"
              className="border-2 border-dashed border-oag-border rounded-lg p-6 text-center cursor-pointer hover:border-oag-blue/50 hover:bg-oag-blue/5 transition-colors block"
            >
              <FileText size={24} className="text-oag-muted mx-auto mb-2" />
              <p className="text-xs text-oag-muted">
                Hacé click para subir archivos ERP
              </p>
              <p className="text-xs text-oag-muted/70 mt-0.5">
                Podés subir uno por tipo: facturas, notas de crédito, etc.
              </p>
            </label>
          ) : (
            <div className="space-y-1.5">
              {erpUploading > 0 && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-blue-200 bg-blue-50/50">
                  <Loader size={13} className="text-blue-600 animate-spin flex-shrink-0" />
                  <span className="text-xs text-blue-700">
                    Subiendo {erpUploading} archivo{erpUploading > 1 ? 's' : ''}...
                  </span>
                </div>
              )}
              {archivosGestion.map((a: any) => (
                <div
                  key={a.id}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg border border-green-200 bg-green-50/50"
                >
                  <FileText size={13} className="text-green-700 flex-shrink-0" />
                  <span className="text-xs font-medium text-oag-text flex-1 truncate" title={a.nombre_original}>
                    {a.nombre_original}
                  </span>
                  {a.size_bytes && (
                    <span className="text-xs text-oag-muted flex-shrink-0">{formatSize(a.size_bytes)}</span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleDeleteArchivo(a.id, a.nombre_original)}
                    disabled={deletingId === a.id}
                    className="p-1 rounded hover:bg-red-100 text-oag-muted hover:text-red-700 transition-colors flex-shrink-0"
                    title="Eliminar este archivo"
                  >
                    {deletingId === a.id ? (
                      <Loader size={12} className="animate-spin" />
                    ) : (
                      <Trash2 size={12} />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ARCA — Tipos de Cambio se gestionan globalmente en Administración */}
        <div className="grid grid-cols-2 gap-4">
          <FileUpload
            label="Comprobantes Emitidos (ARCA)"
            description="Descarga de mis comprobantes emitidos desde ARCA"
            onUpload={(f) => handleUpload('COMPROBANTES_EMITIDOS', f)}
            isLoading={uploading['COMPROBANTES_EMITIDOS']}
            isUploaded={!!getArchivo('COMPROBANTES_EMITIDOS')}
            uploadedName={getArchivo('COMPROBANTES_EMITIDOS')?.nombre_original}
          />
        </div>
      </div>

      {/* Info + Ejecutar */}
      <div className="flex items-start gap-3">
        <div className="flex-1 card p-4 flex items-start gap-2">
          <Info size={14} className="text-oag-blue mt-0.5 flex-shrink-0" />
          <p className="text-xs text-oag-muted leading-relaxed">
            <strong className="text-oag-text">Importante:</strong> Las notas de crédito se negativizan automáticamente.
            Todo se convierte a USD usando los tipos de cambio provistos. La tolerancia de diferencia es de USD 1 por redondeo.
            La bajada de gestión normalizada queda disponible para el Paso 2.
          </p>
        </div>
        <button
          className="btn-primary flex items-center gap-2 flex-shrink-0"
          onClick={() => ejecutarMutation.mutate()}
          disabled={!canRun || ejecutarMutation.isPending}
        >
          {ejecutarMutation.isPending ? (
            <Loader size={14} className="animate-spin" />
          ) : (
            <Play size={14} />
          )}
          {ejecutarMutation.isPending ? 'Procesando...' : 'Ejecutar Cruce'}
        </button>
      </div>

      {/* Resultado */}
      {loadingResultado && (
        <div className="flex items-center justify-center py-8">
          <Loader size={20} className="animate-spin text-oag-muted" />
        </div>
      )}

      {resultado && (
        <>
          <PasoFeedback
            validacion={resultado.validacion}
            parserDiagnostico={resultado.parser_diagnostico}
          />

          {/* Alertas estructurales (SOLO_GESTION, etc.) */}
          {(resultado.alertas || []).map((alerta: any, i: number) => (
            <div key={i} className="card p-4 border-red-300 bg-red-50 flex items-start gap-3">
              <AlertTriangle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-800">{alerta.titulo}</p>
                <p className="text-xs text-red-700 mt-0.5 leading-relaxed">{alerta.detalle}</p>
              </div>
            </div>
          ))}

          {/* Resumen */}
          {resumen.archivos_gestion > 1 && (
            <div className="card p-3 border-blue-200 bg-blue-50/40 flex items-center gap-2">
              <FileText size={13} className="text-blue-700 flex-shrink-0" />
              <p className="text-xs text-blue-800">
                Se consolidaron <strong>{resumen.archivos_gestion} archivos ERP</strong> en el cruce
              </p>
            </div>
          )}
          <div className="grid grid-cols-6 gap-3">
            {[
              { label: 'Total ARCA', value: resumen.total_arca, color: '' },
              { label: 'Total Gestión', value: resumen.total_gestion, color: '' },
              { label: 'Match OK', value: resumen.ok, color: 'text-green-700' },
              { label: 'Diferencias', value: resumen.con_diferencia, color: resumen.con_diferencia > 0 ? 'text-yellow-700' : 'text-green-700' },
              { label: 'Solo ARCA', value: resumen.solo_arca, color: resumen.solo_arca > 0 ? 'text-red-700' : '' },
              { label: 'Solo Gestión', value: resumen.solo_gestion, color: resumen.solo_gestion > 0 ? 'text-red-700 font-extrabold' : '' },
            ].map((s, i) => (
              <div key={i} className="card p-3">
                <p className="text-xs text-oag-muted">{s.label}</p>
                <p className={cn('text-xl font-bold mt-0.5', s.color || 'text-oag-text')}>{s.value}</p>
              </div>
            ))}
          </div>

          {/* Montos totales */}
          {(() => {
            const diff = (resumen.monto_total_gestion_usd ?? 0) - (resumen.monto_total_arca_usd ?? 0)
            const diffColor = Math.abs(diff) <= 1 ? 'text-green-700' : diff > 0 ? 'text-yellow-700' : 'text-red-700'
            return (
              <div className="grid grid-cols-3 gap-3">
                <div className="card p-3">
                  <p className="text-xs text-oag-muted">Total Facturado ARCA (USD)</p>
                  <p className="text-lg font-bold text-oag-text">{formatUSD(resumen.monto_total_arca_usd)}</p>
                </div>
                <div className="card p-3">
                  <p className="text-xs text-oag-muted">Total Facturado Gestión (USD)</p>
                  <p className="text-lg font-bold text-oag-text">{formatUSD(resumen.monto_total_gestion_usd)}</p>
                </div>
                <div className="card p-3">
                  <p className="text-xs text-oag-muted">Diferencia Total (USD)</p>
                  <p className={cn('text-lg font-bold', diffColor)}>{formatUSD(diff)}</p>
                </div>
              </div>
            )
          })()}

          {/* Tabla de conciliación */}
          <div className="card p-5">
            <h3 className="section-title">Conciliación por Comprobante</h3>
            <DataTable
              columns={columns}
              data={conciliacion}
              searchable
              searchKeys={['numero', 'cliente', 'estado']}
              maxHeight="360px"
              rowClassName={(row) =>
                row.estado === 'DIFERENCIA' ? 'bg-yellow-50/60' :
                row.estado === 'SOLO_ARCA' ? 'bg-red-50/40' :
                row.estado === 'SOLO_GESTION' ? 'bg-orange-50/40' :
                row.estado === 'MANUAL' ? 'bg-blue-50/40' : ''
              }
            />
          </div>
        </>
      )}
    </div>
  )
}
