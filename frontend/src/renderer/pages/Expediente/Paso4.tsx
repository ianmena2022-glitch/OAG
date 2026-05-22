import React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { expedientesAPI, pasosAPI } from '../../lib/api'
import { useNotificationStore } from '../../store'
import { formatUSD } from '../../lib/utils'
import FileUpload from '../../components/FileUpload'
import DataTable, { Column } from '../../components/DataTable'
import { Play, Loader, Info } from 'lucide-react'

interface Props { expediente: any }

const MESES_SHORT = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const MESES_FULL = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

export default function Paso4({ expediente }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [uploading, setUploading] = React.useState<Record<string, boolean>>({})

  const archivos = expediente.archivos || []
  const getArchivo = (tipo: string) => archivos.find((a: any) => a.tipo === tipo)

  const handleUpload = async (tipo: string, file: File) => {
    setUploading((p) => ({ ...p, [tipo]: true }))
    try {
      await expedientesAPI.subirArchivo(expediente.id, tipo, file)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      push('success', 'Archivo cargado')
    } catch { push('error', 'Error al subir') }
    finally { setUploading((p) => ({ ...p, [tipo]: false })) }
  }

  const { data: resultado } = useQuery({
    queryKey: ['paso4', expediente.id],
    queryFn: () => pasosAPI.resultadoPaso(expediente.id, 4).then((r) => r.data),
    enabled: expediente.pasos_completados?.includes(4),
    retry: false,
  })

  const ejecutarMutation = useMutation({
    mutationFn: () => pasosAPI.ejecutarPaso(expediente.id, 4),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      qc.invalidateQueries({ queryKey: ['paso4', expediente.id] })
      push('success', 'Análisis de compras completado')
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error en Paso 4'),
  })

  const canRun = getArchivo('COMPROBANTES_RECIBIDOS') && getArchivo('TIPOS_CAMBIO')
  const resumen = resultado?.resumen || []
  const totales = resultado?.totales || {}

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-oag-text">Paso 4 — Análisis Detallado de Compras</h2>
        <p className="text-xs text-oag-muted mt-0.5">
          Comprobantes recibidos de ARCA: resumen de compras por proveedor y mes en USD.
        </p>
      </div>

      <div className="card p-4">
        <h3 className="section-title">Archivos Requeridos</h3>
        <div className="grid grid-cols-2 gap-4">
          <FileUpload
            label="Comprobantes Recibidos (ARCA)"
            description="Descarga de mis comprobantes recibidos desde ARCA"
            onUpload={(f) => handleUpload('COMPROBANTES_RECIBIDOS', f)}
            isLoading={uploading['COMPROBANTES_RECIBIDOS']}
            isUploaded={!!getArchivo('COMPROBANTES_RECIBIDOS')}
            uploadedName={getArchivo('COMPROBANTES_RECIBIDOS')?.nombre_original}
          />
          <FileUpload
            label="Proveedores con Apertura por Tipo"
            description="Lista de proveedores que requieren desglose FC/NC/ND"
            onUpload={(f) => handleUpload('PROVEEDORES_APERTURA', f)}
            isLoading={uploading['PROVEEDORES_APERTURA']}
            isUploaded={!!getArchivo('PROVEEDORES_APERTURA')}
            uploadedName={getArchivo('PROVEEDORES_APERTURA')?.nombre_original}
          />
        </div>
        <p className="text-xs text-oag-muted mt-2">
          * Los tipos de cambio se toman del archivo ya cargado en el Paso 1.
        </p>
      </div>

      <div className="flex items-start gap-3">
        <div className="flex-1 card p-3 flex items-start gap-2">
          <Info size={14} className="text-oag-blue mt-0.5 flex-shrink-0" />
          <p className="text-xs text-oag-muted">
            Las notas de crédito se negativizan automáticamente. Todo se convierte a USD.
            Los proveedores en la lista de apertura muestran subtotales por FC, NC y ND.
          </p>
        </div>
        <button
          className="btn-primary flex items-center gap-2 flex-shrink-0"
          onClick={() => ejecutarMutation.mutate()}
          disabled={!canRun || ejecutarMutation.isPending}
        >
          {ejecutarMutation.isPending ? <Loader size={14} className="animate-spin" /> : <Play size={14} />}
          {ejecutarMutation.isPending ? 'Procesando...' : 'Ejecutar Análisis'}
        </button>
      </div>

      {resultado && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="card p-3">
              <p className="text-xs text-oag-muted">Total Compras (USD)</p>
              <p className="text-lg font-bold text-oag-text">{formatUSD(totales.total_compras_usd)}</p>
            </div>
            <div className="card p-3">
              <p className="text-xs text-oag-muted">Total Proveedores</p>
              <p className="text-lg font-bold text-oag-text">{totales.total_proveedores}</p>
            </div>
          </div>

          {/* Tabla resumen compras */}
          <div className="card p-5">
            <h3 className="section-title">Resumen de Compras por Proveedor (USD)</h3>
            <div className="overflow-auto max-h-96">
              <table className="w-full border-collapse text-xs">
                <thead className="sticky top-0">
                  <tr>
                    <th className="table-header text-left min-w-[220px]">Proveedor</th>
                    <th className="table-header text-center w-28">CUIT</th>
                    {MESES_FULL.map((m) => (
                      <th key={m} className="table-header text-right w-20">{m.slice(0, 3)}</th>
                    ))}
                    <th className="table-header text-right w-24">Total USD</th>
                  </tr>
                </thead>
                <tbody>
                  {resumen.map((row: any, i: number) => (
                    <tr key={i} className={i % 2 === 0 ? 'bg-white hover:bg-blue-50/20' : 'bg-oag-zebra hover:bg-blue-50/20'}>
                      <td className="table-cell font-medium">{row.nombre_proveedor}</td>
                      <td className="table-cell text-center text-oag-muted">{row.cuit_proveedor}</td>
                      {MESES_FULL.map((m) => (
                        <td key={m} className="table-cell text-right font-mono">
                          {row[m] ? formatUSD(row[m]).replace('USD ', '') : '—'}
                        </td>
                      ))}
                      <td className="table-cell text-right font-mono font-bold">{formatUSD(row.Total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
