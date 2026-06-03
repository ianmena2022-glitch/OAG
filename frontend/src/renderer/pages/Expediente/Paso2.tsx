import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { expedientesAPI, pasosAPI } from '../../lib/api'
import { useNotificationStore } from '../../store'
import { formatUSD, formatPercent } from '../../lib/utils'
import FileUpload from '../../components/FileUpload'
import DataTable, { Column } from '../../components/DataTable'
import { Play, Loader, Info } from 'lucide-react'
import { cn } from '../../lib/utils'
import PasoFeedback from '../../components/PasoFeedback'

interface Props { expediente: any }

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const MESES_FULL = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

export default function Paso2({ expediente }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [tab, setTab] = useState<'ranking_c' | 'ranking_p' | 'muestreo' | 'clasificacion' | 'apertura'>('ranking_c')
  const [uploading, setUploading] = useState<Record<string, boolean>>({})
  // ran: true después de ejecutar por primera vez en esta sesión,
  // para que el query se dispare aunque pasos_completados aún no esté actualizado
  const [ran, setRan] = useState(false)

  const archivos = expediente.archivos || []
  const getArchivo = (tipo: string) => archivos.find((a: any) => a.tipo === tipo)

  const handleUpload = async (tipo: string, file: File) => {
    setUploading((p) => ({ ...p, [tipo]: true }))
    try {
      await expedientesAPI.subirArchivo(expediente.id, tipo, file)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      push('success', 'Archivo cargado')
    } catch {
      push('error', 'Error al subir archivo')
    } finally {
      setUploading((p) => ({ ...p, [tipo]: false }))
    }
  }

  const { data: resultado, isLoading: loadingResultado } = useQuery({
    queryKey: ['paso2', expediente.id],
    queryFn: () => pasosAPI.resultadoPaso(expediente.id, 2).then((r) => r.data),
    enabled: !!expediente.pasos_completados?.includes(2) || ran,
    retry: false,
  })

  const ejecutarMutation = useMutation({
    mutationFn: () => pasosAPI.ejecutarPaso(expediente.id, 2),
    onSuccess: () => {
      setRan(true)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      qc.invalidateQueries({ queryKey: ['paso2', expediente.id] })
      push('success', 'Paso 2 ejecutado — clasificación con IA completada')
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error en Paso 2'),
  })

  const canRun = expediente.pasos_completados?.includes(1)

  // Columnas ranking clientes
  const colsClientes: Column<any>[] = [
    { key: 'cliente', label: 'Cliente', searchable: true },
    { key: 'total_usd', label: 'Total USD', type: 'usd', align: 'right', width: '130px' },
    { key: 'porcentaje', label: '% del total', type: 'percent', align: 'right', width: '100px' },
  ]

  const colsProductos: Column<any>[] = [
    { key: 'articulo', label: 'Producto' },
    { key: 'total_usd', label: 'Total USD', type: 'usd', align: 'right', width: '130px' },
    { key: 'porcentaje', label: '% del total', type: 'percent', align: 'right', width: '100px' },
  ]

  const colsMuestreo: Column<any>[] = [
    { key: 'fecha', label: 'Fecha', type: 'date', width: '90px' },
    { key: 'tipo_comprobante', label: 'Tipo', width: '60px', align: 'center' },
    { key: 'numero_comprobante', label: 'Comprobante', width: '140px' },
    { key: 'cliente', label: 'Cliente' },
    { key: 'monto_usd', label: 'Monto USD', type: 'usd', align: 'right', width: '120px' },
    {
      key: 'es_especial', label: 'Especial', width: '80px', align: 'center',
      render: (v) => v ? <span className="badge-warning">SÍ</span> : null,
    },
  ]

  const colsClasificacion: Column<any>[] = [
    { key: 'articulo', label: 'Producto' },
    {
      key: 'agroquimico', label: 'Agroquímico', width: '100px', align: 'center',
      render: (v) => v === 'SI' ? <span className="badge-ok">SÍ</span> :
        v === 'NO' ? <span className="badge-error">NO</span> :
        <span className="badge-warning">{v}</span>,
    },
    {
      key: 'syngenta', label: 'Syngenta', width: '90px', align: 'center',
      render: (v) => v === 'SI' ? <span className="badge-ok">SÍ</span> :
        v === 'NO' ? <span className="badge-error">NO</span> :
        <span className="badge-warning">{v}</span>,
    },
    { key: 'justificacion', label: 'Justificación IA', render: (v) => <span className="text-xs text-oag-muted">{v}</span> },
  ]

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-oag-text">Paso 2 — Análisis Producto Ventas</h2>
        <p className="text-xs text-oag-muted mt-0.5">
          Rankings, muestreo, clasificación con IA y tabla de apertura de agroquímicos.
        </p>
      </div>

      {/* Archivos opcionales */}
      <div className="card p-4">
        <h3 className="section-title">Archivos Opcionales</h3>
        <div className="grid grid-cols-2 gap-4">
          <FileUpload
            label="Clientes Especiales (Muestreo)"
            description="Lista de clientes que deben incluirse forzosamente en el muestreo"
            onUpload={(f) => handleUpload('CLIENTES_ESPECIALES', f)}
            isLoading={uploading['CLIENTES_ESPECIALES']}
            isUploaded={!!getArchivo('CLIENTES_ESPECIALES')}
            uploadedName={getArchivo('CLIENTES_ESPECIALES')?.nombre_original}
          />
        </div>
      </div>

      <div className="flex items-start gap-3">
        <div className="flex-1 card p-3 flex items-start gap-2">
          <Info size={14} className="text-oag-blue mt-0.5 flex-shrink-0" />
          <p className="text-xs text-oag-muted">
            La clasificación de productos (agroquímico/Syngenta) se realiza con IA (Claude Opus).
            Requiere el maestro Syngenta cargado en Administración. El proceso puede demorar varios minutos.
          </p>
        </div>
        <button
          className="btn-primary flex items-center gap-2 flex-shrink-0"
          onClick={() => ejecutarMutation.mutate()}
          disabled={!canRun || ejecutarMutation.isPending}
        >
          {ejecutarMutation.isPending ? <Loader size={14} className="animate-spin" /> : <Play size={14} />}
          {ejecutarMutation.isPending ? 'Procesando con IA...' : 'Ejecutar Análisis'}
        </button>
      </div>

      {loadingResultado && (
        <div className="flex items-center justify-center py-8">
          <Loader size={20} className="animate-spin text-oag-muted" />
        </div>
      )}

      {resultado && (
        <>
          <PasoFeedback validacion={resultado.validacion} />

          {/* Totales */}
          <div className="grid grid-cols-5 gap-3">
            {[
              { label: 'Total Facturado', value: formatUSD(resultado.totales?.total_facturado_usd) },
              { label: 'Total Agroquímicos', value: formatUSD(resultado.totales?.total_agro_usd) },
              { label: 'Total Syngenta', value: formatUSD(resultado.totales?.total_syngenta_usd) },
              { label: 'Productos únicos', value: resultado.totales?.cant_productos },
              { label: 'Productos agroquímicos', value: resultado.totales?.cant_productos_agro },
            ].map((s, i) => (
              <div key={i} className="card p-3 flex flex-col items-center text-center">
                <p className="text-xs text-oag-muted leading-tight min-h-[2.4em] flex items-center justify-center">
                  {s.label}
                </p>
                <p className="text-base font-bold text-oag-text mt-1">{s.value}</p>
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div className="card overflow-hidden">
            <div className="flex border-b border-oag-border bg-oag-light">
              {[
                { key: 'ranking_c', label: 'Ranking Clientes' },
                { key: 'ranking_p', label: 'Ranking Productos' },
                { key: 'muestreo', label: `Muestreo (${resultado.muestreo?.length ?? 0})` },
                { key: 'clasificacion', label: 'Clasificación IA' },
                { key: 'apertura', label: 'Tabla de Apertura' },
              ].map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key as any)}
                  className={cn(
                    'px-4 py-2.5 text-xs font-medium transition-colors border-b-2',
                    tab === t.key
                      ? 'border-oag-blue text-oag-blue bg-white'
                      : 'border-transparent text-oag-muted hover:text-oag-text'
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div className="p-5">
              {tab === 'ranking_c' && (
                <DataTable columns={colsClientes} data={resultado.ranking_clientes || []} searchable searchKeys={['cliente']} maxHeight="340px" />
              )}
              {tab === 'ranking_p' && (
                <DataTable columns={colsProductos} data={resultado.ranking_productos || []} searchable searchKeys={['articulo']} maxHeight="340px" />
              )}
              {tab === 'muestreo' && (
                <>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="badge-warning">ESPECIAL</span>
                    <span className="text-xs text-oag-muted">= Cliente de la lista de especiales (forzado)</span>
                  </div>
                  <DataTable columns={colsMuestreo} data={resultado.muestreo || []} searchable searchKeys={['cliente', 'numero_comprobante']} maxHeight="340px" />
                </>
              )}
              {tab === 'clasificacion' && (
                <DataTable columns={colsClasificacion} data={resultado.clasificacion || []} searchable searchKeys={['articulo']} maxHeight="340px" />
              )}
              {tab === 'apertura' && (
                <div className="overflow-auto max-h-96">
                  <table className="w-full border-collapse text-xs">
                    <thead className="sticky top-0">
                      <tr>
                        <th className="table-header text-left min-w-[200px]">Producto</th>
                        <th className="table-header text-center w-20">Syngenta</th>
                        <th className="table-header text-right w-24">Total USD</th>
                        {MESES_FULL.map((m) => (
                          <th key={m} className="table-header text-right w-20">{m.slice(0, 3)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(resultado.tabla_apertura || []).map((row: any, i: number) => (
                        <tr key={i} className={cn('hover:bg-blue-50/30', i % 2 === 0 ? 'bg-white' : 'bg-oag-zebra', row.syngenta === 'SI' && 'bg-blue-50/60')}>
                          <td className="table-cell font-medium">{row.articulo}</td>
                          <td className="table-cell text-center">
                            {row.syngenta === 'SI' ? <span className="badge-ok">SÍ</span> : <span className="text-oag-muted text-xs">—</span>}
                          </td>
                          <td className="table-cell text-right font-mono font-semibold">{formatUSD(row.Total)}</td>
                          {MESES_FULL.map((m) => (
                            <td key={m} className="table-cell text-right font-mono">
                              {row[m] ? formatUSD(row[m]).replace('USD', '').trim() : '—'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
