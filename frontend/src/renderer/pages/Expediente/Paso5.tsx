import React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { pasosAPI } from '../../lib/api'
import { useNotificationStore } from '../../store'
import { downloadBlob } from '../../lib/utils'
import { Play, Download, Loader, FileSpreadsheet, CheckCircle } from 'lucide-react'

interface Props { expediente: any }

export default function Paso5({ expediente }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()

  const { data: resultado } = useQuery({
    queryKey: ['paso5', expediente.id],
    queryFn: () => pasosAPI.resultadoPaso(expediente.id, 5).then((r) => r.data),
    enabled: expediente.pasos_completados?.includes(5),
    retry: false,
  })

  const ejecutarMutation = useMutation({
    mutationFn: () => pasosAPI.ejecutarPaso(expediente.id, 5),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      qc.invalidateQueries({ queryKey: ['paso5', expediente.id] })
      push('success', 'Informe ejecutivo generado')
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error en Paso 5'),
  })

  const downloadMutation = useMutation({
    mutationFn: () => pasosAPI.descargarPaso(expediente.id, 5),
    onSuccess: (res) => {
      downloadBlob(res.data, `OGSA_Informe_Paso5_Exp${expediente.id}.xlsx`)
      push('success', 'Descarga iniciada')
    },
    onError: () => push('error', 'Error al descargar'),
  })

  const canRun = [2, 3, 4].every((p) => expediente.pasos_completados?.includes(p))
  const totales = resultado?.totales

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-oag-text">Paso 5 — Informe Ejecutivo</h2>
        <p className="text-xs text-oag-muted mt-0.5">
          Genera el informe de presentación con los 3 anexos en Excel formateado.
        </p>
      </div>

      {/* Info de contenido */}
      <div className="card p-5">
        <h3 className="section-title">Contenido del Informe</h3>
        <div className="grid grid-cols-3 gap-4">
          {[
            { num: 'I', title: 'Resumen de Compras', desc: 'Top 90% de proveedores más significativos, con apertura por tipo de comprobante para los proveedores configurados.' },
            { num: 'II', title: 'Venta de Agroquímicos', desc: 'Tabla de apertura: todos los productos agroquímicos con indicación Syngenta SÍ/NO y totales por mes en USD.' },
            { num: 'III', title: 'Cruce CRM', desc: 'Conciliación entre ventas Syngenta (gestión) vs CRM, con diferencias y justificaciones.' },
          ].map((a) => (
            <div key={a.num} className="bg-oag-light rounded-lg p-4 border border-oag-border">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-6 h-6 bg-oag-dark text-white text-xs font-bold rounded flex items-center justify-center">
                  {a.num}
                </span>
                <span className="text-sm font-medium text-oag-text">{a.title}</span>
              </div>
              <p className="text-xs text-oag-muted leading-relaxed">{a.desc}</p>
            </div>
          ))}
        </div>

        {!canRun && (
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
            Completar los Pasos 2, 3 y 4 para habilitar la generación del informe.
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <button
          className="btn-primary flex items-center gap-2"
          onClick={() => ejecutarMutation.mutate()}
          disabled={!canRun || ejecutarMutation.isPending}
        >
          {ejecutarMutation.isPending ? <Loader size={14} className="animate-spin" /> : <Play size={14} />}
          {ejecutarMutation.isPending ? 'Generando informe...' : 'Generar Informe'}
        </button>

        {expediente.pasos_completados?.includes(5) && (
          <button
            className="btn-secondary flex items-center gap-2"
            onClick={() => downloadMutation.mutate()}
            disabled={downloadMutation.isPending}
          >
            {downloadMutation.isPending ? <Loader size={14} className="animate-spin" /> : <Download size={14} />}
            Descargar Excel
          </button>
        )}
      </div>

      {totales && (
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle size={18} className="text-oag-success" />
            <h3 className="text-sm font-semibold text-oag-text">Informe generado correctamente</h3>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-oag-muted">Proveedores incluidos (top 90%)</p>
              <p className="text-lg font-bold text-oag-text">{totales.proveedores_incluidos}</p>
              <p className="text-xs text-oag-muted">de {totales.total_proveedores} totales</p>
            </div>
            <div>
              <p className="text-xs text-oag-muted">Líneas — Venta Agroquímicos</p>
              <p className="text-lg font-bold text-oag-text">{totales.lineas_apertura}</p>
            </div>
            <div>
              <p className="text-xs text-oag-muted">Líneas — Cruce CRM</p>
              <p className="text-lg font-bold text-oag-text">{totales.lineas_crm}</p>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded">
            <FileSpreadsheet size={16} className="text-green-700" />
            <div>
              <p className="text-xs font-medium text-green-800">OGSA_Informe_Paso5_Exp{expediente.id}.xlsx</p>
              <p className="text-xs text-green-700">4 hojas: Portada, Anexo I — Compras, Anexo II — Agroquímicos, Anexo III — CRM</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
