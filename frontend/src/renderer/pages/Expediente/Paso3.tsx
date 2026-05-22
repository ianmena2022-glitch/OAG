import React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { expedientesAPI, pasosAPI } from '../../lib/api'
import { useNotificationStore } from '../../store'
import { formatUSD } from '../../lib/utils'
import FileUpload from '../../components/FileUpload'
import DataTable, { Column } from '../../components/DataTable'
import { Play, Loader, Info } from 'lucide-react'
import { cn } from '../../lib/utils'

interface Props { expediente: any }

export default function Paso3({ expediente }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [uploading, setUploading] = React.useState(false)

  const archivos = expediente.archivos || []
  const getArchivo = (tipo: string) => archivos.find((a: any) => a.tipo === tipo)

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      await expedientesAPI.subirArchivo(expediente.id, 'CRM', file)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      push('success', 'CRM cargado correctamente')
    } catch { push('error', 'Error al subir archivo') }
    finally { setUploading(false) }
  }

  const { data: resultado } = useQuery({
    queryKey: ['paso3', expediente.id],
    queryFn: () => pasosAPI.resultadoPaso(expediente.id, 3).then((r) => r.data),
    enabled: expediente.pasos_completados?.includes(3),
    retry: false,
  })

  const ejecutarMutation = useMutation({
    mutationFn: () => pasosAPI.ejecutarPaso(expediente.id, 3),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      qc.invalidateQueries({ queryKey: ['paso3', expediente.id] })
      push('success', 'Paso 3 completado — justificaciones IA generadas')
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error en Paso 3'),
  })

  const canRun = expediente.pasos_completados?.includes(2) && getArchivo('CRM')
  const conciliacion = resultado?.conciliacion || []
  const resumen = resultado?.resumen || {}

  const columns: Column<any>[] = [
    { key: 'producto', label: 'Producto', width: '160px' },
    { key: 'fecha', label: 'Fecha', type: 'date', width: '90px' },
    { key: 'tipo_comprobante', label: 'Tipo', width: '55px', align: 'center' },
    { key: 'numero_comprobante', label: 'Comprobante', width: '130px' },
    { key: 'cuit_cliente', label: 'CUIT', width: '120px' },
    { key: 'cantidad_gestion', label: 'Cant. Gestión', type: 'number', align: 'right', width: '100px' },
    { key: 'cantidad_crm', label: 'Cant. CRM', type: 'number', align: 'right', width: '90px' },
    { key: 'diferencia_cantidad', label: 'Δ Cant.', type: 'number', align: 'right', width: '80px',
      render: (v) => <span className={cn('font-mono', v !== 0 ? 'text-red-700' : 'text-green-700')}>{v ?? '—'}</span>
    },
    { key: 'monto_gestion_usd', label: 'Monto Gestión', type: 'usd', align: 'right', width: '120px' },
    { key: 'monto_crm_usd', label: 'Monto CRM', type: 'usd', align: 'right', width: '110px' },
    { key: 'diferencia_monto', label: 'Δ Monto', type: 'usd', align: 'right', width: '110px',
      render: (v) => <span className={cn('font-mono', Math.abs(v ?? 0) > 1 ? 'text-red-700 font-semibold' : 'text-green-700')}>{formatUSD(v)}</span>
    },
    { key: 'justificacion', label: 'Justificación', render: (v) => <span className="text-xs text-oag-muted">{v}</span> },
  ]

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-oag-text">Paso 3 — Cruce CRM</h2>
        <p className="text-xs text-oag-muted mt-0.5">
          Comparación de ventas Syngenta (gestión) vs reporte CRM de Syngenta. Justificaciones automáticas con IA.
        </p>
      </div>

      <div className="card p-4">
        <h3 className="section-title">Archivos Requeridos</h3>
        <div className="max-w-sm">
          <FileUpload
            label="Reporte CRM Syngenta"
            description="Archivo Excel con las ventas reportadas en el CRM de Syngenta"
            onUpload={handleUpload}
            isLoading={uploading}
            isUploaded={!!getArchivo('CRM')}
            uploadedName={getArchivo('CRM')?.nombre_original}
          />
        </div>
      </div>

      <div className="flex items-start gap-3">
        <div className="flex-1 card p-3 flex items-start gap-2">
          <Info size={14} className="text-oag-blue mt-0.5 flex-shrink-0" />
          <p className="text-xs text-oag-muted">
            Se usan solo los productos de Syngenta del Paso 2. Las justificaciones de diferencias
            son generadas automáticamente por IA y pueden editarse manualmente si es necesario.
          </p>
        </div>
        <button
          className="btn-primary flex items-center gap-2 flex-shrink-0"
          onClick={() => ejecutarMutation.mutate()}
          disabled={!canRun || ejecutarMutation.isPending}
        >
          {ejecutarMutation.isPending ? <Loader size={14} className="animate-spin" /> : <Play size={14} />}
          {ejecutarMutation.isPending ? 'Procesando...' : 'Ejecutar Cruce CRM'}
        </button>
      </div>

      {resultado && (
        <>
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Total líneas', value: resumen.total_lineas, color: '' },
              { label: 'Sin diferencia', value: resumen.sin_diferencia, color: 'text-green-700' },
              { label: 'Con diferencia', value: resumen.con_diferencia, color: resumen.con_diferencia > 0 ? 'text-yellow-700' : 'text-green-700' },
              { label: 'Solo gestión / solo CRM', value: (resumen.solo_gestion ?? 0) + (resumen.solo_crm ?? 0), color: 'text-red-700' },
            ].map((s, i) => (
              <div key={i} className="card p-3">
                <p className="text-xs text-oag-muted">{s.label}</p>
                <p className={cn('text-xl font-bold mt-0.5', s.color || 'text-oag-text')}>{s.value}</p>
              </div>
            ))}
          </div>

          <div className="card p-5">
            <h3 className="section-title">Conciliación CRM</h3>
            <DataTable
              columns={columns}
              data={conciliacion}
              searchable
              searchKeys={['producto', 'numero_comprobante', 'cuit_cliente']}
              maxHeight="360px"
              rowClassName={(row) =>
                row.estado === 'DIFERENCIA' ? 'bg-yellow-50/60' :
                row.estado === 'SOLO_GESTION' || row.estado === 'SOLO_CRM' ? 'bg-red-50/30' : ''
              }
            />
          </div>
        </>
      )}
    </div>
  )
}
