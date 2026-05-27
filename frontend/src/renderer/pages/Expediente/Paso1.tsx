import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { expedientesAPI, pasosAPI } from '../../lib/api'
import { useNotificationStore } from '../../store'
import { formatUSD, downloadBlob } from '../../lib/utils'
import FileUpload from '../../components/FileUpload'
import DataTable, { Column } from '../../components/DataTable'
import { Play, Download, Loader, CheckCircle, AlertTriangle, Info } from 'lucide-react'
import { cn } from '../../lib/utils'
import PasoFeedback from '../../components/PasoFeedback'

interface Props { expediente: any }

const ESTADO_COLORS: Record<string, string> = {
  OK: 'text-green-700 bg-green-50',
  DIFERENCIA: 'text-yellow-700 bg-yellow-50',
  SOLO_ARCA: 'text-red-700 bg-red-50',
  SOLO_GESTION: 'text-orange-700 bg-orange-50',
}

export default function Paso1({ expediente }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [uploading, setUploading] = useState<Record<string, boolean>>({})

  const archivos = expediente.archivos || []
  const getArchivo = (tipo: string) => archivos.find((a: any) => a.tipo === tipo)

  const handleUpload = async (tipo: string, file: File) => {
    setUploading((p) => ({ ...p, [tipo]: true }))
    try {
      await expedientesAPI.subirArchivo(expediente.id, tipo, file)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      push('success', `${tipo.replace('_', ' ')} cargado correctamente`)
    } catch {
      push('error', 'Error al subir archivo')
    } finally {
      setUploading((p) => ({ ...p, [tipo]: false }))
    }
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
    getArchivo('BAJADA_GESTION') &&
    getArchivo('COMPROBANTES_EMITIDOS') &&
    getArchivo('TIPOS_CAMBIO')

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
      key: 'estado', label: 'Estado', width: '110px', align: 'center',
      render: (v) => (
        <span className={cn('text-xs px-2 py-0.5 rounded font-medium', ESTADO_COLORS[v] || '')}>
          {v}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-5">
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
        <div className="grid grid-cols-3 gap-4">
          <FileUpload
            label="Bajada de Gestión"
            description="Reporte de ventas del ERP del distribuidor"
            onUpload={(f) => handleUpload('BAJADA_GESTION', f)}
            isLoading={uploading['BAJADA_GESTION']}
            isUploaded={!!getArchivo('BAJADA_GESTION')}
            uploadedName={getArchivo('BAJADA_GESTION')?.nombre_original}
          />
          <FileUpload
            label="Comprobantes Emitidos (ARCA)"
            description="Descarga de mis comprobantes emitidos desde ARCA"
            onUpload={(f) => handleUpload('COMPROBANTES_EMITIDOS', f)}
            isLoading={uploading['COMPROBANTES_EMITIDOS']}
            isUploaded={!!getArchivo('COMPROBANTES_EMITIDOS')}
            uploadedName={getArchivo('COMPROBANTES_EMITIDOS')?.nombre_original}
          />
          <FileUpload
            label="Tipos de Cambio"
            description="Archivo con fecha y cotización ARS/USD"
            onUpload={(f) => handleUpload('TIPOS_CAMBIO', f)}
            isLoading={uploading['TIPOS_CAMBIO']}
            isUploaded={!!getArchivo('TIPOS_CAMBIO')}
            uploadedName={getArchivo('TIPOS_CAMBIO')?.nombre_original}
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

          {/* Resumen */}
          <div className="grid grid-cols-6 gap-3">
            {[
              { label: 'Total ARCA', value: resumen.total_arca, color: '' },
              { label: 'Total Gestión', value: resumen.total_gestion, color: '' },
              { label: 'Match OK', value: resumen.ok, color: 'text-green-700' },
              { label: 'Diferencias', value: resumen.con_diferencia, color: resumen.con_diferencia > 0 ? 'text-yellow-700' : 'text-green-700' },
              { label: 'Solo ARCA', value: resumen.solo_arca, color: resumen.solo_arca > 0 ? 'text-red-700' : '' },
              { label: 'Solo Gestión', value: resumen.solo_gestion, color: resumen.solo_gestion > 0 ? 'text-orange-700' : '' },
            ].map((s, i) => (
              <div key={i} className="card p-3">
                <p className="text-xs text-oag-muted">{s.label}</p>
                <p className={cn('text-xl font-bold mt-0.5', s.color || 'text-oag-text')}>{s.value}</p>
              </div>
            ))}
          </div>

          {/* Montos totales */}
          <div className="grid grid-cols-2 gap-3">
            <div className="card p-3">
              <p className="text-xs text-oag-muted">Total Facturado ARCA (USD)</p>
              <p className="text-lg font-bold text-oag-text">{formatUSD(resumen.monto_total_arca_usd)}</p>
            </div>
            <div className="card p-3">
              <p className="text-xs text-oag-muted">Total Facturado Gestión (USD)</p>
              <p className="text-lg font-bold text-oag-text">{formatUSD(resumen.monto_total_gestion_usd)}</p>
            </div>
          </div>

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
                row.estado === 'SOLO_GESTION' ? 'bg-orange-50/40' : ''
              }
            />
          </div>
        </>
      )}
    </div>
  )
}
